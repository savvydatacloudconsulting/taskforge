# Task package format

One folder per task, modelled on SWE-bench / Harbor style tasks:

```
shop__time_window__01/
  task.toml                    which repository and version, how to run tests
  instruction.md               the requirements, in plain words
  solution/solution.patch      the reference implementation, as a unified diff
  tests/tests/test_tf_x.py     feature tests (files under tests/ are copied into the repo root as-is)
  validation/proofs.json       evidence from the checker (written by taskforge)
  validation/attempts.json     every attempt, why it was accepted or retried
```

## task.toml

```toml
schema = "1"

[task]
id = "shop__time_window__01"
title = "..."
recipes = ["time_window"]          # the feature recipes used

[repo]
name = "shop"
language = "python"
base_commit = "edb821f4..."        # exact starting version
snapshot = true                    # true when the repository was a plain folder, not git

[run]
test_command = "{python} -m pytest -q"
feature_test_command = "..."       # optional; {files} is replaced by the feature test paths
setup_command = "..."              # optional; run once in each fresh workspace
timeout_seconds = 120
feature_tests = ["tests/test_tf_time_window_01.py"]

[meta]
generator = "taskforge 0.1.0"
attempts = 1
```

`{python}` means the Python that runs taskforge. For a git repository `base_commit` is the real commit id. For a plain
folder TaskForge makes a deterministic snapshot commit (fixed author, date and line endings), so the id is the same on
every machine.

## How a package is verified

1. A fresh copy of the repository at `base_commit` is made.
2. `baseline`: the repository's own tests pass.
3. `fails_before`: the feature tests are added; they must fail.
4. `passes_after`: `solution.patch` is applied; the feature tests must pass, identically in 3 runs.
5. `nothing_breaks`: the full suite passes and every test that passed before still passes.
6. `tests_have_teeth`: broken copies of the changed lines are made; the feature tests must catch at least 60%.

Anyone can repeat this without an AI:

```
taskforge check samples/tasks/shop/<task> --repo examples/shop
taskforge check-all samples/tasks/shop --repo examples/shop
```

In a `src/` layout, `task.toml` also records `pythonpath = "src"` so each workspace tests its own copy of the library.

## Harbor export (the organisers' format)

`taskforge export` writes one Harbor 0.25 task folder per accepted package (`samples/harbor/click/`):

```
click__eligibility_gate__04/
  task.toml                     schema 1.4; [metadata] repository, 40-character base_commit, licence; limits
  instruction.md                the only file shown to the AI being evaluated
  environment/Dockerfile        pinned Python image and packages; fetches only the base commit
  solution/solve.sh             applies solution.patch
  solution/solution.patch
  tests/test.sh                 writes /logs/verifier/reward.txt
  tests/grade.py                restores existing tests, runs both lists, computes the reward
  tests/tf_outcomes.py          records each test's outcome
  tests/config.json
  tests/fail_to_pass.json
  tests/pass_to_pass.json
  tests/files/tests/test_tf_x.py   the new tests
```

Reward: `0.0` if any `pass_to_pass` test does not pass; `1.0` if every `fail_to_pass` test passes; otherwise the share
of `fail_to_pass` tests that pass. If pytest cannot be started, no reward file is written.

```
taskforge export samples/tasks/click --repo <click clone> --config configs/click.json --out samples/harbor/click
taskforge simulate samples/harbor/click --repo <click clone>     # rehearsal without Docker
bash scripts/harbor_check.sh                                     # Harbor's nop and oracle runs (needs Docker)
```

Repository settings (commit, licence, image, packages, install command) are in `configs/click.json`.
