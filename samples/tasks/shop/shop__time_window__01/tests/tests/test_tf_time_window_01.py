from datetime import datetime, timedelta

import pytest

from shop import Promotion, checkout

START = datetime(2025, 1, 1, 0, 0)
END = datetime(2025, 1, 2, 0, 0)


def promo(percent=10, category="office"):
    return Promotion("Sale", percent, START, END, category)


def test_is_active_boundaries():
    p = promo()
    assert p.is_active(START) is True
    assert p.is_active(END - timedelta(microseconds=1)) is True
    assert p.is_active(END) is False
    assert p.is_active(START - timedelta(microseconds=1)) is False


def test_promotion_validation():
    with pytest.raises(ValueError, match="percent_off must be between 1 and 100"):
        promo(percent=0)
    with pytest.raises(ValueError, match="percent_off must be between 1 and 100"):
        promo(percent=101)
    with pytest.raises(ValueError, match="end must be after start"):
        Promotion("Bad", 10, END, START)
    with pytest.raises(ValueError, match="end must be after start"):
        Promotion("Bad", 10, START, START)


def test_discount_applies_only_to_category_inside_window(cart):
    cart.add("BOOK")
    cart.add("MUG")
    order = checkout(cart, "A1", promo(), datetime(2025, 1, 1, 12, 0))
    assert order.subtotal_cents == 2000
    assert order.discount_cents == 120
    assert order.tax_cents == 188
    assert order.total_cents == 2068
    assert cart.is_empty()


def test_discount_applies_to_all_lines_without_category(cart):
    cart.add("BOOK")
    cart.add("MUG")
    order = checkout(cart, "A2", promo(25, None), START)
    assert order.discount_cents == 500
    assert order.tax_cents == 150
    assert order.total_cents == 1650


def test_discount_rounds_down(cart):
    cart.add("PEN")
    order = checkout(cart, "A3", promo(33), START)
    assert order.discount_cents == 49
    assert order.tax_cents == 10
    assert order.total_cents == 111


def test_end_is_exclusive_and_before_start_is_inactive(cart):
    cart.add("BOOK")
    baseline = checkout(cart, "B0")
    cart.add("BOOK")
    at_end = checkout(cart, "B1", promo(), END)
    cart.add("BOOK")
    before = checkout(cart, "B2", promo(), START - timedelta(seconds=1))
    for order in (at_end, before):
        assert order.discount_cents == 0
        assert order.subtotal_cents == baseline.subtotal_cents
        assert order.tax_cents == baseline.tax_cents
        assert order.total_cents == baseline.total_cents


def test_no_eligible_lines_means_no_discount(cart):
    cart.add("MUG")
    order = checkout(cart, "C1", promo(50, "office"), START)
    assert order.discount_cents == 0
    assert order.total_cents == 880


def test_default_checkout_has_zero_discount(cart):
    cart.add("BOOK", 2)
    order = checkout(cart, "D1")
    assert order.discount_cents == 0
    assert order.total_cents == 2640


def test_promotion_without_now_is_rejected_and_cart_untouched(cart):
    cart.add("BOOK")
    with pytest.raises(ValueError, match="now is required when a promotion is given"):
        checkout(cart, "E1", promo())
    assert cart.quantity("BOOK") == 1
    assert not cart.is_empty()


def test_empty_cart_still_rejected_with_promotion(cart):
    with pytest.raises(ValueError, match="cart is empty"):
        checkout(cart, "F1", promo(), START)
