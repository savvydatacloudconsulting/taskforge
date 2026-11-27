"""The task package: a folder shaped like a SWE-bench / Harbor task.

    <task_id>/
      task.toml                 which repo + version, how to run tests, metadata
      instruction.md            the requirements, in plain words
      solution/solution.patch   the reference implementation as a diff
      tests/<repo path>         feature tests; copied into the repo root as-is
      validation/               proof evidence written by the checker

The organisers are still finalising their official template, so this layout
is deliberately small and easy to adapt (see docs/PACKAGE_FORMAT.md).
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__


@dataclass
class RepoConfig:
    path: Path
    name: str
    language: str
    base_commit: str
    test_command: str
    feature_test_command: str | None = None  # may contain {files}
    setup_command: str | None = None
    snapshot: bool = False  # True when the folder is not a git repo (we snapshot it)
    timeout: int = 120
    pythonpath: str | None = None  # repo folder put on PYTHONPATH during tests ("src" layouts)


@dataclass
class TaskPackage:
    task_id: str
    title: str
    recipes: list[str]
    instruction: str
    solution_patch: str
    test_files: dict[str, str]  # repo-relative path -> content
    repo_name: str
    language: str
    base_commit: str
    test_command: str
    snapshot: bool = False
    feature_test_command: str | None = None
    setup_command: str | None = None
    timeout: int = 120
    attempts: int = 1
    generator: str = f"taskforge {__version__}"
    pythonpath: str | None = None

    @property
    def feature_tests(self) -> list[str]:
        return sorted(self.test_files)

    def repo_config(self, path: Path) -> RepoConfig:
        return RepoConfig(
            path=Path(path), name=self.repo_name, language=self.language, base_commit=self.base_commit,
            test_command=self.test_command, feature_test_command=self.feature_test_command,
            setup_command=self.setup_command, snapshot=self.snapshot, timeout=self.timeout,
            pythonpath=self.pythonpath,
        )

    # ------------------------------------------------------------------ io
    def write(self, directory: Path) -> Path:
        d = Path(directory)
        (d / "solution").mkdir(parents=True, exist_ok=True)
        (d / "validation").mkdir(parents=True, exist_ok=True)
        _write_text(d / "task.toml", self._toml())
        _write_text(d / "instruction.md", self.instruction.rstrip() + "\n")
        _write_text(d / "solution" / "solution.patch", self.solution_patch)
        for rel, content in self.test_files.items():
            _write_text(d / "tests" / rel, content if content.endswith("\n") else content + "\n")
        return d

    def _toml(self) -> str:
        q = lambda s: json.dumps(s, ensure_ascii=False)  # JSON strings are valid TOML strings
        lines = [
            'schema = "1"', "",
            "[task]", f"id = {q(self.task_id)}", f"title = {q(self.title)}", f"recipes = {q(self.recipes)}", "",
            "[repo]", f"name = {q(self.repo_name)}", f"language = {q(self.language)}",
            f"base_commit = {q(self.base_commit)}", f"snapshot = {str(self.snapshot).lower()}", "",
            "[run]", f"test_command = {q(self.test_command)}",
        ]
        if self.feature_test_command:
            lines.append(f"feature_test_command = {q(self.feature_test_command)}")
        if self.setup_command:
            lines.append(f"setup_command = {q(self.setup_command)}")
        if self.pythonpath:
            lines.append(f"pythonpath = {q(self.pythonpath)}")
        lines += [f"timeout_seconds = {int(self.timeout)}", f"feature_tests = {q(self.feature_tests)}", "",
                  "[meta]", f"generator = {q(self.generator)}", f"attempts = {int(self.attempts)}", ""]
        return "\n".join(lines)

    @classmethod
    def load(cls, directory: Path) -> "TaskPackage":
        d = Path(directory)
        meta = tomllib.loads((d / "task.toml").read_text(encoding="utf-8"))
        tests: dict[str, str] = {}
        for rel in meta["run"]["feature_tests"]:
            tests[rel] = (d / "tests" / rel).read_text(encoding="utf-8")
        return cls(
            task_id=meta["task"]["id"], title=meta["task"]["title"], recipes=list(meta["task"].get("recipes", [])),
            instruction=(d / "instruction.md").read_text(encoding="utf-8"),
            solution_patch=(d / "solution" / "solution.patch").read_text(encoding="utf-8"),
            test_files=tests, repo_name=meta["repo"]["name"], language=meta["repo"]["language"],
            base_commit=meta["repo"]["base_commit"], snapshot=bool(meta["repo"].get("snapshot", False)),
            test_command=meta["run"]["test_command"], feature_test_command=meta["run"].get("feature_test_command"),
            setup_command=meta["run"].get("setup_command"), timeout=int(meta["run"].get("timeout_seconds", 120)),
            attempts=int(meta.get("meta", {}).get("attempts", 1)),
            generator=meta.get("meta", {}).get("generator", ""),
            pythonpath=meta["run"].get("pythonpath"),
        )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
