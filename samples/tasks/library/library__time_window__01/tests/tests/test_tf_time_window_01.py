from datetime import date

import pytest

START = date(2026, 3, 18)
END = date(2026, 3, 25)


def test_return_inside_window_has_no_fine(lib, today):
    lib.lend("111", "m1", today)  # due 2026-03-15
    lib.set_fine_amnesty(START, END)
    assert lib.return_book("111", "m1", date(2026, 3, 20)) == 0


def test_start_is_inclusive(lib, today):
    lib.lend("111", "m1", today)
    lib.set_fine_amnesty(START, END)
    assert lib.is_amnesty_active(START) is True
    assert lib.return_book("111", "m1", START) == 0


def test_end_is_exclusive(lib, today):
    lib.lend("111", "m1", today)
    lib.set_fine_amnesty(START, END)
    assert lib.is_amnesty_active(date(2026, 3, 24)) is True
    assert lib.is_amnesty_active(END) is False
    # 10 days late on the end date, amnesty already over
    assert lib.return_book("111", "m1", END) == 500


def test_before_window_still_fined(lib, today):
    lib.lend("111", "m1", today)
    lib.set_fine_amnesty(START, END)
    assert lib.is_amnesty_active(date(2026, 3, 17)) is False
    assert lib.return_book("111", "m1", date(2026, 3, 17)) == 100


def test_not_active_without_window(lib):
    assert lib.is_amnesty_active(date(2026, 3, 20)) is False


def test_invalid_window_rejected_and_keeps_old_window(lib):
    lib.set_fine_amnesty(START, END)
    with pytest.raises(ValueError, match="invalid amnesty window"):
        lib.set_fine_amnesty(END, START)
    with pytest.raises(ValueError, match="invalid amnesty window"):
        lib.set_fine_amnesty(START, START)
    assert lib.is_amnesty_active(date(2026, 3, 20)) is True


def test_new_window_replaces_old(lib, today):
    lib.lend("111", "m1", today)
    lib.set_fine_amnesty(START, END)
    lib.set_fine_amnesty(date(2026, 4, 1), date(2026, 4, 5))
    assert lib.is_amnesty_active(date(2026, 3, 20)) is False
    assert lib.return_book("111", "m1", date(2026, 3, 20)) == 250


def test_clear_amnesty(lib, today):
    lib.clear_fine_amnesty()  # safe when nothing is configured
    lib.lend("111", "m1", today)
    lib.set_fine_amnesty(START, END)
    lib.clear_fine_amnesty()
    assert lib.is_amnesty_active(date(2026, 3, 20)) is False
    assert lib.return_book("111", "m1", date(2026, 3, 20)) == 250


def test_amnesty_return_still_removes_loan(lib, today):
    lib.lend("222", "m1", today)
    lib.set_fine_amnesty(START, END)
    assert lib.copies_available("222") == 0
    assert lib.return_book("222", "m1", date(2026, 3, 20)) == 0
    assert lib.copies_available("222") == 1
    assert lib.loans_of("m1") == []


def test_amnesty_does_not_hide_missing_loan(lib):
    lib.set_fine_amnesty(START, END)
    with pytest.raises(KeyError, match="no such loan"):
        lib.return_book("111", "m1", date(2026, 3, 20))
