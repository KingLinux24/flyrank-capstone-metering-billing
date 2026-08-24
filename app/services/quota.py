from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Subscription, Tenant, UsageEvent
from app.pricing import SUB_ACTIVE, TokenUsage


@dataclass(frozen=True)
class PeriodUsage:
    api_calls: int
    tokens: int
    cost_micros: int


class QuotaExceeded(Exception):
    def __init__(self, metric: str, used: int, limit: int, requested: int) -> None:
        self.metric = metric
        self.used = used
        self.limit = limit
        self.requested = requested
        super().__init__(f"{metric} quota exceeded")


class PaymentRequired(Exception):
    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(f"subscription status {status} requires payment")


def period_usage(db: Session, tenant_id: str, period_start) -> PeriodUsage:
    row = db.execute(
        select(
            func.coalesce(func.sum(UsageEvent.api_calls), 0),
            func.coalesce(
                func.sum(
                    UsageEvent.input_tokens
                    + UsageEvent.cached_input_tokens
                    + UsageEvent.output_tokens
                    + UsageEvent.reasoning_tokens
                ),
                0,
            ),
            func.coalesce(func.sum(UsageEvent.cost_micros), 0),
        ).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.created_at >= period_start,
        )
    ).one()
    return PeriodUsage(api_calls=int(row[0]), tokens=int(row[1]), cost_micros=int(row[2]))


def require_active_subscription(sub: Subscription | None) -> Subscription:
    if sub is None:
        raise PaymentRequired("missing")
    if sub.status != SUB_ACTIVE:
        raise PaymentRequired(sub.status)
    return sub


def assert_quota(
    current: PeriodUsage,
    requested_calls: int,
    requested_tokens: TokenUsage,
    api_limit: int,
    token_limit: int,
) -> None:
    next_calls = current.api_calls + requested_calls
    next_tokens = current.tokens + requested_tokens.total_tokens
    if next_calls > api_limit:
        raise QuotaExceeded("api_calls", current.api_calls, api_limit, requested_calls)
    if next_tokens > token_limit:
        raise QuotaExceeded("tokens", current.tokens, token_limit, requested_tokens.total_tokens)


def lock_tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.execute(
        select(Tenant).where(Tenant.id == tenant_id).with_for_update()
    ).scalar_one()
    return tenant
