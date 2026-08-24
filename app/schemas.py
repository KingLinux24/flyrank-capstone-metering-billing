from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8_000)
    input_tokens: int = Field(default=0, ge=0, le=10_000_000)
    cached_input_tokens: int = Field(default=0, ge=0, le=10_000_000)
    output_tokens: int = Field(default=0, ge=0, le=10_000_000)
    reasoning_tokens: int = Field(default=0, ge=0, le=10_000_000)


class GenerateResponse(BaseModel):
    id: str
    tenant_id: str
    replayed: bool
    api_calls: int
    tokens: int
    cost_micros: int
    cost_usd: str
    usage: dict
    text: str


class UsageBreakdown(BaseModel):
    used: int
    limit: int
    remaining: int


class UsageResponse(BaseModel):
    tenant_id: str
    plan: str
    subscription_status: str
    period_start: str
    period_end: str
    api_calls: UsageBreakdown
    tokens: UsageBreakdown
    cost_micros: int
    cost_usd: str
    cost_detail: dict


class CheckoutRequest(BaseModel):
    success_url: str | None = None
    cancel_url: str | None = None


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class ErrorBody(BaseModel):
    error: str
    code: str
    detail: dict | None = None
