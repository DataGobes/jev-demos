"""Jev pricing.

https://docs.typesafe.ai/models -- charged per input token; output tokens are free.
"""

PRICE_PER_MTOK_USD = 0.042


def cost_usd(tokens: int) -> float:
    return tokens * PRICE_PER_MTOK_USD / 1_000_000
