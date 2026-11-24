# Evidence

| Path | What it shows | How to reproduce |
|---|---|---|
| `shop/report.html`, `report.md`, `report.json`, `run.json` | 8 tasks for `examples/shop`: four proofs per task, mutation kill rates, variation matrix | `taskforge demo` |
| `shop/recheck.txt` | the 8 saved packages re-verified from their files alone (no AI) | `taskforge check-all samples/tasks/shop --repo examples/shop` |
| `library/report.*`, `run.json` | 6 tasks for `examples/library`, including one real retry (see `library__tiered_rates__03/validation/attempts.json` in `samples/tasks/library`) | `taskforge demo --example library` |
| `solver/shop/`, `solver/library/` (`solver_report.html`, `solve_results.json`) | the solver check: an AI that saw only the instruction solved 14 of 14 tasks, judged by the hidden tests | `taskforge solve samples/tasks/shop --repo examples/shop --backend replay --replay-dir samples/solver_replay/shop` |
| `controls/controls.md` and `controls/<name>/` | the checker's self-test: 1 good and 6 deliberately bad task packages, each with the verdict the checker gave | `taskforge controls --out evidence/controls` |
| `pytest.txt` | the full test-suite log | `pytest -v` |

Local folder and user names were redacted from `pytest.txt` (shown as `<project>` and `~`); TaskForge itself hides such
paths in the saved proof files.

Every "reproduce" command runs offline. The shop and library numbers come from replaying the recorded AI answers in
`samples/replay/`; the factory re-verifies every answer on each run, so nothing is taken on trust.

Note on provenance: the AI answers were produced by independent AI agents through the manual backend, not by a live
`claude` or `api` run. See `docs/LIMITATIONS.md`.
