# Solver check report

Repository `shop` at `edb821f448`. Solver: **independent AI agent (sees instruction only)** (attempts allowed per task: 1).

The solver saw only the repository and each task's instruction. The hidden tests and the reference solution were never shown to it.

## Summary

- Tasks solved: **8 of 8** (100%); on the first try: 8 (100%)
- Single-recipe tasks: 100% of 5; combined-recipe tasks: 100% of 3
- How unsolved tasks ended: none

## By feature recipe

| Recipe | Tasks | Solved |
|---|---|---|
| audit_trail | 1 | 1 |
| dedup_merge | 1 | 1 |
| quantity_limit | 1 | 1 |
| rounding_policy | 2 | 2 |
| rule_stacking | 2 | 2 |
| tiered_rates | 1 | 1 |
| time_window | 1 | 1 |
| validation_rejection | 2 | 2 |

## Tasks

| Task | Result | Attempts | Detail |
|---|---|---|---|
| shop__audit_trail__06 | solved (first try) | 1 | all hidden tests and the existing suite pass |
| shop__dedup_merge__02 | solved (first try) | 1 | all hidden tests and the existing suite pass |
| shop__quantity_limit_x_rounding_policy__07 | solved (first try) | 1 | all hidden tests and the existing suite pass |
| shop__rounding_policy_x_validation_rejection__04 | solved (first try) | 1 | all hidden tests and the existing suite pass |
| shop__rule_stacking__03 | solved (first try) | 1 | all hidden tests and the existing suite pass |
| shop__tiered_rates_x_rule_stacking__05 | solved (first try) | 1 | all hidden tests and the existing suite pass |
| shop__time_window__01 | solved (first try) | 1 | all hidden tests and the existing suite pass |
| shop__validation_rejection__08 | solved (first try) | 1 | all hidden tests and the existing suite pass |

Read docs/LIMITATIONS.md: when the solver is the same model family as the task author, solve rates are expected to be higher than for a different system.
