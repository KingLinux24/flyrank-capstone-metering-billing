from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import UsageEvent
from app.pricing import PLAN_FREE, PLAN_PRO, SUB_PAST_DUE
from tests.helpers import make_plans, make_tenant

FREE_KEY = "sk_live_test_free_bbbbbbbb"
UNPAID_KEY = "sk_live_test_unpaid_cccccc"
PRO_KEY = "sk_live_test_pro_dddddddd"


def test_just_under_quota_is_allowed(client: TestClient, db: Session):
    plans = make_plans(db)
    tenant = make_tenant(db, name="under", plan=plans[PLAN_FREE], api_key=FREE_KEY)
    db.add(
        UsageEvent(
            tenant_id=tenant.id,
            idempotency_key="seed-999",
            api_calls=999,
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cost_micros=0,
            result_json="{}",
        )
    )
    db.commit()
    res = client.post(
        "/v1/generate",
        json={"prompt": "boundary-under"},
        headers={"X-API-Key": FREE_KEY, "Idempotency-Key": "call-1000"},
    )
    assert res.status_code == 200
    usage = client.get("/v1/usage", headers={"X-API-Key": FREE_KEY})
    assert usage.json()["api_calls"]["used"] == 1000
    assert usage.json()["api_calls"]["limit"] == 1000


def test_at_limit_next_request_is_429(client: TestClient, db: Session):
    plans = make_plans(db)
    tenant = make_tenant(db, name="at-limit", plan=plans[PLAN_FREE], api_key=FREE_KEY)
    db.add(
        UsageEvent(
            tenant_id=tenant.id,
            idempotency_key="seed-1000",
            api_calls=1000,
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cost_micros=0,
            result_json="{}",
        )
    )
    db.commit()
    res = client.post(
        "/v1/generate",
        json={"prompt": "boundary-over"},
        headers={"X-API-Key": FREE_KEY, "Idempotency-Key": "call-1001"},
    )
    assert res.status_code == 429
    assert res.headers.get("retry-after") == "3600"
    body = res.json()
    payload = body["detail"]
    assert payload["code"] == "quota_exceeded"
    assert payload["detail"]["metric"] == "api_calls"
    assert payload["detail"]["used"] == 1000
    assert payload["detail"]["limit"] == 1000
    assert db.query(UsageEvent).filter(UsageEvent.idempotency_key == "call-1001").count() == 0


def test_token_overage_is_429(client: TestClient, db: Session):
    plans = make_plans(db)
    make_tenant(db, name="tokens", plan=plans[PLAN_FREE], api_key=FREE_KEY)
    db.commit()
    res = client.post(
        "/v1/generate",
        json={"prompt": "too many tokens", "input_tokens": 100_001},
        headers={"X-API-Key": FREE_KEY, "Idempotency-Key": "tok-over"},
    )
    assert res.status_code == 429
    assert res.json()["detail"]["detail"]["metric"] == "tokens"


def test_past_due_is_402(client: TestClient, db: Session):
    plans = make_plans(db)
    make_tenant(db, name="unpaid", plan=plans[PLAN_FREE], api_key=UNPAID_KEY, status=SUB_PAST_DUE)
    db.commit()
    res = client.post(
        "/v1/generate",
        json={"prompt": "pay me"},
        headers={"X-API-Key": UNPAID_KEY, "Idempotency-Key": "unpaid-1"},
    )
    assert res.status_code == 402
    assert res.json()["detail"]["code"] == "payment_required"


def test_pro_higher_limits(client: TestClient, db: Session):
    plans = make_plans(db)
    make_tenant(db, name="pro", plan=plans[PLAN_PRO], api_key=PRO_KEY)
    db.commit()
    res = client.post(
        "/v1/generate",
        json={"prompt": "pro", "input_tokens": 50_000},
        headers={"X-API-Key": PRO_KEY, "Idempotency-Key": "pro-ok"},
    )
    assert res.status_code == 200
