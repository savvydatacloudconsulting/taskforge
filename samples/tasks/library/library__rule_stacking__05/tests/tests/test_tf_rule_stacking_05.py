from datetime import timedelta

import pytest

import library
from library import Book, Library, Member


def _late_return(lib, isbn, member_id, today, late_days):
    due = lib.lend(isbn, member_id, today)
    return lib.return_book(isbn, member_id, due + timedelta(days=late_days))


def test_constants_exported():
    assert library.DEMAND_MULTIPLIER == 3
    assert library.REDUCED_MEMBER_DISCOUNT_CENTS == 20
    assert library.MAX_DAILY_RATE_CENTS == 140


def test_no_flags_keeps_base_rate(lib, today):
    assert lib.daily_fine_rate("111", "m1") == 50
    assert _late_return(lib, "111", "m1", today, 3) == 150


def test_only_reduced_member(lib, today):
    lib.set_reduced_rate("m1", True)
    assert lib.daily_fine_rate("111", "m1") == 30
    assert _late_return(lib, "111", "m1", today, 3) == 90


def test_only_high_demand_is_capped(lib, today):
    lib.set_high_demand("111", True)
    assert lib.daily_fine_rate("111", "m1") == 140
    assert _late_return(lib, "111", "m1", today, 3) == 420


def test_both_apply_in_order_then_cap(lib, today):
    lib.set_high_demand("111", True)
    lib.set_reduced_rate("m1", True)
    # (50 * 3) - 20 = 130, under the cap; the other order would give 90
    assert lib.daily_fine_rate("111", "m1") == 130
    assert _late_return(lib, "111", "m1", today, 3) == 390


def test_on_time_return_is_free_with_flags(lib, today):
    lib.set_high_demand("111", True)
    lib.set_reduced_rate("m1", True)
    assert _late_return(lib, "111", "m1", today, 0) == 0
    assert _late_return(lib, "111", "m2", today, -5) == 0


def test_flags_are_independent(lib, today):
    lib.set_high_demand("111", True)
    lib.set_reduced_rate("m1", True)
    assert lib.daily_fine_rate("222", "m1") == 30
    assert lib.daily_fine_rate("222", "m2") == 50
    assert lib.daily_fine_rate("111", "m2") == 140
    assert _late_return(lib, "111", "m2", today, 2) == 280


def test_unsetting_flags_restores_rate(lib):
    lib.set_high_demand("111", True)
    lib.set_reduced_rate("m1", True)
    lib.set_high_demand("111", False)
    assert lib.daily_fine_rate("111", "m1") == 30
    lib.set_reduced_rate("m1", False)
    assert lib.daily_fine_rate("111", "m1") == 50


def test_flags_read_at_return_time_and_persist(lib, today):
    due = lib.lend("111", "m1", today)
    lib.set_high_demand("111", True)
    assert lib.return_book("111", "m1", due + timedelta(days=1)) == 140
    assert lib.daily_fine_rate("111", "m1") == 140


def test_unknown_ids_raise_key_error(lib):
    with pytest.raises(KeyError):
        lib.set_high_demand("999", True)
    with pytest.raises(KeyError):
        lib.set_reduced_rate("nobody", True)
    with pytest.raises(KeyError):
        lib.daily_fine_rate("999", "m1")
    with pytest.raises(KeyError):
        lib.daily_fine_rate("111", "nobody")


def test_return_without_loan_still_key_error(lib, today):
    lib.set_high_demand("111", True)
    with pytest.raises(KeyError):
        lib.return_book("111", "m1", today)
