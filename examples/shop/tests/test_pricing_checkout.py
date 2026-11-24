import pytest

from shop import checkout, format_money, tax_cents


def test_tax_rounds_half_up():
    assert tax_cents(1000) == 100
    assert tax_cents(15) == 2  # 1.5 rounds up
    assert tax_cents(14) == 1


def test_format_money():
    assert format_money(0) == "$0.00"
    assert format_money(1205) == "$12.05"
    assert format_money(-99) == "-$0.99"


def test_checkout_totals_and_clears_cart(cart):
    cart.add("PEN", 2)
    cart.add("BOOK")
    order = checkout(cart, "A-1")
    assert order.subtotal_cents == 1500
    assert order.tax_cents == 150
    assert order.total_cents == 1650
    assert order.lines == [("PEN", 2, 150), ("BOOK", 1, 1200)]
    assert cart.is_empty()


def test_checkout_empty_cart(cart):
    with pytest.raises(ValueError):
        checkout(cart, "A-2")
