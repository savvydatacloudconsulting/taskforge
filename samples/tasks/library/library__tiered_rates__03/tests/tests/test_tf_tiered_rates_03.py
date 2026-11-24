from datetime import timedelta

import pytest

import library
from library import tiered_fine
from library.lending import tiered_fine as lending_tiered_fine


def test_exported_from_both_places():
    assert library.tiered_fine is lending_tiered_fine
    assert "tiered_fine" in library.__all__


def test_zero_late_days_is_free():
    assert tiered_fine(0) == 0


def test_first_band_uses_base_rate():
    assert tiered_fine(1) == 50
    assert tiered_fine(3) == 150
    assert tiered_fine(7) == 350


def test_second_band_is_charged_marginally():
    assert tiered_fine(8) == 450
    assert tiered_fine(10) == 650
    assert tiered_fine(14) == 1050


def test_third_band_is_charged_marginally():
    assert tiered_fine(15) == 1250
    assert tiered_fine(20) == 2250
    assert tiered_fine(30) == 1050 + 16 * 200


def test_edges_belong_to_lower_band():
    assert tiered_fine(7) - tiered_fine(6) == 50
    assert tiered_fine(8) - tiered_fine(7) == 100
    assert tiered_fine(14) - tiered_fine(13) == 100
    assert tiered_fine(15) - tiered_fine(14) == 200


def test_negative_late_days_rejected():
    with pytest.raises(ValueError, match="late_days must be >= 0"):
        tiered_fine(-1)


def test_return_book_tiered_on_time_and_early(lib, today):
    due = lib.lend("111", "m1", today)
    assert lib.return_book("111", "m1", due, tiered=True) == 0
    due = lib.lend("222", "m2", today)
    assert lib.return_book("222", "m2", due - timedelta(days=5), tiered=True) == 0


def test_return_book_tiered_late(lib, today):
    due = lib.lend("111", "m1", today)
    assert lib.return_book("111", "m1", due + timedelta(days=10), tiered=True) == 650


def test_return_book_tiered_across_all_bands(lib, today):
    due = lib.lend("111", "m1", today)
    assert lib.return_book("111", "m1", due + timedelta(days=20), tiered=True) == 2250


def test_return_book_flat_is_unchanged(lib, today):
    due = lib.lend("111", "m1", today)
    assert lib.return_book("111", "m1", due + timedelta(days=10), tiered=False) == 500
    due = lib.lend("111", "m2", today)
    assert lib.return_book("111", "m2", due + timedelta(days=20)) == 1000


def test_tiered_return_still_removes_loan_and_checks_errors(lib, today):
    due = lib.lend("111", "m1", today)
    lib.return_book("111", "m1", due + timedelta(days=1), tiered=True)
    assert lib.loans_of("m1") == []
    assert lib.copies_available("111") == 2
    with pytest.raises(KeyError, match="no such loan"):
        lib.return_book("111", "m1", due, tiered=True)
