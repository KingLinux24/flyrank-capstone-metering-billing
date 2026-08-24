from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_tenant
from app.models import Tenant
from app.schemas import CheckoutRequest, CheckoutResponse
from app.services.stripe_sync import create_checkout_session

router = APIRouter(prefix="/v1", tags=["checkout"])


@router.post("/checkout", response_model=CheckoutResponse)
def checkout(
    body: CheckoutRequest,
    tenant: Tenant = Depends(require_tenant),
    db: Session = Depends(get_db),
):
    del db
    try:
        return create_checkout_session(tenant, body.success_url, body.cancel_url)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/checkout/success")
def checkout_success(session_id: str | None = None):
    return {"ok": True, "session_id": session_id, "message": "Checkout completed in Stripe test mode."}


@router.get("/checkout/cancel")
def checkout_cancel():
    return {"ok": False, "message": "Checkout canceled."}
