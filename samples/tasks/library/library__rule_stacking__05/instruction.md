## Background

Late fines are currently a flat `FINE_CENTS_PER_DAY` (50 cents) per late day. The library wants two independent adjustments to the daily fine rate that can both apply to the same return:

* a **high-demand** flag on a book (popular titles are fined more heavily), and
* a **reduced-rate** flag on a member (e.g. students and seniors are fined less).

When both apply they must be combined in a fixed order, and the resulting daily rate may never exceed a maximum.

## Requirements

1. Add three module-level constants in `library/lending.py`, also exported from the `library` package: `DEMAND_MULTIPLIER = 3`, `REDUCED_MEMBER_DISCOUNT_CENTS = 20` and `MAX_DAILY_RATE_CENTS = 140`.
2. `Library.set_high_demand(isbn, flag)` marks (`flag` true) or unmarks (`flag` false) a book as high-demand. Books are not high-demand by default. An unknown ISBN raises `KeyError`.
3. `Library.set_reduced_rate(member_id, flag)` marks (`flag` true) or unmarks (`flag` false) a member as reduced-rate. Members are not reduced-rate by default. An unknown member raises `KeyError`.
4. `Library.daily_fine_rate(isbn, member_id)` returns the daily fine in cents for that book and member. It starts from `FINE_CENTS_PER_DAY` and applies the rules in this exact order:
   1. if the book is high-demand, multiply the rate by `DEMAND_MULTIPLIER`;
   2. then, if the member is reduced-rate, subtract `REDUCED_MEMBER_DISCOUNT_CENTS`;
   3. finally, cap the result at `MAX_DAILY_RATE_CENTS` (the cap is applied last, after the discount).
   An unknown ISBN or unknown member raises `KeyError`.
5. `Library.return_book` must compute the fine as `late_days * daily_fine_rate(isbn, member_id)`, using the flags as they are at the moment of return. Late days are computed exactly as before (never negative), so an on-time return costs 0 whatever the flags. The existing errors (`KeyError("no such loan")`) are unchanged, and fines for books and members with no flags set stay exactly as before.
6. Flags are independent per book and per member: a flag set on one book or member never changes the rate for another. Flags persist after a book is returned.

## Public interface

* `library.lending.DEMAND_MULTIPLIER: int` (3), `REDUCED_MEMBER_DISCOUNT_CENTS: int` (20), `MAX_DAILY_RATE_CENTS: int` (140); all three importable from `library` as well.
* `Library.set_high_demand(self, isbn: str, flag: bool) -> None`
* `Library.set_reduced_rate(self, member_id: str, flag: bool) -> None`
* `Library.daily_fine_rate(self, isbn: str, member_id: str) -> int`
* Unknown ISBN or member id raises `KeyError` (same lookups as the existing code).
* `Library.return_book(isbn, member_id, today) -> int` keeps its signature and returns the fine in cents.

## Examples

```python
lib.set_high_demand("111", True)
lib.daily_fine_rate("111", "m2")   # 150 capped to 140
lib.set_reduced_rate("m1", True)
lib.daily_fine_rate("222", "m1")   # 50 - 20 = 30
lib.daily_fine_rate("111", "m1")   # 150 - 20 = 130 (under the cap)
```

If "111" is high-demand and "m1" is reduced-rate, returning it 3 days late costs `3 * 130 = 390` cents. If only the book is high-demand, it costs `3 * 140 = 420` cents. If neither flag is set, it costs `3 * 50 = 150` cents.
