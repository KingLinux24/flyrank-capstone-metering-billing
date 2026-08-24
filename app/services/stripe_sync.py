from __future__ import annotations

import stripe
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Plan, ProcessedStripeEvent, Subscription, Tenant, utcnow
from app.pricing import PLAN_FREE, PLAN_PRO, SUB_ACTIVE, SUB_CANCELED, SUB_PAST_DUE, SUB_UNPAID


def _status_from_stripe(status: str | None) -> str:
    mapping = {
        "active": SUB_ACTIVE,
        "trialing": SUB_ACTIVE,
        "past_due": SUB_PAST_DUE,
        "unpaid": SUB_UNPAID,
        "canceled": SUB_CANCELED,
        "incomplete_expired": SUB_CANCELED,
    }
    return mapping.get(status or "", SUB_ACTIVE)


def already_processed(db: Session, event_id: str) -> bool:
    return db.get(ProcessedStripeEvent, event_id) is not None


def mark_processed(db: Session, event_id: str, event_type: str) -> bool:
    db.add(ProcessedStripeEvent(id=event_id, event_type=event_type, processed_at=utcnow()))
    try:
        db.flush()
        return True
    except IntegrityError:
        db.rollback()
        return False


def create_checkout_session(tenant: Tenant, success_url: str | None, cancel_url: str | None) -> dict:
    settings = get_settings()
    if not settings.stripe_secret_key or settings.stripe_secret_key.startswith("sk_test_replace"):
        raise RuntimeError("STRIPE_SECRET_KEY is not configured")
    if not settings.stripe_pro_price_id or settings.stripe_pro_price_id.startswith("price_replace"):
        raise RuntimeError("STRIPE_PRO_PRICE_ID is not configured")
    stripe.api_key = settings.stripe_secret_key
    success = success_url or settings.stripe_success_url
    cancel = cancel_url or settings.stripe_cancel_url
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": settings.stripe_pro_price_id, "quantity": 1}],
        success_url=success + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel,
        client_reference_id=tenant.id,
        metadata={"tenant_id": tenant.id},
        subscription_data={"metadata": {"tenant_id": tenant.id}},
    )
    return {"checkout_url": session.url, "session_id": session.id}


def apply_subscription(
    db: Session,
    *,
    tenant_id: str | None,
    stripe_customer_id: str | None,
    stripe_subscription_id: str | None,
    status: str,
    plan_code: str,
) -> None:
    tenant = None
    if tenant_id:
        tenant = db.get(Tenant, tenant_id)
    if tenant is None and stripe_customer_id:
        sub = (
            db.query(Subscription)
            .filter(Subscription.stripe_customer_id == stripe_customer_id)
            .one_or_none()
        )
        tenant = sub.tenant if sub else None
    if tenant is None:
        return
    plan = db.query(Plan).filter(Plan.code == plan_code).one()
    start, end = utcnow(), utcnow()
    sub = tenant.subscription
    if sub is None:
        return
    sub.plan_id = plan.id
    sub.status = status
    if stripe_customer_id:
        sub.stripe_customer_id = stripe_customer_id
    if stripe_subscription_id:
        sub.stripe_subscription_id = stripe_subscription_id
    sub.period_start = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sub.period_end = end
    sub.updated_at = utcnow()


def handle_stripe_event(db: Session, event: dict) -> str:
    event_id = event["id"]
    event_type = event["type"]
    if already_processed(db, event_id):
        return "duplicate"
    if not mark_processed(db, event_id, event_type):
        return "duplicate"

    data = event.get("data", {}).get("object", {})
    if event_type == "checkout.session.completed":
        tenant_id = (data.get("metadata") or {}).get("tenant_id") or data.get("client_reference_id")
        apply_subscription(
            db,
            tenant_id=tenant_id,
            stripe_customer_id=data.get("customer"),
            stripe_subscription_id=data.get("subscription"),
            status=SUB_ACTIVE,
            plan_code=PLAN_PRO,
        )
    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        meta = data.get("metadata") or {}
        price = None
        items = (data.get("items") or {}).get("data") or []
        if items:
            price = (items[0].get("price") or {}).get("id")
        pro = db.query(Plan).filter(Plan.code == PLAN_PRO).one()
        plan_code = PLAN_PRO if price and price == pro.stripe_price_id else PLAN_PRO
        if data.get("status") in ("canceled", "incomplete_expired"):
            plan_code = PLAN_FREE
        apply_subscription(
            db,
            tenant_id=meta.get("tenant_id"),
            stripe_customer_id=data.get("customer"),
            stripe_subscription_id=data.get("id"),
            status=_status_from_stripe(data.get("status")),
            plan_code=plan_code if data.get("status") not in ("canceled",) else PLAN_FREE,
        )
    elif event_type == "customer.subscription.deleted":
        meta = data.get("metadata") or {}
        apply_subscription(
            db,
            tenant_id=meta.get("tenant_id"),
            stripe_customer_id=data.get("customer"),
            stripe_subscription_id=data.get("id"),
            status=SUB_CANCELED,
            plan_code=PLAN_FREE,
        )
    db.commit()
    return "processed"
