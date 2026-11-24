from datetime import date, datetime, timedelta

import pytest

from library import FINE_CENTS_PER_DAY, LOAN_DAYS, Member


def test_member_window_fields_default_to_none():
    m = Member("x", "Xi")
    assert m.valid_from is None
    assert m.valid_until is None


def test_add_member_rejects_non_date_bounds(lib):
    with pytest.raises(TypeError, match="valid_from must be a date"):
        lib.add_member(Member("m3", "Cy", valid_from="2026-03-01"))
    with pytest.raises(TypeError, match="valid_until must be a date"):
        lib.add_member(Member("m3", "Cy", valid_until=20260301))
    with pytest.raises(TypeError, match="valid_from must be a date"):
        lib.add_member(Member("m3", "Cy", valid_from=datetime(2026, 3, 1, 9, 0)))
    with pytest.raises(TypeError, match="valid_until must be a date"):
        lib.add_member(Member("m3", "Cy", valid_until=datetime(2026, 3, 1, 9, 0)))


def test_valid_from_is_checked_before_valid_until(lib):
    with pytest.raises(TypeError, match="valid_from must be a date"):
        lib.add_member(Member("m3", "Cy", valid_from="x", valid_until="y"))


def test_add_member_rejects_reversed_window_and_does_not_register(lib, today):
    with pytest.raises(ValueError, match="valid_from is after valid_until"):
        lib.add_member(
            Member("m3", "Cy", valid_from=today + timedelta(days=1), valid_until=today)
        )
    with pytest.raises(KeyError):
        lib.loans_of("m3")
    # the id is still free, so a corrected member can be registered
    lib.add_member(Member("m3", "Cy", valid_from=today, valid_until=today))
    assert lib.loans_of("m3") == []


def test_validation_runs_before_duplicate_check(lib, today):
    with pytest.raises(ValueError, match="valid_from is after valid_until"):
        lib.add_member(
            Member("m1", "Dup", valid_from=today + timedelta(days=2), valid_until=today)
        )


def test_single_day_window_is_valid(lib, today):
    lib.add_member(Member("m3", "Cy", valid_from=today, valid_until=today))
    assert lib.lend("111", "m3", today) == today


def test_lend_rejects_non_date_today(lib, today):
    with pytest.raises(TypeError, match="today must be a date"):
        lib.lend("111", "m1", "2026-03-01")
    with pytest.raises(TypeError, match="today must be a date"):
        lib.lend("111", "m1", datetime(2026, 3, 1, 12, 0))
    assert lib.loans_of("m1") == []


def test_today_type_check_precedes_lookups(lib):
    with pytest.raises(TypeError, match="today must be a date"):
        lib.lend("999", "nobody", None)


def test_lend_before_window_start_is_rejected(lib, today):
    lib.add_member(
        Member("m3", "Cy", valid_from=today + timedelta(days=1), valid_until=today + timedelta(days=30))
    )
    with pytest.raises(ValueError, match="membership not active on 2026-03-01"):
        lib.lend("111", "m3", today)
    assert lib.loans_of("m3") == []
    assert lib.copies_available("111") == 2


def test_lend_window_bounds_are_inclusive(lib, today):
    start = today
    end = today + timedelta(days=5)
    lib.add_member(Member("m3", "Cy", valid_from=start, valid_until=end))
    assert lib.lend("111", "m3", start) == end  # first day is allowed
    lib.return_book("111", "m3", start)
    assert lib.lend("111", "m3", end) == end  # last day is allowed
    lib.return_book("111", "m3", end)
    with pytest.raises(ValueError, match="membership not active on 2026-03-07"):
        lib.lend("111", "m3", end + timedelta(days=1))


def test_open_ended_bounds(lib, today):
    lib.add_member(Member("m3", "Cy", valid_from=today))
    lib.add_member(Member("m4", "Di", valid_until=today + timedelta(days=100)))
    with pytest.raises(ValueError, match="membership not active"):
        lib.lend("111", "m3", today - timedelta(days=1))
    assert lib.lend("111", "m3", today + timedelta(days=500)) == today + timedelta(
        days=500 + LOAN_DAYS
    )
    assert lib.lend("222", "m4", today - timedelta(days=400)) == today - timedelta(
        days=400 - LOAN_DAYS
    )


def test_due_date_is_capped_by_valid_until(lib, today):
    lib.add_member(Member("m3", "Cy", valid_until=today + timedelta(days=5)))
    assert lib.lend("111", "m3", today) == today + timedelta(days=5)


def test_due_date_not_capped_when_membership_outlasts_loan(lib, today):
    lib.add_member(Member("m3", "Cy", valid_until=today + timedelta(days=LOAN_DAYS)))
    lib.add_member(Member("m4", "Di", valid_until=today + timedelta(days=365)))
    assert lib.lend("111", "m3", today) == today + timedelta(days=LOAN_DAYS)
    assert lib.lend("111", "m4", today) == today + timedelta(days=LOAN_DAYS)


def test_fine_uses_capped_due_date_and_return_works_after_expiry(lib, today):
    end = today + timedelta(days=5)
    lib.add_member(Member("m3", "Cy", valid_until=end))
    lib.lend("111", "m3", today)
    # the membership expired on `end`; returning is still allowed and is fined from the capped due date
    assert lib.return_book("111", "m3", end + timedelta(days=3)) == 3 * FINE_CENTS_PER_DAY
    assert lib.loans_of("m3") == []


def test_window_check_precedes_already_borrowed(lib, today):
    end = today + timedelta(days=2)
    lib.add_member(Member("m3", "Cy", valid_until=end))
    lib.lend("111", "m3", today)
    with pytest.raises(ValueError, match="membership not active on 2026-03-04"):
        lib.lend("111", "m3", end + timedelta(days=1))
    with pytest.raises(ValueError, match="already borrowed"):
        lib.lend("111", "m3", today)
