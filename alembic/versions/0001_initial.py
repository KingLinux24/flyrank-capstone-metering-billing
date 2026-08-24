"""Initial schema: tenants, plans, subscriptions, usage events.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("api_calls_limit", sa.Integer(), nullable=False),
        sa.Column("token_limit", sa.Integer(), nullable=False),
        sa.Column("stripe_price_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("api_key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("api_key_prefix", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenants_api_key_hash", "tenants", ["api_key_hash"], unique=True)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(64), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_subscriptions_tenant"),
    )
    op.create_index("ix_subscriptions_stripe_sub", "subscriptions", ["stripe_subscription_id"])
    op.create_index("ix_subscriptions_stripe_customer", "subscriptions", ["stripe_customer_id"])

    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("api_calls", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_usage_tenant_idempotency"),
    )
    op.create_index("ix_usage_events_tenant_created", "usage_events", ["tenant_id", "created_at"])

    op.create_table(
        "processed_stripe_events",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "usage_rollups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("api_calls", sa.Integer(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "period_start", name="uq_rollup_tenant_period"),
    )

    op.create_table(
        "job_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_name", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("job_alerts")
    op.drop_table("usage_rollups")
    op.drop_table("processed_stripe_events")
    op.drop_table("usage_events")
    op.drop_table("subscriptions")
    op.drop_table("tenants")
    op.drop_table("plans")
