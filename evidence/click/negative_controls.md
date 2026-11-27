# Failure cases on pallets/click

Each accepted task was damaged on purpose and checked again, without AI. 14 of 15 damaged tasks were rejected.

| Task | Damage | Check expected to fail | Verdict | First failed check |
|---|---|---|---|---|
| click__dedup_merge_x_eligibility_gate__05 | Tests that already pass | fails_before | rejected | fails_before: the feature tests already PASS on the original repository, so they do not test any new behaviour |
| click__dedup_merge_x_eligibility_gate__05 | A broken solution | passes_after | rejected | passes_after: the feature tests FAIL with the reference solution applied |
| click__dedup_merge_x_eligibility_gate__05 | Tests with the assertions removed | tests_have_teeth | rejected | tests_have_teeth: tests caught only 1 of 12 broken versions (8%, need 60%) |
| click__eligibility_gate__04 | Tests that already pass | fails_before | rejected | fails_before: the feature tests already PASS on the original repository, so they do not test any new behaviour |
| click__eligibility_gate__04 | A broken solution | passes_after | rejected | passes_after: the feature tests FAIL with the reference solution applied |
| click__eligibility_gate__04 | Tests with the assertions removed | tests_have_teeth | rejected | tests_have_teeth: tests caught only 0 of 5 broken versions (0%, need 60%) |
| click__quantity_limit_x_audit_trail__01 | Tests that already pass | fails_before | rejected | fails_before: the feature tests already PASS on the original repository, so they do not test any new behaviour |
| click__quantity_limit_x_audit_trail__01 | A broken solution | passes_after | rejected | passes_after: the feature tests FAIL with the reference solution applied |
| click__quantity_limit_x_audit_trail__01 | Tests with the assertions removed | tests_have_teeth | ACCEPTED | every check passed |
| click__threshold_effect__03 | Tests that already pass | fails_before | rejected | fails_before: the feature tests already PASS on the original repository, so they do not test any new behaviour |
| click__threshold_effect__03 | A broken solution | passes_after | rejected | passes_after: the feature tests FAIL with the reference solution applied |
| click__threshold_effect__03 | Tests with the assertions removed | tests_have_teeth | rejected | tests_have_teeth: tests caught only 1 of 12 broken versions (8%, need 60%) |
| click__validation_rejection__02 | Tests that already pass | fails_before | rejected | fails_before: the feature tests already PASS on the original repository, so they do not test any new behaviour |
| click__validation_rejection__02 | A broken solution | passes_after | rejected | passes_after: the feature tests FAIL with the reference solution applied |
| click__validation_rejection__02 | Tests with the assertions removed | tests_have_teeth | rejected | fails_before: the feature tests already PASS on the original repository, so they do not test any new behaviour |

## Why a damaged copy can still be accepted

A planted bug counts as caught whenever the tests fail, including when the remaining test code crashes. A feature that is mostly about stored values and errors can therefore keep a high kill rate with no assert statement left. The check shows that bugs make the tests fail, not that the tests compare the right values.
