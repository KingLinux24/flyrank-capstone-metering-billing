from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_tenant
from app.models import Tenant
from app.schemas import UsageResponse
from app.services.billing import usage_snapshot

router = APIRouter(prefix="/v1", tags=["usage"])


@router.get("/usage", response_model=UsageResponse)
def get_usage(db: Session = Depends(get_db), tenant: Tenant = Depends(require_tenant)):
    return usage_snapshot(db, tenant)
