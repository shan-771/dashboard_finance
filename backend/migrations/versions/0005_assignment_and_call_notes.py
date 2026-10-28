"""Add first-claim assignment and per-enquiry call notes.

Revision ID: 0005_assignment_and_call_notes
Revises: 0004_enquiry_approvals
Create Date: 2026-10-28
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_assignment_and_call_notes"
down_revision: str | None = "0004_enquiry_approvals"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("claim_attempt_window_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("claim_attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("enquiries", sa.Column("notes", sa.Text(), nullable=True))
    op.drop_constraint("ck_enquiries_status", "enquiries", type_="check")
    op.create_check_constraint(
        "ck_enquiries_status",
        "enquiries",
        "status IN ('New', 'Assigned', 'Attended', 'Follow-ups', 'Closed', 'Open', 'Lost')",
    )
    op.alter_column("users", "claim_attempt_count", server_default=None)


def downgrade() -> None:
    op.execute("UPDATE enquiries SET status = 'Attended' WHERE status = 'Assigned'")
    op.drop_constraint("ck_enquiries_status", "enquiries", type_="check")
    op.create_check_constraint(
        "ck_enquiries_status",
        "enquiries",
        "status IN ('New', 'Attended', 'Follow-ups', 'Closed', 'Open', 'Lost')",
    )
    op.drop_column("enquiries", "notes")
    op.drop_column("users", "claim_attempt_count")
    op.drop_column("users", "claim_attempt_window_started_at")
