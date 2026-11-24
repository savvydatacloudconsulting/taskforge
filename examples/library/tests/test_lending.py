from datetime import date

import pytest

from library import Book, Member


def test_lend_returns_due_date_and_reduces_copies(lib, today):
    due = lib.lend("111", "m1", today)
    assert due == date(2026, 3, 15)
    assert lib.copies_available("111") == 1


def test_cannot_borrow_same_book_twice(lib, today):
    lib.lend("111", "m1", today)
    with pytest.raises(ValueError, match="already borrowed"):
        lib.lend("111", "m1", today)


def test_no_copies_left(lib, today):
    lib.lend("222", "m1", today)
    with pytest.raises(ValueError, match="no copies"):
        lib.lend("222", "m2", today)


def test_unknown_book_and_member(lib, today):
    with pytest.raises(KeyError):
        lib.lend("999", "m1", today)
    with pytest.raises(KeyError):
        lib.lend("111", "nobody", today)


def test_return_on_time_has_no_fine(lib, today):
    lib.lend("111", "m1", today)
    assert lib.return_book("111", "m1", date(2026, 3, 15)) == 0
    assert lib.copies_available("111") == 2


def test_late_return_is_fined_per_day(lib, today):
    lib.lend("111", "m1", today)
    assert lib.return_book("111", "m1", date(2026, 3, 18)) == 3 * 50


def test_return_without_loan(lib, today):
    with pytest.raises(KeyError):
        lib.return_book("111", "m1", today)


def test_loans_of_is_sorted(lib, today):
    lib.lend("222", "m1", today)
    lib.lend("111", "m1", today)
    assert lib.loans_of("m1") == ["111", "222"]
    assert lib.loans_of("m2") == []


def test_duplicates_rejected(lib):
    with pytest.raises(ValueError):
        lib.add_book(Book("111", "Again"))
    with pytest.raises(ValueError):
        lib.add_member(Member("m1", "Again"))
