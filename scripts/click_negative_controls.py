"""Failure cases on the real repository: damage each accepted click task and show the checker's verdict.

    python scripts/click_negative_controls.py <click clone> [report.md] [--only <task id>]

Three kinds of damage per task: tests that already pass, a bug planted in the reference solution, and
tests with their assert statements removed. No AI is used.
"""

import argparse
import json
from pathlib import Path

from taskforge.checker import Checker
from taskforge.package import TaskPackage
from taskforge.webapp import SABOTAGE, sabotage

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="damage accepted click tasks and show the verdicts")
    parser.add_argument("clone", type=Path)
    parser.add_argument("report", type=Path, nargs="?")
    parser.add_argument("--only", help="check one task only")
    args = parser.parse_args()
    clone, report_path = args.clone.resolve(), args.report
    folders = sorted((ROOT / "samples" / "tasks" / "click").iterdir())
    if args.only:
        folders = [f for f in folders if f.name == args.only]
        if not folders:
            parser.error(f"unknown task {args.only}")
    rows, rejected = [], 0
    checker = None
    for folder in folders:
        pkg = TaskPackage.load(folder)
        cfg = pkg.repo_config(clone)
        checker = checker or Checker(cfg)
        proofs = json.loads((folder / "validation" / "proofs.json").read_text(encoding="utf-8"))["proofs"]
        mutants = next(p for p in proofs if p["name"] == "tests_have_teeth")["evidence"]["mutant_list"]
        for kind, (label, target) in SABOTAGE.items():
            bad, _ = sabotage(pkg, kind, cfg, mutants)
            result = checker.check(bad)
            failed = result.failed_proofs
            verdict = "ACCEPTED" if result.accepted else "rejected"
            rejected += not result.accepted
            why = f"{failed[0].name}: {failed[0].detail}" if failed else "every check passed"
            rows.append((pkg.task_id, label, target, verdict, why))
            if args.only:
                print(f"\n{label}: {verdict}\n    {why}", flush=True)
            else:
                print(f"{pkg.task_id[:44]:44s} {label:32s} {verdict}  ({why[:90]})", flush=True)
    summary = f"{rejected} of {len(rows)} damaged tasks were rejected."
    print(summary)
    if report_path:
        table = "\n".join(f"| {t} | {label} | {target} | {v} | {why} |" for t, label, target, v, why in rows)
        note = "" if rejected == len(rows) else (
            "\n## Why a damaged copy can still be accepted\n\nA planted bug counts as caught whenever the tests fail, "
            "including when the remaining test code crashes. A feature that is mostly about stored values and errors "
            "can therefore keep a high kill rate with no assert statement left. The check shows that bugs make the "
            "tests fail, not that the tests compare the right values.\n")
        report_path.write_text(
            "# Failure cases on pallets/click\n\nEach accepted task was damaged on purpose and checked again, "
            f"without AI. {summary}\n\n| Task | Damage | Check expected to fail | Verdict | First failed check |\n"
            f"|---|---|---|---|---|\n{table}\n{note}", encoding="utf-8", newline="\n")
    return 0 if rejected == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
