import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services.stripe_sync import handle_stripe_event

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    if not settings.stripe_webhook_secret or settings.stripe_webhook_secret.startswith("whsec_replace"):
        raise HTTPException(status_code=503, detail="STRIPE_WEBHOOK_SECRET is not configured")
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature") from exc
    except Exception as exc:  # stripe.SignatureVerificationError across SDK versions
        if "Signature" not in type(exc).__name__ and "signature" not in str(exc).lower():
            raise
        raise HTTPException(status_code=400, detail="Invalid Stripe signature") from exc
    payload_dict = event if isinstance(event, dict) else event.to_dict()
    result = handle_stripe_event(db, payload_dict)
    return {"received": True, "status": result}
