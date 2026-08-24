from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_tenant
from app.models import Tenant
from app.pricing import TokenUsage
from app.schemas import GenerateRequest, GenerateResponse
from app.services.meter import PaymentRequired, QuotaExceeded, record_generate

router = APIRouter(prefix="/v1", tags=["generate"])


@router.post("/generate", response_model=GenerateResponse)
def generate(
    body: GenerateRequest,
    response: Response,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(require_tenant),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required",
        )
    tokens = TokenUsage(
        input_tokens=body.input_tokens,
        cached_input_tokens=body.cached_input_tokens,
        output_tokens=body.output_tokens,
        reasoning_tokens=body.reasoning_tokens,
    )
    try:
        result = record_generate(
            db,
            tenant_id=tenant.id,
            idempotency_key=idempotency_key,
            prompt=body.prompt,
            tokens=tokens,
        )
    except PaymentRequired as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Payment required",
                "code": "payment_required",
                "detail": {
                    "reason": "subscription_inactive",
                    "subscription_status": exc.status,
                    "message": "Your plan is not active. Upgrade or update payment to continue.",
                },
            },
        ) from exc
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Quota exceeded",
                "code": "quota_exceeded",
                "detail": {
                    "metric": exc.metric,
                    "used": exc.used,
                    "limit": exc.limit,
                    "requested": exc.requested,
                    "message": (
                        f"This request would exceed your {exc.metric} quota "
                        f"({exc.used} used of {exc.limit}; requested {exc.requested})."
                    ),
                },
            },
            headers={"Retry-After": "3600"},
        ) from exc
    return result
