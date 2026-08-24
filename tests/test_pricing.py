from app.pricing import (
    CACHED_INPUT_PER_MILLION_MICROS,
    INPUT_PER_MILLION_MICROS,
    OUTPUT_PER_MILLION_MICROS,
    TokenUsage,
    token_cost_micros,
)


def test_fresh_input_million_tokens_is_three_dollars():
    cost = token_cost_micros(TokenUsage(input_tokens=1_000_000))
    assert cost == INPUT_PER_MILLION_MICROS
    assert cost == 3_000_000


def test_cached_input_is_cheaper_than_fresh_input():
    fresh = token_cost_micros(TokenUsage(input_tokens=1_000_000))
    cached = token_cost_micros(TokenUsage(cached_input_tokens=1_000_000))
    assert cached == CACHED_INPUT_PER_MILLION_MICROS
    assert cached == 300_000
    assert cached * 10 == fresh


def test_reasoning_tokens_billed_as_output():
    output = token_cost_micros(TokenUsage(output_tokens=1_000_000))
    reasoning = token_cost_micros(TokenUsage(reasoning_tokens=1_000_000))
    assert output == OUTPUT_PER_MILLION_MICROS
    assert reasoning == output


def test_categories_are_not_summed_then_priced_as_one_rate():
    usage = TokenUsage(
        input_tokens=1_000_000,
        cached_input_tokens=1_000_000,
        output_tokens=1_000_000,
        reasoning_tokens=1_000_000,
    )
    # Wrong: price (1M+1M+1M+1M) at the input rate.
    naive_as_input = 4 * INPUT_PER_MILLION_MICROS
    correct = (
        INPUT_PER_MILLION_MICROS
        + CACHED_INPUT_PER_MILLION_MICROS
        + OUTPUT_PER_MILLION_MICROS
        + OUTPUT_PER_MILLION_MICROS
    )
    assert token_cost_micros(usage) == correct
    assert token_cost_micros(usage) != naive_as_input
    assert token_cost_micros(usage) == 3_000_000 + 300_000 + 15_000_000 + 15_000_000
