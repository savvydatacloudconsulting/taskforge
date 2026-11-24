"""The solver check: can someone OTHER than the task's author solve the task?

An AI is shown only the repository at its base commit and the task's instruction.
It never sees the feature tests or the reference solution. Its answer is applied
to a fresh workspace and judged by the task's own hidden tests plus the existing
suite. The result is a solve rate per task and per feature recipe: independent
evidence that tasks are clear and solvable, and a picture of what AI systems
get right and wrong.
"""

from __future__ import annotations

import html
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__
from .checker import Checker
from .generator import ParseError, parse_response, scrub_volatile
from .llm import Backend, BudgetExceeded, LLMError, NeedsAnswer
from .package import RepoConfig, TaskPackage
from .patchutil import is_test_path, safe_relpath
from .repo import RepoContext, load_context, render_context
from .report import CSS
from .runner import PatchError, Workspace, parse_outcomes

SOLVER_SYSTEM = (
    "You are a careful software engineer. You implement feature requests in existing code. "
    "You follow the requested output format exactly, with no commentary outside it."
)

OUTPUT_FORMAT = """\
=== FILE solution <relative/path> ===
<complete new file content>
=== END ===
(Repeat the FILE section for every file you modify or create. No code fences around file content.
No text outside the sections.)"""


@dataclass
class SolveAttempt:
    number: int
    outcome: str  # solved | parse_error | invalid | tests_failed | broke_existing | llm_error
    detail: str
    seconds: float = 0.0


@dataclass
class SolveResult:
    task_id: str
    recipes: list[str]
    solved: bool = False
    pending: bool = False
    attempts: list[SolveAttempt] = field(default_factory=list)
    detail: str = ""
    failing_tests: list[str] = field(default_factory=list)
    files_changed: int = 0

    @property
    def first_try(self) -> bool:
        return bool(self.attempts) and self.attempts[0].outcome == "solved"

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id, "recipes": self.recipes, "solved": self.solved, "first_try": self.first_try,
            "detail": self.detail, "failing_tests": self.failing_tests, "files_changed": self.files_changed,
            "attempts": [vars(a) for a in self.attempts],
        }


# ------------------------------------------------------------------- prompts

def build_solver_prompt(repo: RepoConfig, ctx: RepoContext, instruction: str) -> str:
    return f"""\
# Task
Implement the feature request below in the repository shown. Hidden tests will check your work against the
Requirements and the Public interface. You cannot see them. The existing tests must keep passing.

# Repository
name: {repo.name}
language: {repo.language}
test command: {repo.test_command}

{ctx.full_text}

# Feature request
{instruction.strip()}

# Rules
1. Output the COMPLETE new content of every non-test file you modify or create. Do not output unchanged files.
2. Do not edit or delete existing tests and do not add tests.
3. Use only the standard library and dependencies the repository already uses.
4. Follow every requirement exactly: names, signatures, error types, exact messages and boundary behaviour.

# Output format (exact)
{OUTPUT_FORMAT}
"""


def solver_feedback(previous: str, problem: str) -> str:
    return f"""

# Your previous attempt did not pass the hidden tests
{problem}

Fix the problem and output the COMPLETE set of changed files again, in exactly the same format.

## Previous output
{previous[:24000]}
"""


# ------------------------------------------------------------------ solving

def _validate(files: dict[str, str]) -> list[str]:
    errs: list[str] = []
    if not files:
        return ["no '=== FILE solution <path> ===' section found"]
    for path, content in files.items():
        try:
            safe_relpath(path)
        except ValueError as e:
            errs.append(str(e))
            continue
        if is_test_path(path):
            errs.append(f"{path} is a test file; solutions must not edit or add tests")
        if path.endswith(".py"):
            try:
                compile(content, path, "exec")
            except SyntaxError as e:
                errs.append(f"{path} has a syntax error: {e.msg} (line {e.lineno})")
    return errs


class Solver:
    def __init__(self, repo: RepoConfig, backend: Backend, *, attempts: int = 1, checker: Checker | None = None,
                 context_budget: int = 60_000, log: Callable[[str], None] = lambda s: None):
        self.repo = repo
        self.backend = backend
        self.attempts = attempts
        self.checker = checker or Checker(repo)
        self.context_budget = context_budget
        self.log = log
        self._ctx: RepoContext | None = None

    def context(self) -> RepoContext:
        if self._ctx is None:
            with Workspace(self.repo) as ws:
                self._ctx = load_context(self.repo, ws.dir)
            render_context(self._ctx, self.context_budget)
        return self._ctx

    def solve(self, pkg: TaskPackage) -> SolveResult:
        result = SolveResult(pkg.task_id, list(pkg.recipes))
        base_prompt = build_solver_prompt(self.repo, self.context(), pkg.instruction)
        _, base_outcomes = self.checker.baseline()
        feedback, last_raw = "", ""
        for n in range(1, self.attempts + 1):
            t0 = time.monotonic()
            prompt = base_prompt + (solver_feedback(last_raw, feedback) if feedback else "")
            try:
                raw = self.backend.complete(prompt, SOLVER_SYSTEM)
            except NeedsAnswer:
                result.pending = True
                return result
            except BudgetExceeded:
                raise
            except LLMError as e:
                result.attempts.append(SolveAttempt(n, "llm_error", str(e), time.monotonic() - t0))
                result.detail = f"AI backend error: {e}"
                return result
            last_raw = raw
            try:
                files = parse_response(raw).solution_files
            except ParseError as e:
                feedback = f"The output could not be parsed: {e}."
                result.attempts.append(SolveAttempt(n, "parse_error", str(e), time.monotonic() - t0))
                result.detail = f"unparseable answer: {e}"
                continue
            errs = _validate(files)
            if errs:
                feedback = "The output broke the rules:\n- " + "\n- ".join(errs)
                result.attempts.append(SolveAttempt(n, "invalid", "; ".join(errs)[:400], time.monotonic() - t0))
                result.detail = "invalid answer: " + errs[0]
                continue
            outcome, detail, failing = self._judge(pkg, files, base_outcomes)
            result.files_changed = len(files)
            result.attempts.append(SolveAttempt(n, outcome, detail[:600], time.monotonic() - t0))
            if outcome == "solved":
                result.solved, result.detail, result.failing_tests = True, "all hidden tests and the existing suite pass", []
                return result
            result.detail, result.failing_tests = detail, failing
            feedback = detail
        return result

    def _judge(self, pkg: TaskPackage, files: dict[str, str], base_outcomes: dict[str, str]) -> tuple[str, str, list[str]]:
        with Workspace(self.repo) as ws:
            ws.run_setup()
            ws.write_files(files)
            ws.write_files(pkg.test_files)  # the hidden tests arrive only now
            feat = ws.run_feature_tests(pkg.feature_tests)
            if not feat.ok:
                out = parse_outcomes(feat.stdout)
                failing = sorted(k for k, v in out.items() if v in ("FAILED", "ERROR"))
                names = ", ".join(failing[:6]) or "(see output)"
                tail = "\n".join(scrub_volatile(feat.tail(1500)).splitlines()[-25:])
                return "tests_failed", f"Hidden tests failed: {names}\nOutput:\n{tail}", failing
            full = ws.run_tests()
            out = parse_outcomes(full.stdout)
            broken = sorted(k for k, v in base_outcomes.items() if v == "PASSED" and out.get(k) in ("FAILED", "ERROR"))
            if not full.ok or broken:
                tail = "\n".join(scrub_volatile(full.tail(1500)).splitlines()[-25:])
                return "broke_existing", f"Existing tests broke: {', '.join(broken[:6]) or '(see output)'}\nOutput:\n{tail}", broken
            return "solved", "ok", []


def find_packages(folder: Path) -> list[Path]:
    return sorted(p.parent for p in Path(folder).rglob("task.toml"))


def solve_all(folder: Path, repo_path: Path, backend: Backend, out_dir: Path, *, attempts: int = 1,
              label: str = "", log: Callable[[str], None] = lambda s: None, checker_kwargs: dict | None = None) -> dict:
    dirs = find_packages(folder)
    if not dirs:
        raise ValueError(f"no task.toml found under {folder}")
    pkgs = [TaskPackage.load(d) for d in dirs]
    repo = pkgs[0].repo_config(Path(repo_path))
    solver = Solver(repo, backend, attempts=attempts, checker=Checker(repo, **(checker_kwargs or {})), log=log)
    base, _ = solver.checker.baseline()
    log(f"repository {repo.name} @ {repo.base_commit[:10]}: baseline {base.status.upper()}")
    if base.status == "fail":
        raise RuntimeError("the repository's own tests do not pass: " + base.detail)
    results: list[SolveResult] = []
    pending = 0
    t0 = time.monotonic()
    for i, pkg in enumerate(pkgs, start=1):
        log(f"[{i}/{len(pkgs)}] {pkg.task_id}")
        try:
            r = solver.solve(pkg)
        except BudgetExceeded as e:
            log(f"  stopped: {e}")
            break
        if r.pending:
            pending += 1
            log("  -> waiting for an answer (manual backend)")
            continue
        results.append(r)
        log("  -> SOLVED" + (" (first try)" if r.first_try else f" (attempt {len(r.attempts)})") if r.solved
            else f"  -> not solved: {r.detail.splitlines()[0][:100]}")
    data = {
        "generator": f"taskforge {__version__}", "solver": label or backend.name, "repo": repo.name,
        "base_commit": repo.base_commit, "attempts_allowed": attempts, "seconds": round(time.monotonic() - t0, 1),
        "pending": pending, "ai": backend.stats(), "results": [r.to_dict() for r in results],
        "summary": summarise(results),
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "solve_results.json").write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")
    write_solver_reports(out)
    return data


# -------------------------------------------------------------------- reports

def summarise(results: list[SolveResult]) -> dict:
    total = len(results)
    solved = [r for r in results if r.solved]
    by_recipe: dict[str, dict[str, int]] = {}
    for r in results:
        for rid in r.recipes:
            d = by_recipe.setdefault(rid, {"tasks": 0, "solved": 0})
            d["tasks"] += 1
            d["solved"] += 1 if r.solved else 0
    single = [r for r in results if len(r.recipes) == 1]
    combo = [r for r in results if len(r.recipes) > 1]
    rate = lambda rs: round(sum(1 for r in rs if r.solved) / len(rs), 3) if rs else None
    return {
        "tasks": total, "solved": len(solved), "solved_first_try": sum(1 for r in results if r.first_try),
        "solve_rate": rate(results), "first_try_rate": round(sum(1 for r in results if r.first_try) / total, 3) if total else None,
        "single_recipe": {"tasks": len(single), "rate": rate(single)},
        "combined_recipes": {"tasks": len(combo), "rate": rate(combo)},
        "by_recipe": dict(sorted(by_recipe.items())),
        "failure_kinds": _count(a.outcome for r in results if not r.solved for a in r.attempts[-1:]),
    }


def _count(items) -> dict[str, int]:
    out: dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


def _pct(x) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def solver_markdown(data: dict) -> str:
    s = data["summary"]
    L = ["# Solver check report", "",
         f"Repository `{data['repo']}` at `{data['base_commit'][:10]}`. Solver: **{data['solver']}** "
         f"(attempts allowed per task: {data['attempts_allowed']}).", "",
         "The solver saw only the repository and each task's instruction. The hidden tests and the reference solution "
         "were never shown to it.", "",
         "## Summary", "",
         f"- Tasks solved: **{s['solved']} of {s['tasks']}** ({_pct(s['solve_rate'])}); on the first try: "
         f"{s['solved_first_try']} ({_pct(s['first_try_rate'])})",
         f"- Single-recipe tasks: {_pct(s['single_recipe']['rate'])} of {s['single_recipe']['tasks']}; "
         f"combined-recipe tasks: {_pct(s['combined_recipes']['rate'])} of {s['combined_recipes']['tasks']}",
         f"- How unsolved tasks ended: {s['failure_kinds'] or 'none'}", "",
         "## By feature recipe", "", "| Recipe | Tasks | Solved |", "|---|---|---|"]
    for rid, d in s["by_recipe"].items():
        L.append(f"| {rid} | {d['tasks']} | {d['solved']} |")
    L += ["", "## Tasks", "", "| Task | Result | Attempts | Detail |", "|---|---|---|---|"]
    for r in data["results"]:
        res = "solved" + (" (first try)" if r["first_try"] else "") if r["solved"] else "NOT solved"
        detail = r["detail"].splitlines()[0][:110] if r["detail"] else ""
        L.append(f"| {r['task_id']} | {res} | {len(r['attempts'])} | {detail} |")
    L += ["", "Read docs/LIMITATIONS.md: when the solver is the same model family as the task author, solve rates are "
          "expected to be higher than for a different system.", ""]
    return "\n".join(L)


def solver_html(data: dict) -> str:
    e = html.escape
    s = data["summary"]
    cards = [(f"{s['solved']}/{s['tasks']}", "tasks solved"), (_pct(s["solve_rate"]), "solve rate"),
             (_pct(s["first_try_rate"]), "solved on first try"), (_pct(s["single_recipe"]["rate"]), "single-recipe tasks"),
             (_pct(s["combined_recipes"]["rate"]), "combined-recipe tasks")]
    recipe_rows = "".join(
        f"<tr><td>{e(rid)}</td><td>{d['tasks']}</td><td>{d['solved']}</td>"
        f"<td><div style='background:var(--line);border-radius:4px;height:10px;width:140px'>"
        f"<div style='background:var(--blue);height:10px;border-radius:4px;width:{140 * d['solved'] / d['tasks']:.0f}px'></div></div></td></tr>"
        for rid, d in s["by_recipe"].items())
    task_rows = ""
    for r in data["results"]:
        pill = "accepted" if r["solved"] else "rejected"
        label = ("solved" + (" first try" if r["first_try"] else "")) if r["solved"] else "not solved"
        detail = e(r["detail"].splitlines()[0][:140]) if r["detail"] else ""
        task_rows += (f'<tr><td class="id">{e(r["task_id"])}</td><td><span class="pill {pill}">{label}</span></td>'
                      f"<td>{len(r['attempts'])}</td><td>{detail}</td></tr>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TaskForge solver report</title><style>{CSS}</style></head><body>
<header><h1>Solver check</h1><p>{e(data['repo'])} @ {e(data['base_commit'][:10])} | solver: {e(str(data['solver']))} |
attempts allowed: {data['attempts_allowed']} | {e(data['generator'])}</p></header><main>
<p>The solver saw only the repository and each task's instruction. The hidden tests and the reference solution were never shown to it.</p>
<div class="cards">{''.join(f'<div class="card"><b>{e(str(a))}</b><span>{e(b)}</span></div>' for a, b in cards)}</div>
<h2>By feature recipe</h2><table><tr><th>Recipe</th><th>Tasks</th><th>Solved</th><th></th></tr>{recipe_rows}</table>
<h2>Tasks</h2><div class="scroll"><table><tr><th>Task</th><th>Result</th><th>Attempts</th><th>Detail</th></tr>{task_rows}</table></div>
<p class="id">Solve rates are expected to be higher when the solver is the same model family as the task author. See docs/LIMITATIONS.md.</p>
</main></body></html>"""


def write_solver_reports(out_dir: Path) -> dict[str, Path]:
    out = Path(out_dir)
    data = json.loads((out / "solve_results.json").read_text(encoding="utf-8"))
    paths = {"md": out / "solver_report.md", "html": out / "solver_report.html"}
    paths["md"].write_text(solver_markdown(data), encoding="utf-8", newline="\n")
    paths["html"].write_text(solver_html(data), encoding="utf-8", newline="\n")
    return paths
