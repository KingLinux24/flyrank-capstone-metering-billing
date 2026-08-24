from __future__ import annotations

import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import UsageEvent, utcnow
from app.pricing import TokenUsage, event_cost_micros, micros_to_usd_string
from app.services.quota import (
    PaymentRequired,
    QuotaExceeded,
    assert_quota,
    lock_tenant,
    period_usage,
    require_active_subscription,
)


def _payload(
    event: UsageEvent,
    *,
    replayed: bool,
    text: str,
) -> dict:
    return {
        "id": event.id,
        "tenant_id": event.tenant_id,
        "replayed": replayed,
        "api_calls": event.api_calls,
        "tokens": event.total_tokens,
        "cost_micros": event.cost_micros,
        "cost_usd": micros_to_usd_string(event.cost_micros),
        "usage": {
            "api_calls": event.api_calls,
            "input_tokens": event.input_tokens,
            "cached_input_tokens": event.cached_input_tokens,
            "output_tokens": event.output_tokens,
            "reasoning_tokens": event.reasoning_tokens,
        },
        "text": text,
    }


def find_by_idempotency(db: Session, tenant_id: str, key: str) -> UsageEvent | None:
    return (
        db.query(UsageEvent)
        .filter(UsageEvent.tenant_id == tenant_id, UsageEvent.idempotency_key == key)
        .one_or_none()
    )


def record_generate(
    db: Session,
    *,
    tenant_id: str,
    idempotency_key: str,
    prompt: str,
    tokens: TokenUsage,
) -> dict:
    tenant = lock_tenant(db, tenant_id)
    existing = find_by_idempotency(db, tenant_id, idempotency_key)
    if existing is not None:
        stored = json.loads(existing.result_json)
        stored["replayed"] = True
        return stored
    sub = tenant.subscription
    require_active_subscription(sub)
    current = period_usage(db, tenant_id, sub.period_start)
    assert_quota(current, 1, tokens, sub.plan.api_calls_limit, sub.plan.token_limit)

    from app.models import new_id
    cost = event_cost_micros(1, tokens)
    text = f"simulated response for: {prompt[:80]}"
    event = UsageEvent(
        id=new_id(),
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        api_calls=1,
        input_tokens=tokens.input_tokens,
        cached_input_tokens=tokens.cached_input_tokens,
        output_tokens=tokens.output_tokens,
        reasoning_tokens=tokens.reasoning_tokens,
        cost_micros=cost,
        result_json="{}",
        created_at=utcnow(),
    )
    payload = _payload(event, replayed=False, text=text)
    event.result_json = json.dumps(payload)
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = find_by_idempotency(db, tenant_id, idempotency_key)
        if existing is None:
            raise
        stored = json.loads(existing.result_json)
        stored["replayed"] = True
        return stored
    db.commit()
    db.refresh(event)
    return json.loads(event.result_json)


__all__ = ["PaymentRequired", "QuotaExceeded", "record_generate"]
