## Background
The library currently charges a flat `FINE_CENTS_PER_DAY` (50 cents) for every day a book is returned after its due date. To discourage long overdue loans, the library wants an optional escalating fine schedule: the longer a book is late, the more each additional late day costs. The fine is split into bands of late days, and each band is charged at its own daily rate (a marginal scheme, like income-tax brackets: a late day is charged at the rate of the band it falls in, never at the rate of a higher band).

The fine schedule is:

| Late days (1 = first day after the due date) | Rate per late day |
|----------------------------------------------|-------------------|
| 1 to 7 (inclusive)                           | 50 cents          |
| 8 to 14 (inclusive)                          | 100 cents         |
| 15 and above                                 | 200 cents         |

A day that lies exactly on an edge belongs to the lower band: late day 7 costs 50 cents and late day 8 costs 100 cents; late day 14 costs 100 cents and late day 15 costs 200 cents.

## Requirements
1. Add a module-level function `tiered_fine(late_days)` that returns the total fine in cents for a book that is `late_days` days late, using the marginal schedule above.
2. `tiered_fine(0)` returns `0`. A book returned on the due date or earlier is not late.
3. Late days are charged band by band: for example 8 late days cost 7 days at 50 plus 1 day at 100.
4. `tiered_fine` raises `ValueError` with the message `late_days must be >= 0` when `late_days` is negative.
5. `Library.return_book` gets a new optional parameter `tiered` (default `False`). With `tiered=False` it behaves exactly as before (flat 50 cents per late day). With `tiered=True` it computes the number of late days as before (never negative) and returns `tiered_fine(late_days)`.
6. With `tiered=True` the loan is still removed and the same errors are raised as before (for example `KeyError("no such loan")` when there is no such loan).
7. `tiered_fine` must be importable from both `library.lending` and `library`.

## Public interface
- `library.lending.tiered_fine(late_days: int) -> int`, also exported as `library.tiered_fine` (add it to the package `__all__`).
- `Library.return_book(self, isbn: str, member_id: str, today: date, tiered: bool = False) -> int`.
- Error type and message for negative input: `ValueError("late_days must be >= 0")`.
- Existing names (`LOAN_DAYS`, `FINE_CENTS_PER_DAY`, `Library`, `Book`, `Member`) are unchanged.

## Examples
```python
from library import tiered_fine

tiered_fine(0)    # 0
tiered_fine(3)    # 150   (3 * 50)
tiered_fine(7)    # 350   (7 * 50)
tiered_fine(8)    # 450   (7 * 50 + 1 * 100)
tiered_fine(10)   # 650   (7 * 50 + 3 * 100)
tiered_fine(14)   # 1050  (7 * 50 + 7 * 100)
tiered_fine(15)   # 1250  (7 * 50 + 7 * 100 + 1 * 200)
tiered_fine(20)   # 2250  (7 * 50 + 7 * 100 + 6 * 200)

# lib.lend("111", "m1", date(2026, 3, 1)) is due on 2026-03-15
lib.return_book("111", "m1", date(2026, 3, 25), tiered=True)   # 10 days late -> 650
lib.return_book("111", "m1", date(2026, 3, 25))                # 10 days late, flat -> 500
```
