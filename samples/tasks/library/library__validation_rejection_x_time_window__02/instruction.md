## Background

The `library` package lets members borrow books through `Library.lend(isbn, member_id, today)`. Memberships are currently open-ended. The library now wants memberships that are only valid inside a date window, and it wants malformed input to the lending entry points rejected with precise errors instead of failing later in confusing ways.

## Requirements

1. `Member` gains two optional fields, `valid_from` and `valid_until`, both defaulting to `None` (meaning "no bound on that side"). Existing positional construction `Member("m1", "Ana")` keeps working.
2. `Library.add_member` validates the window before doing anything else (including the duplicate-id check). A value that is not `None` must be a `datetime.date` and must not be a `datetime.datetime`; otherwise raise `TypeError` with the message `valid_from must be a date` or `valid_until must be a date` respectively (check `valid_from` first). A rejected member must not be registered.
3. If both bounds are set and `valid_from` is later than `valid_until`, `add_member` raises `ValueError("valid_from is after valid_until")`. A window where both bounds are the same day is valid.
4. `Library.lend` validates `today` first, before any lookup: it must be a `datetime.date` and not a `datetime.datetime`; otherwise raise `TypeError("today must be a date")`. This check takes precedence over the existing unknown-isbn / unknown-member `KeyError`s.
5. After the existing unknown isbn / unknown member checks, and before the "already borrowed" and "no copies available" checks, `lend` enforces the membership window. Both bounds are inclusive: if `today` is earlier than `valid_from` or later than `valid_until`, raise `ValueError` with the message `membership not active on <today in ISO format>`. A rejected lend must not create a loan.
6. A loan can never outlive the membership: when the member has a `valid_until`, the due date returned by `lend` (and used for later fines) is the earlier of `today + LOAN_DAYS` and `valid_until`. Members without `valid_until` behave exactly as before.
7. `return_book` is unchanged and is allowed after a membership has expired; the late fine is computed against the (possibly capped) due date.

## Public interface

- `library.models.Member(member_id: str, name: str, valid_from: date | None = None, valid_until: date | None = None)` (still a frozen dataclass).
- `Library.add_member(member)` raises `TypeError("valid_from must be a date")`, `TypeError("valid_until must be a date")` or `ValueError("valid_from is after valid_until")` as described above; duplicate ids still raise `ValueError("duplicate member: <id>")` afterwards.
- `Library.lend(isbn, member_id, today) -> date` raises `TypeError("today must be a date")` and `ValueError("membership not active on YYYY-MM-DD")` as described above.
- No other public names change.

## Examples

```python
lib.add_member(Member("m3", "Cy", valid_from=date(2026, 3, 1), valid_until=date(2026, 3, 5)))
lib.lend("111", "m3", date(2026, 3, 1))   # -> date(2026, 3, 5), capped by valid_until
lib.lend("222", "m3", date(2026, 3, 6))   # ValueError: membership not active on 2026-03-06
lib.lend("222", "m3", "2026-03-02")       # TypeError: today must be a date
lib.add_member(Member("m4", "Di", valid_from=date(2026, 4, 1), valid_until=date(2026, 3, 1)))
                                          # ValueError: valid_from is after valid_until
```
