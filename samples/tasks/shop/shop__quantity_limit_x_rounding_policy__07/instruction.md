## Background

The shop library lets a `Cart` hold any quantity of any product, and `checkout` computes tax once on the whole subtotal, rounding half up. The business now wants two related changes:

* A cart can be configured with a hard cap on how many units of a single SKU it may hold.
* Checkout can optionally compute tax per unit using banker's rounding (round half to even), then multiply by the quantity of each line. Because the cap limits how many units of a SKU a cart holds, only quantities that were actually accepted into the cart contribute to the per-unit tax.

Existing behaviour (no cap, tax on the subtotal rounded half up) must remain the default.

## Requirements

1. `Cart` accepts an optional `max_per_sku` argument (default `None`, meaning no cap). If it is given and is not a positive integer (zero or negative), the constructor raises `ValueError`.
2. The cap applies per SKU, to the total quantity of that SKU in the cart (existing quantity plus the quantity being added). Different SKUs have independent caps of the same size.
3. `Cart.add(sku, quantity)` raises `QuantityLimitError` when the resulting quantity of that SKU would exceed `max_per_sku`. A resulting quantity exactly equal to the cap is allowed.
4. A rejected `add` leaves the cart completely unchanged (no partial add: if 1 unit is in the cart, the cap is 2 and `add(sku, 2)` is attempted, the cart still holds exactly 1 unit).
5. `QuantityLimitError` is a subclass of `ValueError`. Its message is exactly `limit of <max_per_sku> per item exceeded for <sku>`.
6. Existing validation keeps priority over the cap: a non-positive quantity raises a plain `ValueError` (not `QuantityLimitError`), and an unknown SKU raises `KeyError`, even when the requested quantity would also exceed the cap.
7. `Cart.remaining(sku)` returns how many more units of `sku` can be added: `max_per_sku - quantity(sku)` when a cap is set, or `None` when no cap is set.
8. A new function `tax_cents_half_even(amount_cents, rate_percent=TAX_RATE_PERCENT)` in `shop.pricing` returns the tax on a non-negative amount, rounded to the nearest cent, with exact halves rounded to the nearest EVEN number of cents (for example 0.5 cents becomes 0, 1.5 becomes 2, 2.5 becomes 2, 3.5 becomes 4). The existing `tax_cents` is unchanged (half up).
9. `checkout(cart, order_id, per_unit_tax=False)` accepts a new keyword argument. When `False` (default) behaviour is exactly as before. When `True`, the order's `tax_cents` is the sum over cart lines of `tax_cents_half_even(unit_price_cents) * quantity`, `total_cents` is `subtotal_cents + tax_cents`, and `subtotal_cents` and `lines` are unchanged. The cart is emptied afterwards in both modes, and an empty cart still raises `ValueError("cart is empty")`.
10. `QuantityLimitError` and `tax_cents_half_even` are importable from the top-level `shop` package as well as from their modules.

## Public interface

* `shop.cart.QuantityLimitError(ValueError)` (also `shop.QuantityLimitError`).
* `shop.cart.Cart(catalog, max_per_sku=None)`; `Cart.add(sku, quantity=1)`; `Cart.remaining(sku) -> int | None`.
* `shop.pricing.tax_cents_half_even(amount_cents, rate_percent=TAX_RATE_PERCENT) -> int` (also `shop.tax_cents_half_even`).
* `shop.checkout.checkout(cart, order_id, per_unit_tax=False) -> Order`.
* Error message for a rejected add: `limit of 2 per item exceeded for PEN` (for a cap of 2 and SKU `PEN`).

## Examples

```python
from shop import Cart, Catalog, Product, QuantityLimitError, checkout, tax_cents_half_even

catalog = Catalog([Product("B", "Bolt", 25)])
cart = Cart(catalog, max_per_sku=2)
cart.add("B", 2)
cart.remaining("B")          # 0
cart.add("B")                # raises QuantityLimitError("limit of 2 per item exceeded for B")

tax_cents_half_even(25)      # 2   (2.5 cents rounds to the even value 2)
tax_cents_half_even(35)      # 4   (3.5 cents rounds to the even value 4)
tax_cents_half_even(5)       # 0   (0.5 cents rounds to 0)

order = checkout(cart, "o1", per_unit_tax=True)
order.subtotal_cents         # 50
order.tax_cents              # 4   (2 units * 2 cents), whereas the default mode gives 5
order.total_cents            # 54
```
