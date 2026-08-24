# EVIDENCE

One proof per Definition of Done box (§ 6). Command output below was captured from `pytest` on this repo. Re-run `pytest -q` to regenerate.

## Metering

**A billable action creates exactly one usage event, even under retries — deduplicated by idempotency key.**

Test: `tests/test_idempotency.py::test_retry_same_idempotency_key_does_not_double_count`

```
tests/test_idempotency.py::test_retry_same_idempotency_key_does_not_double_count PASSED
```

Second response sets `replayed: true` and `UsageEvent` count stays 1.

**A test proves double-counting cannot happen.**

Same test as above, plus `test_different_keys_create_two_events` (two keys → two rows).

## Quotas

**Usage is checked against the tenant's plan; requests over the limit are rejected.**

```
tests/test_quota.py::test_at_limit_next_request_is_429 PASSED
tests/test_quota.py::test_token_overage_is_429 PASSED
```

**Responses carry the correct status codes (429 / 402) and a message explaining why.**

- 429: `quota_exceeded` with metric/used/limit/requested and `Retry-After: 3600`
- 402: `tests/test_quota.py::test_past_due_is_402` → `payment_required`

Boundary honesty:

```
tests/test_quota.py::test_just_under_quota_is_allowed PASSED
```

999 used + 1 call → 200 and usage 1000. Next distinct key → 429.

## Cost calculation

**Monthly usage rolls up into a cost figure per tenant.**

```
tests/test_usage.py::test_usage_rollup_matches_pinned_cost PASSED
```

`GET /v1/usage` `cost_micros` matches `POST /v1/generate`.

**AI token pricing handles cached input, reasoning, and output correctly.**

```
tests/test_pricing.py::test_cached_input_is_cheaper_than_fresh_input PASSED
tests/test_pricing.py::test_reasoning_tokens_billed_as_output PASSED
tests/test_pricing.py::test_categories_are_not_summed_then_priced_as_one_rate PASSED
```

Pinned: 1M fresh input = 3_000_000 micros; 1M cached = 300_000; 1M output or reasoning = 15_000_000.

**Pricing constants are pinned and covered by tests.**

See `app/pricing.py` and `tests/test_pricing.py`.

## Stripe integration

**Subscription checkout works end-to-end in Stripe test mode.**

Automated stand-in (no network): `checkout.session.completed` flips Free → Pro:

```
tests/test_webhooks.py::test_checkout_completed_flips_free_to_pro PASSED
```

Live proof (when `sk_test` + CLI are configured): paste `stripe listen` log + `GET /v1/usage` showing `"plan": "pro"` here.

**Webhooks verify signatures, ignore duplicate events, and update tenant plan/status.**

```
tests/test_webhooks.py::test_forged_webhook_is_400 PASSED
tests/test_webhooks.py::test_duplicate_event_is_ignored PASSED
tests/test_webhooks.py::test_subscription_deleted_returns_to_free PASSED
```

## Data model, tests & documentation

**Database includes tenants, plans, subscriptions, and usage events; customer data isolated per tenant.**

Schema: `alembic/versions/0001_initial.py`. Isolation:

```
tests/test_usage.py::test_tenant_isolation PASSED
```

**Tests cover duplicate usage, quota boundaries, cost, invalid webhook, duplicate webhook.**

File set: `tests/test_idempotency.py`, `test_quota.py`, `test_pricing.py`, `test_webhooks.py`, plus `test_jobs.py` (background rollup retries/alerts) and `test_usage.py` (422 validation).

**README + architecture diagram + setup; submission-pack files present.**

`README.md`, `DESIGN.md`, `capstone.yaml`, `EVIDENCE.md`, `BUILDLOG.md`, `.env.example`.
