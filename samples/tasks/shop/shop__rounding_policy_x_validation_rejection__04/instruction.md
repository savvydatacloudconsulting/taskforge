## Background
Tax is currently always rounded half up and always computed once on the whole cart subtotal. Merchants need to pick the rounding rule, and some need tax computed per cart line (each line rounded on its own, then summed). Because a bad rounding setting must never silently change money, invalid settings have to be rejected before anything is charged or the cart is emptied.

## Requirements
1. `tax_cents` accepts a new keyword argument `rounding` (default `"half_up"`) selecting how the exact tax `amount_cents * rate_percent / 100` is rounded to a whole cent. The supported modes are:
   - `"half_up"`: nearest cent; an exact half rounds up (this is the existing behaviour).
   - `"half_even"`: nearest cent; an exact half rounds to the even cent (banker's rounding).
   - `"floor"`: always round down.
   - `"ceil"`: always round up (an exact whole-cent result is unchanged).
2. Calling `tax_cents` without `rounding` must return exactly what it returned before.
3. `tax_cents` raises `ValueError("unknown rounding mode: <value>")` if `rounding` is not one of the four modes, where `<value>` is the given value formatted with `str`.
4. `tax_cents` raises `ValueError("rate_percent must be between 0 and 100")` if `rate_percent` is below 0 or above 100 (0 and 100 themselves are valid). If both `rounding` and `rate_percent` are invalid, the rounding error is the one raised.
5. `checkout` accepts new keyword arguments `rounding` (default `"half_up"`) and `per_line` (default `False`).
6. With `per_line=False` the order tax is `tax_cents(subtotal, rounding=rounding)`. With `per_line=True` the order tax is the sum, over the cart lines, of `tax_cents(unit_price * quantity, rounding=rounding)`. `subtotal_cents` and `total_cents` (subtotal plus tax) follow as before.
7. `checkout` raises `ValueError("unknown rounding mode: <value>")` for an unsupported `rounding`, and `TypeError("per_line must be a bool")` if `per_line` is not a `bool`. These checks happen before anything else, so they are raised even when the cart is empty (the rounding check is made first), and in every rejected case the cart is left untouched.
8. A valid `checkout` call still empties the cart afterwards, and an empty cart with valid settings still raises `ValueError("cart is empty")`.

## Public interface
- `shop.pricing.ROUNDING_MODES`: tuple `("half_up", "half_even", "floor", "ceil")`.
- `shop.pricing.tax_cents(amount_cents, rate_percent=TAX_RATE_PERCENT, rounding="half_up") -> int`
- `shop.checkout.checkout(cart, order_id, rounding="half_up", per_line=False) -> Order`
- Errors: `ValueError("unknown rounding mode: X")`, `ValueError("rate_percent must be between 0 and 100")`, `TypeError("per_line must be a bool")`.

## Examples
At the default 10% rate, tax on 5 cents is exactly 0.5 cents: `half_up` gives 1, `half_even` gives 0, `floor` gives 0, `ceil` gives 1. Tax on 15 cents is exactly 1.5: `half_up` 2, `half_even` 2, `floor` 1, `ceil` 2. Tax on 25 cents (2.5): `half_up` 3, `half_even` 2. Tax on 1 cent (0.1): `half_up` 0, `ceil` 1. Tax on 0 cents is 0 in every mode.

`tax_cents(3, 50, rounding="half_even")` is 2 (1.5 rounds to the even 2).

A cart holding one 5-cent item and one 1-cent item, checked out with `rounding="ceil"`: with `per_line=False` the subtotal is 6, tax is `ceil(0.6)` = 1; with `per_line=True` tax is `ceil(0.5) + ceil(0.1)` = 2.

`checkout(cart, "o1", rounding="banker")` raises `ValueError("unknown rounding mode: banker")` and the cart still holds its items.
