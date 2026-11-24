## Background

Products and cart lines are currently added one at a time. `Catalog.add` rejects any repeated SKU, and `Cart.add` has to be called once per line. Bulk loading, for example from an imported product feed or a pasted order list, will contain repeated entries. The right handling depends on what is repeated:

- In a catalog, a repeated product that is *identical* (all fields equal) is harmless and is ignored. A repeated SKU with *different* data is a real conflict and is rejected.
- In a cart, repeated SKUs are merged by summing their quantities.

Both bulk operations must be atomic: if any entry is invalid, nothing is changed.

## Requirements

1. `Catalog.add_all(products)` adds every product from an iterable and returns the number of products that were newly added to the catalog.
2. A product that is equal (`==`) to a product already in the catalog is ignored and not counted.
3. A product that is equal to an earlier product in the same input is ignored and not counted. Only the first occurrence counts.
4. A product whose SKU matches a product already in the catalog, or an earlier product in the same input, but which differs in any other field, raises `ValueError` with the message `conflicting sku: <sku>`.
5. `Catalog.add_all` is atomic. If a `ValueError` is raised, the catalog is unchanged, including products that appeared earlier in the same input.
6. `Cart.add_all(items)` takes an iterable of `(sku, quantity)` tuples and returns the number of distinct SKUs in the input.
7. Repeated SKUs in the input are merged. Their quantities are summed and added to any quantity already in the cart for that SKU.
8. A quantity of zero or less raises `ValueError("quantity must be positive")`. An unknown SKU raises `KeyError` (the same error `Catalog.get` raises).
9. `Cart.add_all` is atomic. If any entry is invalid, the cart is unchanged, even if valid entries came before the invalid one.
10. An empty input is allowed. It changes nothing and returns `0`.
11. Existing behaviour of `Catalog.add`, `Cart.add` and everything else is unchanged.

## Public interface

- `Catalog.add_all(self, products) -> int`
  - `products` is an iterable of `Product`.
  - Raises `ValueError("conflicting sku: <sku>")` on a conflicting repeat.
- `Cart.add_all(self, items) -> int`
  - `items` is an iterable of `(sku: str, quantity: int)` tuples.
  - Raises `ValueError("quantity must be positive")` for a quantity <= 0.
  - Raises `KeyError` for an unknown SKU.

## Examples

```python
catalog = Catalog([Product("PEN", "Pen", 150)])
catalog.add_all([
    Product("PEN", "Pen", 150),     # identical to existing: ignored
    Product("MUG", "Mug", 800),     # new
    Product("MUG", "Mug", 800),     # identical repeat in input: ignored
])                                  # -> 1

catalog.add_all([Product("PEN", "Pen", 175)])   # ValueError: conflicting sku: PEN

cart = Cart(catalog)
cart.add_all([("PEN", 2), ("MUG", 1), ("PEN", 3)])   # -> 2
cart.quantity("PEN")                                 # -> 5
```
