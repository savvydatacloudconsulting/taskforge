import pytest


def test_can_add_up_to_the_limit(cart):
    cart.add("PEN", 10)
    assert cart.quantity("PEN") == 10


def test_one_call_over_the_limit_is_rejected(cart):
    with pytest.raises(ValueError, match="limit of 10"):
        cart.add("PEN", 11)
    assert cart.quantity("PEN") == 0


def test_limit_applies_across_calls_and_cart_is_unchanged(cart):
    cart.add("PEN", 6)
    with pytest.raises(ValueError, match="limit of 10"):
        cart.add("PEN", 5)
    assert cart.quantity("PEN") == 6


def test_limit_is_per_product(cart):
    cart.add("PEN", 10)
    cart.add("MUG", 10)
    assert cart.quantity("PEN") == 10 and cart.quantity("MUG") == 10


def test_removing_makes_room_again(cart):
    cart.add("BOOK", 10)
    cart.remove("BOOK", 4)
    cart.add("BOOK", 4)
    assert cart.quantity("BOOK") == 10
    with pytest.raises(ValueError):
        cart.add("BOOK", 1)
