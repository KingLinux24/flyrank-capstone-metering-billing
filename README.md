# Usage Metering & Billing Engine

Backend service for **how much this tenant used, what it costs, and whether they hit the plan limit**. Built for the FlyRank internship capstone: idempotent metering, honest quota status codes, integer money math, and Stripe **test mode** only.

Suggested public repo name: `flyrank-capstone-metering-billing`.

## What it does

- Records one usage event per billable `POST /v1/generate`, even if the client retries with the same `Idempotency-Key`
- Enforces Free / Pro monthly quotas (**429** over quota, **402** if payment/upgrade is required)
- Prices API calls and AI tokens with pinned constants (cached input cheaper; reasoning billed as output)
- Mirrors Stripe subscriptions through signature-verified, deduplicated webhooks
- Rolls up usage in a background worker (retries + failure alert row)

Token counts are **simulated**. There is no model API key and no live payments.

## Architecture

```
Client ──► POST /v1/generate
            └─ MeterService.record(tenant, qty, idempotencyKey)
               ├─ duplicate key? → original result (no new event)
               ├─ store usage_event
               └─ quota check → 200 or 429 / 402

GET /v1/usage ── rollup(usage_events) → { used, limit, cost }

Stripe Checkout (test mode) ── subscription created
Stripe ─ signed webhook ─► POST /webhooks/stripe
         ├─ verify signature (forged → 400)
         ├─ deduplicate event id (replay → ignored)
         └─ update tenant plan / status
```

Layers: `app/api` (HTTP) → `app/services` (rules) → `app/models` (Postgres). Pricing lives in `app/pricing.py` and is covered by pinned tests.

## Plans

| Plan | API calls / month | AI tokens / month |
|------|-------------------|-------------------|
| Free | 1,000 | 100,000 |
| Pro  | 100,000 | 10,000,000 |

Quota rule: a request is allowed if `current + requested <= limit`. At **999/1000**, the next 1-call request succeeds (usage becomes 1000). The request after that is **429**.

## Setup

Requires Docker (Postgres + API + worker). No credit card.

```bash
cp .env.example .env   # optional; Compose runs without Stripe keys
docker compose up --build
```

Wait until the API is healthy, then:

```bash
curl -s http://localhost:8000/health
```

Seed runs automatically on API start. Demo keys (safe placeholders, not Stripe secrets):

| Tenant | Situation | `X-API-Key` |
|--------|-----------|-------------|
| Acme Free | 999/1000 API calls | `sk_live_demo_free_tenant_key_001` |
| Acme Pro | high limits | `sk_live_demo_pro_tenant_key_001` |
| Acme Unpaid | `past_due` → 402 | `sk_live_demo_unpaid_tenant_key_01` |

Re-seed:

```bash
docker compose exec api python -m app.seed
```

Tests (inside the API container, or locally with `pip install -r requirements.txt`):

```bash
docker compose exec api pytest -q
```

Local tests use in-memory SQLite; they do not need Docker or Stripe.

## API

Billable generate (dummy response, real metering):

```bash
curl -s -X POST http://localhost:8000/v1/generate \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: sk_live_demo_free_tenant_key_001' \
  -H 'Idempotency-Key: demo-retry-1' \
  -d '{"prompt":"hello","input_tokens":10,"cached_input_tokens":5,"output_tokens":20,"reasoning_tokens":8}'
```

Replay the same key — usage must not increase:

```bash
curl -s -X POST http://localhost:8000/v1/generate \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: sk_live_demo_free_tenant_key_001' \
  -H 'Idempotency-Key: demo-retry-1' \
  -d '{"prompt":"hello","input_tokens":10,"cached_input_tokens":5,"output_tokens":20,"reasoning_tokens":8}'
```

Usage rollup:

```bash
curl -s http://localhost:8000/v1/usage \
  -H 'X-API-Key: sk_live_demo_free_tenant_key_001'
```

Over-quota (after the seeded tenant takes one more successful call):

```bash
curl -s -i -X POST http://localhost:8000/v1/generate \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: sk_live_demo_free_tenant_key_001' \
  -H 'Idempotency-Key: demo-over-quota' \
  -d '{"prompt":"one more"}'
```

Payment required:

```bash
curl -s -i -X POST http://localhost:8000/v1/generate \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: sk_live_demo_unpaid_tenant_key_01' \
  -H 'Idempotency-Key: demo-unpaid' \
  -d '{"prompt":"hello"}'
```

### Stripe test mode (optional, still $0)

1. Create a Stripe account, stay in **test mode**, copy `sk_test_…`.
2. Create a recurring Price for Pro; put its id in `STRIPE_PRO_PRICE_ID`.
3. Install [Stripe CLI](https://stripe.com/docs/stripe-cli), then:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Put the printed `whsec_…` in `.env` as `STRIPE_WEBHOOK_SECRET` and restart the API.

4. Checkout:

```bash
curl -s -X POST http://localhost:8000/v1/checkout \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: sk_live_demo_free_tenant_key_001' \
  -d '{}'
```

Open `checkout_url`, pay with `4242 4242 4242 4242`, any future expiry, any CVC. The webhook should flip the tenant Free → Pro. Confirm with `GET /v1/usage`.

Replay / forge checks:

```bash
stripe trigger checkout.session.completed
curl -s -i -X POST http://localhost:8000/webhooks/stripe \
  -H 'stripe-signature: t=1,v1=deadbeef' \
  -d '{"id":"evt_forged"}'
```

Forged signatures must return **400** and must not change plans.

## Money math

Costs are integers (`cost_micros`, 1 USD = 1_000_000). Token categories are priced separately using the constants in `app/pricing.py`. Reasoning tokens use the **output** rate. Cached input uses a cheaper rate. Tests in `tests/test_pricing.py` pin the million-token fixtures.

## Limitations

- Stripe Checkout is skipped unless test keys are configured (`POST /v1/checkout` returns 503).
- No invoices, proration, or overage billing (stretch, not built).
- Demo API keys are public placeholders for local seed data; they are not Stripe secrets. Rotate them if you expose a deployed instance.
- Webhook processing is synchronous; a missed event is not auto-reconciled against Stripe (that is a stretch goal).
- Monthly period is calendar-month start on seed; Checkout does not implement Stripe proration.

## Project layout

| Path | Role |
|------|------|
| `app/api/` | HTTP boundary, validation, status codes |
| `app/services/` | Metering, quotas, usage rollup, Stripe sync |
| `app/pricing.py` | Pinned rates |
| `alembic/` | Schema migrations |
| `app/jobs/rollup.py` | Background aggregation + alerts |
| `tests/` | Idempotency, quota boundaries, pricing, webhooks |
