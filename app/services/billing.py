from sqlalchemy.orm import Session

from app.models import Tenant
from app.pricing import TokenUsage, event_cost_micros, micros_to_usd_string
from app.services.quota import period_usage


def usage_snapshot(db: Session, tenant: Tenant) -> dict:
    sub = tenant.subscription
    if sub is None:
        raise ValueError("tenant has no subscription")
    current = period_usage(db, tenant.id, sub.period_start)
    plan = sub.plan
    return {
        "tenant_id": tenant.id,
        "plan": plan.code,
        "subscription_status": sub.status,
        "period_start": sub.period_start.isoformat(),
        "period_end": sub.period_end.isoformat(),
        "api_calls": {
            "used": current.api_calls,
            "limit": plan.api_calls_limit,
            "remaining": max(plan.api_calls_limit - current.api_calls, 0),
        },
        "tokens": {
            "used": current.tokens,
            "limit": plan.token_limit,
            "remaining": max(plan.token_limit - current.tokens, 0),
        },
        "cost_micros": current.cost_micros,
        "cost_usd": micros_to_usd_string(current.cost_micros),
        "cost_detail": {
            "unit": "micro-USD (1 USD = 1_000_000)",
            "api_call_rate_micros": event_cost_micros(1, TokenUsage()),
            "rules": [
                "cached input tokens are priced cheaper than fresh input",
                "reasoning tokens are billed at the output rate",
                "token categories are priced separately, never summed first",
            ],
        },
    }
