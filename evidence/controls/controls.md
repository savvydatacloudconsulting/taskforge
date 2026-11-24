# Checker self-test (control tasks)

| Control task | fails_before | passes_after | nothing_breaks | tests_have_teeth | Verdict | As expected |
|---|---|---|---|---|---|---|
| good_quantity_limit | PASS | PASS | PASS | PASS | accepted | yes |
| bad_tests_already_pass | FAIL | PASS | PASS | FAIL | rejected | yes |
| bad_no_tests_collected | FAIL | FAIL | skip | skip | rejected | yes |
| bad_solution_off_by_one | PASS | FAIL | skip | skip | rejected | yes |
| bad_breaks_existing_tests | PASS | PASS | FAIL | FAIL | rejected | yes |
| bad_weak_tests | PASS | PASS | PASS | FAIL | rejected | yes |
| bad_patch_does_not_apply | PASS | FAIL | skip | skip | rejected | yes |
