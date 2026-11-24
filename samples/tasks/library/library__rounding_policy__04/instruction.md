## Background

Late fines are currently `late_days * FINE_CENTS_PER_DAY` cents. The library now wants to give individual members a percentage discount on their late fines (for example a volunteer or a student discount). A percentage of a fine is usually not a whole number of cents, so the library needs an exact rounding policy: the discounted fine is rounded to the nearest 5 cents, with halves rounded up, and any fine that is not fully waived is charged at least 5 cents.

## Requirements

1. Add a module-level constant `FINE_ROUND_UNIT_CENTS = 5` in `library/lending.py`.
2. Add a module-level function `discounted_fine(fine_cents: int, percent: int) -> int` in `library/lending.py` that returns the amount payable in cents after applying a discount of `percent` percent to `fine_cents`. The exact amount is `fine_cents * (100 - percent) / 100`. It is rounded to the nearest multiple of `FINE_ROUND_UNIT_CENTS`; an exact tie between two multiples goes UP (round half up, not banker's rounding).
3. Minimum charge: if `fine_cents > 0` and `percent < 100`, the result is never below `FINE_ROUND_UNIT_CENTS`, even when the exact amount rounds down to 0. If `fine_cents == 0` or `percent == 100`, the result is `0`.
4. `discounted_fine` raises `ValueError("fine_cents must not be negative")` when `fine_cents < 0`, and `ValueError("percent must be between 0 and 100")` when `percent` is below 0 or above 100 (0 and 100 are both valid). The fine check is done first.
5. Add `Library.set_fine_discount(member_id: str, percent: int) -> None`. It stores the member's discount percent (a later call replaces the earlier value; `0` means no discount). An unknown member raises `KeyError("unknown member: <id>")` (the same error the library already uses). A percent outside 0 to 100 raises `ValueError("percent must be between 0 and 100")`. The member is checked before the percent, and an invalid call must not change the stored discount.
6. `Library.return_book` must return `discounted_fine(late_days * FINE_CENTS_PER_DAY, discount)` where `discount` is the percent set for the returning member at the time of the return (default `0`). Members without a discount, and members with discount `0`, get exactly the same fines as before. Discounts are per member and do not affect other members.
7. Export `discounted_fine` and `FINE_ROUND_UNIT_CENTS` from the `library` package (add them to `__all__`).

## Public interface

- `library.lending.FINE_ROUND_UNIT_CENTS == 5` (also importable from `library`)
- `library.lending.discounted_fine(fine_cents: int, percent: int) -> int` (also importable from `library`)
- `Library.set_fine_discount(member_id: str, percent: int) -> None`
- Errors: `ValueError("fine_cents must not be negative")`, `ValueError("percent must be between 0 and 100")`, `KeyError("unknown member: <id>")`
- `Library.return_book(isbn, member_id, today) -> int` keeps its signature; it now applies the member's discount.

## Examples

```python
discounted_fine(50, 10)    # exact 45.0   -> 45
discounted_fine(50, 15)    # exact 42.5   -> tie between 40 and 45 -> 45
discounted_fine(50, 25)    # exact 37.5   -> tie between 35 and 40 -> 40
discounted_fine(100, 33)   # exact 67.0   -> nearest multiple of 5 is 65
discounted_fine(150, 95)   # exact 7.5    -> tie between 5 and 10 -> 10
discounted_fine(150, 98)   # exact 3.0    -> rounds to 5
discounted_fine(50, 99)    # exact 0.5    -> rounds to 0, minimum charge -> 5
discounted_fine(50, 100)   # fully waived -> 0
discounted_fine(0, 50)     # nothing owed -> 0

lib.set_fine_discount("m1", 25)
lib.lend("111", "m1", today)
lib.return_book("111", "m1", today + timedelta(days=15))  # 1 day late: fine 50, discounted -> 40
```
