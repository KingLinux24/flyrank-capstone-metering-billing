from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import UsageEvent
from app.pricing import PLAN_FREE, SUB_ACTIVE
from tests.helpers import make_plans, make_tenant

API_KEY = "sk_live_test_tenant_aaaaaaa"
HEADERS = {"X-API-Key": API_KEY, "Idempotency-Key": "idem-key-0001"}


def _setup(db: Session):
    plans = make_plans(db)
    tenant = make_tenant(db, name="T", plan=plans[PLAN_FREE], api_key=API_KEY, status=SUB_ACTIVE)
    db.commit()
    return tenant


def test_retry_same_idempotency_key_does_not_double_count(client: TestClient, db: Session):
    _setup(db)
    body = {"prompt": "hello", "input_tokens": 10, "output_tokens": 20}
    first = client.post("/v1/generate", json=body, headers=HEADERS)
    second = client.post("/v1/generate", json=body, headers=HEADERS)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["replayed"] is True
    assert first.json()["cost_micros"] == second.json()["cost_micros"]
    count = db.query(UsageEvent).filter(UsageEvent.tenant_id == first.json()["tenant_id"]).count()
    assert count == 1


def test_different_keys_create_two_events(client: TestClient, db: Session):
    _setup(db)
    body = {"prompt": "hello", "output_tokens": 1}
    a = client.post("/v1/generate", json=body, headers={**HEADERS, "Idempotency-Key": "key-aaaaaa"})
    b = client.post("/v1/generate", json=body, headers={**HEADERS, "Idempotency-Key": "key-bbbbbb"})
    assert a.status_code == 200
    assert b.status_code == 200
    assert a.json()["id"] != b.json()["id"]
    assert db.query(UsageEvent).count() == 2


def test_missing_idempotency_key_is_400(client: TestClient, db: Session):
    _setup(db)
    res = client.post("/v1/generate", json={"prompt": "x"}, headers={"X-API-Key": API_KEY})
    assert res.status_code == 400
