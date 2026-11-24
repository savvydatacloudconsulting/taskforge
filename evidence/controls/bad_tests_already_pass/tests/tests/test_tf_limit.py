import pytest


def test_zero_quantity_rejected(cart):
    with pytest.raises(ValueError):
        cart.add("PEN", 0)
