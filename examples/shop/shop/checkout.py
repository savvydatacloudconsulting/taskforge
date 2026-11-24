from __future__ import annotations

from dataclasses import dataclass

from .cart import Cart
from .pricing import tax_cents


@dataclass
class Order:
    order_id: str
    lines: list[tuple[str, int, int]]  # (sku, quantity, unit price in cents)
    subtotal_cents: int
    tax_cents: int
    total_cents: int


def checkout(cart: Cart, order_id: str) -> Order:
    """Turn a cart into an order. The cart is emptied afterwards."""
    if cart.is_empty():
        raise ValueError("cart is empty")
    lines = [(p.sku, qty, p.price_cents) for p, qty in cart.lines()]
    subtotal = cart.subtotal_cents()
    tax = tax_cents(subtotal)
    order = Order(order_id, lines, subtotal, tax, subtotal + tax)
    cart.clear()
    return order
