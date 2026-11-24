import pytest

from shop import Order, checkout, shipping_cents


def test_tier_edges():
    assert shipping_cents(0) == 899
    assert shipping_cents(4999) == 899
    assert shipping_cents(5000) == 499
    assert shipping_cents(9999) == 499
    assert shipping_cents(10000) == 0
    assert shipping_cents(50000) == 0


def test_member_discount_rounds_half_up():
    assert shipping_cents(4000, member=True) == 450
    assert shipping_cents(6000, member=True) == 250
    assert shipping_cents(10000, member=True) == 0


def test_express_only_is_capped():
    assert shipping_cents(4000, express=True) == 1200
    assert shipping_cents(6000, express=True) == 1099
    assert shipping_cents(10000, express=True) == 600


def test_member_and_express_stack_before_cap():
    assert shipping_cents(4000, express=True, member=True) == 1050
    assert shipping_cents(6000, express=True, member=True) == 850
    assert shipping_cents(20000, express=True, member=True) == 600


def test_negative_subtotal_rejected():
    with pytest.raises(ValueError, match="subtotal must be non-negative"):
        shipping_cents(-1)


def test_order_has_default_shipping_field():
    order = Order("X", [], 100, 10, 110)
    assert order.shipping_cents == 0


def test_checkout_without_shipping_unchanged(cart):
    cart.add("BOOK", 5)
    order = checkout(cart, "A1", member=True)
    assert order.shipping_cents == 0
    assert order.total_cents == 6000 + 600


def test_checkout_standard_shipping(cart):
    cart.add("BOOK", 5)
    order = checkout(cart, "A2", shipping="standard")
    assert order.subtotal_cents == 6000
    assert order.tax_cents == 600
    assert order.shipping_cents == 499
    assert order.total_cents == 7099
    assert cart.is_empty()


def test_checkout_express_member_stacking(cart):
    cart.add("BOOK", 5)
    order = checkout(cart, "A3", shipping="express", member=True)
    assert order.shipping_cents == 850
    assert order.total_cents == 6000 + 600 + 850


def test_checkout_express_cap(cart):
    cart.add("BOOK", 3)
    order = checkout(cart, "A4", shipping="express")
    assert order.subtotal_cents == 3600
    assert order.shipping_cents == 1200
    assert order.total_cents == 3600 + 360 + 1200


def test_checkout_unknown_shipping_leaves_cart(cart):
    cart.add("MUG", 2)
    with pytest.raises(ValueError, match="unknown shipping method: overnight"):
        checkout(cart, "A5", shipping="overnight")
    assert cart.quantity("MUG") == 2


def test_checkout_empty_cart_still_rejected(cart):
    with pytest.raises(ValueError, match="cart is empty"):
        checkout(cart, "A6", shipping="standard")
