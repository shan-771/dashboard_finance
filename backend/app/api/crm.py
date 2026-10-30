from collections import deque
from datetime import datetime, time, timedelta, timezone
from threading import Lock
from time import monotonic
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.core.config import get_settings
from app.dependencies import AuthenticatedSession, get_current_auth, require_csrf, require_manager
from app.models import (
    ChangeRequestStatus, Customer, Enquiry, EnquiryAuditEvent, EnquiryChangeRequest,
    EnquiryStatus, FollowUp, User, UserRole, utc_now,
)
from app.notifications import notify_active_role, notify_users, publish_notifications
from app.retention import DELETION_RECOVERY_WINDOW, purge_deleted_enquiry
from app.schemas import (
    ChangeRequestDecision,
    ChangeRequestPage,
    ChangeRequestResponse,
    CompleteFollowUpRequest,
    CreateEnquiryRequest,
    CreatePublicEnquiryRequest,
    CustomerResponse,
    DeletedEnquiryPage,
    DeletedEnquiryResponse,
    EnquiryPurgeResponse,
    EnquiryChangeRequestCreate,
    EnquiryEditFields,
    EnquiryPage,
    EnquiryResponse,
    FollowUpPage,
    FollowUpHistoryPage,
    FollowUpResponse,
    MergeCustomerRequest,
    PublicEnquiryAccepted,
    ScheduleFollowUpRequest,
    SaveEnquiryContactRequest,
    UpdateEnquiryHandlerRequest,
    UpdateEnquiryStatusRequest,
)


router = APIRouter(tags=["customers and enquiries"])
FINAL_STATUSES = {EnquiryStatus.CLOSED, EnquiryStatus.OPEN, EnquiryStatus.LOST}
ACTIVE_STATUSES = {EnquiryStatus.NEW.value, EnquiryStatus.ASSIGNED.value, EnquiryStatus.ATTENDED.value, EnquiryStatus.FOLLOW_UPS.value}
ALLOWED_TRANSITIONS = {
    EnquiryStatus.NEW: {EnquiryStatus.ASSIGNED, EnquiryStatus.ATTENDED, *FINAL_STATUSES},
    EnquiryStatus.ASSIGNED: {EnquiryStatus.FOLLOW_UPS, *FINAL_STATUSES},
    EnquiryStatus.ATTENDED: {EnquiryStatus.FOLLOW_UPS, *FINAL_STATUSES},
    EnquiryStatus.FOLLOW_UPS: FINAL_STATUSES,
}
PUBLIC_WINDOW_SECONDS = 60
PUBLIC_MAX_REQUESTS = 5
_public_requests: dict[str, deque[float]] = {}
_public_request_lock = Lock()


def enquiry_response(enquiry: Enquiry, completed_follow_up_count: int = 0) -> EnquiryResponse:
    next_follow_up_at = enquiry.next_follow_up_at
    if next_follow_up_at is not None and next_follow_up_at.tzinfo is None:
        next_follow_up_at = next_follow_up_at.replace(tzinfo=timezone.utc)
    return EnquiryResponse(
        id=enquiry.id,
        customer=CustomerResponse.model_validate(enquiry.customer),
        service_type=enquiry.service_type,
        source=enquiry.source,
        status=enquiry.status,
        handled_by_id=enquiry.handled_by_id,
        handled_by_name=enquiry.handled_by.display_name if enquiry.handled_by else None,
        notes=enquiry.notes,
        outcome_reason=enquiry.outcome_reason,
        do_not_contact=enquiry.do_not_contact,
        next_follow_up_at=next_follow_up_at,
        completed_follow_up_count=completed_follow_up_count,
        created_at=enquiry.created_at,
        updated_at=enquiry.updated_at,
    )


def completed_follow_up_counts(db: Session, enquiry_ids: list[UUID]) -> dict[UUID, int]:
    if not enquiry_ids:
        return {}
    rows = db.execute(
        select(FollowUp.enquiry_id, func.count(FollowUp.id))
        .where(FollowUp.enquiry_id.in_(enquiry_ids))
        .group_by(FollowUp.enquiry_id)
    ).all()
    return {enquiry_id: count for enquiry_id, count in rows}


def require_actionable_enquiry(enquiry: Enquiry) -> None:
    if enquiry.status not in ACTIVE_STATUSES or enquiry.do_not_contact:
        raise HTTPException(status_code=409, detail="Follow-ups are unavailable for finalized or do-not-contact enquiries")


def require_enquiry_handler(enquiry: Enquiry, auth: AuthenticatedSession) -> None:
    if auth.user.role != UserRole.MANAGER.value and enquiry.handled_by_id != auth.user.id:
        raise HTTPException(status_code=403, detail="Only the staff member handling this enquiry can update it")


def enforce_claim_rate_limit(db: Session, user_id: UUID) -> None:
    """Persist a modest claim-attempt limit so clients cannot hammer the claim endpoint."""
    now = utc_now()
    user = db.scalar(
        select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)
    )
    if user is None:
        raise HTTPException(status_code=401, detail="Staff session is no longer active")
    window = user.claim_attempt_window_started_at
    if window is not None and window.tzinfo is None:
        window = window.replace(tzinfo=timezone.utc)
    if window is None or now - window >= timedelta(minutes=1):
        user.claim_attempt_window_started_at = now
        user.claim_attempt_count = 1
    elif user.claim_attempt_count >= 10:
        raise HTTPException(status_code=429, detail="Too many claim attempts. Try again in a minute.")
    else:
        user.claim_attempt_count += 1
    db.commit()


@router.get("/customers", response_model=list[CustomerResponse])
def list_customers(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthenticatedSession, Depends(get_current_auth)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Customer]:
    return list(db.scalars(
        select(Customer).where(Customer.merged_into_customer_id.is_(None))
        .order_by(Customer.created_at.desc()).limit(limit).offset(offset)
    ).all())


@router.post("/public/enquiries", response_model=PublicEnquiryAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_public_enquiry(
    payload: CreatePublicEnquiryRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> PublicEnquiryAccepted:
    client_ip = request.client.host if request.client else "unknown"
    now = monotonic()
    with _public_request_lock:
        for address, history in list(_public_requests.items()):
            while history and history[0] <= now - PUBLIC_WINDOW_SECONDS:
                history.popleft()
            if not history:
                del _public_requests[address]
        requests = _public_requests.setdefault(client_ip, deque())
        if len(requests) >= PUBLIC_MAX_REQUESTS:
            raise HTTPException(status_code=429, detail="Too many enquiries. Please try again shortly.")
        requests.append(now)

    customer = Customer(**payload.customer.model_dump())
    db.add(customer)
    db.flush()
    enquiry = Enquiry(
        customer_id=customer.id,
        service_type=payload.service_type,
        source="Website",
        status=EnquiryStatus.NEW.value,
    )
    db.add(enquiry)
    db.flush()
    notifications = notify_active_role(
        db,
        UserRole.STAFF,
        notification_type="new_enquiry",
        title="New enquiry received",
        message=f"{customer.name} submitted a {payload.service_type} enquiry.",
        enquiry_id=enquiry.id,
    )
    db.commit()
    publish_notifications(notifications)
    return PublicEnquiryAccepted()


@router.post(
    "/customers/{target_customer_id}/link",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_auth), Depends(require_csrf)],
)
def link_customer_records(
    target_customer_id: UUID,
    payload: MergeCustomerRequest,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str | int]:
    if target_customer_id == payload.source_customer_id:
        raise HTTPException(status_code=422, detail="A customer cannot be linked to itself")
    target = db.scalar(select(Customer).where(Customer.id == target_customer_id).with_for_update())
    source = db.scalar(select(Customer).where(Customer.id == payload.source_customer_id).with_for_update())
    if target is None or source is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    if target.merged_into_customer_id is not None or source.merged_into_customer_id is not None:
        raise HTTPException(status_code=409, detail="Only active customer records can be linked")
    relinked = db.query(Enquiry).filter(Enquiry.customer_id == source.id).update(
        {Enquiry.customer_id: target.id}, synchronize_session=False
    )
    source.merged_into_customer_id = target.id
    db.commit()
    return {
        "customer_id": str(target.id),
        "linked_customer_id": str(source.id),
        "enquiries_relinked": relinked,
    }


@router.get("/enquiries", response_model=EnquiryPage)
def list_enquiries(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthenticatedSession, Depends(get_current_auth)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: EnquiryStatus | None = Query(default=None, alias="status"),
    service_type: str | None = Query(default=None, min_length=1, max_length=80),
    source: str | None = Query(default=None, min_length=1, max_length=40),
    handled_by_id: UUID | None = None,
    search: str | None = Query(default=None, min_length=1, max_length=120),
) -> EnquiryPage:
    conditions = []
    if status_filter:
        conditions.append(Enquiry.status == status_filter.value)
    if service_type:
        conditions.append(Enquiry.service_type == service_type.strip())
    if source:
        conditions.append(Enquiry.source == source.strip())
    if handled_by_id:
        conditions.append(Enquiry.handled_by_id == handled_by_id)
    if search:
        needle = f"%{search.strip()}%"
        conditions.append(
            select(Customer.id).where(
                Customer.id == Enquiry.customer_id,
                or_(Customer.name.ilike(needle), Customer.phone.ilike(needle), Customer.email.ilike(needle)),
            ).exists()
        )
    stmt = select(Enquiry).options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by)).where(Enquiry.deleted_at.is_(None), *conditions)
    total = db.scalar(select(func.count()).select_from(Enquiry).where(Enquiry.deleted_at.is_(None), *conditions)) or 0
    rows = db.scalars(stmt.order_by(Enquiry.created_at.desc()).limit(limit).offset(offset)).unique().all()
    counts = completed_follow_up_counts(db, [item.id for item in rows])
    return EnquiryPage(
        items=[enquiry_response(item, counts.get(item.id, 0)) for item in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/enquiries/deleted",
    response_model=DeletedEnquiryPage,
    dependencies=[Depends(require_manager)],
)
def list_recoverable_deleted_enquiries(
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DeletedEnquiryPage:
    cutoff = utc_now() - DELETION_RECOVERY_WINDOW
    conditions = [Enquiry.deleted_at.is_not(None), Enquiry.deleted_at > cutoff]
    total = db.scalar(select(func.count()).select_from(Enquiry).where(*conditions)) or 0
    rows = db.scalars(
        select(Enquiry)
        .options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by))
        .where(*conditions)
        .order_by(Enquiry.deleted_at.desc())
        .limit(limit)
        .offset(offset)
    ).unique().all()
    counts = completed_follow_up_counts(db, [item.id for item in rows])
    items = []
    for item in rows:
        assert item.deleted_at is not None
        base = enquiry_response(item, counts.get(item.id, 0)).model_dump()
        items.append(DeletedEnquiryResponse(
            **base,
            deleted_at=item.deleted_at,
            purge_at=item.deleted_at + DELETION_RECOVERY_WINDOW,
        ))
    return DeletedEnquiryPage(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/enquiries",
    response_model=EnquiryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_enquiry(
    payload: CreateEnquiryRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryResponse:
    if payload.customer_id is not None:
        customer = db.get(Customer, payload.customer_id)
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        if customer.merged_into_customer_id is not None:
            raise HTTPException(status_code=409, detail="Customer record has been linked; use the active customer record")
    else:
        assert payload.customer is not None
        customer = Customer(**payload.customer.model_dump())
        db.add(customer)
        db.flush()

    enquiry = Enquiry(
        customer_id=customer.id,
        service_type=payload.service_type,
        source=payload.source,
        status=EnquiryStatus.NEW.value,
        handled_by_id=None,
    )
    db.add(enquiry)
    db.flush()
    notifications = notify_active_role(
        db,
        UserRole.STAFF,
        notification_type="new_enquiry",
        title="New enquiry received",
        message=f"{customer.name} submitted a {payload.service_type} enquiry.",
        enquiry_id=enquiry.id,
    )
    db.commit()
    publish_notifications(notifications)
    db.refresh(enquiry)
    # Return a stable response while the request session is still open.
    enquiry.customer = customer
    return enquiry_response(enquiry)


@router.patch(
    "/enquiries/{enquiry_id}/status",
    response_model=EnquiryResponse,
    dependencies=[Depends(require_csrf)],
)
def update_enquiry_status(
    enquiry_id: UUID,
    payload: UpdateEnquiryStatusRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryResponse:
    enquiry = db.scalar(
        select(Enquiry)
        .options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by))
        .where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_(None))
        .with_for_update(of=Enquiry)
    )
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    if payload.status == EnquiryStatus.ASSIGNED:
        raise HTTPException(status_code=409, detail="Use the Pick enquiry action to claim an enquiry")
    if _.user.role == UserRole.STAFF.value and payload.status == EnquiryStatus.ATTENDED:
        raise HTTPException(status_code=409, detail="Pick this enquiry before marking it attended")
    require_enquiry_handler(enquiry, _)
    current = EnquiryStatus(enquiry.status)
    if current == EnquiryStatus.ASSIGNED and payload.status == EnquiryStatus.FOLLOW_UPS:
        raise HTTPException(status_code=409, detail="Save the call notes and follow-up date to move this enquiry to Follow-ups")
    if payload.status != current and payload.status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=409, detail="This enquiry status transition is not allowed")
    if enquiry.do_not_contact and not payload.do_not_contact:
        raise HTTPException(status_code=409, detail="A do-not-contact instruction cannot be removed")
    if payload.do_not_contact and payload.status != EnquiryStatus.LOST:
        raise HTTPException(status_code=422, detail="Do-not-contact can only be recorded for a Lost enquiry")
    enquiry.status = payload.status.value
    enquiry.outcome_reason = payload.outcome_reason
    enquiry.do_not_contact = payload.do_not_contact
    if payload.status in FINAL_STATUSES:
        enquiry.next_follow_up_at = None
    db.commit()
    db.refresh(enquiry)
    count = db.scalar(select(func.count(FollowUp.id)).where(FollowUp.enquiry_id == enquiry.id)) or 0
    return enquiry_response(enquiry, count)


@router.post(
    "/enquiries/{enquiry_id}/claim",
    response_model=EnquiryResponse,
    dependencies=[Depends(require_csrf)],
)
def claim_enquiry(
    enquiry_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryResponse:
    if auth.user.role != UserRole.STAFF.value:
        raise HTTPException(status_code=403, detail="Only Staff can pick enquiries")
    enforce_claim_rate_limit(db, auth.user.id)
    claimed = db.execute(
        update(Enquiry)
        .where(
            Enquiry.id == enquiry_id,
            Enquiry.deleted_at.is_(None),
            Enquiry.status == EnquiryStatus.NEW.value,
            Enquiry.handled_by_id.is_(None),
        )
        .values(status=EnquiryStatus.ASSIGNED.value, handled_by_id=auth.user.id, updated_at=utc_now())
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        current = db.scalar(
            select(Enquiry).options(joinedload(Enquiry.handled_by))
            .where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_(None))
        )
        if current is None:
            raise HTTPException(status_code=404, detail="Enquiry not found")
        if current.handled_by is not None:
            raise HTTPException(status_code=409, detail=f"This enquiry has already been picked by {current.handled_by.display_name}")
        raise HTTPException(status_code=409, detail="This enquiry is no longer available to pick")
    db.commit()
    enquiry = db.scalar(
        select(Enquiry).options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by))
        .where(Enquiry.id == enquiry_id)
    )
    assert enquiry is not None
    count = db.scalar(select(func.count(FollowUp.id)).where(FollowUp.enquiry_id == enquiry.id)) or 0
    return enquiry_response(enquiry, count)


def enquiry_edit_snapshot(enquiry: Enquiry) -> dict[str, str]:
    return {"service_type": enquiry.service_type, "source": enquiry.source}


def request_is_stale(change_request: EnquiryChangeRequest, enquiry: Enquiry) -> bool:
    current = enquiry.updated_at
    base = change_request.base_updated_at
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return current != base


@router.post(
    "/enquiries/{enquiry_id}/change-requests",
    response_model=ChangeRequestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_enquiry_change_request(
    enquiry_id: UUID,
    payload: EnquiryChangeRequestCreate,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryChangeRequest:
    if auth.user.role != UserRole.STAFF.value:
        raise HTTPException(status_code=403, detail="Only Staff can submit approval requests")
    enquiry = db.scalar(select(Enquiry).where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_(None)))
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    pending = db.scalar(select(EnquiryChangeRequest.id).where(
        EnquiryChangeRequest.enquiry_id == enquiry.id,
        EnquiryChangeRequest.status.in_((ChangeRequestStatus.PENDING.value, ChangeRequestStatus.APPROVED.value)),
    ))
    if pending is not None:
        raise HTTPException(status_code=409, detail="This enquiry already has a pending change request")
    proposed = payload.proposed_changes
    changes = proposed.model_dump(exclude_unset=True, exclude_none=True) if proposed else None
    if payload.request_type == "edit" and not changes:
        raise HTTPException(status_code=422, detail="Provide at least one editable field")
    request_record = EnquiryChangeRequest(
        enquiry_id=enquiry.id,
        request_type=payload.request_type,
        proposed_changes=changes,
        original_snapshot=enquiry_edit_snapshot(enquiry),
        base_updated_at=enquiry.updated_at,
        reason=payload.reason,
        submitted_by_user_id=auth.user.id,
    )
    db.add(request_record)
    if payload.request_type == "delete":
        notifications = notify_active_role(
            db,
            UserRole.MANAGER,
            notification_type="deletion_request",
            title="Deletion request to review",
            message=f"A Staff member requested deletion of {enquiry.customer.name}'s {enquiry.service_type} enquiry.",
            enquiry_id=enquiry.id,
        )
    else:
        notifications = []
    db.commit()
    publish_notifications(notifications)
    db.refresh(request_record)
    return request_record


@router.get(
    "/enquiries/{enquiry_id}/change-requests",
    response_model=ChangeRequestResponse | None,
)
def get_enquiry_deletion_request(
    enquiry_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryChangeRequest | None:
    enquiry_exists = db.scalar(
        select(Enquiry.id).where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_(None))
    )
    if enquiry_exists is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    return db.scalar(
        select(EnquiryChangeRequest)
        .where(
            EnquiryChangeRequest.enquiry_id == enquiry_id,
            EnquiryChangeRequest.request_type == "delete",
            EnquiryChangeRequest.status.in_(
                (ChangeRequestStatus.PENDING.value, ChangeRequestStatus.APPROVED.value)
            ),
        )
        .order_by(EnquiryChangeRequest.created_at.desc())
        .limit(1)
    )


@router.get(
    "/change-requests",
    response_model=ChangeRequestPage,
    dependencies=[Depends(require_manager)],
)
def list_enquiry_change_requests(
    db: Annotated[Session, Depends(get_db)],
    status_filter: str = Query(default=ChangeRequestStatus.PENDING.value, alias="status", pattern="^(pending|approved|rejected|stale|completed)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ChangeRequestPage:
    conditions = [EnquiryChangeRequest.status == status_filter]
    total = db.scalar(select(func.count()).select_from(EnquiryChangeRequest).where(*conditions)) or 0
    items = db.scalars(
        select(EnquiryChangeRequest).where(*conditions)
        .order_by(EnquiryChangeRequest.created_at.asc()).limit(limit).offset(offset)
    ).all()
    return ChangeRequestPage(items=items, total=total, limit=limit, offset=offset)


@router.patch(
    "/change-requests/{change_request_id}",
    response_model=ChangeRequestResponse,
    dependencies=[Depends(require_manager), Depends(require_csrf)],
)
def decide_enquiry_change_request(
    change_request_id: UUID,
    payload: ChangeRequestDecision,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryChangeRequest:
    change_request = db.scalar(
        select(EnquiryChangeRequest).where(EnquiryChangeRequest.id == change_request_id).with_for_update()
    )
    if change_request is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    if change_request.status != ChangeRequestStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="This request has already been decided")
    if change_request.submitted_by_user_id == auth.user.id:
        raise HTTPException(status_code=403, detail="You cannot approve your own request")
    enquiry = db.scalar(select(Enquiry).where(Enquiry.id == change_request.enquiry_id).with_for_update())
    if enquiry is None or enquiry.deleted_at is not None:
        raise HTTPException(status_code=409, detail="The enquiry is no longer active")
    if request_is_stale(change_request, enquiry):
        change_request.status = ChangeRequestStatus.STALE.value
        change_request.decided_by_user_id = auth.user.id
        change_request.decided_at = utc_now()
        change_request.decision_note = "Enquiry changed after this request was submitted; submit a new request."
        db.commit()
        raise HTTPException(status_code=409, detail="The enquiry changed after this request was submitted")
    change_request.decided_by_user_id = auth.user.id
    change_request.decided_at = utc_now()
    change_request.decision_note = payload.note
    if payload.decision == "reject":
        change_request.status = ChangeRequestStatus.REJECTED.value
    elif change_request.request_type == "delete":
        # A Manager's explicit approval is also the final confirmation for a soft deletion.
        before = enquiry_edit_snapshot(enquiry)
        deletion_time = utc_now()
        enquiry.deleted_at = deletion_time
        change_request.status = ChangeRequestStatus.COMPLETED.value
        change_request.confirmed_by_user_id = auth.user.id
        change_request.confirmed_at = deletion_time
        db.add(EnquiryAuditEvent(
            enquiry_id=enquiry.id,
            actor_user_id=auth.user.id,
            action="manager_confirmed_soft_deletion",
            before_values=before,
            after_values={"deleted": True, "reason": change_request.reason},
        ))
    else:
        before = enquiry_edit_snapshot(enquiry)
        for field, value in (change_request.proposed_changes or {}).items():
            setattr(enquiry, field, value)
        after = enquiry_edit_snapshot(enquiry)
        change_request.status = ChangeRequestStatus.COMPLETED.value
        db.add(EnquiryAuditEvent(
            enquiry_id=enquiry.id,
            actor_user_id=auth.user.id,
            action="approved_staff_edit",
            before_values=before,
            after_values=after,
        ))
    notifications = []
    if change_request.request_type == "delete" and change_request.submitted_by_user_id is not None:
        decision = "approved" if payload.decision == "approve" else "rejected"
        notifications = notify_users(
            db,
            [change_request.submitted_by_user_id],
            notification_type="deletion_decision",
            title=f"Deletion request {decision}",
            message=f"The Manager {decision} your deletion request for {enquiry.customer.name}'s {enquiry.service_type} enquiry.",
            enquiry_id=enquiry.id,
        )
    db.commit()
    publish_notifications(notifications)
    db.refresh(change_request)
    return change_request


@router.post(
    "/change-requests/{change_request_id}/confirm-deletion",
    response_model=ChangeRequestResponse,
    dependencies=[Depends(require_manager), Depends(require_csrf)],
)
def confirm_enquiry_deletion(
    change_request_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryChangeRequest:
    change_request = db.scalar(
        select(EnquiryChangeRequest).where(EnquiryChangeRequest.id == change_request_id).with_for_update()
    )
    if change_request is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    if change_request.request_type != "delete" or change_request.status != ChangeRequestStatus.APPROVED.value:
        raise HTTPException(status_code=409, detail="Only an approved deletion request can be confirmed")
    enquiry = db.scalar(select(Enquiry).where(Enquiry.id == change_request.enquiry_id).with_for_update())
    if enquiry is None or enquiry.deleted_at is not None:
        raise HTTPException(status_code=409, detail="The enquiry is no longer active")
    if request_is_stale(change_request, enquiry):
        change_request.status = ChangeRequestStatus.STALE.value
        change_request.decision_note = "Enquiry changed after deletion approval; review the record again."
        db.commit()
        raise HTTPException(status_code=409, detail="The enquiry changed after deletion approval")
    before = enquiry_edit_snapshot(enquiry)
    enquiry.deleted_at = utc_now()
    change_request.status = ChangeRequestStatus.COMPLETED.value
    change_request.confirmed_by_user_id = auth.user.id
    change_request.confirmed_at = utc_now()
    db.add(EnquiryAuditEvent(
        enquiry_id=enquiry.id,
        actor_user_id=auth.user.id,
        action="confirmed_soft_deletion",
        before_values=before,
        after_values={"deleted": True, "reason": change_request.reason},
    ))
    db.commit()
    db.refresh(change_request)
    return change_request


@router.post(
    "/enquiries/{enquiry_id}/restore",
    response_model=EnquiryResponse,
    dependencies=[Depends(require_manager), Depends(require_csrf)],
)
def restore_deleted_enquiry(
    enquiry_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryResponse:
    customer_id = db.scalar(
        select(Enquiry.customer_id).where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_not(None))
    )
    if customer_id is None:
        raise HTTPException(status_code=404, detail="Recoverable enquiry not found")
    customer = db.scalar(select(Customer).where(Customer.id == customer_id).with_for_update())
    if customer is None:
        raise HTTPException(status_code=409, detail="The enquiry's customer record is unavailable")
    enquiry = db.scalar(
        select(Enquiry)
        .options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by))
        .where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_not(None))
        .with_for_update(of=Enquiry)
    )
    if enquiry is None or enquiry.deleted_at is None:
        raise HTTPException(status_code=404, detail="Recoverable enquiry not found")
    deleted_at = enquiry.deleted_at
    if deleted_at.tzinfo is None:
        deleted_at = deleted_at.replace(tzinfo=timezone.utc)
    if deleted_at + DELETION_RECOVERY_WINDOW <= utc_now():
        raise HTTPException(status_code=409, detail="The five-day recovery window has expired")
    enquiry.deleted_at = None
    db.add(EnquiryAuditEvent(
        enquiry_id=enquiry.id,
        actor_user_id=auth.user.id,
        action="manager_restored_enquiry",
        before_values={"deleted": True},
        after_values={"deleted": False},
    ))
    db.commit()
    db.refresh(enquiry)
    count = db.scalar(select(func.count(FollowUp.id)).where(FollowUp.enquiry_id == enquiry.id)) or 0
    return enquiry_response(enquiry, count)


@router.delete(
    "/enquiries/{enquiry_id}/permanent",
    response_model=EnquiryPurgeResponse,
    dependencies=[Depends(require_manager), Depends(require_csrf)],
)
def permanently_delete_enquiry(
    enquiry_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryPurgeResponse:
    purged, customer_deleted = purge_deleted_enquiry(db, enquiry_id)
    if not purged:
        raise HTTPException(status_code=404, detail="Deleted enquiry not found")
    db.commit()
    return EnquiryPurgeResponse(
        enquiry_id=enquiry_id,
        customer_deleted=customer_deleted,
    )


@router.patch(
    "/enquiries/{enquiry_id}",
    response_model=EnquiryResponse,
    dependencies=[Depends(require_manager), Depends(require_csrf)],
)
def manager_edit_enquiry(
    enquiry_id: UUID,
    payload: EnquiryEditFields,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryResponse:
    enquiry = db.scalar(
        select(Enquiry).options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by))
        .where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_(None)).with_for_update(of=Enquiry)
    )
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one editable field")
    before = enquiry_edit_snapshot(enquiry)
    for field, value in changes.items():
        setattr(enquiry, field, value)
    after = enquiry_edit_snapshot(enquiry)
    db.add(EnquiryAuditEvent(
        enquiry_id=enquiry.id,
        actor_user_id=auth.user.id,
        action="manager_direct_edit",
        before_values=before,
        after_values=after,
    ))
    db.commit()
    db.refresh(enquiry)
    count = db.scalar(select(func.count(FollowUp.id)).where(FollowUp.enquiry_id == enquiry.id)) or 0
    return enquiry_response(enquiry, count)


@router.put(
    "/enquiries/{enquiry_id}/follow-up",
    response_model=EnquiryResponse,
    dependencies=[Depends(require_csrf)],
)
def schedule_enquiry_follow_up(
    enquiry_id: UUID,
    payload: ScheduleFollowUpRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryResponse:
    enquiry = db.scalar(
        select(Enquiry).options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by))
        .where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_(None)).with_for_update(of=Enquiry)
    )
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    require_enquiry_handler(enquiry, auth)
    require_actionable_enquiry(enquiry)
    enquiry.next_follow_up_at = payload.next_follow_up_at
    if enquiry.status == EnquiryStatus.ASSIGNED.value and payload.next_follow_up_at is not None:
        enquiry.status = EnquiryStatus.FOLLOW_UPS.value
    db.commit()
    db.refresh(enquiry)
    count = db.scalar(select(func.count(FollowUp.id)).where(FollowUp.enquiry_id == enquiry.id)) or 0
    return enquiry_response(enquiry, count)


@router.put(
    "/enquiries/{enquiry_id}/contact",
    response_model=EnquiryResponse,
    dependencies=[Depends(require_csrf)],
)
def save_enquiry_contact(
    enquiry_id: UUID,
    payload: SaveEnquiryContactRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryResponse:
    enquiry = db.scalar(
        select(Enquiry).options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by))
        .where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_(None)).with_for_update(of=Enquiry)
    )
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    require_enquiry_handler(enquiry, auth)
    require_actionable_enquiry(enquiry)
    if enquiry.status not in {EnquiryStatus.ASSIGNED.value, EnquiryStatus.ATTENDED.value, EnquiryStatus.FOLLOW_UPS.value}:
        raise HTTPException(status_code=409, detail="Pick this enquiry before recording a call and scheduling follow-up")
    enquiry.notes = payload.notes or None
    enquiry.next_follow_up_at = payload.next_follow_up_at
    enquiry.status = EnquiryStatus.FOLLOW_UPS.value
    db.commit()
    db.refresh(enquiry)
    count = db.scalar(select(func.count(FollowUp.id)).where(FollowUp.enquiry_id == enquiry.id)) or 0
    return enquiry_response(enquiry, count)


@router.post(
    "/enquiries/{enquiry_id}/follow-ups",
    response_model=FollowUpResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def record_completed_follow_up(
    enquiry_id: UUID,
    payload: CompleteFollowUpRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> FollowUp:
    enquiry = db.scalar(select(Enquiry).where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_(None)).with_for_update())
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    require_enquiry_handler(enquiry, auth)
    require_actionable_enquiry(enquiry)
    follow_up = FollowUp(
        enquiry_id=enquiry.id,
        completed_at=payload.completed_at,
        created_by_user_id=auth.user.id,
    )
    db.add(follow_up)
    # Completing the enquiry records the final contact and removes it from active follow-up work.
    enquiry.next_follow_up_at = None
    enquiry.status = EnquiryStatus.CLOSED.value
    db.commit()
    db.refresh(follow_up)
    return follow_up


@router.get("/enquiries/{enquiry_id}/follow-ups", response_model=FollowUpHistoryPage)
def list_completed_follow_ups(
    enquiry_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthenticatedSession, Depends(get_current_auth)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> FollowUpHistoryPage:
    if db.scalar(select(Enquiry.id).where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_(None))) is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    base = select(FollowUp).where(FollowUp.enquiry_id == enquiry_id)
    total = db.scalar(select(func.count()).select_from(FollowUp).where(FollowUp.enquiry_id == enquiry_id)) or 0
    items = db.scalars(base.order_by(FollowUp.completed_at.desc()).limit(limit).offset(offset)).all()
    return FollowUpHistoryPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/follow-ups", response_model=FollowUpPage)
def list_actionable_follow_ups(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthenticatedSession, Depends(get_current_auth)],
    bucket: str = Query(pattern="^(due-today|upcoming|overdue)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> FollowUpPage:
    zone = ZoneInfo(get_settings().business_timezone)
    now = datetime.now(zone)
    today_start = datetime.combine(now.date(), time.min, tzinfo=zone).astimezone(timezone.utc)
    tomorrow_start = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    conditions = [
        Enquiry.deleted_at.is_(None),
        Enquiry.status.in_(ACTIVE_STATUSES),
        Enquiry.do_not_contact.is_(False),
        Enquiry.next_follow_up_at.is_not(None),
    ]
    if bucket == "due-today":
        conditions.extend((Enquiry.next_follow_up_at >= today_start, Enquiry.next_follow_up_at < tomorrow_start))
    elif bucket == "upcoming":
        conditions.append(Enquiry.next_follow_up_at >= tomorrow_start)
    else:
        conditions.append(Enquiry.next_follow_up_at < today_start)
    stmt = select(Enquiry).options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by)).where(*conditions)
    total = db.scalar(select(func.count()).select_from(Enquiry).where(*conditions)) or 0
    rows = db.scalars(stmt.order_by(Enquiry.next_follow_up_at.asc()).limit(limit).offset(offset)).unique().all()
    counts = completed_follow_up_counts(db, [item.id for item in rows])
    return FollowUpPage(
        bucket=bucket,
        items=[enquiry_response(item, counts.get(item.id, 0)) for item in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/enquiries/{enquiry_id}/handler",
    response_model=EnquiryResponse,
    dependencies=[Depends(require_csrf)],
)
def update_enquiry_handler(
    enquiry_id: UUID,
    payload: UpdateEnquiryHandlerRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryResponse:
    if auth.user.role != UserRole.MANAGER.value:
        raise HTTPException(status_code=403, detail="Only Managers can directly change the handler")
    enquiry = db.scalar(
        select(Enquiry)
        .options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by))
        .where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_(None))
        .with_for_update(of=Enquiry)
    )
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    if payload.handled_by_id is None:
        enquiry.handled_by = None
        if enquiry.status in {EnquiryStatus.ASSIGNED.value, EnquiryStatus.FOLLOW_UPS.value}:
            enquiry.status = EnquiryStatus.NEW.value
            enquiry.next_follow_up_at = None
    else:
        handler = db.get(User, payload.handled_by_id)
        if handler is None or not handler.is_active or handler.role != UserRole.STAFF.value:
            raise HTTPException(status_code=422, detail="Handler must be an active Staff account")
        enquiry.handled_by = handler
        if enquiry.status == EnquiryStatus.NEW.value:
            enquiry.status = EnquiryStatus.ASSIGNED.value
    db.commit()
    db.refresh(enquiry)
    count = db.scalar(select(func.count(FollowUp.id)).where(FollowUp.enquiry_id == enquiry.id)) or 0
    return enquiry_response(enquiry, count)
