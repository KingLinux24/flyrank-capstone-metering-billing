from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    api_calls_limit: Mapped[int] = mapped_column(Integer)
    token_limit: Mapped[int] = mapped_column(Integer)
    stripe_price_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="plan")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128))
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    api_key_prefix: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    subscription: Mapped[Subscription | None] = relationship(back_populates="tenant", uselist=False)
    usage_events: Mapped[list[UsageEvent]] = relationship(back_populates="tenant")


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_subscriptions_tenant"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    status: Mapped[str] = mapped_column(String(32))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    tenant: Mapped[Tenant] = relationship(back_populates="subscription")
    plan: Mapped[Plan] = relationship(back_populates="subscriptions", lazy="joined")


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_usage_tenant_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    api_calls: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer)
    cached_input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    reasoning_tokens: Mapped[int] = mapped_column(Integer)
    cost_micros: Mapped[int] = mapped_column(BigInteger)
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tenant: Mapped[Tenant] = relationship(back_populates="usage_events")

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.cached_input_tokens
            + self.output_tokens
            + self.reasoning_tokens
        )


class ProcessedStripeEvent(Base):
    __tablename__ = "processed_stripe_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UsageRollup(Base):
    __tablename__ = "usage_rollups"
    __table_args__ = (UniqueConstraint("tenant_id", "period_start", name="uq_rollup_tenant_period"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    api_calls: Mapped[int] = mapped_column(Integer)
    tokens: Mapped[int] = mapped_column(Integer)
    cost_micros: Mapped[int] = mapped_column(BigInteger)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobAlert(Base):
    __tablename__ = "job_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_name: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
