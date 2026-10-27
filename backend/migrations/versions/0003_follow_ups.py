"""Add completed and scheduled follow-up tracking.

Revision ID: 0003_follow_ups
Revises: 0002_customers_enquiries
Create Date: 2026-10-27
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_follow_ups"
down_revision: str | None = "0002_customers_enquiries"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("enquiries", sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_enquiries_next_follow_up_at", "enquiries", ["next_follow_up_at"], unique=False)
    op.create_table(
        "follow_ups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("enquiry_id", sa.Uuid(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enquiry_id"], ["enquiries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_follow_ups_enquiry_id", "follow_ups", ["enquiry_id"], unique=False)
    op.create_index("ix_follow_ups_completed_at", "follow_ups", ["completed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_follow_ups_completed_at", table_name="follow_ups")
    op.drop_index("ix_follow_ups_enquiry_id", table_name="follow_ups")
    op.drop_table("follow_ups")
    op.drop_index("ix_enquiries_next_follow_up_at", table_name="enquiries")
    op.drop_column("enquiries", "next_follow_up_at")
