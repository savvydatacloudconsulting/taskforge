"""Export accepted task packages as Harbor 0.25 task folders, and rehearse their grading locally.

    <task_id>/
      task.toml                 repository, base commit, licence, limits
      instruction.md            the only file shown to the AI being evaluated
      environment/Dockerfile    builds the repository at the base commit
      solution/solve.sh         applies solution.patch (used by Harbor's oracle agent)
      tests/test.sh             grades and writes /logs/verifier/reward.txt
      tests/grade.py, tf_outcomes.py, config.json, files/<new test files>
      tests/fail_to_pass.json, pass_to_pass.json

The two test lists come from real runs: the repository before the change, and with the reference
solution applied. ``simulate`` runs the same grading script without Docker. It is a rehearsal, not a
replacement for ``harbor run``.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import harbor_grade, harbor_outcomes
from .package import TaskPackage, _write_text
from .runner import Workspace, clean_env

SCHEMA_VERSION = "1.4"


class ExportError(ValueError):
    pass


@dataclass
class HarborConfig:
    repo_url: str
    base_commit: str
    license: str
    base_image: str
    apt_packages: list[str]
    pip_packages: list[str]
    install_command: str
    release: str = ""
    org: str = "taskforge"
    test_paths: list[str] = field(default_factory=lambda: ["tests"])
    protected_paths: list[str] = field(default_factory=lambda: ["tests", "pyproject.toml"])
    python: str = "/usr/local/bin/python"
    agent_timeout_sec: float = 1800.0
    verifier_timeout_sec: float = 600.0
    build_timeout_sec: float = 900.0
    cpus: int = 2
    memory_mb: int = 4096
    storage_mb: int = 10240
    stability_runs: int = 3

    @classmethod
    def load(cls, path: Path) -> "HarborConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        try:
            config = cls(**data)
        except TypeError as e:
            raise ExportError(f"bad Harbor settings in {path}: {e}") from e
        if len(config.base_commit) != 40 or set(config.base_commit) - set("0123456789abcdef"):
            raise ExportError("base_commit must be the full 40-character commit hash")
        return config


def dockerfile(config: HarborConfig) -> str:
    url = config.repo_url.rstrip("/").removesuffix(".git") + ".git"
    return f"""\
FROM {config.base_image}

RUN apt-get update \\
 && apt-get install -y --no-install-recommends {' '.join(config.apt_packages)} \\
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir {' '.join(config.pip_packages)}

# Only the base commit is fetched, so later upstream history is not in the image.
WORKDIR /app
RUN git init -q . \\
 && git fetch -q --depth 1 {url} {config.base_commit} \\
 && git -c advice.detachedHead=false checkout -q FETCH_HEAD \\
 && rm -f .git/FETCH_HEAD

RUN {config.install_command}

ENV PYTHONDONTWRITEBYTECODE=1 LANG=C.UTF-8
"""


def task_toml(pkg: TaskPackage, config: HarborConfig, counts: tuple[int, int]) -> str:
    q = lambda value: json.dumps(value, ensure_ascii=False)  # JSON strings and arrays are valid TOML
    return f"""\
schema_version = {q(SCHEMA_VERSION)}

[task]
name = {q(f"{config.org}/{pkg.task_id}")}
description = {q(pkg.title)}
keywords = {q(pkg.recipes)}

[metadata]
task_id = {q(pkg.task_id)}
repository = {q(config.repo_url)}
base_commit = {q(config.base_commit)}
release = {q(config.release)}
language = {q(pkg.language)}
license = {q(config.license)}
recipes = {q(pkg.recipes)}
generator = {q(pkg.generator)}
attempts = {int(pkg.attempts)}
fail_to_pass_tests = {counts[0]}
pass_to_pass_tests = {counts[1]}

[verifier]
timeout_sec = {float(config.verifier_timeout_sec)}

[agent]
timeout_sec = {float(config.agent_timeout_sec)}

[environment]
build_timeout_sec = {float(config.build_timeout_sec)}
cpus = {config.cpus}
memory_mb = {config.memory_mb}
storage_mb = {config.storage_mb}
"""


SOLVE_SH = """\
#!/bin/bash
# Apply the reference solution (used by Harbor's oracle agent).
set -euo pipefail
cd /app
git -c safe.directory=/app apply --whitespace=nowarn /solution/solution.patch
"""


def test_sh(config: HarborConfig) -> str:
    return f"""\
#!/bin/bash
# Harbor runs this after the agent has finished. It writes /logs/verifier/reward.txt.
mkdir -p /logs/verifier
cd /app
{config.python} /tests/grade.py --app /app --tests /tests --out /logs/verifier
"""


def collect_tests(pkg: TaskPackage, repo_path: Path, config: HarborConfig) -> dict:
    """Run the tests before and after the reference solution and sort them into the two lists."""
    cfg = pkg.repo_config(repo_path)
    files = pkg.feature_tests
    with tempfile.TemporaryDirectory(prefix="tf_plugin_") as tmp:
        plugin = Path(tmp)
        _write_text(plugin / "tf_outcomes.py", Path(harbor_outcomes.__file__).read_text(encoding="utf-8"))

        def run(ws: Workspace, args: list[str]):
            return harbor_grade.run_pytest(ws.dir, plugin, args, pythonpath=cfg.pythonpath,
                                           timeout=int(config.verifier_timeout_sec), env=clean_env())

        with Workspace(cfg) as ws:
            before, code, tail = run(ws, config.test_paths)
            if code != 0:
                raise ExportError(f"the original repository's tests do not pass:\n{tail}")
            ws.write_files(pkg.test_files)
            new_before, _, _ = run(ws, files)
        with Workspace(cfg) as ws:
            ws.apply_patch(pkg.solution_patch)
            ws.write_files(pkg.test_files)
            after, code, tail = run(ws, [f"--ignore={f}" for f in files] + config.test_paths)
            runs = []
            for _ in range(config.stability_runs):
                outcomes, new_code, new_tail = run(ws, files)
                if new_code != 0:
                    raise ExportError(f"the new tests do not pass with the reference solution:\n{new_tail}")
                runs.append(outcomes)
    if any(r != runs[0] for r in runs):
        raise ExportError("the new tests give different results across runs")
    passed_before = sorted(t for t, o in before.items() if o == "passed")
    broken = [t for t in passed_before if after.get(t) != "passed"]
    if broken:
        raise ExportError(f"the reference solution breaks {len(broken)} existing tests, for example {broken[:3]}")
    new_passed = sorted(t for t, o in runs[0].items() if o == "passed")
    fail_to_pass = [t for t in new_passed if new_before.get(t) != "passed"]
    unchanged = [t for t in new_passed if new_before.get(t) == "passed"]
    if not fail_to_pass:
        raise ExportError("no new test goes from failing to passing")
    return {
        "fail_to_pass": fail_to_pass,
        "pass_to_pass": passed_before + unchanged,
        "summary": {
            "existing_tests_passing_before": len(passed_before),
            "existing_tests_skipped_or_expected_to_fail": sum(1 for o in before.values() if o == "skipped"),
            "new_tests": len(runs[0]), "fail_to_pass": len(fail_to_pass),
            "new_tests_that_also_pass_before": len(unchanged), "stability_runs": config.stability_runs,
        },
    }


def export_task(task_dir: Path, repo_path: Path, config: HarborConfig, out_root: Path) -> tuple[Path, dict]:
    pkg = TaskPackage.load(task_dir)
    if pkg.base_commit != config.base_commit:
        raise ExportError(f"{pkg.task_id} was made at commit {pkg.base_commit}, "
                          f"but the settings name {config.base_commit}")
    lists = collect_tests(pkg, repo_path, config)
    out = Path(out_root) / pkg.task_id
    if out.exists():
        if not (out / "task.toml").exists():
            raise ExportError(f"{out} exists and is not a task folder; remove it first")
        shutil.rmtree(out)
    counts = (len(lists["fail_to_pass"]), len(lists["pass_to_pass"]))
    _write_text(out / "task.toml", task_toml(pkg, config, counts))
    _write_text(out / "instruction.md", pkg.instruction.rstrip() + "\n")
    _write_text(out / "environment" / "Dockerfile", dockerfile(config))
    _write_text(out / "solution" / "solve.sh", SOLVE_SH)
    _write_text(out / "solution" / "solution.patch", pkg.solution_patch)
    tests = out / "tests"
    _write_text(tests / "test.sh", test_sh(config))
    _write_text(tests / "grade.py", Path(harbor_grade.__file__).read_text(encoding="utf-8"))
    _write_text(tests / "tf_outcomes.py", Path(harbor_outcomes.__file__).read_text(encoding="utf-8"))
    settings = {"base_commit": config.base_commit, "pythonpath": pkg.pythonpath, "test_paths": config.test_paths,
                "protected_paths": config.protected_paths, "feature_files": pkg.feature_tests,
                "timeout_sec": int(config.verifier_timeout_sec)}
    _write_text(tests / "config.json", json.dumps(settings, indent=2) + "\n")
    for name in ("fail_to_pass", "pass_to_pass"):
        _write_text(tests / f"{name}.json", json.dumps(lists[name], indent=1) + "\n")
    for relative, content in pkg.test_files.items():
        _write_text(tests / "files" / relative, content if content.endswith("\n") else content + "\n")
    return out, lists["summary"]


def simulate_task(harbor_dir: Path, repo_path: Path) -> dict:
    """Grade the untouched repository (like Harbor's "nop" agent) and the reference solution ("oracle")."""
    harbor_dir = Path(harbor_dir).resolve()
    settings = json.loads((harbor_dir / "tests" / "config.json").read_text(encoding="utf-8"))
    from .package import RepoConfig

    repo = RepoConfig(path=Path(repo_path).resolve(), name="repo", language="python",
                      base_commit=settings["base_commit"], test_command="{python} -m pytest -q",
                      pythonpath=settings.get("pythonpath"))
    result = {"task": harbor_dir.name}
    for agent in ("nop", "oracle"):
        with Workspace(repo) as ws, tempfile.TemporaryDirectory(prefix="tf_logs_") as logs:
            if agent == "oracle":
                ws.apply_patch((harbor_dir / "solution" / "solution.patch").read_text(encoding="utf-8"))
            with contextlib.redirect_stdout(io.StringIO()):  # the failing output is expected for "nop"
                report = harbor_grade.grade(ws.dir, harbor_dir / "tests", Path(logs), env=clean_env())
        result[agent] = report
    result["ok"] = result["nop"]["reward"] == 0.0 and result["oracle"]["reward"] == 1.0
    # An untouched repository must fail only the feature tests.
    result["ok"] = result["ok"] and result["nop"]["pass_to_pass"]["passed"] == result["nop"]["pass_to_pass"]["total"]
    return result


def upstream_check(task_dir: Path, repo_path: Path, ref_commit: str) -> dict:
    """The new tests must also fail on a newer upstream commit, or the feature already exists there."""
    pkg = TaskPackage.load(task_dir)
    cfg = pkg.repo_config(repo_path)
    cfg.base_commit = ref_commit
    with Workspace(cfg) as ws:
        ws.write_files(pkg.test_files)
        res = ws.run_feature_tests(pkg.feature_tests)
    return {"task": pkg.task_id, "upstream_commit": ref_commit, "new_tests_fail_upstream": not res.ok,
            "exit_code": res.returncode, "tail": res.tail(600)}
