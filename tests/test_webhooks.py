from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ProcessedStripeEvent, Subscription
from app.pricing import PLAN_FREE, PLAN_PRO, SUB_ACTIVE, SUB_CANCELED
from app.services.stripe_sync import handle_stripe_event
from tests.helpers import make_plans, make_tenant, stripe_event

KEY = "sk_live_test_stripe_ffffff"


def test_checkout_completed_flips_free_to_pro(db: Session):
    plans = make_plans(db)
    tenant = make_tenant(db, name="upgrader", plan=plans[PLAN_FREE], api_key=KEY)
    db.commit()
    event = stripe_event(
        "evt_1",
        "checkout.session.completed",
        {
            "id": "cs_test_1",
            "customer": "cus_1",
            "subscription": "sub_1",
            "client_reference_id": tenant.id,
            "metadata": {"tenant_id": tenant.id},
        },
    )
    assert handle_stripe_event(db, event) == "processed"
    db.refresh(tenant.subscription)
    assert tenant.subscription.plan.code == PLAN_PRO
    assert tenant.subscription.status == SUB_ACTIVE
    assert tenant.subscription.stripe_customer_id == "cus_1"


def test_duplicate_event_is_ignored(db: Session):
    plans = make_plans(db)
    tenant = make_tenant(db, name="dup", plan=plans[PLAN_FREE], api_key=KEY)
    db.commit()
    event = stripe_event(
        "evt_dup",
        "checkout.session.completed",
        {
            "customer": "cus_2",
            "subscription": "sub_2",
            "metadata": {"tenant_id": tenant.id},
        },
    )
    assert handle_stripe_event(db, event) == "processed"
    assert handle_stripe_event(db, event) == "duplicate"
    assert db.query(ProcessedStripeEvent).count() == 1


def test_subscription_deleted_returns_to_free(db: Session):
    plans = make_plans(db)
    tenant = make_tenant(db, name="cancel", plan=plans[PLAN_PRO], api_key=KEY)
    tenant.subscription.stripe_customer_id = "cus_3"
    db.commit()
    event = stripe_event(
        "evt_del",
        "customer.subscription.deleted",
        {"id": "sub_3", "customer": "cus_3", "metadata": {"tenant_id": tenant.id}},
    )
    handle_stripe_event(db, event)
    db.commit()
    db.refresh(tenant.subscription)
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).one()
    assert sub.status == SUB_CANCELED
    assert sub.plan.code == PLAN_FREE


def test_forged_webhook_is_400(client: TestClient, db: Session):
    make_plans(db)
    db.commit()
    res = client.post(
        "/webhooks/stripe",
        content=b'{"id":"evt_forged","type":"checkout.session.completed"}',
        headers={"stripe-signature": "t=1,v1=deadbeef"},
    )
    assert res.status_code == 400
    assert db.query(ProcessedStripeEvent).count() == 0
