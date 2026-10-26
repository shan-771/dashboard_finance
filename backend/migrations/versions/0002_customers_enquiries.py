"""Add customers and unified enquiries.

Revision ID: 0002_customers_enquiries
Revises: 0001_users_sessions
Create Date: 2026-10-24
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_customers_enquiries"
down_revision: str | None = "0001_users_sessions"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("merged_into_customer_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["merged_into_customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customers_phone", "customers", ["phone"], unique=False)
    op.create_index("ix_customers_email", "customers", ["email"], unique=False)
    op.create_index("ix_customers_merged_into_customer_id", "customers", ["merged_into_customer_id"], unique=False)
    op.create_table(
        "enquiries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("service_type", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("handled_by_id", sa.Uuid(), nullable=True),
        sa.Column("outcome_reason", sa.Text(), nullable=True),
        sa.Column("do_not_contact", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('New', 'Attended', 'Follow-ups', 'Closed', 'Open', 'Lost')",
            name="ck_enquiries_status",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["handled_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_enquiries_customer_id", "enquiries", ["customer_id"], unique=False)
    op.create_index("ix_enquiries_status", "enquiries", ["status"], unique=False)
    op.create_index("ix_enquiries_handled_by_id", "enquiries", ["handled_by_id"], unique=False)
    op.create_index("ix_enquiries_created_at", "enquiries", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_enquiries_created_at", table_name="enquiries")
    op.drop_index("ix_enquiries_handled_by_id", table_name="enquiries")
    op.drop_index("ix_enquiries_status", table_name="enquiries")
    op.drop_index("ix_enquiries_customer_id", table_name="enquiries")
    op.drop_table("enquiries")
    op.drop_index("ix_customers_merged_into_customer_id", table_name="customers")
    op.drop_index("ix_customers_email", table_name="customers")
    op.drop_index("ix_customers_phone", table_name="customers")
    op.drop_table("customers")
