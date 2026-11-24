## Background
Orders currently have no shipping cost. Add a shipping fee that depends on the order subtotal in tiers (the larger the
subtotal, the cheaper the shipping), and let two independent adjustments stack on top of the tier fee: a member discount
and an express surcharge. The combined result is limited by a maximum fee. Shipping is not taxed.

## Requirements
1. Add `shipping_cents(subtotal_cents, express=False, member=False)` to `shop/pricing.py` and export it from `shop`.
2. The base fee depends on the subtotal tier. A subtotal exactly on a tier edge belongs to the higher (cheaper) tier:
   - subtotal below 5000 cents: 899 cents
   - subtotal from 5000 up to but not including 10000 cents: 499 cents
   - subtotal of 10000 cents or more: 0 cents
3. If `member` is true, the base fee is halved, rounded half up to a whole cent (for example 899 becomes 450 and 499
   becomes 250).
4. If `express` is true, a flat surcharge of 600 cents is added. The surcharge is added AFTER the member discount, and it is
   added even when the base fee is 0.
5. The final fee is never more than 1200 cents. The cap is applied last, after both adjustments.
6. A negative `subtotal_cents` raises `ValueError("subtotal must be non-negative")`.
7. `Order` gets a new field `shipping_cents: int = 0` (last field, with the default, so existing construction keeps working).
8. `checkout(cart, order_id, shipping=None, member=False)` gains two optional parameters. `shipping` is `None`
   (no shipping, behaviour exactly as before), `"standard"` or `"express"`. When it is `"standard"` or `"express"`, the
   order's `shipping_cents` is `shipping_cents(subtotal, express=(shipping == "express"), member=member)` where subtotal is
   the cart subtotal before tax. `member` is ignored when `shipping` is `None`.
9. The order total is `subtotal_cents + tax_cents + shipping_cents`. Tax is still computed from the subtotal only.
10. Any other value for `shipping` raises `ValueError("unknown shipping method: <value>")` and leaves the cart untouched.
    An empty cart still raises `ValueError("cart is empty")` as before.

## Public interface
- `shop.pricing.shipping_cents(subtotal_cents: int, express: bool = False, member: bool = False) -> int`
  (also importable as `shop.shipping_cents`)
- `shop.checkout.Order.shipping_cents: int = 0`
- `shop.checkout.checkout(cart, order_id, shipping=None, member=False) -> Order`
- Errors: `ValueError("subtotal must be non-negative")`, `ValueError("unknown shipping method: <value>")`.

## Examples
- `shipping_cents(4999)` -> `899`; `shipping_cents(5000)` -> `499`; `shipping_cents(10000)` -> `0`.
- `shipping_cents(4000, member=True)` -> `450`.
- `shipping_cents(4000, express=True)` -> `1200` (899 + 600 = 1499, capped).
- `shipping_cents(4000, express=True, member=True)` -> `1050` (450 + 600, under the cap).
- `shipping_cents(10000, express=True)` -> `600`.
- A cart of 5 notebooks (1200 each, subtotal 6000) checked out with `shipping="standard"` gives tax 600, shipping 499 and
  total 7099.
