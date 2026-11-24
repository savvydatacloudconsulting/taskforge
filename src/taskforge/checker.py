"""The fairness checker: the proofs every task must earn.

  baseline       (precondition) the original repository's tests pass
  fails_before   the feature tests FAIL on the original repository
  passes_after   the feature tests PASS with the reference solution (3 stable runs)
  nothing_breaks every test that passed before still passes
  tests_have_teeth  deliberately broken copies of the solution are caught

The checker never talks to an AI model, so anyone can re-run it offline.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .mutate import apply_mutation, find_sites
from .package import RepoConfig, TaskPackage
from .patchutil import is_test_path, parse_patch
from .runner import PatchError, RunResult, Workspace, parse_outcomes

PASS, FAIL, SKIPPED = "pass", "fail", "skipped"
PROOF_ORDER = ["fails_before", "passes_after", "nothing_breaks", "tests_have_teeth"]


@dataclass
class ProofResult:
    name: str
    status: str
    detail: str
    evidence: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == PASS


@dataclass
class CheckReport:
    task_id: str
    proofs: list[ProofResult]
    seconds: float = 0.0
    baseline: ProofResult | None = None

    @property
    def accepted(self) -> bool:
        if self.baseline is not None and self.baseline.status == FAIL:
            return False
        return all(p.status in (PASS, SKIPPED) for p in self.proofs) and any(p.status == PASS for p in self.proofs)

    @property
    def failed_proofs(self) -> list[ProofResult]:
        return [p for p in self.proofs if p.status == FAIL]

    def proof(self, name: str) -> ProofResult | None:
        return next((p for p in self.proofs if p.name == name), None)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id, "accepted": self.accepted, "seconds": round(self.seconds, 2),
            "baseline": asdict(self.baseline) if self.baseline else None,
            "proofs": [asdict(p) for p in self.proofs],
        }


def _outcome_summary(res: RunResult) -> dict:
    out = parse_outcomes(res.stdout)
    counts: dict[str, int] = {}
    for v in out.values():
        counts[v] = counts.get(v, 0) + 1
    return {"returncode": res.returncode, "timed_out": res.timed_out, "counts": counts, "seconds": round(res.duration, 2)}


class Checker:
    def __init__(self, repo: RepoConfig, *, stability_runs: int = 3, max_mutants: int = 12,
                 min_kill_rate: float = 0.6, seed: int = 0, mutant_timeout: int = 60):
        self.repo = repo
        self.stability_runs = stability_runs
        self.max_mutants = max_mutants
        self.min_kill_rate = min_kill_rate
        self.seed = seed
        self.mutant_timeout = mutant_timeout
        self._baseline: tuple[ProofResult, dict[str, str]] | None = None

    # ---------------------------------------------------------------- baseline
    def baseline(self) -> tuple[ProofResult, dict[str, str]]:
        if self._baseline is None:
            with Workspace(self.repo) as ws:
                setup = ws.run_setup()
                if setup is not None and not setup.ok:
                    self._baseline = (ProofResult("baseline", FAIL, "setup command failed", {"tail": setup.tail()}), {})
                    return self._baseline
                res = ws.run_tests()
            outcomes = parse_outcomes(res.stdout)
            passed = {k: v for k, v in outcomes.items() if v == "PASSED"}
            if res.ok:
                detail = f"original repository passes ({len(passed)} tests)" if passed else "original repository passes"
                self._baseline = (ProofResult("baseline", PASS, detail, _outcome_summary(res)), outcomes)
            else:
                ev = _outcome_summary(res)
                ev["tail"] = res.tail()
                self._baseline = (ProofResult("baseline", FAIL, "the original repository's own tests do not pass", ev), outcomes)
        return self._baseline

    # ------------------------------------------------------------------ check
    def check(self, task: TaskPackage, *, only: list[str] | None = None) -> CheckReport:
        start = time.monotonic()
        base, base_outcomes = self.baseline()
        report = CheckReport(task.task_id, [], baseline=base)
        if base.status == FAIL:
            report.seconds = time.monotonic() - start
            return report
        wanted = only or PROOF_ORDER
        files = task.feature_tests
        if not files:
            report.proofs.append(ProofResult("fails_before", FAIL, "the task has no feature test files"))
            report.seconds = time.monotonic() - start
            return report

        report.proofs.append(self._fails_before(task, files))

        ws_after: Workspace | None = None
        try:
            passes, ws_after = self._passes_after(task, files)
            report.proofs.append(passes)
            if passes.status == PASS and ws_after is not None:
                report.proofs.append(self._nothing_breaks(ws_after, base_outcomes))
                report.proofs.append(self._teeth(task, ws_after, files))
            else:
                why = "skipped: needs 'passes_after' first"
                report.proofs.append(ProofResult("nothing_breaks", SKIPPED, why))
                report.proofs.append(ProofResult("tests_have_teeth", SKIPPED, why))
        finally:
            if ws_after is not None:
                ws_after.cleanup()
        report.proofs = [p for p in report.proofs if p.name in wanted]
        report.seconds = time.monotonic() - start
        return report

    # ---------------------------------------------------------------- proofs
    def _fails_before(self, task: TaskPackage, files: list[str]) -> ProofResult:
        with Workspace(self.repo) as ws:
            ws.run_setup()
            ws.write_files(task.test_files)
            res = ws.run_feature_tests(files)
        out = parse_outcomes(res.stdout)
        ev = _outcome_summary(res)
        ev["tail"] = res.tail(800)
        if res.returncode == 5 or (not out and "no tests ran" in res.stdout):
            return ProofResult("fails_before", FAIL, "no tests were collected, so nothing was checked", ev)
        if res.ok:
            return ProofResult("fails_before", FAIL,
                               "the feature tests already PASS on the original repository, so they do not test any new behaviour", ev)
        failing = sorted(k for k, v in out.items() if v in ("FAILED", "ERROR"))
        ev["failing_tests"] = failing
        n = len(failing)
        return ProofResult("fails_before", PASS, f"feature tests fail on the original repository ({n} failing)" if n
                           else "feature tests fail on the original repository", ev)

    def _passes_after(self, task: TaskPackage, files: list[str]) -> tuple[ProofResult, Workspace | None]:
        ws = Workspace(self.repo)
        ok = False
        try:
            ws.run_setup()
            try:
                ws.apply_patch(task.solution_patch)
            except PatchError as e:
                return ProofResult("passes_after", FAIL, "the reference solution does not apply cleanly", {"error": str(e)}), None
            ws.write_files(task.test_files)
            runs, signatures = [], []
            for i in range(self.stability_runs):
                res = ws.run_feature_tests(files)
                out = parse_outcomes(res.stdout)
                runs.append(_outcome_summary(res))
                signatures.append(tuple(sorted(out.items())) if out else (res.returncode,))
                if not res.ok:
                    ev = {"runs": runs, "tail": res.tail(1800)}
                    return ProofResult("passes_after", FAIL,
                                       "the feature tests FAIL with the reference solution applied", ev), None
            if len(set(signatures)) != 1:
                return ProofResult("passes_after", FAIL, "the feature tests give different results across runs (flaky)",
                                   {"runs": runs}), None
            n = len(parse_outcomes(res.stdout))
            ok = True
            detail = f"feature tests pass with the solution, identical across {self.stability_runs} runs"
            if n:
                detail += f" ({n} tests)"
            return ProofResult("passes_after", PASS, detail, {"runs": runs}), ws
        finally:
            if not ok:
                ws.cleanup()

    def _nothing_breaks(self, ws: Workspace, base_outcomes: dict[str, str]) -> ProofResult:
        res = ws.run_tests()
        out = parse_outcomes(res.stdout)
        ev = _outcome_summary(res)
        if not res.ok:
            ev["tail"] = res.tail(1800)
            broken = sorted(k for k, v in base_outcomes.items() if v == "PASSED" and out.get(k) in ("FAILED", "ERROR"))
            ev["broken_tests"] = broken
            return ProofResult("nothing_breaks", FAIL,
                               "the full test suite fails with the solution applied"
                               + (f" (broken: {', '.join(broken[:5])})" if broken else ""), ev)
        missing = sorted(k for k, v in base_outcomes.items() if v == "PASSED" and out.get(k) != "PASSED")
        if base_outcomes and out and missing:
            ev["broken_tests"] = missing
            return ProofResult("nothing_breaks", FAIL, f"tests that passed before no longer pass: {', '.join(missing[:5])}", ev)
        kept = sum(1 for v in base_outcomes.values() if v == "PASSED")
        return ProofResult("nothing_breaks", PASS,
                           f"the full suite passes; all {kept} original tests still pass" if kept
                           else "the full suite passes with the solution applied", ev)

    def _teeth(self, task: TaskPackage, ws: Workspace, files: list[str]) -> ProofResult:
        if task.language != "python":
            return ProofResult("tests_have_teeth", SKIPPED,
                               f"mutation testing is only implemented for Python (language: {task.language})")
        changes = parse_patch(task.solution_patch)
        targets = {p: c for p, c in changes.items() if p.endswith(".py") and not is_test_path(p)}
        pool: list[tuple[str, int, str, str]] = []  # (path, site_index, description, original source)
        for path, change in sorted(targets.items()):
            if not ws.exists(path):
                continue
            src = ws.read(path)
            try:
                sites = find_sites(src, change.added_lines)
            except SyntaxError:
                continue
            pool += [(path, s.index, s.description, src) for s in sites]
        if not pool:
            return ProofResult("tests_have_teeth", SKIPPED,
                               "the solution has no testable logic to mutate (no comparisons, arithmetic, conditions or returns)")
        rng = random.Random(f"{self.seed}:{task.task_id}")
        rng.shuffle(pool)
        chosen = pool[: self.max_mutants]
        killed, survived, invalid = 0, [], 0
        for path, idx, desc, original in chosen:
            try:
                mutated = apply_mutation(original, idx, targets[path].added_lines)
            except (ValueError, SyntaxError):
                invalid += 1
                continue
            ws.write_files({path: mutated})
            res = ws.run_feature_tests(files, timeout=self.mutant_timeout)
            ws.write_files({path: original})
            if res.ok:
                survived.append(f"{path}: {desc}")
            else:
                killed += 1
        total = killed + len(survived)
        if total == 0:
            return ProofResult("tests_have_teeth", SKIPPED, "no valid mutants could be built", {"invalid": invalid})
        rate = killed / total
        ev = {"mutants": total, "killed": killed, "survived": survived, "kill_rate": round(rate, 3),
              "available_sites": len(pool), "required": self.min_kill_rate}
        if rate >= self.min_kill_rate:
            return ProofResult("tests_have_teeth", PASS, f"tests caught {killed} of {total} broken versions ({rate:.0%})", ev)
        return ProofResult("tests_have_teeth", FAIL,
                           f"tests caught only {killed} of {total} broken versions ({rate:.0%}, need {self.min_kill_rate:.0%})", ev)


def check_package(task_dir: Path, repo_path: Path, **kwargs) -> CheckReport:
    """Re-run all proofs for a saved task package against a local copy of its repository."""
    task = TaskPackage.load(task_dir)
    cfg = task.repo_config(repo_path)
    return Checker(cfg, **kwargs).check(task)
