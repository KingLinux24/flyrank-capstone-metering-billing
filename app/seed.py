"""Idempotent seed: Free + Pro plans, demo tenants, monthly period."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import configure_engine, get_session_factory
from app.deps import generate_api_key, hash_api_key
from app.models import Base, Plan, Subscription, Tenant, UsageEvent, utcnow
from app.pricing import (
    FREE_API_CALLS_LIMIT,
    FREE_TOKEN_LIMIT,
    PLAN_FREE,
    PLAN_PRO,
    PRO_API_CALLS_LIMIT,
    PRO_TOKEN_LIMIT,
    SUB_ACTIVE,
    TokenUsage,
    event_cost_micros,
)


def month_start(now: datetime | None = None) -> datetime:
    now = now or utcnow()
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


def upsert_plans(db: Session, stripe_price_id: str | None) -> dict[str, Plan]:
    plans = {}
    specs = [
        (PLAN_FREE, "Free", FREE_API_CALLS_LIMIT, FREE_TOKEN_LIMIT, None),
        (PLAN_PRO, "Pro", PRO_API_CALLS_LIMIT, PRO_TOKEN_LIMIT, stripe_price_id or None),
    ]
    for code, name, calls, tokens, price in specs:
        plan = db.query(Plan).filter(Plan.code == code).one_or_none()
        if plan is None:
            plan = Plan(code=code, name=name, api_calls_limit=calls, token_limit=tokens, stripe_price_id=price)
            db.add(plan)
        else:
            plan.name = name
            plan.api_calls_limit = calls
            plan.token_limit = tokens
            if price:
                plan.stripe_price_id = price
        plans[code] = plan
    db.flush()
    return plans


def upsert_tenant(db: Session, name: str, prefix_tag: str, plan: Plan, api_key: str | None) -> tuple[Tenant, str]:
    tenant = db.query(Tenant).filter(Tenant.name == name).one_or_none()
    raw = api_key or generate_api_key()
    if tenant is None:
        tenant = Tenant(
            name=name,
            api_key_hash=hash_api_key(raw),
            api_key_prefix=raw[:12],
        )
        db.add(tenant)
        db.flush()
        start = month_start()
        db.add(
            Subscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                status=SUB_ACTIVE,
                period_start=start,
                period_end=utcnow(),
            )
        )
        printed = raw
    else:
        printed = f"(existing prefix {tenant.api_key_prefix}…)"
        if tenant.subscription is None:
            db.add(
                Subscription(
                    tenant_id=tenant.id,
                    plan_id=plan.id,
                    status=SUB_ACTIVE,
                    period_start=month_start(),
                    period_end=utcnow(),
                )
            )
        else:
            tenant.subscription.plan_id = plan.id
            tenant.subscription.status = SUB_ACTIVE
    return tenant, printed


def seed_near_quota(db: Session, tenant: Tenant) -> None:
    """Leave the free tenant at 999/1000 API calls so the next call is the boundary."""
    existing = db.query(UsageEvent).filter(UsageEvent.tenant_id == tenant.id).count()
    if existing:
        return
    tokens = TokenUsage()
    cost = event_cost_micros(1, tokens)
    # 999 identical events would be slow to insert one-by-one in a demo; one event
    # with api_calls=999 keeps the rollup honest.
    db.add(
        UsageEvent(
            tenant_id=tenant.id,
            idempotency_key="seed-near-quota",
            api_calls=999,
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cost_micros=cost * 999,
            result_json='{"id":"seed","replayed":false,"text":"seed"}',
        )
    )


def run() -> None:
    settings = get_settings()
    configure_engine(settings.database_url)
    engine = configure_engine(settings.database_url)
    if settings.database_url.startswith("sqlite"):
        Path("data").mkdir(exist_ok=True)
        Base.metadata.create_all(engine)
    db = get_session_factory()()
    try:
        plans = upsert_plans(db, settings.stripe_pro_price_id)
        # Stable demo keys so README curl examples work. Rotate if this repo is forked.
        free_key = "sk_live_demo_free_tenant_key_001"
        pro_key = "sk_live_demo_pro_tenant_key_001"
        unpaid_key = "sk_live_demo_unpaid_tenant_key_01"
        free_tenant, _ = upsert_tenant(db, "Acme Free", "free", plans[PLAN_FREE], free_key)
        upsert_tenant(db, "Acme Pro", "pro", plans[PLAN_PRO], pro_key)
        unpaid, _ = upsert_tenant(db, "Acme Unpaid", "unpaid", plans[PLAN_FREE], unpaid_key)
        if unpaid.subscription:
            unpaid.subscription.status = "past_due"
        seed_near_quota(db, free_tenant)
        db.commit()
        print("Seed complete.")
        print(f"  Free tenant (999/1000 calls) X-API-Key: {free_key}")
        print(f"  Pro tenant                  X-API-Key: {pro_key}")
        print(f"  Unpaid tenant (402 demo)    X-API-Key: {unpaid_key}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
