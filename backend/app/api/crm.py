from collections import deque
from datetime import datetime, time, timedelta, timezone
from threading import Lock
from time import monotonic
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.core.config import get_settings
from app.dependencies import AuthenticatedSession, get_current_auth, require_csrf
from app.models import Customer, Enquiry, EnquiryStatus, FollowUp, User, UserRole
from app.schemas import (
    CompleteFollowUpRequest,
    CreateEnquiryRequest,
    CreatePublicEnquiryRequest,
    CustomerResponse,
    EnquiryPage,
    EnquiryResponse,
    FollowUpPage,
    FollowUpHistoryPage,
    FollowUpResponse,
    MergeCustomerRequest,
    PublicEnquiryAccepted,
    ScheduleFollowUpRequest,
    UpdateEnquiryHandlerRequest,
    UpdateEnquiryStatusRequest,
)


router = APIRouter(tags=["customers and enquiries"])
FINAL_STATUSES = {EnquiryStatus.CLOSED, EnquiryStatus.OPEN, EnquiryStatus.LOST}
ACTIVE_STATUSES = {EnquiryStatus.NEW.value, EnquiryStatus.ATTENDED.value, EnquiryStatus.FOLLOW_UPS.value}
ALLOWED_TRANSITIONS = {
    EnquiryStatus.NEW: {EnquiryStatus.ATTENDED, *FINAL_STATUSES},
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
    db.add(Enquiry(
        customer_id=customer.id,
        service_type=payload.service_type,
        source="Website",
        status=EnquiryStatus.NEW.value,
    ))
    db.commit()
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
    stmt = select(Enquiry).options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by)).where(*conditions)
    total = db.scalar(select(func.count()).select_from(Enquiry).where(*conditions)) or 0
    rows = db.scalars(stmt.order_by(Enquiry.created_at.desc()).limit(limit).offset(offset)).unique().all()
    counts = completed_follow_up_counts(db, [item.id for item in rows])
    return EnquiryPage(
        items=[enquiry_response(item, counts.get(item.id, 0)) for item in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


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
    db.commit()
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
        .where(Enquiry.id == enquiry_id)
    )
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    current = EnquiryStatus(enquiry.status)
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


@router.put(
    "/enquiries/{enquiry_id}/follow-up",
    response_model=EnquiryResponse,
    dependencies=[Depends(require_csrf)],
)
def schedule_enquiry_follow_up(
    enquiry_id: UUID,
    payload: ScheduleFollowUpRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryResponse:
    enquiry = db.scalar(
        select(Enquiry).options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by))
        .where(Enquiry.id == enquiry_id)
    )
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    require_actionable_enquiry(enquiry)
    enquiry.next_follow_up_at = payload.next_follow_up_at
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
    enquiry = db.get(Enquiry, enquiry_id)
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    require_actionable_enquiry(enquiry)
    follow_up = FollowUp(
        enquiry_id=enquiry.id,
        completed_at=payload.completed_at,
        created_by_user_id=auth.user.id,
    )
    db.add(follow_up)
    # Completing the scheduled contact clears its current reminder; staff can schedule the next one afterward.
    enquiry.next_follow_up_at = None
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
    if db.get(Enquiry, enquiry_id) is None:
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
    _: Annotated[AuthenticatedSession, Depends(get_current_auth)],
) -> EnquiryResponse:
    enquiry = db.scalar(
        select(Enquiry)
        .options(joinedload(Enquiry.customer), joinedload(Enquiry.handled_by))
        .where(Enquiry.id == enquiry_id)
    )
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    if payload.handled_by_id is None:
        enquiry.handled_by = None
    else:
        handler = db.get(User, payload.handled_by_id)
        if handler is None or not handler.is_active or handler.role != UserRole.STAFF.value:
            raise HTTPException(status_code=422, detail="Handler must be an active Staff account")
        enquiry.handled_by = handler
    db.commit()
    db.refresh(enquiry)
    count = db.scalar(select(func.count(FollowUp.id)).where(FollowUp.enquiry_id == enquiry.id)) or 0
    return enquiry_response(enquiry, count)
