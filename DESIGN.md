# Design: Usage Metering & Billing Engine

**Problem.** A multi-tenant SaaS backend must answer: how much has this tenant used, what does it cost, and have they hit their plan limit — correctly under retries and webhook replays.

**Data model.** `plans` (free/pro + monthly quotas) · `tenants` (API key hash only) · `subscriptions` (status, Stripe ids, billing period) · `usage_events` (unique `(tenant_id, idempotency_key)`, token categories, integer `cost_micros`) · `processed_stripe_events` · `usage_rollups` (background job). Money is never a float: 1 USD = 1_000_000 micros.

**API.** `POST /v1/generate` (dummy billable action; requires `Idempotency-Key`) · `GET /v1/usage` · `POST /v1/checkout` · `POST /webhooks/stripe` · `GET /health`. Auth is `X-API-Key`. Tenants only see their own rows.

**Layers.** HTTP routers validate and map errors (`app/api`) → services (`meter`, `quota`, `billing`, `stripe_sync`) → SQLAlchemy models. Stripe SDK stays behind `stripe_sync`. Swap Postgres for SQLite in tests without touching quota math.

**Idempotency.** Lock the tenant row, insert the usage event, treat unique-key conflicts as a replay of the stored JSON result. Retries return the original event id and cost; they do not insert a second row.

**Quotas.** Before insert: `used + requested > limit` → **429** with `Retry-After` and a metric breakdown. Inactive/past_due/canceled subscription → **402**. Boundary: 999/1000 is allowed; 1000/1000 then another call is 429.

**Non-goal.** No live Stripe, no invoicing, no proration, no overage billing, no real model calls. Tokens are numbers the client sends so pricing rules can be tested.

**Background job.** `app.jobs.rollup` aggregates per-tenant period usage off the request path, retries three times, and writes `job_alerts` on failure.
