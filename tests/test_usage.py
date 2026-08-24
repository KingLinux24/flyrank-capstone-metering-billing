from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.pricing import PLAN_FREE, event_cost_micros, TokenUsage
from tests.helpers import make_plans, make_tenant

KEY = "sk_live_test_usage_eeeeee"


def test_usage_rollup_matches_pinned_cost(client: TestClient, db: Session):
    plans = make_plans(db)
    make_tenant(db, name="cost", plan=plans[PLAN_FREE], api_key=KEY)
    db.commit()
    tokens = {
        "prompt": "price me",
        "input_tokens": 1_000,
        "cached_input_tokens": 2_000,
        "output_tokens": 3_000,
        "reasoning_tokens": 4_000,
    }
    res = client.post(
        "/v1/generate",
        json=tokens,
        headers={"X-API-Key": KEY, "Idempotency-Key": "cost-key-1"},
    )
    assert res.status_code == 200
    expected = event_cost_micros(
        1,
        TokenUsage(
            input_tokens=1000,
            cached_input_tokens=2000,
            output_tokens=3000,
            reasoning_tokens=4000,
        ),
    )
    assert res.json()["cost_micros"] == expected
    usage = client.get("/v1/usage", headers={"X-API-Key": KEY})
    body = usage.json()
    assert body["cost_micros"] == expected
    assert body["api_calls"]["used"] == 1
    assert body["tokens"]["used"] == 10_000
    assert body["plan"] == "free"


def test_tenant_isolation(client: TestClient, db: Session):
    plans = make_plans(db)
    make_tenant(db, name="a", plan=plans[PLAN_FREE], api_key="sk_live_aaa_tenant_key")
    make_tenant(db, name="b", plan=plans[PLAN_FREE], api_key="sk_live_bbb_tenant_key")
    db.commit()
    client.post(
        "/v1/generate",
        json={"prompt": "only a"},
        headers={"X-API-Key": "sk_live_aaa_tenant_key", "Idempotency-Key": "iso-a"},
    )
    a = client.get("/v1/usage", headers={"X-API-Key": "sk_live_aaa_tenant_key"}).json()
    b = client.get("/v1/usage", headers={"X-API-Key": "sk_live_bbb_tenant_key"}).json()
    assert a["api_calls"]["used"] == 1
    assert b["api_calls"]["used"] == 0
    assert a["tenant_id"] != b["tenant_id"]


def test_bad_input_is_422(client: TestClient, db: Session):
    plans = make_plans(db)
    make_tenant(db, name="v", plan=plans[PLAN_FREE], api_key=KEY)
    db.commit()
    res = client.post(
        "/v1/generate",
        json={"prompt": "x", "input_tokens": -1},
        headers={"X-API-Key": KEY, "Idempotency-Key": "bad-input"},
    )
    assert res.status_code == 422
    assert res.json()["code"] == "validation_error"


def test_unknown_api_key_is_401(client: TestClient, db: Session):
    make_plans(db)
    db.commit()
    res = client.get("/v1/usage", headers={"X-API-Key": "nope"})
    assert res.status_code == 401
