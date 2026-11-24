from __future__ import annotations

from .catalog import Catalog, Product


class Cart:
    """Items a customer wants to buy: SKU -> quantity."""

    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self._lines: dict[str, int] = {}

    def add(self, sku: str, quantity: int = 1) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.catalog.get(sku)  # raises KeyError for unknown products
        self._lines[sku] = self._lines.get(sku, 0) + quantity

    def remove(self, sku: str, quantity: int | None = None) -> None:
        if sku not in self._lines:
            raise KeyError(f"not in cart: {sku}")
        if quantity is None or quantity >= self._lines[sku]:
            del self._lines[sku]
        else:
            if quantity <= 0:
                raise ValueError("quantity must be positive")
            self._lines[sku] -= quantity

    def quantity(self, sku: str) -> int:
        return self._lines.get(sku, 0)

    def lines(self) -> list[tuple[Product, int]]:
        return [(self.catalog.get(sku), qty) for sku, qty in self._lines.items()]

    def subtotal_cents(self) -> int:
        return sum(product.price_cents * qty for product, qty in self.lines())

    def is_empty(self) -> bool:
        return not self._lines

    def clear(self) -> None:
        self._lines.clear()
