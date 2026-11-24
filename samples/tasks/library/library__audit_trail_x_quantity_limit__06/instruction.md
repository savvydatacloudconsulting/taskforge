## Background
`library.Library` lets members borrow books but places no cap on how many books one member can hold at once, and it keeps no record of what happened. Add a per-member cap on simultaneous loans and an ordered audit trail of lending events. The trail must also record the lend and return attempts that were rejected, including those rejected by the new cap.

## Requirements
1. Add the module constant `MAX_LOANS_PER_MEMBER = 10` in `library/lending.py`. `Library.__init__` gains an optional keyword argument `max_loans_per_member: int = MAX_LOANS_PER_MEMBER`. A value below 1 raises `ValueError("max_loans_per_member must be at least 1")`.
2. The cap applies per member. A member may hold at most `max_loans_per_member` active loans at once, counted across all books. Other members' loans do not count toward it.
3. A `lend` that would exceed the cap raises `LoanLimitError` with the message `loan limit reached: <limit>`, where `<limit>` is the configured cap. State is unchanged: no loan is created and `copies_available` is unchanged.
4. `LoanLimitError` is a subclass of `ValueError`. It is defined in `library/lending.py` and exported from the `library` package.
5. Once a member returns a book, a slot frees up and that member may lend again.
6. `lend` checks conditions in this order. Unknown isbn or member raises `KeyError` as before. Then "already borrowed" (`ValueError("already borrowed")`). Then the loan cap. Then "no copies available" (`ValueError("no copies available")`). A member at the cap who asks for a book with no copies left therefore gets `LoanLimitError`.
7. Add `Library.history(member_id=None) -> list[dict]`. It returns the audit trail in the order the events happened (oldest first). With a `member_id` it returns only that member's events, still in order. An unknown `member_id` raises `KeyError("unknown member: <id>")`. The returned list and its dicts are copies: changing them does not change the library's internal record.
8. Every `lend` that succeeds appends an entry with `action="lend"`, `outcome="ok"` and `reason=None`.
9. Every `lend` that is rejected by one of the three `ValueError` checks appends an entry with `action="lend"` and `outcome="rejected"` before the error is raised. The `reason` is `"already_borrowed"`, `"limit_reached"` or `"no_copies"` respectively. A `lend` with an unknown isbn or member raises `KeyError` and appends nothing.
10. Every `return_book` that succeeds appends an entry with `action="return"`, `outcome="ok"` and `reason=None`. A `return_book` for a loan that does not exist appends an entry with `action="return"`, `outcome="rejected"` and `reason="no_loan"` before raising `KeyError("no such loan")`.
11. Each entry is a dict with exactly the keys `action`, `isbn`, `member_id`, `date` (the `today` argument of the call), `outcome`, `reason` and `active_loans`. `active_loans` is the number of active loans the member holds after the call finished. For a rejected call it is the member's unchanged count, so a rejection caused by the cap has `active_loans` equal to the cap.
12. Existing behaviour (due dates, fines, `loans_of`, `copies_available`, duplicate checks) is unchanged.

## Public interface
- `library.lending.MAX_LOANS_PER_MEMBER: int` (value `10`), also importable from `library`.
- `library.lending.LoanLimitError(ValueError)`, also importable from `library`.
- `Library(max_loans_per_member: int = MAX_LOANS_PER_MEMBER)`.
- `Library.history(member_id: str | None = None) -> list[dict]` with entry keys `action` (`"lend"` or `"return"`), `isbn`, `member_id`, `date` (a `datetime.date`), `outcome` (`"ok"` or `"rejected"`), `reason` (`None`, `"already_borrowed"`, `"limit_reached"`, `"no_copies"` or `"no_loan"`) and `active_loans` (int).
- Error messages: `loan limit reached: <limit>`, `max_loans_per_member must be at least 1`, `unknown member: <id>`.

## Examples
```python
lib = Library(max_loans_per_member=1)
lib.add_book(Book("111", "Dune", copies=2))
lib.add_book(Book("222", "Emma"))
lib.add_member(Member("m1", "Ana"))
lib.lend("111", "m1", date(2026, 3, 1))
lib.lend("222", "m1", date(2026, 3, 2))   # raises LoanLimitError("loan limit reached: 1")
lib.history("m1")[-1]
# {"action": "lend", "isbn": "222", "member_id": "m1", "date": date(2026, 3, 2),
#  "outcome": "rejected", "reason": "limit_reached", "active_loans": 1}
lib.return_book("111", "m1", date(2026, 3, 3))
lib.lend("222", "m1", date(2026, 3, 3))   # succeeds now
```
