## Background
`shop.checkout.checkout(cart, order_id)` currently accepts anything as the `order_id`: empty strings, whitespace-only strings, non-string values, or arbitrarily long identifiers. Bad identifiers end up inside `Order` objects and cause trouble downstream. Add input validation to `checkout` so that malformed order identifiers are rejected with precise errors before anything is changed.

## Requirements
1. If `order_id` is not an instance of `str`, `checkout` raises `TypeError` with the message `order_id must be a string`. (`None`, integers and `bytes` are all rejected.)
2. If `order_id` is a string that is empty or consists only of whitespace, `checkout` raises `ValueError` with the message `order_id must not be empty`.
3. If `order_id` contains any whitespace character (space, tab, newline, ...) anywhere and is not empty/whitespace-only per requirement 2, `checkout` raises `ValueError` with the message `order_id must not contain whitespace`. This includes leading and trailing whitespace such as `" A1"` or `"A1 "`.
4. If `order_id` is longer than 32 characters, `checkout` raises `ValueError` with the message `order_id must be at most 32 characters`. Exactly 32 characters is allowed.
5. Checks are applied in this order: type (1), empty (2), whitespace (3), length (4). Only the first failing check is reported.
6. The `order_id` validation happens before the empty-cart check. If both the order id is malformed and the cart is empty, the order id error is raised.
7. When validation fails, the cart must be left completely unchanged (its lines and quantities are untouched, it is not cleared).
8. Valid identifiers (non-empty strings without whitespace, at most 32 characters) behave exactly as before: the returned `Order` has the same fields and values, `order_id` is stored unchanged, the cart is emptied afterwards, and an empty cart with a valid id still raises `ValueError("cart is empty")`.

## Public interface
- `shop.checkout.checkout(cart: Cart, order_id: str) -> Order` (signature unchanged).
- Errors and exact messages:
  - `TypeError("order_id must be a string")`
  - `ValueError("order_id must not be empty")`
  - `ValueError("order_id must not contain whitespace")`
  - `ValueError("order_id must be at most 32 characters")`
  - `ValueError("cart is empty")` (existing behaviour, unchanged)

## Examples
```python
checkout(cart, "ORD-1")        # works as before
checkout(cart, "")             # ValueError: order_id must not be empty
checkout(cart, "   ")          # ValueError: order_id must not be empty
checkout(cart, "A 1")          # ValueError: order_id must not contain whitespace
checkout(cart, "X" * 33)       # ValueError: order_id must be at most 32 characters
checkout(cart, 42)             # TypeError: order_id must be a string
checkout(empty_cart, "bad id") # ValueError: order_id must not contain whitespace
```
