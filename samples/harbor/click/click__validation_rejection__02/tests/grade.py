"""Grade one task: run the regression tests and the new feature tests, then write the reward.

    reward = 0.0 if any test in pass_to_pass.json does not pass
             1.0 if every test in fail_to_pass.json passes
             otherwise the share of fail_to_pass.json that passes

If the tests cannot be started at all, no reward file is written (Harbor then reports a null reward).
This file is copied into each exported task as tests/grade.py. Standard library only.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def reward_for(outcomes: dict, fail_to_pass: list, pass_to_pass: list) -> float:
    if any(outcomes.get(test) != "passed" for test in pass_to_pass):
        return 0.0
    if not fail_to_pass:
        return 0.0
    passed = sum(1 for test in fail_to_pass if outcomes.get(test) == "passed")
    return round(passed / len(fail_to_pass), 4)


def run_pytest(app: Path, plugin_dir: Path, args: list, pythonpath: str | None = None, timeout: int = 600,
               env: dict | None = None, python: str = sys.executable):
    """Run pytest in ``app``. Returns (outcomes by test id, exit code, end of the output)."""
    env = dict(os.environ if env is None else env)
    paths = [str(Path(plugin_dir).resolve())] + ([str(Path(app).resolve() / pythonpath)] if pythonpath else [])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="tf_grade_") as tmp:
        report = Path(tmp) / "outcomes.json"
        env["TF_OUTCOMES"] = str(report)
        command = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "tf_outcomes", *args]
        try:
            done = subprocess.run(command, cwd=str(app), env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=timeout)
            code, output = done.returncode, (done.stdout or "") + (done.stderr or "")
        except subprocess.TimeoutExpired:
            code, output = -9, f"pytest did not finish within {timeout} seconds"
        # No report means pytest could not run the tests (for example, the library no longer imports).
        outcomes = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
    return outcomes, code, output[-6000:]


def restore_inputs(app: Path, config: dict) -> None:
    """Put the existing tests and test settings back to the base commit, so edits to them cannot raise the score."""
    git = ["git", "-c", "safe.directory=*", "-c", "core.autocrlf=false", "-C", str(app)]
    for path in config["protected_paths"]:
        subprocess.run(git + ["checkout", "-q", config["base_commit"], "--", path], check=True)
        if (app / path).is_dir():
            subprocess.run(git + ["clean", "-fdxq", "--", path], check=True)
    for extra in ("conftest.py", "pytest.ini", "tox.ini", "setup.cfg"):
        tracked = subprocess.run(git + ["ls-files", "--error-unmatch", extra], capture_output=True)
        if tracked.returncode != 0:
            (app / extra).unlink(missing_ok=True)


def grade(app: Path, tests: Path, out: Path, env: dict | None = None, python: str = sys.executable) -> dict:
    config = json.loads((tests / "config.json").read_text(encoding="utf-8"))
    fail_to_pass = json.loads((tests / "fail_to_pass.json").read_text(encoding="utf-8"))
    pass_to_pass = json.loads((tests / "pass_to_pass.json").read_text(encoding="utf-8"))
    if subprocess.run([python, "-c", "import pytest"], capture_output=True, env=env).returncode != 0:
        raise RuntimeError("pytest is not available, so the task cannot be graded")
    restore_inputs(app, config)
    for relative in config["feature_files"]:
        target = app / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tests / "files" / relative, target)
    common = {"pythonpath": config.get("pythonpath"), "timeout": config.get("timeout_sec", 600),
              "env": env, "python": python}
    regression_args = [f"--ignore={f}" for f in config["feature_files"]] + config["test_paths"]
    outcomes, regression_code, regression_tail = run_pytest(app, tests, regression_args, **common)
    feature, feature_code, feature_tail = run_pytest(app, tests, config["feature_files"], **common)
    outcomes.update(feature)
    broken = [t for t in pass_to_pass if outcomes.get(t) != "passed"]
    missing = [t for t in fail_to_pass if outcomes.get(t) != "passed"]
    report = {
        "reward": reward_for(outcomes, fail_to_pass, pass_to_pass),
        "fail_to_pass": {"total": len(fail_to_pass), "passed": len(fail_to_pass) - len(missing), "not_passed": missing},
        "pass_to_pass": {"total": len(pass_to_pass), "passed": len(pass_to_pass) - len(broken),
                         "not_passed": broken[:100]},
        "exit_codes": {"regression": regression_code, "feature": feature_code},
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "grade_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "reward.txt").write_text(f"{report['reward']}\n", encoding="utf-8")
    if broken or missing:
        print(regression_tail if broken else "")
        print(feature_tail if missing else "")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="grade a task and write reward.txt")
    parser.add_argument("--app", default="/app")
    parser.add_argument("--tests", default="/tests")
    parser.add_argument("--out", default="/logs/verifier")
    args = parser.parse_args()
    report = grade(Path(args.app), Path(args.tests), Path(args.out))
    print(f"reward {report['reward']}: feature tests {report['fail_to_pass']['passed']}/"
          f"{report['fail_to_pass']['total']}, regression tests {report['pass_to_pass']['passed']}/"
          f"{report['pass_to_pass']['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
