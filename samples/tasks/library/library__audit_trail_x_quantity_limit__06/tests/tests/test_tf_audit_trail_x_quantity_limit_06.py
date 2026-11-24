from datetime import date, timedelta

import pytest

from library import Book, Library, LoanLimitError, Member, MAX_LOANS_PER_MEMBER

D1 = date(2026, 3, 1)
D2 = date(2026, 3, 2)
D3 = date(2026, 3, 3)


def small_lib(limit=2, books=3, copies=1):
    lib = Library(max_loans_per_member=limit)
    for n in range(books):
        lib.add_book(Book(f"b{n}", f"Title {n}", copies=copies))
    lib.add_member(Member("m1", "Ana"))
    lib.add_member(Member("m2", "Ben"))
    return lib


def test_default_cap_is_ten():
    assert MAX_LOANS_PER_MEMBER == 10
    lib = small_lib(limit=10, books=0)
    lib = Library()
    for n in range(11):
        lib.add_book(Book(f"b{n}", "T"))
    lib.add_member(Member("m1", "Ana"))
    for n in range(10):
        lib.lend(f"b{n}", "m1", D1)
    with pytest.raises(LoanLimitError, match="loan limit reached: 10"):
        lib.lend("b10", "m1", D1)
    assert len(lib.loans_of("m1")) == 10


def test_invalid_cap_rejected():
    with pytest.raises(ValueError, match="max_loans_per_member must be at least 1"):
        Library(max_loans_per_member=0)


def test_cap_rejects_and_leaves_state_unchanged():
    lib = small_lib(limit=2)
    lib.lend("b0", "m1", D1)
    lib.lend("b1", "m1", D1)
    with pytest.raises(LoanLimitError) as exc:
        lib.lend("b2", "m1", D2)
    assert str(exc.value) == "loan limit reached: 2"
    assert isinstance(exc.value, ValueError)
    assert lib.loans_of("m1") == ["b0", "b1"]
    assert lib.copies_available("b2") == 1


def test_cap_is_per_member():
    lib = small_lib(limit=1, copies=2)
    lib.lend("b0", "m1", D1)
    assert lib.lend("b0", "m2", D1) == D1 + timedelta(days=14)
    with pytest.raises(LoanLimitError):
        lib.lend("b1", "m2", D1)


def test_return_frees_a_slot():
    lib = small_lib(limit=1)
    lib.lend("b0", "m1", D1)
    with pytest.raises(LoanLimitError):
        lib.lend("b1", "m1", D2)
    lib.return_book("b0", "m1", D3)
    lib.lend("b1", "m1", D3)
    assert lib.loans_of("m1") == ["b1"]


def test_check_order_cap_before_no_copies_after_already_borrowed():
    lib = small_lib(limit=1)
    lib.lend("b0", "m1", D1)
    lib.lend("b1", "m2", D1)
    with pytest.raises(LoanLimitError):
        lib.lend("b1", "m1", D2)  # at cap AND no copies left: cap wins
    with pytest.raises(ValueError, match="already borrowed") as exc:
        lib.lend("b0", "m1", D2)  # at cap AND already borrowed: already borrowed wins
    assert not isinstance(exc.value, LoanLimitError)
    with pytest.raises(ValueError, match="no copies available"):
        small = small_lib(limit=3)
        small.lend("b0", "m1", D1)
        small.lend("b0", "m2", D1)


def test_history_records_successes_in_order():
    lib = small_lib(limit=2)
    lib.lend("b0", "m1", D1)
    lib.return_book("b0", "m1", D2)
    assert lib.history() == [
        {"action": "lend", "isbn": "b0", "member_id": "m1", "date": D1,
         "outcome": "ok", "reason": None, "active_loans": 1},
        {"action": "return", "isbn": "b0", "member_id": "m1", "date": D2,
         "outcome": "ok", "reason": None, "active_loans": 0},
    ]


def test_history_records_cap_rejection_with_active_count():
    lib = small_lib(limit=1)
    lib.lend("b0", "m1", D1)
    with pytest.raises(LoanLimitError):
        lib.lend("b1", "m1", D2)
    assert lib.history("m1")[-1] == {
        "action": "lend", "isbn": "b1", "member_id": "m1", "date": D2,
        "outcome": "rejected", "reason": "limit_reached", "active_loans": 1,
    }
    assert len(lib.history()) == 2


def test_history_records_other_rejections():
    lib = small_lib(limit=3)
    lib.lend("b0", "m1", D1)
    with pytest.raises(ValueError, match="already borrowed"):
        lib.lend("b0", "m1", D2)
    with pytest.raises(ValueError, match="no copies available"):
        lib.lend("b0", "m2", D2)
    with pytest.raises(KeyError, match="no such loan"):
        lib.return_book("b1", "m2", D3)
    reasons = [(e["action"], e["outcome"], e["reason"]) for e in lib.history()]
    assert reasons == [
        ("lend", "ok", None),
        ("lend", "rejected", "already_borrowed"),
        ("lend", "rejected", "no_copies"),
        ("return", "rejected", "no_loan"),
    ]
    assert lib.history("m2")[-1]["active_loans"] == 0


def test_unknown_isbn_or_member_not_recorded():
    lib = small_lib()
    with pytest.raises(KeyError):
        lib.lend("nope", "m1", D1)
    with pytest.raises(KeyError):
        lib.lend("b0", "ghost", D1)
    assert lib.history() == []


def test_history_filter_by_member_and_unknown_member():
    lib = small_lib(limit=2, copies=2)
    lib.lend("b0", "m1", D1)
    lib.lend("b0", "m2", D2)
    lib.lend("b1", "m1", D3)
    assert [e["isbn"] for e in lib.history("m1")] == ["b0", "b1"]
    assert [e["member_id"] for e in lib.history("m2")] == ["m2"]
    assert len(lib.history()) == 3
    with pytest.raises(KeyError, match="unknown member: ghost"):
        lib.history("ghost")


def test_history_returns_copies():
    lib = small_lib()
    lib.lend("b0", "m1", D1)
    snapshot = lib.history()
    snapshot[0]["outcome"] = "tampered"
    snapshot.clear()
    assert lib.history()[0]["outcome"] == "ok"
    assert len(lib.history()) == 1
