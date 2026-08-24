"""Pinned pricing constants. Money is integer micro-units: 1 USD = 1_000_000 micros.

Token prices are micros per 1,000,000 tokens so category math stays integer.
Cached input is cheaper than fresh input. Reasoning tokens are billed as output.
Categories must not be summed then priced as a single rate.
"""

from dataclasses import dataclass

USD_MICROS = 1_000_000

# $0.01 per API call (included usage is still costed for the usage rollup).
API_CALL_MICROS = 10_000

# Modeled on typical chat-model price bands (Gemini-style cached + thinking).
INPUT_PER_MILLION_MICROS = 3_000_000  # $3.00 / 1M
CACHED_INPUT_PER_MILLION_MICROS = 300_000  # $0.30 / 1M
OUTPUT_PER_MILLION_MICROS = 15_000_000  # $15.00 / 1M

PLAN_FREE = "free"
PLAN_PRO = "pro"

FREE_API_CALLS_LIMIT = 1_000
FREE_TOKEN_LIMIT = 100_000
PRO_API_CALLS_LIMIT = 100_000
PRO_TOKEN_LIMIT = 10_000_000

SUB_ACTIVE = "active"
SUB_PAST_DUE = "past_due"
SUB_CANCELED = "canceled"
SUB_UNPAID = "unpaid"


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.cached_input_tokens
            + self.output_tokens
            + self.reasoning_tokens
        )


def token_cost_micros(usage: TokenUsage) -> int:
    """Price each token category separately, then sum.

    Reasoning tokens count as output. Cached input uses the cheaper rate.
    Integer division is applied once at the end of the weighted sum so
    per-million rates stay exact for million-token fixtures.
    """
    billed_output = usage.output_tokens + usage.reasoning_tokens
    weighted = (
        usage.input_tokens * INPUT_PER_MILLION_MICROS
        + usage.cached_input_tokens * CACHED_INPUT_PER_MILLION_MICROS
        + billed_output * OUTPUT_PER_MILLION_MICROS
    )
    return weighted // 1_000_000


def api_call_cost_micros(api_calls: int) -> int:
    return api_calls * API_CALL_MICROS


def event_cost_micros(api_calls: int, usage: TokenUsage) -> int:
    return api_call_cost_micros(api_calls) + token_cost_micros(usage)


def micros_to_usd_string(micros: int) -> str:
    dollars = micros // USD_MICROS
    remainder = micros % USD_MICROS
    return f"{dollars}.{remainder:06d}"
