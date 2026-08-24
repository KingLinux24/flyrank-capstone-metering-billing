"""Background usage rollup: off the request path, with retries and a failure alert."""

from __future__ import annotations

import logging
import time
import traceback

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import configure_engine, get_session_factory
from app.models import JobAlert, Subscription, UsageRollup, utcnow
from app.services.quota import period_usage

log = logging.getLogger("rollup")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

JOB = "usage_rollup"
MAX_ATTEMPTS = 3


def alert(db: Session, message: str) -> None:
    db.add(JobAlert(job_name=JOB, message=message))
    db.commit()
    log.error("ALERT %s: %s", JOB, message)


def run_once(db: Session) -> int:
    count = 0
    subs = db.query(Subscription).all()
    now = utcnow()
    for sub in subs:
        usage = period_usage(db, sub.tenant_id, sub.period_start)
        row = (
            db.query(UsageRollup)
            .filter(UsageRollup.tenant_id == sub.tenant_id, UsageRollup.period_start == sub.period_start)
            .one_or_none()
        )
        if row is None:
            row = UsageRollup(
                tenant_id=sub.tenant_id,
                period_start=sub.period_start,
                api_calls=usage.api_calls,
                tokens=usage.tokens,
                cost_micros=usage.cost_micros,
                computed_at=now,
            )
            db.add(row)
        else:
            row.api_calls = usage.api_calls
            row.tokens = usage.tokens
            row.cost_micros = usage.cost_micros
            row.computed_at = now
        count += 1
    db.commit()
    return count


def run_with_retries() -> None:
    db = get_session_factory()()
    last_error = None
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                n = run_once(db)
                log.info("rollup ok tenants=%s attempt=%s", n, attempt)
                return
            except Exception as exc:  # noqa: BLE001 — job boundary
                last_error = exc
                log.exception("rollup failed attempt=%s", attempt)
                db.rollback()
                time.sleep(0.5 * attempt)
        alert(db, f"rollup failed after {MAX_ATTEMPTS} attempts: {last_error}\n{traceback.format_exc()}")
    finally:
        db.close()


def main() -> None:
    settings = get_settings()
    configure_engine(settings.database_url)
    log.info("usage rollup worker interval=%ss", settings.rollup_interval_seconds)
    while True:
        run_with_retries()
        time.sleep(settings.rollup_interval_seconds)


if __name__ == "__main__":
    main()
