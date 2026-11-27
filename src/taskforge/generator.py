"""The factory loop: plan -> ask the AI -> build the package -> prove it -> accept or reject."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from . import __version__
from .checker import CheckReport, Checker
from .edits import EditError, apply_blocks, parse_blocks
from .llm import DEFAULT_SYSTEM, Backend, BudgetExceeded, LLMError, NeedsAnswer
from .package import RepoConfig, TaskPackage
from .patchutil import is_test_path, parse_patch, safe_relpath
from .recipes import Plan, plan_batch
from .repo import RepoContext, load_context, render_context, render_selection
from .runner import PatchError, Workspace
from .variation import MIN_DISTANCE, Signature, batch_score, nearest, signature

MARKER_RE = re.compile(r"^=== (TITLE|INSTRUCTION|END|(FILE|EDIT) (solution|test) (.+?)) ===\s*$")
MAX_FILE_CHARS = 80_000  # for a file the AI writes out in full; edits to larger files are fine
MAX_SELECTED = 8


class ParseError(ValueError):
    pass


@dataclass
class ParsedTask:
    title: str
    instruction: str
    solution_files: dict[str, str]
    test_files: dict[str, str]
    edits: dict[str, str] = field(default_factory=dict)  # path -> SEARCH/REPLACE blocks, not yet applied


@dataclass
class Attempt:
    number: int
    outcome: str  # accepted | parse_error | invalid | proof_failed | too_similar | llm_error
    detail: str
    seconds: float = 0.0


@dataclass
class TaskResult:
    task_id: str
    plan: list[str]
    status: str  # accepted | rejected | pending
    title: str = ""
    attempts: list[Attempt] = field(default_factory=list)
    package: TaskPackage | None = None
    report: CheckReport | None = None
    reason: str = ""
    nearest_distance: float | None = None
    nearest_task: str | None = None
    raw_response: str = ""


# ------------------------------------------------------------------ parsing

def _strip_fence(text: str) -> str:
    lines = text.strip("\n").splitlines()
    if len(lines) >= 2 and lines[0].lstrip().startswith("```") and lines[-1].strip() == "```":
        lines = lines[1:-1]
    return "\n".join(lines).strip("\n") + "\n"


def parse_response(text: str) -> ParsedTask:
    sections: list[tuple[str, str, list[str]]] = []  # (kind, label, lines)
    closed = False
    for line in text.replace("\r\n", "\n").split("\n"):
        m = MARKER_RE.match(line.strip())
        if m:
            if m.group(1) == "END":
                closed = True  # ends the current section; many models write END after every file, so keep reading
                continue
            closed = False
            if m.group(1) in ("TITLE", "INSTRUCTION"):
                sections.append((m.group(1), "", []))
            else:
                if m.group(2) == "EDIT" and m.group(3) == "test":
                    raise ParseError("tests must be new files: use '=== FILE test <path> ===', not EDIT")
                kind = "edit" if m.group(2) == "EDIT" else m.group(3)
                sections.append((kind, m.group(4).strip(), []))
        elif sections and not closed:
            sections[-1][2].append(line)
    if not sections:
        raise ParseError("no '=== TITLE ===' / '=== INSTRUCTION ===' / '=== FILE ... ===' markers found")
    title, instruction = "", ""
    solution: dict[str, str] = {}
    tests: dict[str, str] = {}
    edits: dict[str, str] = {}
    for kind, label, lines in sections:
        body = "\n".join(lines)
        if kind == "TITLE":
            title = next((ln.strip() for ln in lines if ln.strip()), "")
        elif kind == "INSTRUCTION":
            instruction = body.strip("\n") + "\n"
        elif kind == "solution":
            if label in solution:
                raise ParseError(f"solution file listed twice: {label}")
            solution[label] = _strip_fence(body)
        elif kind == "test":
            if label in tests:
                raise ParseError(f"test file listed twice: {label}")
            tests[label] = _strip_fence(body)
        elif kind == "edit":
            edits[label] = edits.get(label, "") + body + "\n"  # several EDIT sections per file are fine
    both = sorted(set(edits) & set(solution))
    if both:
        raise ParseError(f"{both[0]} is given both as a whole FILE and as an EDIT; use one of them")
    return ParsedTask(title, instruction, solution, tests, edits)


def resolve_edits(p: ParsedTask, sources: dict[str, str]) -> tuple[set[str], list[str]]:
    """Turn EDIT sections into complete file contents. Returns the edited paths and any problems."""
    edited: set[str] = set()
    errors: list[str] = []
    for path, body in p.edits.items():
        if path not in sources:
            errors.append(f"cannot EDIT {path}: it is not an existing source file")
            continue
        try:
            p.solution_files[path] = apply_blocks(sources[path], parse_blocks(body))
            edited.add(path)
        except EditError as e:
            errors.append(f"{path}: {e}")
    return edited, errors


def format_response(title: str, instruction: str, solution: dict[str, str], tests: dict[str, str]) -> str:
    """The inverse of parse_response: write an answer in the exact format the factory expects."""
    parts = [f"=== TITLE ===\n{title}\n=== INSTRUCTION ===\n{instruction.strip()}\n"]
    for path, content in solution.items():
        parts.append(f"=== FILE solution {path} ===\n{content.rstrip()}\n")
    for path, content in tests.items():
        parts.append(f"=== FILE test {path} ===\n{content.rstrip()}\n")
    parts.append("=== END ===\n")
    return "".join(parts)


def validate_parsed(p: ParsedTask, repo: RepoConfig, existing_files: set[str],
                    edited: set[str] | None = None) -> list[str]:
    errs: list[str] = []
    if not p.title or len(p.title) > 140:
        errs.append("TITLE must be one short line (max 140 characters)")
    if len(p.instruction) < 300 or "requirements" not in p.instruction.lower():
        errs.append("INSTRUCTION must be a full markdown spec with a '## Requirements' section")
    if not p.solution_files:
        errs.append("at least one '=== FILE solution <path> ===' section is required")
    if not p.test_files:
        errs.append("at least one '=== FILE test <path> ===' section is required")
    if len(p.test_files) > 3:
        errs.append("use at most 3 new test files")
    for path, content in {**p.solution_files, **p.test_files}.items():
        try:
            safe_relpath(path)
        except ValueError as e:
            errs.append(str(e))
            continue
        if len(content) > MAX_FILE_CHARS and path not in (edited or set()):
            errs.append(f"{path} is too large")
        if path.endswith(".py"):
            try:
                compile(content, path, "exec")
            except SyntaxError as e:
                errs.append(f"{path} has a syntax error: {e.msg} (line {e.lineno})")
    for path in p.solution_files:
        if is_test_path(path):
            errs.append(f"solution file {path} looks like a test file; put tests in '=== FILE test ... ==='")
    for path in p.test_files:
        if not is_test_path(path):
            errs.append(f"test file {path} is not recognised as a test path (use the repo's test folder and naming)")
        if path in existing_files:
            errs.append(f"test file {path} already exists; create NEW test files only and never edit existing tests")
    return errs


SIGNATURE_LINE_RE = re.compile(r"^\s*(?:def |class |@)|^\s*\*{0,2}\w+\*{0,2}\s*:\s*[\w\[\], |.]+(?:\s*=\s*[^,]+)?,?\s*$")


def _without_interface_section(instruction: str) -> str:
    """Drop '## Public interface': naming exact signatures there is required, not a leak."""
    out, skipping = [], False
    for line in instruction.splitlines():
        if line.startswith("## "):
            skipping = "public interface" in line.lower()
        if not skipping:
            out.append(line)
    return "\n".join(out)


def lint_instruction(instruction: str, patch: str) -> list[str]:
    """Reject instructions that hand over the answer (solution logic copied into the text)."""
    body = _without_interface_section(instruction)
    added = [ln.strip() for c in parse_patch(patch).values() for ln in c.added_text]
    leaked = [ln for ln in added if len(ln) >= 40 and ln in body and not SIGNATURE_LINE_RE.match(ln)]
    if leaked:
        return [f"the instruction contains solution code verbatim (e.g. {leaked[0][:70]!r}); describe behaviour, not code"]
    return []


# ------------------------------------------------------------------- prompts

OUTPUT_FORMAT = """\
=== TITLE ===
<one line>
=== INSTRUCTION ===
<markdown>
=== FILE solution <relative/path> ===
<complete new file content>
=== FILE test <relative/path> ===
<complete new file content>
=== END ===
(Repeat the FILE sections as needed. No code fences around file content. No text outside the sections.)"""

EDIT_OUTPUT_FORMAT = """\
=== TITLE ===
<one line>
=== INSTRUCTION ===
<markdown>
=== EDIT solution <relative/path of an existing source file> ===
<<<<<<< SEARCH
<consecutive lines copied exactly, with indentation, from the current code shown above>
=======
<the lines that replace them>
>>>>>>> REPLACE
=== FILE test <relative/path> ===
<complete new file content>
=== END ===
(One EDIT section may hold several SEARCH/REPLACE blocks. Each SEARCH text must occur exactly once in its file.
Use '=== FILE solution <path> ===' with complete content only for a NEW source file. No text outside the sections.)"""

LARGE_RULES = """\
5. This is a large, mature library. The feature must NOT already exist in it, neither under another name nor as an
   option of an existing function. Prefer a small, realistic request that a real user of this library could make.
6. Change existing files with EDIT sections (see the output format); never rewrite a large file. Only edit code that is
   shown above in full or as an excerpt. Keep type hints and docstring style consistent with the surrounding code.
"""


def build_prompt(repo: RepoConfig, ctx: RepoContext, plan: Plan, others: list[str], suggested_test: str,
                 large: bool = False) -> str:
    done = "\n".join(f"- {a}" for a in others) if others else "(none)"
    solution_rule = (
        "change only what the feature needs, in the\n   repository's style" if large else
        "output the COMPLETE new content of every non-test file you modify or create. Keep it focused and in the\n"
        "   repository's style")
    extra_rules = LARGE_RULES if large else ""
    output_format = EDIT_OUTPUT_FORMAT if large else OUTPUT_FORMAT
    return f"""\
# Goal
Create ONE new feature-development task for the repository below. A task is: (1) a clear instruction another
engineer could implement from the text alone, (2) your own reference solution, and (3) tests that FAIL on the
current code and PASS with your solution. An automatic checker will verify all of this.

# Repository
name: {repo.name}
language: {repo.language}
test command: {repo.test_command}

{ctx.full_text}

# Feature idea (recipe)
{plan.describe()}

# Variation
Other tasks are being made for this same repository from these recipes. Yours must differ from all of them in
BEHAVIOUR (different rules, data flow or interactions), not merely in names, labels or constants:
{done}

# Rules
1. INSTRUCTION is markdown with these sections: "## Background", "## Requirements" (numbered, each independently
   testable), "## Public interface" (the exact names, signatures, error types and messages the tests rely on) and
   "## Examples". Do not include implementation code beyond short usage examples. The tests may only rely on what
   the instruction states.
2. SOLUTION: {solution_rule}; use only the standard library and dependencies the repository already uses. Never edit
   existing test files. All existing behaviour must keep working.
3. TESTS: create NEW test file(s) only. {suggested_test} Tests must be deterministic (no network, no real clock, no
   randomness), cover normal cases, boundaries and error cases, and contain at least 6 assertions overall. Each test
   must check behaviour that is NEW (it must fail on the current code).
4. The feature must be solvable from the instruction alone and small enough for one focused change (roughly 15 to 80
   changed lines).
{extra_rules}
# Output format (exact)
{output_format}
"""


def feedback_block(previous: str, problem: str) -> str:
    return f"""

# Your previous attempt was rejected
{problem}

Fix the problem and output the COMPLETE task again, in exactly the same format (all sections, all files).

## Previous output
{previous[:24000]}
"""


VOLATILE = [
    (re.compile(r"0x[0-9a-fA-F]{6,}"), "0x..."),                          # memory addresses
    (re.compile(r"\b\d+\.\d+s\b"), "Ns"),                                  # durations
    (re.compile(r"(?:[A-Za-z]:)?[\\/][^\s'\"]*tf_ws_[A-Za-z0-9_]+[\\/]repo"), "<repo>"),  # temp workspace paths
    (re.compile(r"tf_ws_[A-Za-z0-9_]+"), "tf_ws"),
]


def scrub_volatile(text: str) -> str:
    """Remove run-to-run noise so that the same failure always produces the same prompt (replayable runs)."""
    for pattern, repl in VOLATILE:
        text = pattern.sub(repl, text)
    return text


def proof_feedback(report: CheckReport) -> str:
    notes = []
    for p in report.failed_proofs:
        text = f"- Check '{p.name}' FAILED: {p.detail}."
        ev = p.evidence
        if p.name == "fails_before":
            text += " Make every important test require the NEW behaviour, so it fails on the unmodified repository."
        elif p.name == "tests_have_teeth":
            survived = ev.get("survived", [])
            if survived:
                text += " These deliberately broken versions of your solution still passed your tests:\n  " + "\n  ".join(survived[:8])
            text += "\n  Add assertions (boundaries, both branches, exact values) that would catch such changes."
        elif p.name in ("passes_after", "nothing_breaks"):
            tail = ev.get("tail") or ev.get("error") or ""
            if tail:
                text += "\n  Output:\n" + "\n".join("    " + ln for ln in scrub_volatile(tail[-1500:]).splitlines()[-30:])
        notes.append(text)
    if report.baseline is not None and report.baseline.status == "fail":
        notes.append("- The repository's own tests do not pass before any change (this is not your fault).")
    return "\n".join(notes) or "The automatic checker rejected the task."


# --------------------------------------------------------------------- factory

class Factory:
    def __init__(
        self, repo: RepoConfig, backend: Backend, out_dir: Path, *, seed: int = 0, max_attempts: int = 3,
        min_distance: float = MIN_DISTANCE, checker: Checker | None = None, context_budget: int = 60_000,
        log: Callable[[str], None] = lambda s: None, on_event: Callable[[dict], None] | None = None,
    ):
        self.repo = repo
        self.backend = backend
        self.out = Path(out_dir)
        self.seed = seed
        self.max_attempts = max_attempts
        self.min_distance = min_distance
        self.checker = checker or Checker(repo, seed=seed)
        self.on_event = on_event
        if on_event is not None:
            self.checker.progress = on_event
        self.context_budget = context_budget
        self.log = log
        self._ctx: RepoContext | None = None
        self.accepted_sigs: list[Signature] = []
        self.pending = 0

    # context ---------------------------------------------------------------
    def context(self) -> RepoContext:
        if self._ctx is None:
            with Workspace(self.repo) as ws:
                self._ctx = load_context(self.repo, ws.dir)
            render_context(self._ctx, self.context_budget)
        return self._ctx

    def _select_files(self, plan: Plan, ctx: RepoContext) -> RepoContext:
        """Large repositories: first ask which code matters, then show only that in full."""
        outlines = render_context(replace(ctx), 0).full_text
        prompt = (f"Repository {self.repo.name} ({self.repo.language}). Feature idea:\n{plan.describe()}\n\n"
                  f"{outlines}\n\nWhich parts of the code would you need to read or change to implement a small feature "
                  f"of this kind? Answer with ONLY a JSON list of up to {MAX_SELECTED} entries. Each entry is a source "
                  "path from the file tree, or \"path::Name\" for one class, function or Class.method in it, for example "
                  "[\"src/pkg/a.py\", \"src/pkg/b.py::Parser.parse\"]. For files longer than about 500 lines, name the "
                  "classes or functions instead of the whole file.")
        selected: list[str] = []
        try:
            raw = self.backend.complete(prompt, DEFAULT_SYSTEM)
            match = re.search(r"\[.*\]", raw, re.S)
            if match:
                selected = [s for s in json.loads(match.group(0))
                            if isinstance(s, str) and s.partition("::")[0] in ctx.sources][:MAX_SELECTED]
        except NeedsAnswer:
            raise
        except BudgetExceeded:
            raise
        except (LLMError, ValueError, TypeError):
            selected = []
        if not selected:
            selected = sorted(ctx.sources, key=lambda r: len(ctx.sources[r]))[:2]
        return render_selection(ctx, selected)

    # main loop -------------------------------------------------------------
    def run(self, n: int, only: list[str] | None = None) -> list[TaskResult]:
        start_index = self._existing_count()
        plans = plan_batch(n, self.seed, only)
        results: list[TaskResult] = []
        self.log(f"repository {self.repo.name} @ {self.repo.base_commit[:10]}  ({self.repo.language}, test: {self.repo.test_command})")
        base, _ = self.checker.baseline()
        self.log(f"baseline: {base.status.upper()}  {base.detail}")
        if base.status == "fail":
            raise RuntimeError("the repository's own tests do not pass, so no task can be proven fair: " + base.detail)
        ctx = self.context()
        for i, plan in enumerate(plans, start=1):
            idx = start_index + i
            task_id = f"{self.repo.name}__{'_x_'.join(plan.ids)}__{idx:02d}"
            self.log(f"[{i}/{len(plans)}] {task_id}")
            others = [q.slug for q in plans if q is not plan]
            try:
                result = self._make_task(task_id, plan, ctx, others)
            except BudgetExceeded as e:
                self.log(f"  stopped: {e}")
                break
            if result.status == "pending":
                self.pending += 1
                self.log("  -> waiting for an answer (manual backend)")
                continue
            self._write(result)
            results.append(result)
            tag = "ACCEPTED" if result.status == "accepted" else f"rejected ({result.reason[:90]})"
            self.log(f"  -> {tag}  after {len(result.attempts)} attempt(s)")
        return results

    def _event(self, kind: str, **data) -> None:
        if self.on_event is not None:
            self.on_event({"type": kind, **data})

    def make_task(self, task_id: str, plan: Plan, others: list[str] | None = None) -> TaskResult:
        """Make (and save) one task for one plan. Used by the web page."""
        result = self._make_task(task_id, plan, self.context(), list(others or []))
        if result.status != "pending":
            self._write(result)
        return result

    def load_accepted_signatures(self) -> None:
        """Remember tasks already saved in the output folder, so new ones must differ from them."""
        for toml in sorted((self.out / "accepted").glob("*/task.toml")):
            pkg = TaskPackage.load(toml.parent)
            self.accepted_sigs.append(signature(pkg.task_id, pkg.solution_patch, pkg.recipes))

    def _existing_count(self) -> int:
        n = 0
        for sub in ("accepted", "rejected"):
            d = self.out / sub
            if d.exists():
                n += sum(1 for p in d.iterdir() if p.is_dir())
        return n

    def _make_task(self, task_id: str, plan: Plan, ctx: RepoContext, others: list[str]) -> TaskResult:
        result = TaskResult(task_id, plan.ids, "rejected")
        large = ctx.overflow
        if large:
            try:
                ctx = self._select_files(plan, ctx)
            except NeedsAnswer:
                result.status = "pending"
                return result
        suggested = (f"Put them at `{ctx.test_dir}/test_tf_{task_id.split('__', 1)[1].replace('__', '_')}.py`."
                     if self.repo.language == "python"
                     else f"Put them in the repository's test location, with a file name starting with `tf_` or `test`.")
        base_prompt = build_prompt(self.repo, ctx, plan, others, suggested, large=large)
        feedback = ""
        last_raw = ""
        existing = set(ctx.tree)
        sources = ctx.sources
        for attempt in range(1, self.max_attempts + 1):
            t0 = time.monotonic()
            self._event("attempt", number=attempt, previous=vars(result.attempts[-1]) if result.attempts else None)
            prompt = base_prompt + (feedback_block(last_raw, feedback) if feedback else "")
            try:
                raw = self.backend.complete(prompt, DEFAULT_SYSTEM)
            except NeedsAnswer:
                result.status = "pending"
                return result
            except BudgetExceeded:
                raise
            except LLMError as e:
                result.attempts.append(Attempt(attempt, "llm_error", str(e), time.monotonic() - t0))
                result.reason = f"AI backend error: {e}"
                return result
            last_raw = raw
            result.raw_response = raw
            try:
                parsed = parse_response(raw)
            except ParseError as e:
                feedback = f"The output could not be parsed: {e}."
                result.attempts.append(Attempt(attempt, "parse_error", str(e), time.monotonic() - t0))
                result.reason = f"unparseable AI output: {e}"
                continue
            edited, errs = resolve_edits(parsed, sources)
            errs = errs or validate_parsed(parsed, self.repo, existing, edited)
            if errs:
                feedback = "The output broke the rules:\n- " + "\n- ".join(errs)
                result.attempts.append(Attempt(attempt, "invalid", "; ".join(errs)[:400], time.monotonic() - t0))
                result.reason = "invalid output: " + errs[0]
                result.title = parsed.title
                continue
            try:
                with Workspace(self.repo) as ws:
                    ws.write_files(parsed.solution_files)
                    patch = ws.make_patch(list(parsed.solution_files))
            except Exception as e:  # noqa: BLE001 - any git failure is a rejected attempt
                feedback = f"The solution files could not be turned into a patch: {e}"
                result.attempts.append(Attempt(attempt, "invalid", feedback[:400], time.monotonic() - t0))
                result.reason = "could not build a patch"
                continue
            if not patch.strip():
                feedback = "Your solution files are identical to the repository, so there is no change."
                result.attempts.append(Attempt(attempt, "invalid", "empty patch", time.monotonic() - t0))
                result.reason = "empty solution"
                continue
            leaks = lint_instruction(parsed.instruction, patch)
            if leaks:
                feedback = leaks[0]
                result.attempts.append(Attempt(attempt, "invalid", leaks[0][:300], time.monotonic() - t0))
                result.reason = "instruction leaks the solution"
                continue
            pkg = TaskPackage(
                task_id=task_id, title=parsed.title, recipes=plan.ids, instruction=parsed.instruction,
                solution_patch=patch, test_files=parsed.test_files, repo_name=self.repo.name,
                language=self.repo.language, base_commit=self.repo.base_commit, test_command=self.repo.test_command,
                snapshot=self.repo.snapshot, feature_test_command=self.repo.feature_test_command,
                setup_command=self.repo.setup_command, timeout=self.repo.timeout, attempts=attempt,
                generator=f"taskforge {__version__}", pythonpath=self.repo.pythonpath,
            )
            result.package, result.title = pkg, parsed.title
            self._event("draft", title=pkg.title, instruction=pkg.instruction, patch=pkg.solution_patch, tests=pkg.test_files)
            report = self.checker.check(pkg)
            result.report = report
            if not report.accepted:
                feedback = proof_feedback(report)
                names = ", ".join(p.name for p in report.failed_proofs) or "baseline"
                result.attempts.append(Attempt(attempt, "proof_failed", f"failed: {names}", time.monotonic() - t0))
                result.reason = "failed proof: " + (report.failed_proofs[0].detail if report.failed_proofs else "baseline")
                self.log(f"    attempt {attempt}: failed {names}")
                continue
            sig = signature(task_id, patch, plan.ids)
            dist, other = nearest(sig, self.accepted_sigs)
            result.nearest_distance, result.nearest_task = dist, other
            if dist < self.min_distance:
                feedback = (f"The task is too similar to the already accepted task '{other}' (variation distance "
                            f"{dist:.2f}, need at least {self.min_distance:.2f}). Change the behaviour itself: different rules, "
                            "different data flow or a different interaction, not just different names or constants.")
                result.attempts.append(Attempt(attempt, "too_similar", f"distance {dist:.2f} to {other}", time.monotonic() - t0))
                result.reason = f"cosmetic duplicate of {other} (distance {dist:.2f})"
                self.log(f"    attempt {attempt}: too similar to {other} ({dist:.2f})")
                continue
            result.attempts.append(Attempt(attempt, "accepted", "all proofs passed", time.monotonic() - t0))
            result.status, result.reason = "accepted", ""
            self.accepted_sigs.append(sig)
            return result
        return result

    # output ----------------------------------------------------------------
    def _write(self, r: TaskResult) -> None:
        folder = self.out / ("accepted" if r.status == "accepted" else "rejected") / r.task_id
        folder.mkdir(parents=True, exist_ok=True)
        if r.package is not None:
            r.package.write(folder)
        (folder / "validation").mkdir(exist_ok=True)
        if r.report is not None:
            (folder / "validation" / "proofs.json").write_text(json.dumps(r.report.to_dict(), indent=2), encoding="utf-8", newline="\n")
        info = {
            "task_id": r.task_id, "status": r.status, "title": r.title, "recipes": r.plan, "reason": r.reason,
            "nearest_task": r.nearest_task, "nearest_distance": r.nearest_distance,
            "attempts": [vars(a) for a in r.attempts],
        }
        (folder / "validation" / "attempts.json").write_text(json.dumps(info, indent=2), encoding="utf-8", newline="\n")
        if r.status != "accepted" and r.package is None and r.raw_response:
            (folder / "raw_response.txt").write_text(r.raw_response, encoding="utf-8", newline="\n")

    def write_run_summary(self, results: list[TaskResult], seconds: float) -> dict:
        acc = [r for r in results if r.status == "accepted"]
        summary = {
            "repo": self.repo.name, "language": self.repo.language, "base_commit": self.repo.base_commit,
            "seed": self.seed, "generator": f"taskforge {__version__}", "seconds": round(seconds, 1),
            "requested": len(results), "accepted": len(acc), "rejected": len(results) - len(acc), "pending": self.pending,
            "mean_attempts": round(sum(len(r.attempts) for r in results) / len(results), 2) if results else 0,
            "variation_score": batch_score(self.accepted_sigs), "ai": self.backend.stats(),
        }
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8", newline="\n")
        return summary
