import pytest

from shop import discounted_subtotal_cents, stacked_discount_cents


@pytest.fixture
def full_cart(cart):
    cart.add("BOOK", 2)
    cart.add("MUG", 1)
    return cart  # subtotal 3200


def test_both_promotions_apply_under_cap(full_cart):
    assert stacked_discount_cents(full_cart, {"office": 10}, 500) == 740


def test_cap_limits_combined_discount(full_cart):
    assert stacked_discount_cents(full_cart, {"office": 50}, 1000) == 1600
    assert stacked_discount_cents(full_cart, {"office": 50}, 1000, cap_percent=80) == 2200


def test_only_category_discount(full_cart):
    assert stacked_discount_cents(full_cart, {"kitchen": 25}) == 200
    assert stacked_discount_cents(full_cart, {"kitchen": 25}, 0) == 200


def test_only_coupon(full_cart):
    assert stacked_discount_cents(full_cart, None, 300) == 300
    assert stacked_discount_cents(full_cart, {}, 300) == 300


def test_coupon_applies_after_category_discount(cart):
    cart.add("BOOK")  # 1200
    # category first: 600 off, then coupon 400 -> 1000 (coupon-first would give 800)
    assert stacked_discount_cents(cart, {"office": 50}, 400, cap_percent=100) == 1000


def test_coupon_cannot_exceed_remaining_amount(cart):
    cart.add("PEN")  # 150
    assert stacked_discount_cents(cart, {"office": 100}, 500, cap_percent=100) == 150
    assert stacked_discount_cents(cart, None, 1000, cap_percent=100) == 150


def test_floor_division_for_line_discount_and_cap(cart):
    cart.add("PEN")  # 150
    assert stacked_discount_cents(cart, {"office": 15}) == 22
    assert stacked_discount_cents(cart, None, 1000, cap_percent=33) == 49


def test_line_discount_uses_quantity_and_ignores_unknown_categories(cart):
    cart.add("PEN", 3)  # 450
    cart.add("MUG")  # 800
    assert stacked_discount_cents(cart, {"office": 10, "garden": 90}) == 45


def test_empty_cart_and_zero_cap(cart, full_cart):
    assert stacked_discount_cents(cart.__class__(cart.catalog), {"office": 10}, 500) == 0
    assert stacked_discount_cents(full_cart, {"office": 10}, 500, cap_percent=0) == 0


def test_discounted_subtotal(full_cart):
    assert discounted_subtotal_cents(full_cart, {"office": 10}, 500) == 2460
    assert discounted_subtotal_cents(full_cart) == 3200
    assert full_cart.subtotal_cents() == 3200


def test_validation_errors(cart, full_cart):
    with pytest.raises(ValueError, match="percent must be between 0 and 100"):
        stacked_discount_cents(full_cart, {"office": 101})
    with pytest.raises(ValueError, match="percent must be between 0 and 100"):
        stacked_discount_cents(full_cart, {"office": -1})
    with pytest.raises(ValueError, match="coupon must not be negative"):
        stacked_discount_cents(full_cart, None, -5)
    with pytest.raises(ValueError, match="cap_percent must be between 0 and 100"):
        stacked_discount_cents(full_cart, None, 0, cap_percent=101)
    with pytest.raises(ValueError, match="cap_percent must be between 0 and 100"):
        stacked_discount_cents(full_cart, None, 0, cap_percent=-1)
    empty = cart.__class__(cart.catalog)
    with pytest.raises(ValueError, match="coupon must not be negative"):
        stacked_discount_cents(empty, None, -1)
