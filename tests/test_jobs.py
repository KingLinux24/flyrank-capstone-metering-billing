from app.config import get_settings
from app.db import configure_engine, get_session_factory
from app.jobs.rollup import run_once, run_with_retries
from app.models import Base, JobAlert, UsageRollup
from app.pricing import PLAN_FREE
from tests.helpers import make_plans, make_tenant


def test_rollup_writes_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path}/job.db")
    get_settings.cache_clear()
    engine = configure_engine(f"sqlite+pysqlite:///{tmp_path}/job.db")
    Base.metadata.create_all(engine)
    db = get_session_factory()()
    plans = make_plans(db)
    make_tenant(db, name="job", plan=plans[PLAN_FREE], api_key="sk_live_job_key_zzzz")
    db.commit()
    n = run_once(db)
    assert n == 1
    assert db.query(UsageRollup).count() == 1
    db.close()


def test_rollup_alerts_after_retries(monkeypatch):
    from app.jobs import rollup as rollup_mod

    def boom(_db):
        raise RuntimeError("db down")

    monkeypatch.setattr(rollup_mod, "run_once", boom)
    monkeypatch.setattr(rollup_mod.time, "sleep", lambda _s: None)

    engine = configure_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    run_with_retries()
    db = get_session_factory()()
    alerts = db.query(JobAlert).all()
    assert len(alerts) == 1
    assert "db down" in alerts[0].message
    db.close()
