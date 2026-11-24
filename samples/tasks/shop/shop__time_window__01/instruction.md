## Background
The `shop` library can turn a cart into an `Order` with `checkout(cart, order_id)`, but it has no notion of promotions. Marketing wants a percentage-off promotion that is only valid inside a time window (for example a weekend sale). To keep behaviour deterministic, the current time must never be read from the system clock: the caller passes it in.

## Requirements
1. Add a new module `shop/promotions.py` with a frozen dataclass `Promotion` that has the fields `name: str`, `percent_off: int`, `start: datetime`, `end: datetime` and `category: str | None = None` (in that order).
2. `Promotion.is_active(now)` returns `True` when `start <= now < end` (start inclusive, end exclusive) and `False` otherwise.
3. Creating a `Promotion` with `percent_off` below 1 or above 100 raises `ValueError("percent_off must be between 1 and 100")`.
4. Creating a `Promotion` with `end` less than or equal to `start` raises `ValueError("end must be after start")`.
5. `checkout` accepts two new optional parameters, `promotion=None` and `now=None`, after `order_id`. With no promotion, behaviour is exactly as before and `Order.discount_cents` is `0`.
6. `Order` gets a new last field `discount_cents: int = 0`. `Order.subtotal_cents` remains the full pre-discount subtotal.
7. When a promotion is given and is active at `now`, the discount is computed from the eligible lines only: the lines whose product category equals `promotion.category`, or all lines when `promotion.category` is `None`. `discount_cents = eligible_subtotal_cents * percent_off // 100` (rounded down).
8. Tax is computed with the existing `tax_cents` on `subtotal_cents - discount_cents`, and `total_cents = subtotal_cents - discount_cents + tax_cents`.
9. When a promotion is given but is not active at `now`, or no line is eligible, the discount is `0` and the order is identical to one created without a promotion.
10. When a promotion is given and `now` is `None`, `checkout` raises `ValueError("now is required when a promotion is given")`, and the cart is left untouched (not emptied). The existing empty-cart check still applies first.
11. `Promotion` is also exported from the `shop` package (`from shop import Promotion` works).

## Public interface
- `shop.promotions.Promotion(name, percent_off, start, end, category=None)`: frozen dataclass; `start` and `end` are `datetime.datetime` values.
- `Promotion.is_active(now: datetime) -> bool`
- `shop.checkout.checkout(cart, order_id, promotion=None, now=None) -> Order`
- `shop.checkout.Order.discount_cents: int` (default `0`, last field)
- Errors: `ValueError` with the exact messages given above.

## Examples
```python
from datetime import datetime
from shop import Promotion, checkout

promo = Promotion("Sale", 10, datetime(2025, 1, 1), datetime(2025, 1, 2), category="office")
# cart: 1 BOOK (1200, office) + 1 MUG (800, kitchen)
order = checkout(cart, "A1", promo, datetime(2025, 1, 1, 12, 0))
# subtotal 2000, discount 120, tax 188, total 2068
order = checkout(cart, "A2", promo, datetime(2025, 1, 2))   # end is exclusive -> discount 0
```
