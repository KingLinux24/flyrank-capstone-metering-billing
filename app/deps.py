import hashlib
import hmac
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Tenant


def hash_api_key(raw: str) -> str:
    secret = get_settings().app_secret_key.encode()
    return hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()


def generate_api_key() -> str:
    return "sk_live_" + secrets.token_urlsafe(24)


def require_tenant(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Tenant:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    tenant = db.query(Tenant).filter(Tenant.api_key_hash == hash_api_key(x_api_key)).one_or_none()
    if tenant is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return tenant
