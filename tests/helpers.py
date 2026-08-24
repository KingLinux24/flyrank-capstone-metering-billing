from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.deps import hash_api_key
from app.models import Plan, Subscription, Tenant, utcnow
from app.pricing import (
    FREE_API_CALLS_LIMIT,
    FREE_TOKEN_LIMIT,
    PLAN_FREE,
    PLAN_PRO,
    PRO_API_CALLS_LIMIT,
    PRO_TOKEN_LIMIT,
    SUB_ACTIVE,
)


def make_plans(db: Session) -> dict[str, Plan]:
    free = Plan(code=PLAN_FREE, name="Free", api_calls_limit=FREE_API_CALLS_LIMIT, token_limit=FREE_TOKEN_LIMIT)
    pro = Plan(
        code=PLAN_PRO,
        name="Pro",
        api_calls_limit=PRO_API_CALLS_LIMIT,
        token_limit=PRO_TOKEN_LIMIT,
        stripe_price_id="price_test_pro",
    )
    db.add_all([free, pro])
    db.flush()
    return {PLAN_FREE: free, PLAN_PRO: pro}


def make_tenant(
    db: Session,
    *,
    name: str,
    plan: Plan,
    api_key: str,
    status: str = SUB_ACTIVE,
) -> Tenant:
    tenant = Tenant(name=name, api_key_hash=hash_api_key(api_key), api_key_prefix=api_key[:12])
    db.add(tenant)
    db.flush()
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    db.add(
        Subscription(
            tenant_id=tenant.id,
            plan_id=plan.id,
            status=status,
            period_start=start,
            period_end=datetime(2026, 9, 1, tzinfo=timezone.utc),
            updated_at=utcnow(),
        )
    )
    db.flush()
    return tenant


def stripe_event(event_id: str, event_type: str, obj: dict) -> dict:
    return {"id": event_id, "type": event_type, "data": {"object": obj}}
