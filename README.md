# TaskForge

**A reusable factory that turns a code repository into new feature-development tasks, and refuses to ship any task it
cannot prove is fair.** Built for the Innodata AI Hackathon, Track 1 (Coding Task Factory).

Each task is a small folder: a plain-words **instruction**, a **reference solution** (a diff), and **tests**. An
automatic checker, which never uses an AI, then earns the task four proofs:

| Proof | What it shows |
|---|---|
| **Fails before** | the new feature tests fail on the original repository, so they really test something new |
| **Passes after** | with the reference solution applied they pass, identically in 3 runs (no flakiness) |
| **Nothing breaks** | the whole existing suite still passes and every test that passed before still passes |
| **Tests have teeth** | deliberately broken copies of the solution are caught by the tests (mutation testing) |

On top of the proofs, `taskforge solve` runs a **solver check**: a different AI sees only the repository and each task's
instruction (never the tests or the reference solution), and the hidden tests judge its answer. That is independent
evidence that a task is clear and solvable by someone other than its author, and it gives a solve rate per feature recipe.

Tasks that cannot earn all four proofs are retried with the evidence (up to 3 attempts) and then rejected. Tasks that
differ only in names, strings or numbers are rejected as **cosmetic duplicates**, so variation is real.

## Results (all reproducible offline, no API key)

| What | Result |
|---|---|
| `shop` example repository, 8 tasks (8 different recipes, 3 of the tasks are combinations) | **8 of 8 accepted**, mean mutation kill rate **92%**, variation score **0.81** |
| `library` example repository, 6 tasks | **6 of 6 accepted**, **1 real retry** (checker caught an arithmetic mismatch, the AI fixed it), kill rate **99%**, variation **0.79** |
| Solver check (`taskforge solve`): independent AI agents saw only the instruction | **14 of 14 tasks solved on the first try** (shop 8/8, library 6/6), judged by the hidden tests and the existing suite. Same model family as the task authors, so expect lower rates for other systems. |
| Checker self-test (`taskforge controls`) | the 1 good control task is accepted and **all 6 bad ones are rejected for the right reason** |
| Offline re-check of the shop packages (`check-all`) | **8 of 8** re-accepted from the saved files alone |
| JavaScript repository (`examples/jscart`) | goes through the same proofs; mutation testing is skipped (Python only), and reported as skipped |
| Test suite | **103 tests pass** (`evidence/pytest.txt`), including the checker's control tasks and the factory loop with scripted AI answers |

Evidence lives in `evidence/` and the generated task packages in `samples/tasks/`. See
[docs/LIMITATIONS.md](docs/LIMITATIONS.md) for how the samples were made and what is not covered. Read that file first.

## Try it in the browser

```bash
taskforge ui          # then open http://localhost:8765
```

The page runs the real factory and shows each step as it happens: read the repository and pick a recipe, the feature
request, the reference solution and tests, the three checks, the planted bugs, and the saved package. Three buttons then
try to **cheat the checker** (tests that already pass, a broken solution, tests with the assertions removed); it must
reject all three. "Who writes the exam?" offers a recorded example (offline), any AI chat by copy and paste (no key
needed), Claude Code, or the Anthropic API.

The server listens on 127.0.0.1 only and needs a per-session token, but it does run repository tests and AI-written code
on your computer, so only point it at repositories you trust.

## Quick start

Needs Python 3.11+ and git. No other packages (pytest only for the repositories you test).

```bash
git clone <this repository> && cd taskforge
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

taskforge controls                  # self-test: accepts the good task, rejects 6 bad ones (about 1 minute)
taskforge demo                      # whole pipeline on examples/shop, offline, replaying recorded AI answers
taskforge demo --example library    # the same on a second repository
taskforge solve samples/tasks/shop --repo examples/shop --backend replay --replay-dir samples/solver_replay/shop
                                    # solver check, offline: replays recorded solver answers, judged by the hidden tests
```

Open `taskforge_out/demo_shop/report.html` for the dashboard. Re-check one saved task without any AI:

```bash
taskforge check samples/tasks/shop/shop__time_window__01 --repo examples/shop
taskforge check-all samples/tasks/shop --repo examples/shop
```

## Generate tasks for your own repository

```bash
taskforge analyze path/to/repo                       # language, commit, test command, baseline check
taskforge generate path/to/repo -n 8 --backend claude --record-dir cache/
taskforge solve taskforge_out/repo/accepted --repo path/to/repo --backend claude   # solver check
```

| Backend | Needs | Notes |
|---|---|---|
| `claude` | Claude Code installed and logged in | uses your subscription, no API key |
| `api` | `ANTHROPIC_API_KEY` | copy `.env.example` to `.env` (never commit `.env`) |
| `manual` | nothing | the factory writes `pending/<key>.prompt.txt`; any AI (or person) writes the reply to `<key>.txt`; run again |
| `replay` | recorded answers | deterministic, offline (used by `taskforge demo`) |

Useful options: `--recipes quantity_limit,time_window`, `--attempts 3`, `--seed N`, `--max-calls N`,
`--test-command "..."`, `--feature-test-command "node --test {files}"`, `--setup-command "..."`.
Any language works if you give it a test command; per-test checks and mutation testing are Python-only.

## What is in a task package

```
shop__time_window__01/
  task.toml                 repository, exact base commit, test commands, recipes
  instruction.md            the requirements
  solution/solution.patch   the reference implementation
  tests/...                 feature tests, copied into the repo root as-is
  validation/               proofs.json (evidence) and attempts.json (every attempt)
```

Details: [docs/PACKAGE_FORMAT.md](docs/PACKAGE_FORMAT.md). How it works: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
The 10 feature recipes (limits, eligibility rules, thresholds, tiers, rounding, time windows, validation, audit trails,
de-duplication, rule stacking) can be combined, so tasks differ in behaviour and interactions: `taskforge recipes`.

## Repository layout

```
src/taskforge/   the factory (stdlib only)       tests/      test-suite incl. the checker's control tasks
examples/        shop, library (Python), jscart  samples/    task packages + recorded AI answers (replay)
evidence/        reports, logs, control tasks    docs/       architecture, package format, limitations, demo script
```

## Honest notes

- The sample tasks were written by independent AI agents (each saw only its prompt) through the `manual` backend, then
  verified by the factory. The live `claude` and `api` backends are implemented but only tested with mocks here.
- The checker proves behaviour, not that an instruction is unambiguous; the isolation is throw-away folders, not a
  container; large-repository mode is untested at scale. Full list in [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Licence

MIT, see [LICENSE](LICENSE).
