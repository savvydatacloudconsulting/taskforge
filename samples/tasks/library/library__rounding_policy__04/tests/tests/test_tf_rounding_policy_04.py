from datetime import timedelta

import pytest

from library import FINE_ROUND_UNIT_CENTS, discounted_fine


def _return_late(lib, today, member_id, late_days, isbn="111"):
    due = lib.lend(isbn, member_id, today)
    return lib.return_book(isbn, member_id, due + timedelta(days=late_days))


def test_unit_constant():
    assert FINE_ROUND_UNIT_CENTS == 5


def test_exact_amounts_are_unchanged():
    assert discounted_fine(50, 10) == 45
    assert discounted_fine(100, 50) == 50
    assert discounted_fine(150, 0) == 150


def test_halves_round_up():
    assert discounted_fine(50, 15) == 45  # 42.5 -> 45
    assert discounted_fine(50, 25) == 40  # 37.5 -> 40
    assert discounted_fine(50, 5) == 50  # 47.5 -> 50
    assert discounted_fine(50, 35) == 35  # 32.5 -> 35
    assert discounted_fine(50, 55) == 25  # 22.5 -> 25
    assert discounted_fine(150, 95) == 10  # 7.5 -> 10


def test_non_ties_round_to_nearest():
    assert discounted_fine(100, 33) == 65  # 67 -> 65
    assert discounted_fine(150, 98) == 5  # 3 -> 5
    assert discounted_fine(100, 67) == 35  # 33 -> 35
    assert discounted_fine(100, 62) == 40  # 38 -> 40


def test_minimum_charge_for_tiny_amounts():
    assert discounted_fine(50, 99) == 5  # 0.5 -> 0 -> minimum 5
    assert discounted_fine(100, 99) == 5  # 1.0 -> 0 -> minimum 5


def test_zero_cases():
    assert discounted_fine(0, 50) == 0
    assert discounted_fine(0, 0) == 0
    assert discounted_fine(50, 100) == 0
    assert discounted_fine(500, 100) == 0


def test_discounted_fine_validation():
    with pytest.raises(ValueError, match="percent must be between 0 and 100"):
        discounted_fine(50, -1)
    with pytest.raises(ValueError, match="percent must be between 0 and 100"):
        discounted_fine(50, 101)
    with pytest.raises(ValueError, match="fine_cents must not be negative"):
        discounted_fine(-50, 10)
    with pytest.raises(ValueError, match="fine_cents must not be negative"):
        discounted_fine(-50, 500)


def test_return_applies_member_discount(lib, today):
    lib.set_fine_discount("m1", 25)
    assert _return_late(lib, today, "m1", 1) == 40  # fine 50 -> 37.5 -> 40


def test_return_with_multiple_days_and_halves(lib, today):
    lib.set_fine_discount("m1", 15)
    assert _return_late(lib, today, "m1", 3) == 130  # fine 150 -> 127.5 -> 130


def test_return_on_time_or_early_costs_nothing(lib, today):
    lib.set_fine_discount("m1", 25)
    assert _return_late(lib, today, "m1", 0) == 0
    assert _return_late(lib, today, "m1", -5, isbn="222") == 0


def test_return_minimum_charge(lib, today):
    lib.set_fine_discount("m1", 99)
    assert _return_late(lib, today, "m1", 1) == 5


def test_full_discount_waives_fine(lib, today):
    lib.set_fine_discount("m1", 100)
    assert _return_late(lib, today, "m1", 4) == 0


def test_no_discount_keeps_old_fines(lib, today):
    assert _return_late(lib, today, "m2", 3) == 150
    lib.set_fine_discount("m1", 0)
    assert _return_late(lib, today, "m1", 2) == 100


def test_discounts_are_per_member(lib, today):
    lib.set_fine_discount("m1", 50)
    assert _return_late(lib, today, "m1", 2) == 50
    assert _return_late(lib, today, "m2", 2) == 100


def test_later_discount_replaces_earlier(lib, today):
    lib.set_fine_discount("m1", 50)
    lib.set_fine_discount("m1", 10)
    assert _return_late(lib, today, "m1", 1) == 45
    lib.set_fine_discount("m1", 0)
    assert _return_late(lib, today, "m1", 1) == 50


def test_discount_in_effect_at_return_time_is_used(lib, today):
    due = lib.lend("111", "m1", today)
    lib.set_fine_discount("m1", 50)
    assert lib.return_book("111", "m1", due + timedelta(days=2)) == 50


def test_set_fine_discount_errors(lib, today):
    with pytest.raises(KeyError, match="unknown member: zz"):
        lib.set_fine_discount("zz", 10)
    with pytest.raises(ValueError, match="percent must be between 0 and 100"):
        lib.set_fine_discount("m1", 101)
    with pytest.raises(ValueError, match="percent must be between 0 and 100"):
        lib.set_fine_discount("m1", -1)


def test_invalid_discount_does_not_change_stored_value(lib, today):
    lib.set_fine_discount("m1", 50)
    with pytest.raises(ValueError):
        lib.set_fine_discount("m1", 150)
    assert _return_late(lib, today, "m1", 2) == 50
