from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Customer, Enquiry, EnquiryAuditEvent, EnquiryChangeRequest, FollowUp, utc_now


DELETION_RECOVERY_WINDOW = timedelta(days=5)


def purge_deleted_enquiry(
    db: Session,
    enquiry_id: UUID,
    *,
    now: datetime | None = None,
    require_expired: bool = False,
) -> tuple[bool, bool]:
    """Permanently remove one deleted enquiry and its history; retain shared customers."""
    now = now or utc_now()
    customer_id = db.scalar(
        select(Enquiry.customer_id).where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_not(None))
    )
    if customer_id is None:
        return False, False

    # Serialize purges/restores of enquiries belonging to one shared customer.
    customer = db.scalar(select(Customer).where(Customer.id == customer_id).with_for_update())
    enquiry = db.scalar(
        select(Enquiry).where(Enquiry.id == enquiry_id, Enquiry.deleted_at.is_not(None)).with_for_update()
    )
    if enquiry is None:
        return False, False
    if require_expired:
        deleted_at = enquiry.deleted_at
        if deleted_at is None:
            return False, False
        if deleted_at.tzinfo is None:
            deleted_at = deleted_at.replace(tzinfo=timezone.utc)
        if deleted_at + DELETION_RECOVERY_WINDOW > now:
            return False, False

    db.execute(delete(FollowUp).where(FollowUp.enquiry_id == enquiry_id))
    db.execute(delete(EnquiryChangeRequest).where(EnquiryChangeRequest.enquiry_id == enquiry_id))
    db.execute(delete(EnquiryAuditEvent).where(EnquiryAuditEvent.enquiry_id == enquiry_id))
    db.execute(delete(Enquiry).where(Enquiry.id == enquiry_id))
    db.flush()

    customer_deleted = False
    remaining_enquiries = db.scalar(
        select(func.count(Enquiry.id)).where(Enquiry.customer_id == customer_id)
    ) or 0
    if customer is not None and remaining_enquiries == 0:
        db.execute(delete(Customer).where(Customer.id == customer_id))
        customer_deleted = True
    return True, customer_deleted


def purge_expired_deleted_enquiries(
    session_factory: sessionmaker[Session],
    *,
    now: datetime | None = None,
    batch_size: int = 100,
) -> int:
    """Purge expired records in customer-locked batches, safe for multiple app workers."""
    now = now or utc_now()
    cutoff = now - DELETION_RECOVERY_WINDOW
    purged_count = 0
    with session_factory() as db:
        customer_ids = db.scalars(
            select(Enquiry.customer_id)
            .where(Enquiry.deleted_at.is_not(None), Enquiry.deleted_at <= cutoff)
            .distinct()
            .order_by(Enquiry.customer_id)
            .limit(batch_size)
        ).all()
        for customer_id in customer_ids:
            customer = db.scalar(
                select(Customer).where(Customer.id == customer_id).with_for_update(skip_locked=True)
            )
            if customer is None:
                continue
            expired_ids = db.scalars(
                select(Enquiry.id)
                .where(
                    Enquiry.customer_id == customer_id,
                    Enquiry.deleted_at.is_not(None),
                    Enquiry.deleted_at <= cutoff,
                )
                .order_by(Enquiry.id)
                .with_for_update(skip_locked=True)
            ).all()
            for enquiry_id in expired_ids:
                deleted, _ = purge_deleted_enquiry(
                    db, enquiry_id, now=now, require_expired=True
                )
                purged_count += int(deleted)
            if not (db.scalar(select(func.count(Enquiry.id)).where(Enquiry.customer_id == customer_id)) or 0):
                db.execute(delete(Customer).where(Customer.id == customer_id))
        db.commit()
    return purged_count
