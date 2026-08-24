from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.checkout import router as checkout_router
from app.api.generate import router as generate_router
from app.api.usage import router as usage_router
from app.api.webhooks import router as webhook_router
from app.api.health import router as health_router
from app.db import configure_engine, get_engine
from app import models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Skip engine configuration in test mode
    import os
    if os.getenv("DATABASE_URL", "").startswith("sqlite"):
        # Tests handle their own engine setup
        yield
        return
    
    from app.db import engine
    if engine is None:
        configure_engine()
        get_engine()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Usage Metering & Billing Engine",
        version="1.0.0",
        description="Tenant usage metering, quotas, integer money math, Stripe test-mode subscriptions.",
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(generate_router)
    application.include_router(usage_router)
    application.include_router(checkout_router)
    application.include_router(webhook_router)

    @application.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": "Invalid input", "code": "validation_error", "detail": exc.errors()},
        )

    return application


app = create_app()
