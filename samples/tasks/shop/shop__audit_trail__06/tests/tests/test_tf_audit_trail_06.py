import pytest

from shop import Cart, CartEvent, checkout


def test_new_cart_has_empty_history(cart):
    assert cart.history() == []


def test_successful_add_and_remove_are_recorded_in_order(cart):
    cart.add("PEN", 3)
    cart.add("MUG")
    cart.remove("PEN", 1)
    assert cart.history() == [
        CartEvent("add", "PEN", 3, True),
        CartEvent("add", "MUG", 1, True),
        CartEvent("remove", "PEN", 1, True),
    ]


def test_event_is_frozen(cart):
    cart.add("PEN")
    event = cart.history()[0]
    assert event.action == "add"
    assert event.sku == "PEN"
    assert event.quantity == 1
    assert event.ok is True
    with pytest.raises(Exception):
        event.quantity = 5


def test_history_returns_a_copy(cart):
    cart.add("PEN")
    snapshot = cart.history()
    snapshot.clear()
    assert cart.history() == [CartEvent("add", "PEN", 1, True)]


def test_failed_adds_are_recorded_and_still_raise(cart):
    with pytest.raises(ValueError):
        cart.add("PEN", 0)
    with pytest.raises(KeyError):
        cart.add("NOPE", 2)
    assert cart.quantity("PEN") == 0
    assert cart.history() == [
        CartEvent("add", "PEN", 0, False),
        CartEvent("add", "NOPE", 2, False),
    ]


def test_remove_records_units_actually_removed(cart):
    cart.add("PEN", 3)
    cart.add("MUG", 2)
    cart.add("BOOK", 1)
    cart.remove("PEN")          # whole line, omitted quantity
    cart.remove("MUG", 10)      # more than held
    cart.remove("BOOK", 1)      # exactly what is held
    assert cart.history()[3:] == [
        CartEvent("remove", "PEN", 3, True),
        CartEvent("remove", "MUG", 2, True),
        CartEvent("remove", "BOOK", 1, True),
    ]
    assert cart.is_empty()


def test_failed_removes_are_recorded_and_still_raise(cart):
    with pytest.raises(KeyError):
        cart.remove("PEN")
    with pytest.raises(KeyError):
        cart.remove("MUG", 2)
    cart.add("BOOK", 4)
    with pytest.raises(ValueError):
        cart.remove("BOOK", 0)
    with pytest.raises(ValueError):
        cart.remove("BOOK", -2)
    assert cart.quantity("BOOK") == 4
    assert cart.history() == [
        CartEvent("remove", "PEN", 0, False),
        CartEvent("remove", "MUG", 2, False),
        CartEvent("add", "BOOK", 4, True),
        CartEvent("remove", "BOOK", 0, False),
        CartEvent("remove", "BOOK", -2, False),
    ]


def test_clear_records_total_units_and_empty_clear_is_a_noop(cart):
    cart.clear()
    assert cart.history() == []
    cart.add("PEN", 2)
    cart.add("MUG", 3)
    cart.clear()
    cart.clear()
    assert cart.history()[2:] == [CartEvent("clear", None, 5, True)]
    assert len(cart.history()) == 3


def test_checkout_appends_a_clear_event(cart):
    cart.add("PEN", 2)
    cart.add("MUG")
    checkout(cart, "o-1")
    assert cart.history()[-1] == CartEvent("clear", None, 3, True)
    assert len(cart.history()) == 3


def test_failed_checkout_records_nothing(cart):
    with pytest.raises(ValueError):
        checkout(cart, "o-2")
    assert cart.history() == []


def test_histories_are_per_cart(catalog):
    a = Cart(catalog)
    b = Cart(catalog)
    a.add("PEN")
    assert b.history() == []
    assert a.history() == [CartEvent("add", "PEN", 1, True)]
