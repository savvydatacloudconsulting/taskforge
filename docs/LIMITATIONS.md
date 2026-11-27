# Limitations and honest notes

What TaskForge does not do, what is only partly tested, and which choices were made because of constraints.

## The pallets/click tasks (the Track 1 entry)

- **Harbor runs were made on one machine only**: Harbor 0.25.0, Docker 29.1.3, Ubuntu 24.04 under WSL2, x86-64. All 10
  runs gave the required reward (`evidence/click/harbor_docker.json`). Each of the 5 `oracle` runs and 5 `nop` runs was
  made once.
- The test lists were recorded on Ubuntu with Python 3.12.3. In the containers (Python 3.12.15, Debian bookworm, tests
  run as root) all 2,434 listed existing tests passed.
- The image pins the Python base image by digest and the Python packages by version. The two system packages (`git`,
  `less`) are not pinned, and building needs network access to fetch them and click.
- The tests ran with network access available. They are not meant to need it, but the task files do not block it.
- The AI answers came from Claude Sonnet through Claude Code sub-agents (model setting `sonnet`) using the manual
  backend: 10 requests (5 to choose which code to read, 5 to write a task). Each sub-agent was told to read only its
  prompt file. That was an instruction, not an enforced sandbox. All 5 tasks passed on the first attempt and no answer
  was edited by hand, so click gives no example of the retry loop (the `library` example does).
- The factory itself was changed for click before the answers were requested: `src/` layout support, selecting code
  from large files, search-and-replace edits, a control run in the mutation check, and the Harbor export.
- "Not upstream" means that each task's new tests fail on click's main branch of 26 November 2026
  (`08b803cf32ceb2ae6a772c62d5da42757a897d44`). It cannot rule out the same idea under another name, or in an open pull
  request.
- Failure cases (`evidence/click/negative_controls.md`): 14 of 15 deliberately damaged copies were rejected. The one
  accepted copy shows a real weakness of the mutation check, described below.
- The solver check has **not** been run on click, so there is no independent evidence that these five instructions are
  enough to solve them.
- Feature quality was judged by reading the instructions. The tasks are opt-in additions to a mature library; some, such
  as a history of subcommand registrations, are less likely real requests than others.

## How the sample tasks were produced

- The 8 sample tasks for the `shop` example were written by **independent AI agents** that each saw only the factory's
  prompt (not the checker, the other tasks or the code of TaskForge). They were delivered through the **manual backend**
  (`--backend manual`): the factory wrote each prompt to a file, an agent wrote the reply, and the factory then built the
  package and ran every proof itself.
- Why not the live `claude` or `api` backend? On the development machine the headless Claude Code login had expired and
  there was no API key. The `claude` and `api` backends are implemented, but they are only tested with mocked
  subprocess and HTTP calls in this repository, **not against the real services**.
- Nothing in the samples was fixed by hand after the agents answered. The recorded replies in `samples/replay/shop/`
  are exactly what was verified, and `taskforge demo` replays them offline.
- All 8 samples were accepted on the first attempt, so the retry loop is demonstrated by tests with scripted answers
  (`tests/test_factory_cli_report.py`), not by retries in the real samples. One retry did happen during development:
  an over-strict "instruction leaks the solution" lint rejected a correct task. That was a bug in our lint, now fixed
  (signatures in the "Public interface" section are allowed) and covered by a test.

## What the checker proves, and what it does not

- It proves behavioural properties: the tests fail before, pass after (3 stable runs), nothing that passed before breaks,
  and deliberately broken copies of the solution are caught.
- It does **not** prove the instruction is unambiguous for a human or an AI. The optional solver check (below) gives
  some evidence; it supports only small repositories where the solver can return whole files.
- A planted bug counts as caught whenever the tests fail, including when the test code crashes. Tests with no assert
  statement can still catch most bugs in a feature that mainly raises errors or stores values, so the proof shows that
  bugs make the tests fail, not that the tests compare the right values.
- The mutation check uses a fixed set of operators and a 60% threshold. Some mutants are harmless (equivalent) and are
  not detected as such, so a perfect kill rate is not expected. Tasks whose solution has no mutable logic get the proof
  marked `skipped` rather than `pass`.
- The mutants are a random sample (at most 12 of the possible broken versions, chosen by a seed), so the kill rate can
  differ a little between runs with different seeds: generation used seed 1 or 2, `taskforge check` uses seed 0 by
  default (for example 83% versus 75% for the same task). Both pass the 60% bar; use `--seed` to try other samples.
- Mutation testing is **Python only**. For other languages that proof is reported as `skipped`, and the other three
  proofs still run (demonstrated on a small JavaScript repository).
- Per-test results are parsed only from pytest output. For other test runners the proofs use the exit code of the whole
  run, so "nothing breaks" cannot name the exact test that broke.

## The solver check

- The solvers for the sample tasks were independent AI agents from the **same model family that wrote the tasks**, working
  without running any code (they only read the prompt). Same-family solvers are expected to score higher than a
  different system would, so the solve rates in `evidence/solver/` show that the instructions are clear enough to be
  implemented from text alone. They are **not a benchmark of frontier models**.
- A 100% solve rate shows the instructions were clear enough, but it leaves nothing to compare, so the per-recipe tables
  are flat. The check becomes informative with a different or weaker solver, or with harder tasks.
- Development note: the first scoring run showed only 2 of 14 solved. The cause was our own parser, which stopped at
  the first `=== END ===` and dropped later files when a solver wrote END after every file. It is fixed (and covered by
  `test_parse_accepts_end_marker_after_every_file`), and all recorded answers were scored again. The recorded answers
  themselves were not changed.
- Only 14 tasks on two small repositories were solved, with one attempt each (pass@1), so per-recipe rates rest on very
  few tasks and are not statistically meaningful.
- The solver prompt shows the names of existing tests (as style references) but never the hidden tests or the reference
  solution; `tests/test_solver.py` asserts this. A solver can still guess behaviour from common conventions.
- Like generation, the solver goes through the manual backend in this repository's samples; the `claude` and `api`
  backends are not tested against the real services.

## Isolation and safety

- Every factory run happens in a throw-away copy of the repository with a timeout, with environment variables that look
  like secrets (`KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `CREDENTIAL`) removed. This is **not a container**: network access
  and the rest of the file system are not blocked. Run untrusted repositories inside Docker or a VM. Only the exported
  Harbor tasks run in containers; the factory itself has no Docker runner.
- Generated tests and solutions are validated for path safety (no `..`, no absolute paths, no `.git`), may not edit
  existing tests, and must create new test files only.
- The recipes are benign feature patterns. There are no special guardrails for security-related tasks; the organisers
  said they would come back on that point.

## Scale

- Prompts include whole source files while they fit (default 60,000 characters). For larger repositories there is a
  two-step mode: the AI chooses files or definitions from outlines, then sees those in full. It has been run on click
  only. Python definitions can be selected one by one; other languages are selected by whole file.
- The Harbor export builds Python tasks that use pytest. The other two starting repositories (TypeScript and C++) are
  not supported.
- The solver check and the web page have not been adapted to click.
- The variation score is a heuristic (normalised token shingles plus recipe tags and touched symbols). The 0.25
  near-duplicate threshold was set on the example repositories and may need tuning elsewhere.
- There is no cost accounting beyond counting AI calls. `--max-calls` and the answer cache limit spending.

## Package formats

The factory keeps its own small package format (used by the checker and the examples) and exports the organisers' format,
Harbor 0.25, from it. See [PACKAGE_FORMAT.md](PACKAGE_FORMAT.md).
