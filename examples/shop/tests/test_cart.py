import pytest


def test_add_and_quantity(cart):
    cart.add("PEN", 2)
    cart.add("PEN")
    assert cart.quantity("PEN") == 3


def test_add_rejects_non_positive_quantity(cart):
    with pytest.raises(ValueError):
        cart.add("PEN", 0)


def test_add_unknown_product(cart):
    with pytest.raises(KeyError):
        cart.add("NOPE")


def test_remove_partial_and_full(cart):
    cart.add("MUG", 3)
    cart.remove("MUG", 1)
    assert cart.quantity("MUG") == 2
    cart.remove("MUG")
    assert cart.quantity("MUG") == 0


def test_remove_missing_line(cart):
    with pytest.raises(KeyError):
        cart.remove("MUG")


def test_subtotal(cart):
    cart.add("PEN", 2)
    cart.add("BOOK")
    assert cart.subtotal_cents() == 2 * 150 + 1200


def test_clear_and_is_empty(cart):
    assert cart.is_empty()
    cart.add("PEN")
    assert not cart.is_empty()
    cart.clear()
    assert cart.is_empty()
