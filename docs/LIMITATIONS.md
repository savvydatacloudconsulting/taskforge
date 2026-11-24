# Limitations and honest notes

What TaskForge does not do, what is only partly tested, and which choices were made because of constraints.

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
- It does **not** prove the instruction is unambiguous for a human or an AI. Solvability is shown by our own reference
  solution passing the tests; an independent solver agent is a natural next step and is not built.
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

- Every run happens in a throw-away copy of the repository with a timeout, with environment variables that look like
  secrets (`KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `CREDENTIAL`) removed. This is **not a container**: network access and
  the rest of the file system are not blocked. Run untrusted repositories inside Docker or a VM. A Docker runner was not
  built (Docker was not available on the development machine).
- Generated tests and solutions are validated for path safety (no `..`, no absolute paths, no `.git`), may not edit
  existing tests, and must create new test files only.
- The recipes are benign feature patterns. There are no special guardrails for security-related tasks; the organisers
  said they would come back on that point.

## Scale

- Prompts include whole source files while they fit (default 60,000 characters), and outlines for the rest. For larger
  repositories there is a two-step mode (ask which files to change, then show them in full). It is covered by unit tests
  on small examples but has **not been run on a large repository**.
- The variation score is a heuristic (normalised token shingles plus recipe tags and touched symbols). The 0.25
  near-duplicate threshold was set on the example repositories and may need tuning elsewhere.
- There is no cost accounting beyond counting AI calls. `--max-calls` and the answer cache limit spending.

## Package format

The organisers are still finalising their official task template. The layout used here follows the anatomy described in
the explainer session (a task file naming the repository and version, the instruction as markdown, the reference solution
as a diff under `solution/`, and the tests). It will need a small adapter when the official template is published.
