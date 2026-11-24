# Demo video script (about 3 minutes)

Record the terminal and the browser. Everything below runs offline, with no API key. Use a large terminal font.

## 0:00 – Problem (20 s)
"Fair coding tests are hard to make: tasks can be unclear, impossible, or too easy, and tests can miss broken code.
TaskForge is a factory that turns a code repository into new coding tasks and refuses to ship any task it cannot prove
is fair."

## 0:20 – Run the factory (50 s)
```
taskforge analyze examples/shop
taskforge demo
```
Say: "It reads the repository at an exact commit, plans eight tasks from ten feature recipes, including combinations,
asks an AI for each task, then runs the proofs itself." Point at the progress lines and the final line
(`accepted 8 of 8 tasks ... variation score 0.81`).

## 1:10 – Open the report (50 s)
Open `taskforge_out/demo_shop/report.html`. Show:
- the four proof columns for every task (fails before, passes after, nothing breaks, tests have teeth),
- the mutation kill rate (the tests caught about 9 in 10 deliberately broken versions),
- the variation heat-map ("distance 0 would mean only names or numbers differ").

Open one task folder: `task.toml`, `instruction.md`, `solution/solution.patch`, the tests.

## 2:00 – Prove the checker itself (40 s)
```
taskforge controls
```
Say: "Here is the proof that the checker is not a rubber stamp. One good task is accepted, and six deliberately bad
ones are rejected, each for the right reason: tests that already pass, no tests collected, a wrong solution, a solution
that breaks existing tests, weak tests, and a patch that does not apply."

## 2:40 – Re-check offline and close (20 s)
```
taskforge check samples/tasks/shop/shop__time_window__01 --repo examples/shop
```
Say: "Anyone can repeat the proof without an AI. It works on a second Python repository and on a JavaScript repository
too, but mutation testing is Python-only, which is written down in LIMITATIONS.md. Thank you."

## Checklist before recording
- `pytest` passes (`evidence/pytest.txt`).
- No `.env` or keys are visible in the terminal or the file tree.
- The video link is set to "unlisted" and opens when you are logged out.
