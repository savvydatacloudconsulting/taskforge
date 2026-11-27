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

## Track 1 results: pallets/click

Starting commit: click **8.5.1**, `cf19179e8e2fd54c601378cec9e0d21bb12b6fb1`, where its 2,434 tests pass (24 skipped,
1 expected failure). Harbor 0.25 task folders are in [`samples/harbor/click/`](samples/harbor/click).

| Task | The new feature | New tests (fail before, pass after) | Planted bugs caught |
|---|---|---|---|
| `quantity_limit_x_audit_trail__01` | cap a group's subcommands and keep a registration history | 12 | 12 of 12 |
| `validation_rejection__02` | `click.DateTime` rejects malformed format lists | 23 | 9 of 9 |
| `threshold_effect__03` | `write_dl` spreads rows once a description is tall enough | 10 | 9 of 12 |
| `eligibility_gate__04` | `click.File(allow_dash=False)` requires a real file path | 25 | 5 of 5 |
| `dedup_merge_x_eligibility_gate__05` | `consistent=True` options merge repeats and reject conflicts | 21 | 10 of 12 |

| Check | Result |
|---|---|
| Four proofs | 5 of 5 accepted on the first attempt; variation score 0.886 |
| Features absent upstream | the new tests of all 5 fail on click's main branch of 26 Nov 2026 |
| Harbor 0.25.0 loads the folders | 5 of 5 |
| **`harbor run` in Docker** ([results](evidence/click/harbor_docker.json)) | **10 of 10 runs as required**: `nop` 0.0 and `oracle` 1.0 for all 5 tasks, with all 2,434 existing tests passing in every run |
| Grading rehearsal without Docker (`taskforge simulate`) | untouched repository 0.0 and reference solution 1.0 for 5 of 5 |
| Failure cases ([report](evidence/click/negative_controls.md)) | 14 of 15 deliberately damaged copies rejected; the one accepted shows a limit of the mutation check |

The AI answers came from Claude Sonnet through Claude Code sub-agents (manual backend, 10 requests, no hand edits) and
are recorded in `samples/replay/click/`.

### Reproduce it (Linux or WSL, no API key)

```bash
bash scripts/reproduce_click.sh     # fetches click, replays the AI answers, re-checks, exports, rehearses grading
```

With Docker (and its compose plugin) running and `pip install "harbor==0.25.*"`:

```bash
bash scripts/harbor_check.sh        # harbor run -a nop must score 0.0 and -a oracle 1.0 for every task
```

The script uses `harbor` from your PATH, or the one named in the `HARBOR` variable. The run recorded here took about
7 minutes with Harbor 0.25.0 and Docker 29.1.3 on Ubuntu 24.04 (WSL2).

To generate new tasks with a live model, follow the same setup, then use `--backend claude` or `--backend api`.

## Results on the example repositories (offline, no API key)

| What | Result |
|---|---|
| `shop` example repository, 8 tasks (8 different recipes, 3 of the tasks are combinations) | **8 of 8 accepted**, mean mutation kill rate **92%**, variation score **0.81** |
| `library` example repository, 6 tasks | **6 of 6 accepted**, **1 real retry** (checker caught an arithmetic mismatch, the AI fixed it), kill rate **99%**, variation **0.79** |
| Solver check (`taskforge solve`): independent AI agents saw only the instruction | **14 of 14 tasks solved on the first try** (shop 8/8, library 6/6), judged by the hidden tests and the existing suite. Same model family as the task authors, so expect lower rates for other systems. |
| Checker self-test (`taskforge controls`) | the 1 good control task is accepted and **all 6 bad ones are rejected for the right reason** |
| Offline re-check of the shop packages (`check-all`) | **8 of 8** re-accepted from the saved files alone |
| JavaScript repository (`examples/jscart`) | goes through the same proofs; mutation testing is skipped (Python only), and reported as skipped |
| Test suite | **112 tests pass** (`evidence/pytest.txt`), including the checker's control tasks, the factory loop with scripted AI answers and the Harbor grading |

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
git clone https://github.com/savvydatacloudconsulting/taskforge.git
cd taskforge
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
examples/        shop, library (Python), jscart  samples/    task packages, Harbor folders, recorded AI answers
evidence/        reports, logs, control tasks    docs/       architecture, package format, limitations, demo script
configs/         Harbor settings for click       scripts/    reproduce click, run Harbor's checks, failure cases
```

## Honest notes

- The sample tasks were written by independent AI agents (each told to read only its prompt) through the `manual`
  backend, then verified by the factory. The live `claude` and `api` backends are implemented but only tested with mocks
  here. Claude Code was also used to build the project.
- The checker proves behaviour, not that an instruction is unambiguous; the factory's isolation is throw-away folders,
  not a container; large-repository mode has been run on click only. Full list in
  [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Licence

MIT, see [LICENSE](LICENSE).
