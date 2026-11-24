from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price_cents: int
    category: str = "general"


class Catalog:
    """A set of products, looked up by SKU."""

    def __init__(self, products=()):
        self._products: dict[str, Product] = {}
        for product in products:
            self.add(product)

    def add(self, product: Product) -> None:
        if product.sku in self._products:
            raise ValueError(f"duplicate sku: {product.sku}")
        self._products[product.sku] = product

    def get(self, sku: str) -> Product:
        try:
            return self._products[sku]
        except KeyError:
            raise KeyError(f"unknown sku: {sku}") from None

    def __contains__(self, sku: str) -> bool:
        return sku in self._products

    def by_category(self, category: str) -> list[Product]:
        return [p for p in self._products.values() if p.category == category]
