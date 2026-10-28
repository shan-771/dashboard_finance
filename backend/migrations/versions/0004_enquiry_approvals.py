"""Add enquiry edit/deletion approval history and soft deletion.

Revision ID: 0004_enquiry_approvals
Revises: 0003_follow_ups
Create Date: 2026-10-28
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_enquiry_approvals"
down_revision: str | None = "0003_follow_ups"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("enquiries", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_enquiries_deleted_at", "enquiries", ["deleted_at"], unique=False)
    op.create_table(
        "enquiry_change_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("enquiry_id", sa.Uuid(), nullable=False),
        sa.Column("request_type", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("proposed_changes", sa.JSON(), nullable=True),
        sa.Column("original_snapshot", sa.JSON(), nullable=False),
        sa.Column("base_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("request_type IN ('edit', 'delete')", name="ck_change_requests_type"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'stale', 'completed')", name="ck_change_requests_status"),
        sa.ForeignKeyConstraint(["enquiry_id"], ["enquiries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_enquiry_change_requests_enquiry_id", "enquiry_change_requests", ["enquiry_id"], unique=False)
    op.create_index("ix_enquiry_change_requests_status", "enquiry_change_requests", ["status"], unique=False)
    op.create_table(
        "enquiry_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("enquiry_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("before_values", sa.JSON(), nullable=False),
        sa.Column("after_values", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enquiry_id"], ["enquiries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_enquiry_audit_events_enquiry_id", "enquiry_audit_events", ["enquiry_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_enquiry_audit_events_enquiry_id", table_name="enquiry_audit_events")
    op.drop_table("enquiry_audit_events")
    op.drop_index("ix_enquiry_change_requests_status", table_name="enquiry_change_requests")
    op.drop_index("ix_enquiry_change_requests_enquiry_id", table_name="enquiry_change_requests")
    op.drop_table("enquiry_change_requests")
    op.drop_index("ix_enquiries_deleted_at", table_name="enquiries")
    op.drop_column("enquiries", "deleted_at")
