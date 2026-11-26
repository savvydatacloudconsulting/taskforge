# Architecture

TaskForge is a small, dependency-free Python package (standard library only; `pytest` is needed only to run the tests of
repositories that use it).

```
repository + commit          feature recipes             AI backend
        |                          |                  (claude | api | manual | replay)
        v                          v                          ^
  repo.py  --code map-->  generator.py  --prompt-->  llm.py ---+
                              |   ^
              parse + checks  |   | feedback (which proof failed, with logs)
                              v   |
                          checker.py  <--  runner.py (throw-away workspaces) , mutate.py
                              |
                              v
              variation.py (reject cosmetic duplicates)
                              |
                              v
            package.py (task folder)  -->  report.py (md / html / json)
```

| Module | Job |
|---|---|
| `repo.py` | detect language and test command, resolve the exact commit (snapshot for non-git folders), build a code map for prompts |
| `recipes.py` | 10 domain-neutral feature recipes, grouped in families; plans single and two-recipe combinations |
| `generator.py` | the factory loop: prompt, parse, validate, build patch, run proofs, retry with feedback, accept or reject |
| `checker.py` | the proofs: `fails_before`, `passes_after`, `nothing_breaks`, `tests_have_teeth` (plus a `baseline` precondition) |
| `solver.py` | the solver check: an AI sees only the repository and a task's instruction (never the tests or the reference solution); its answer is judged by the hidden tests and the existing suite; solve rates per task and per recipe |
| `mutate.py` | AST-based mutation engine for Python (comparisons, arithmetic, conditions, constants, returns, logic) |
| `runner.py` | throw-away workspaces, command execution with timeouts, environment scrubbing, patch apply and make |
| `variation.py` | variation distance: names, strings and numbers are erased, structure and recipe tags are compared |
| `llm.py` | backends: `claude` (Claude Code CLI), `api` (Anthropic API), `manual` (file exchange), `replay`; answer cache and call budget |
| `package.py` | the task folder (`task.toml`, `instruction.md`, `solution/`, `tests/`, `validation/`) |
| `report.py` | `report.md`, `report.html` (self-contained dashboard), `report.json`, built from files on disk |
| `controls.py` | the checker's self-test: one good task and six deliberately bad ones |
| `webapp.py`, `web/index.html` | `taskforge ui`: a local page that runs the factory and checker step by step, including the copy-and-paste AI mode and the "cheat the checker" buttons (127.0.0.1 only, Host check, per-session token, one run at a time) |
| `cli.py` | `ui`, `analyze`, `recipes`, `generate`, `solve`, `check`, `check-all`, `report`, `controls`, `demo` |

## The solver check (independent evidence of solvability)

The reference solution proves a task *can* be solved, but it was written by the task's own author. `taskforge solve`
gives the instruction to a different AI run that never sees the tests or the reference solution, applies its answer to a
fresh workspace, and judges it with the hidden tests plus the existing suite. Outcomes are `solved`, `tests_failed`,
`broke_existing`, `parse_error` or `invalid` (editing tests, unsafe paths, syntax errors). With `--attempts N` later
attempts see the failing test output. The report gives the solve rate overall, on the first try, for single versus
combined recipes and per recipe, which shows where instructions are ambiguous or where a solver struggles.

## Design choices

- **The checker never calls an AI.** All proofs are test runs, so anyone can repeat them offline. AI is only used to
  write tasks.
- **AI answers use plain delimiters, not JSON.** Whole files are returned and TaskForge computes the diff itself with
  git, which is far more reliable than asking a model to write a valid patch.
- **Variation is enforced, not hoped for.** Two tasks that differ only in names, strings or numbers have the same
  normalised shape (distance 0) and the later one is rejected as a cosmetic duplicate, with feedback asking for a real
  behavioural change.
- **Retries get evidence.** A failed proof is turned into feedback that includes the surviving mutants or the test
  output, and the model is asked for the complete task again (up to `--attempts`).
- **Deterministic runs.** Prompts do not depend on earlier results, so a recorded set of answers replays exactly
  (`--backend replay`) and the manual backend can answer all prompts of a batch at once.
- **Language-neutral where possible.** The test command is configurable; per-test parsing and mutation are the only
  Python-specific parts and degrade honestly (`skipped`) elsewhere.

## Backends

| Backend | Needs | Use |
|---|---|---|
| `claude` | Claude Code installed and logged in (`claude -p`, tools disabled) | live generation on a Claude subscription |
| `api` | `ANTHROPIC_API_KEY` | live generation through the API |
| `manual` | nothing | the factory writes `pending/<key>.prompt.txt`; put the reply in `<key>.txt` and run again |
| `replay` | a folder of recorded answers | offline, repeatable runs (demo, judging, tests) |

`--record-dir DIR` caches answers from a live backend so reruns are free and repeatable; `--max-calls N` stops after N
live calls.
