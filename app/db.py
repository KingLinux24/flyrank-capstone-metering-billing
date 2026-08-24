from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine: Engine | None = None
SessionLocal: sessionmaker | None = None


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


def configure_engine(url: str | None = None) -> Engine:
    global engine, SessionLocal
    if engine is not None:
        return engine
    url = url or get_settings().database_url
    engine = create_engine(url, **_engine_kwargs(url))
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return engine


def get_engine() -> Engine:
    if engine is None:
        configure_engine()
    assert engine is not None
    return engine


def get_session_factory() -> sessionmaker:
    if SessionLocal is None:
        configure_engine()
    assert SessionLocal is not None
    return SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
