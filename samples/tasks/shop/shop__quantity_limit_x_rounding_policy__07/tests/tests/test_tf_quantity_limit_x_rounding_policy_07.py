import pytest

from shop import (
    Cart,
    Catalog,
    Product,
    QuantityLimitError,
    checkout,
    tax_cents,
    tax_cents_half_even,
)


@pytest.fixture
def small_catalog():
    return Catalog([
        Product("A", "Tiny", 5),
        Product("B", "Bolt", 25),
        Product("C", "Clip", 15),
        Product("D", "Dowel", 35),
    ])


def test_half_even_rounding_values():
    assert tax_cents_half_even(0) == 0
    assert tax_cents_half_even(5) == 0    # 0.5 -> 0
    assert tax_cents_half_even(15) == 2   # 1.5 -> 2
    assert tax_cents_half_even(25) == 2   # 2.5 -> 2
    assert tax_cents_half_even(35) == 4   # 3.5 -> 4
    assert tax_cents_half_even(45) == 4   # 4.5 -> 4
    assert tax_cents_half_even(150) == 15
    assert tax_cents_half_even(16) == 2   # 1.6 -> 2
    assert tax_cents_half_even(14) == 1   # 1.4 -> 1


def test_half_even_custom_rate_and_half_up_unchanged():
    assert tax_cents_half_even(50, 5) == 2   # 2.5 -> 2
    assert tax_cents_half_even(70, 5) == 4   # 3.5 -> 4
    assert tax_cents(25) == 3                # existing half-up policy


def test_cap_rejects_exceeding_add_with_exact_message(small_catalog):
    cart = Cart(small_catalog, max_per_sku=2)
    cart.add("B", 2)
    with pytest.raises(QuantityLimitError) as info:
        cart.add("B")
    assert str(info.value) == "limit of 2 per item exceeded for B"
    assert isinstance(info.value, ValueError)
    assert cart.quantity("B") == 2


def test_rejected_add_is_not_partial(small_catalog):
    cart = Cart(small_catalog, max_per_sku=2)
    cart.add("C", 1)
    with pytest.raises(QuantityLimitError):
        cart.add("C", 2)
    assert cart.quantity("C") == 1
    assert cart.subtotal_cents() == 15


def test_cap_is_per_sku_and_allows_exact_cap(small_catalog):
    cart = Cart(small_catalog, max_per_sku=2)
    cart.add("A", 2)
    cart.add("B", 1)
    cart.add("B", 1)
    assert cart.quantity("A") == 2
    assert cart.quantity("B") == 2


def test_no_cap_by_default(small_catalog):
    cart = Cart(small_catalog)
    cart.add("A", 50)
    assert cart.quantity("A") == 50
    assert cart.remaining("A") is None


def test_remaining_tracks_cap(small_catalog):
    cart = Cart(small_catalog, max_per_sku=2)
    assert cart.remaining("A") == 2
    cart.add("A")
    assert cart.remaining("A") == 1
    cart.add("A")
    assert cart.remaining("A") == 0
    cart.remove("A", 1)
    assert cart.remaining("A") == 1


@pytest.mark.parametrize("bad", [0, -1])
def test_invalid_cap_rejected(small_catalog, bad):
    with pytest.raises(ValueError):
        Cart(small_catalog, max_per_sku=bad)


def test_existing_validation_has_priority_over_cap(small_catalog):
    cart = Cart(small_catalog, max_per_sku=2)
    with pytest.raises(KeyError):
        cart.add("NOPE", 5)
    with pytest.raises(ValueError) as info:
        cart.add("A", 0)
    assert not isinstance(info.value, QuantityLimitError)


def test_checkout_default_mode_unchanged(small_catalog):
    cart = Cart(small_catalog, max_per_sku=2)
    cart.add("B", 2)
    order = checkout(cart, "o1")
    assert order.subtotal_cents == 50
    assert order.tax_cents == 5
    assert order.total_cents == 55


def test_checkout_per_unit_half_even(small_catalog):
    cart = Cart(small_catalog, max_per_sku=2)
    cart.add("B", 2)
    order = checkout(cart, "o2", per_unit_tax=True)
    assert order.lines == [("B", 2, 25)]
    assert order.subtotal_cents == 50
    assert order.tax_cents == 4
    assert order.total_cents == 54
    assert cart.is_empty()


def test_per_unit_tax_differs_from_subtotal_tax_for_tiny_prices(small_catalog):
    cart = Cart(small_catalog, max_per_sku=2)
    cart.add("A", 2)
    cart.add("D", 2)
    order = checkout(cart, "o3", per_unit_tax=True)
    assert order.subtotal_cents == 80
    assert order.tax_cents == 0 * 2 + 4 * 2
    assert order.total_cents == 88


def test_per_unit_tax_uses_only_accepted_quantities(small_catalog):
    cart = Cart(small_catalog, max_per_sku=2)
    cart.add("C", 2)
    with pytest.raises(QuantityLimitError):
        cart.add("C", 1)
    order = checkout(cart, "o4", per_unit_tax=True)
    assert order.lines == [("C", 2, 15)]
    assert order.subtotal_cents == 30
    assert order.tax_cents == 4
    assert order.total_cents == 34


def test_checkout_empty_cart_still_rejected_in_per_unit_mode(small_catalog):
    cart = Cart(small_catalog, max_per_sku=2)
    with pytest.raises(ValueError, match="cart is empty"):
        checkout(cart, "o5", per_unit_tax=True)
