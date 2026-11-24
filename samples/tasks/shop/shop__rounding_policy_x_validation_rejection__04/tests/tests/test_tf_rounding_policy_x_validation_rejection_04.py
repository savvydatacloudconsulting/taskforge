import pytest

from shop import Cart, Catalog, Product, checkout, tax_cents
from shop.pricing import ROUNDING_MODES


@pytest.fixture
def small_cart():
    catalog = Catalog([
        Product("A", "Five", 5),
        Product("B", "Five too", 5),
        Product("C", "One", 1),
        Product("D", "Fifteen", 15),
    ])
    return Cart(catalog)


def test_modes_constant():
    assert ROUNDING_MODES == ("half_up", "half_even", "floor", "ceil")


@pytest.mark.parametrize(
    "amount, mode, expected",
    [
        (5, "half_up", 1), (5, "half_even", 0), (5, "floor", 0), (5, "ceil", 1),
        (15, "half_up", 2), (15, "half_even", 2), (15, "floor", 1), (15, "ceil", 2),
        (25, "half_up", 3), (25, "half_even", 2),
        (1, "half_up", 0), (1, "half_even", 0), (1, "floor", 0), (1, "ceil", 1),
        (0, "half_up", 0), (0, "half_even", 0), (0, "floor", 0), (0, "ceil", 0),
        (10, "ceil", 1), (10, "floor", 1),
    ],
)
def test_tax_modes_at_default_rate(amount, mode, expected):
    assert tax_cents(amount, rounding=mode) == expected


def test_custom_rate_with_rounding():
    assert tax_cents(3, 50, rounding="half_even") == 2
    assert tax_cents(3, 50, rounding="half_up") == 2
    assert tax_cents(1, 50, rounding="half_even") == 0
    assert tax_cents(200, 100, rounding="ceil") == 200
    assert tax_cents(200, 0, rounding="ceil") == 0


def test_default_rounding_unchanged():
    assert tax_cents(5) == 1
    assert tax_cents(14) == 1
    assert tax_cents(15) == 2


def test_tax_rejects_unknown_rounding():
    with pytest.raises(ValueError) as exc:
        tax_cents(100, rounding="banker")
    assert str(exc.value) == "unknown rounding mode: banker"


@pytest.mark.parametrize("rate", [-1, 101])
def test_tax_rejects_bad_rate(rate):
    with pytest.raises(ValueError) as exc:
        tax_cents(100, rate)
    assert str(exc.value) == "rate_percent must be between 0 and 100"


def test_rounding_error_wins_over_rate_error():
    with pytest.raises(ValueError) as exc:
        tax_cents(100, 500, rounding="nope")
    assert str(exc.value) == "unknown rounding mode: nope"


def test_checkout_whole_vs_per_line(small_cart):
    small_cart.add("A")
    small_cart.add("B")
    order = checkout(small_cart, "o1")
    assert (order.subtotal_cents, order.tax_cents, order.total_cents) == (10, 1, 11)

    small_cart.add("A")
    small_cart.add("B")
    order = checkout(small_cart, "o2", per_line=True)
    assert (order.subtotal_cents, order.tax_cents, order.total_cents) == (10, 2, 12)


def test_checkout_per_line_with_modes(small_cart):
    small_cart.add("A")
    small_cart.add("C")
    order = checkout(small_cart, "o3", rounding="ceil", per_line=True)
    assert order.tax_cents == 2
    assert order.total_cents == 8

    small_cart.add("A")
    small_cart.add("C")
    order = checkout(small_cart, "o4", rounding="ceil")
    assert order.tax_cents == 1

    small_cart.add("A")
    small_cart.add("B")
    order = checkout(small_cart, "o5", rounding="half_even", per_line=True)
    assert order.tax_cents == 0


def test_checkout_per_line_uses_line_quantity(small_cart):
    small_cart.add("D", 3)  # line amount 45 -> tax 4.5
    order = checkout(small_cart, "o6", rounding="half_even", per_line=True)
    assert order.tax_cents == 4
    small_cart.add("D", 3)
    order = checkout(small_cart, "o7", rounding="half_up", per_line=True)
    assert order.tax_cents == 5


def test_checkout_bad_rounding_leaves_cart(small_cart):
    small_cart.add("D", 2)
    with pytest.raises(ValueError) as exc:
        checkout(small_cart, "o8", rounding="banker")
    assert str(exc.value) == "unknown rounding mode: banker"
    assert small_cart.quantity("D") == 2


@pytest.mark.parametrize("value", [1, 0, "yes", None])
def test_checkout_bad_per_line_leaves_cart(small_cart, value):
    small_cart.add("A")
    with pytest.raises(TypeError) as exc:
        checkout(small_cart, "o9", per_line=value)
    assert str(exc.value) == "per_line must be a bool"
    assert small_cart.quantity("A") == 1


def test_checkout_validation_before_empty_check(small_cart):
    with pytest.raises(ValueError) as exc:
        checkout(small_cart, "o10", rounding="banker")
    assert str(exc.value) == "unknown rounding mode: banker"
    with pytest.raises(TypeError):
        checkout(small_cart, "o11", per_line="no")
    with pytest.raises(ValueError) as exc:
        checkout(small_cart, "o12")
    assert str(exc.value) == "cart is empty"


def test_checkout_still_empties_cart(small_cart):
    small_cart.add("D")
    checkout(small_cart, "o13", rounding="floor", per_line=True)
    assert small_cart.is_empty()
