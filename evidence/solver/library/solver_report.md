# Solver check report

Repository `library` at `55a3fafe5b`. Solver: **independent AI agent (sees instruction only)** (attempts allowed per task: 1).

The solver saw only the repository and each task's instruction. The hidden tests and the reference solution were never shown to it.

## Summary

- Tasks solved: **6 of 6** (100%); on the first try: 6 (100%)
- Single-recipe tasks: 100% of 4; combined-recipe tasks: 100% of 2
- How unsolved tasks ended: none

## By feature recipe

| Recipe | Tasks | Solved |
|---|---|---|
| audit_trail | 1 | 1 |
| quantity_limit | 1 | 1 |
| rounding_policy | 1 | 1 |
| rule_stacking | 1 | 1 |
| tiered_rates | 1 | 1 |
| time_window | 2 | 2 |
| validation_rejection | 1 | 1 |

## Tasks

| Task | Result | Attempts | Detail |
|---|---|---|---|
| library__audit_trail_x_quantity_limit__06 | solved (first try) | 1 | all hidden tests and the existing suite pass |
| library__rounding_policy__04 | solved (first try) | 1 | all hidden tests and the existing suite pass |
| library__rule_stacking__05 | solved (first try) | 1 | all hidden tests and the existing suite pass |
| library__tiered_rates__03 | solved (first try) | 1 | all hidden tests and the existing suite pass |
| library__time_window__01 | solved (first try) | 1 | all hidden tests and the existing suite pass |
| library__validation_rejection_x_time_window__02 | solved (first try) | 1 | all hidden tests and the existing suite pass |

Read docs/LIMITATIONS.md: when the solver is the same model family as the task author, solve rates are expected to be higher than for a different system.
