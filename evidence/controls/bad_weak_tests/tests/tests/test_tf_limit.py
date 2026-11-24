from shop import cart as cart_module


def test_limit_constant():
    assert cart_module.MAX_PER_LINE == 10
