import pytest

from shop import checkout


def _message(excinfo):
    return str(excinfo.value)


def test_non_string_order_id_rejected(cart):
    cart.add("PEN", 2)
    for bad in (None, 42, b"A1", ["A1"]):
        with pytest.raises(TypeError) as excinfo:
            checkout(cart, bad)
        assert _message(excinfo) == "order_id must be a string"
    assert cart.quantity("PEN") == 2


def test_empty_and_blank_order_id_rejected(cart):
    cart.add("PEN")
    for bad in ("", "   ", "\t\n"):
        with pytest.raises(ValueError) as excinfo:
            checkout(cart, bad)
        assert _message(excinfo) == "order_id must not be empty"
    assert not cart.is_empty()


def test_whitespace_inside_order_id_rejected(cart):
    cart.add("MUG")
    for bad in ("A 1", " A1", "A1 ", "A\t1", "A1\n"):
        with pytest.raises(ValueError) as excinfo:
            checkout(cart, bad)
        assert _message(excinfo) == "order_id must not contain whitespace"
    assert cart.quantity("MUG") == 1


def test_length_boundary(cart, catalog):
    cart.add("BOOK", 3)
    with pytest.raises(ValueError) as excinfo:
        checkout(cart, "X" * 33)
    assert _message(excinfo) == "order_id must be at most 32 characters"
    assert cart.quantity("BOOK") == 3

    order = checkout(cart, "X" * 32)
    assert order.order_id == "X" * 32
    assert order.lines == [("BOOK", 3, 1200)]
    assert cart.is_empty()


def test_check_order_type_before_empty_before_whitespace_before_length(cart):
    cart.add("PEN")
    with pytest.raises(TypeError):
        checkout(cart, 5)
    with pytest.raises(ValueError) as excinfo:
        checkout(cart, " ")
    assert _message(excinfo) == "order_id must not be empty"
    with pytest.raises(ValueError) as excinfo:
        checkout(cart, "a " + "b" * 40)
    assert _message(excinfo) == "order_id must not contain whitespace"


def test_order_id_error_wins_over_empty_cart(cart):
    with pytest.raises(ValueError) as excinfo:
        checkout(cart, "bad id")
    assert _message(excinfo) == "order_id must not contain whitespace"
    with pytest.raises(TypeError):
        checkout(cart, None)
    with pytest.raises(ValueError) as excinfo:
        checkout(cart, "ORD-1")
    assert _message(excinfo) == "cart is empty"


def test_valid_order_id_behaves_as_before(cart):
    cart.add("PEN", 2)
    cart.add("MUG")
    with pytest.raises(ValueError):
        checkout(cart, "")
    order = checkout(cart, "ORD-1")
    assert order.order_id == "ORD-1"
    assert order.subtotal_cents == 1100
    assert order.tax_cents == 110
    assert order.total_cents == 1210
    assert cart.is_empty()
