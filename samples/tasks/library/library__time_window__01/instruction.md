## Background
The library occasionally runs a "fine amnesty" campaign: for a limited period, members who bring overdue books back
are not charged a late fine. Whether the amnesty applies depends only on the date on which the book is **returned**
(the `today` argument of `Library.return_book`), not on when the book was borrowed or when it was due. The current
date must always be passed in; nothing may read the real clock.

## Requirements
1. `Library` gains a single, optional amnesty window. Initially no amnesty is configured.
2. `Library.set_fine_amnesty(start, end)` configures the window. The window is half-open: it includes `start` and
   excludes `end`. A date `d` is inside the window when `start <= d < end`.
3. `set_fine_amnesty` raises `ValueError("invalid amnesty window")` when `end <= start`. In that case any previously
   configured window must be left unchanged.
4. Calling `set_fine_amnesty` again replaces the previously configured window (there is never more than one window).
5. `Library.clear_fine_amnesty()` removes the configured window. It is safe to call when none is configured.
6. `Library.is_amnesty_active(today)` returns `True` when an amnesty window is configured and `today` is inside it,
   otherwise `False`.
7. `Library.return_book(isbn, member_id, today)` returns `0` as the fine whenever `is_amnesty_active(today)` is `True`,
   even if the book is overdue. The loan is still removed exactly as before (the copy becomes available again and the
   book disappears from `loans_of`).
8. When the amnesty is not active on the return date (no window, before `start`, on or after `end`), the fine is
   computed exactly as before (`FINE_CENTS_PER_DAY` per late day).
9. Errors from `return_book` are unchanged: returning a book that is not on loan still raises `KeyError("no such loan")`,
   even if an amnesty is active.

## Public interface
- `Library.set_fine_amnesty(self, start: date, end: date) -> None`
  - raises `ValueError` with message `invalid amnesty window` if `end <= start`.
- `Library.clear_fine_amnesty(self) -> None`
- `Library.is_amnesty_active(self, today: date) -> bool`
- `Library.return_book(self, isbn: str, member_id: str, today: date) -> int` (existing; behaviour extended as above)

No new constants or modules are required. `LOAN_DAYS` is 14 and `FINE_CENTS_PER_DAY` is 50.

## Examples
```python
from datetime import date
from library import Book, Library, Member

lib = Library()
lib.add_book(Book("111", "Dune"))
lib.add_member(Member("m1", "Ana"))
lib.lend("111", "m1", date(2026, 3, 1))          # due 2026-03-15

lib.set_fine_amnesty(date(2026, 3, 18), date(2026, 3, 25))
lib.is_amnesty_active(date(2026, 3, 18))          # True  (start is inclusive)
lib.is_amnesty_active(date(2026, 3, 25))          # False (end is exclusive)
lib.return_book("111", "m1", date(2026, 3, 20))   # 0 instead of 250

lib.lend("111", "m1", date(2026, 3, 1))
lib.return_book("111", "m1", date(2026, 3, 25))   # 500: 10 days late, amnesty over
```
