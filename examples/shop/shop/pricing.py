from __future__ import annotations

TAX_RATE_PERCENT = 10


def tax_cents(amount_cents: int, rate_percent: int = TAX_RATE_PERCENT) -> int:
    """Tax on an amount, rounded half up to the nearest cent."""
    return (amount_cents * rate_percent + 50) // 100


def format_money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100}.{cents % 100:02d}"
