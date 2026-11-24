## Background

The shop library can total a cart but has no way to apply promotions. Two independent promotions must now be able
to apply to the same cart: a per-category percentage discount and a flat-amount coupon. They have to be combined
with a fixed order of application and an overall cap on how much of the subtotal can be discounted.

## Requirements

1. Add a new module `shop/promotions.py` with the function `stacked_discount_cents` (see "Public interface"). All
   amounts are integer cents.
2. Category discount (applied first): `category_percents` maps a product category name to a whole percentage. For
   every cart line whose product category is a key of the mapping, the line discount is
   `unit price * quantity * percent // 100` (integer floor division, per line). The category discount is the sum of
   the line discounts. Categories not present in the mapping are unaffected, and keys that match no product in the
   cart are ignored.
3. Coupon (applied second): `coupon_cents` is a flat amount taken off what is left after the category discount. The
   coupon that is actually applied is `min(coupon_cents, subtotal - category_discount)`, so the coupon can never
   push the total discount past the subtotal.
4. Cap: the combined discount (category discount plus applied coupon) can never exceed
   `subtotal * cap_percent // 100` (integer floor division). When the cap is exceeded the result is exactly that cap
   value.
5. The function returns the final combined discount in cents. With an empty cart it returns 0. When only one of the
   two promotions is supplied (no `category_percents`, or `coupon_cents` of 0) only that promotion contributes.
6. Validation, raising `ValueError` with exactly these messages, checked before any calculation (and also for an
   empty cart):
   - any percentage in `category_percents` that is below 0 or above 100: `"percent must be between 0 and 100"`
   - `coupon_cents` below 0: `"coupon must not be negative"`
   - `cap_percent` below 0 or above 100: `"cap_percent must be between 0 and 100"`
7. Also add `discounted_subtotal_cents`, which takes the same arguments and returns the cart subtotal minus the
   value of `stacked_discount_cents`.
8. Both functions must be importable from the package root: `from shop import stacked_discount_cents,
   discounted_subtotal_cents`. The cart itself must not be modified.

## Public interface

In `shop/promotions.py` (and re-exported from `shop`):

```
stacked_discount_cents(cart: Cart, category_percents: dict[str, int] | None = None,
                       coupon_cents: int = 0, cap_percent: int = 50) -> int
discounted_subtotal_cents(cart: Cart, category_percents: dict[str, int] | None = None,
                          coupon_cents: int = 0, cap_percent: int = 50) -> int
```

Errors: `ValueError("percent must be between 0 and 100")`, `ValueError("coupon must not be negative")`,
`ValueError("cap_percent must be between 0 and 100")`.

## Examples

With catalog PEN (150, "office"), BOOK (1200, "office"), MUG (800, "kitchen") and a cart of 2 BOOK and 1 MUG
(subtotal 3200):

- `stacked_discount_cents(cart, {"office": 10}, 500)` returns `740` (240 category + 500 coupon, under the cap of 1600).
- `stacked_discount_cents(cart, {"office": 50}, 1000)` returns `1600`: 1200 + 1000 = 2200 is above the cap of
  50 percent of 3200.
- `stacked_discount_cents(cart, {"office": 50}, 1000, cap_percent=80)` returns `2200`.
- `discounted_subtotal_cents(cart, {"office": 10}, 500)` returns `2460`.
