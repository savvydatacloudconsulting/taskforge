## Background

A `Cart` currently keeps no record of what happened to it. Support staff want to see, in order, every change made to a cart (including attempted changes that were rejected) so they can explain why a cart looks the way it does.

## Requirements

1. Add a frozen dataclass `CartEvent` with fields `action` (str), `sku` (str or None), `quantity` (int) and `ok` (bool), defined in `shop/cart.py` and exported from the `shop` package (`from shop import CartEvent`).
2. Add a method `Cart.history()` returning a list of `CartEvent` objects in the order the operations happened. A new cart has an empty history.
3. `history()` returns a fresh list on every call: modifying the returned list must not change the cart's real history.
4. A successful `add(sku, quantity)` records `CartEvent("add", sku, quantity, True)`.
5. An `add` that raises (non-positive quantity, or unknown SKU) still raises exactly as before and also records `CartEvent("add", sku, quantity, False)`, using the arguments as passed.
6. A successful `remove(sku, quantity)` records `CartEvent("remove", sku, removed, True)`, where `removed` is the number of units actually taken out of the cart. Removing the whole line (quantity omitted, or quantity greater than or equal to the amount held) records the amount that was held.
7. A `remove` that raises (SKU not in the cart, or a non-positive quantity on a partial removal) still raises exactly as before and also records `CartEvent("remove", sku, requested, False)`, where `requested` is the quantity passed, or `0` if it was omitted (`None`).
8. `clear()` on a non-empty cart records `CartEvent("clear", None, units, True)`, where `units` is the total number of units in the cart before it was cleared. `clear()` on an already-empty cart is a no-op and records nothing.
9. `checkout` empties the cart through `clear()`, so a successful checkout appends a `clear` event for the cart. A checkout that fails because the cart is empty records nothing.
10. Cart contents, subtotals and all existing behaviour are otherwise unchanged.

## Public interface

- `shop.cart.CartEvent` (also `shop.CartEvent`): `@dataclass(frozen=True)` with fields `action: str`, `sku: str | None`, `quantity: int`, `ok: bool`. Dataclass equality is used to compare events.
- `Cart.history(self) -> list[CartEvent]`
- Action strings are exactly `"add"`, `"remove"` and `"clear"`.
- Existing exception types and messages of `add` and `remove` do not change.

## Examples

```python
cart = Cart(catalog)
cart.add("PEN", 2)
cart.remove("PEN", 1)
try:
    cart.add("NOPE")
except KeyError:
    pass
cart.history()
# [CartEvent("add", "PEN", 2, True),
#  CartEvent("remove", "PEN", 1, True),
#  CartEvent("add", "NOPE", 1, False)]

cart.clear()
cart.history()[-1]   # CartEvent("clear", None, 1, True)
cart.clear()         # already empty: nothing recorded
```
