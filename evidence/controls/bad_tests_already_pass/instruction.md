## Background
Customers can currently add any quantity of a product to a cart.

## Requirements
1. A single product line in a cart may never hold more than 10 units.
2. `Cart.add` raises `ValueError` whose message contains `limit of 10` when an add would push a line above 10.
3. A rejected add leaves the cart unchanged.
4. The limit applies per product, not to the cart as a whole.

## Public interface
- `shop.cart.MAX_PER_LINE` (int, value `10`)
- `Cart.add(sku, quantity=1)` raises `ValueError("limit of 10 per product exceeded")`

## Examples
`cart.add("PEN", 10)` works; a further `cart.add("PEN", 1)` raises `ValueError`.
