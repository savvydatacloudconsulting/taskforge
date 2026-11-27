"""Large "src" layout repositories (edits, selected code) and the Harbor export with its grading script."""

from __future__ import annotations

import json
import tomllib

import pytest

from taskforge.edits import EditError, apply_blocks, parse_blocks
from taskforge.generator import Factory, ParseError, parse_response
from taskforge.harbor import ExportError, HarborConfig, export_task, simulate_task, upstream_check
from taskforge.harbor_grade import grade, reward_for
from taskforge.llm import ScriptedBackend
from taskforge.repo import load_context, python_definitions, render_selection, resolve_repo
from taskforge.runner import Workspace, parse_outcomes
from conftest import git

CORE = '''"""Greeting helpers."""

import functools


class Greeter:
    """Say hello."""

    def __init__(self, name: str = "world") -> None:
        self.name = name

    def greet(self) -> str:
        return f"hello {self.name}"


@functools.lru_cache
def shout(text: str) -> str:
    return text.upper()
'''

FILES = {
    "src/mini/__init__.py": "from .core import Greeter\n",
    "src/mini/core.py": CORE,
    "docs/conf.py": "project = 'mini'\n",
    "tests/test_core.py": 'from mini import Greeter\n\n\ndef test_greet():\n    assert Greeter("bo").greet() == "hello bo"\n',
}

SEARCH_REPLACE = '''<<<<<<< SEARCH
    def greet(self) -> str:
        return f"hello {self.name}"
=======
    def greet(self, times: int = 1) -> str:
        if times < 1:
            raise ValueError("times must be at least 1")
        return ", ".join([f"hello {self.name}"] * times)
>>>>>>> REPLACE'''

NEW_TEST = '''import pytest

from mini import Greeter


def test_default_is_once():
    assert Greeter("bo").greet() == "hello bo"


def test_twice():
    assert Greeter("bo").greet(times=2) == "hello bo, hello bo"


@pytest.mark.parametrize("times", [0, -1], ids=["zero times", "minus - one"])
def test_rejects_small(times):
    with pytest.raises(ValueError, match="at least 1"):
        Greeter("bo").greet(times=times)
'''

INSTRUCTION = """## Background
Callers sometimes want a greeting repeated.

## Requirements
1. `Greeter.greet` accepts an optional integer `times`, defaulting to one.
2. The greeting is repeated `times` times, separated by a comma and a space.
3. Values below one raise `ValueError` with the message "times must be at least 1".

## Public interface
`Greeter.greet(times: int = 1) -> str`

## Examples
`Greeter("bo").greet(times=2)` returns "hello bo, hello bo".
"""

ANSWER = (f"=== TITLE ===\nRepeat a greeting\n=== INSTRUCTION ===\n{INSTRUCTION}"
          f"=== EDIT solution src/mini/core.py ===\n{SEARCH_REPLACE}\n"
          f"=== FILE test tests/test_tf_repeat.py ===\n{NEW_TEST}=== END ===\n")


def test_edit_blocks_apply_once_and_report_problems():
    blocks = parse_blocks(SEARCH_REPLACE)
    out = apply_blocks(CORE, blocks)
    assert "times: int = 1" in out and out.count("def greet") == 1
    with pytest.raises(EditError, match="does not match"):
        apply_blocks(out, blocks)
    with pytest.raises(EditError, match="matches 2 places"):
        apply_blocks("a\na\n", parse_blocks("<<<<<<< SEARCH\na\n=======\nb\n>>>>>>> REPLACE"))
    for broken in ("<<<<<<< SEARCH\na\n=======\nb", "plain text", "<<<<<<< SEARCH\n=======\nb\n>>>>>>> REPLACE"):
        with pytest.raises(EditError):
            parse_blocks(broken)


def test_parse_response_reads_edit_sections():
    parsed = parse_response(ANSWER)
    assert list(parsed.edits) == ["src/mini/core.py"] and list(parsed.test_files) == ["tests/test_tf_repeat.py"]
    assert not parsed.solution_files
    with pytest.raises(ParseError, match="tests must be new files"):
        parse_response("=== EDIT test tests/a.py ===\nx\n=== END ===")
    with pytest.raises(ParseError, match="both"):
        parse_response("=== FILE solution a.py ===\nx\n=== EDIT solution a.py ===\ny\n=== END ===")


def test_parse_outcomes_keeps_ids_with_spaces_and_dashes():
    out = parse_outcomes(
        "PASSED tests/a.py::test_x[two words]\n"
        "FAILED tests/a.py::test_y[minus - one] - AssertionError: no - really\n"
        "FAILED tests/a.py::test_z - ValueError: bad - value\n"
        "SKIPPED [1] tests/a.py:3: not here\n")
    assert out["tests/a.py::test_x[two words]"] == "PASSED"
    assert out["tests/a.py::test_y[minus - one]"] == "FAILED"
    assert out["tests/a.py::test_z"] == "FAILED"


def test_reward_rules():
    f2p, p2p = ["a", "b", "c", "d"], ["old"]
    all_pass = dict.fromkeys(f2p + p2p, "passed")
    assert reward_for(all_pass, f2p, p2p) == 1.0
    assert reward_for({**all_pass, "d": "failed"}, f2p, p2p) == 0.75
    assert reward_for({**all_pass, "old": "failed"}, f2p, p2p) == 0.0
    assert reward_for({"old": "passed"}, f2p, p2p) == 0.0


@pytest.fixture
def mini(make_git_repo):
    return resolve_repo(make_git_repo(FILES, "mini"), name="mini")


def test_src_layout_is_detected_and_only_library_code_is_source(mini):
    assert mini.pythonpath == "src"
    with Workspace(mini) as ws:
        ctx = load_context(mini, ws.dir)
        assert ws.run_tests().ok  # imports from the workspace's own src folder
    assert sorted(ctx.sources) == ["src/mini/__init__.py", "src/mini/core.py"]
    lines = CORE.splitlines()
    (start, end), = python_definitions(CORE, "shout")
    assert lines[start - 1] == "@functools.lru_cache" and "upper" in lines[end - 1]
    assert len(python_definitions(CORE, "Greeter.greet")) == 1
    text = render_selection(ctx, ["src/mini/core.py::Greeter.greet", "nope.py::x"]).full_text
    assert "EXCERPT src/mini/core.py :: Greeter.greet" in text and "import functools" in text
    assert 'return f"hello {self.name}"' in text and "return text.upper()" not in text
    assert "def shout(text: str) -> str" in text or "Outlines of all source files" in text


def _accepted_package(mini, tmp_path):
    backend = ScriptedBackend(['["src/mini/core.py::Greeter"]', ANSWER])
    factory = Factory(mini, backend, tmp_path / "out", context_budget=10, max_attempts=1)
    result = factory.run(1, ["validation_rejection"])[0]
    assert result.status == "accepted", result.reason
    return backend, result, tmp_path / "out" / "accepted" / result.task_id


def test_factory_on_a_large_repository_uses_selected_code_and_edits(mini, tmp_path):
    backend, result, folder = _accepted_package(mini, tmp_path)
    selection_prompt, task_prompt = backend.prompts
    assert "path::Name" in selection_prompt
    assert "EXCERPT src/mini/core.py :: Greeter" in task_prompt and "<<<<<<< SEARCH" in task_prompt
    assert "must NOT already exist" in task_prompt
    meta = tomllib.loads((folder / "task.toml").read_text(encoding="utf-8"))
    assert meta["run"]["pythonpath"] == "src" and meta["repo"]["base_commit"] == mini.base_commit
    assert result.report.proof("tests_have_teeth").status == "pass"


def test_a_search_block_that_matches_nothing_is_sent_back(mini, tmp_path):
    wrong = ANSWER.replace('return f"hello {self.name}"\n=======', "return None\n=======")
    backend = ScriptedBackend(['["src/mini/core.py"]', wrong, ANSWER])
    result = Factory(mini, backend, tmp_path / "out", context_budget=10, max_attempts=2).run(
        1, ["validation_rejection"])[0]
    assert result.status == "accepted"
    assert result.attempts[0].outcome == "invalid" and "does not match" in backend.prompts[-1]


def _settings(base_commit):
    return HarborConfig(repo_url="https://example.invalid/mini", base_commit=base_commit, license="MIT",
                        base_image="python:3.12-slim", apt_packages=["git"], pip_packages=["pytest"],
                        install_command="pip install -e .", protected_paths=["tests"])


def test_harbor_export_and_grading(mini, tmp_path):
    _, result, folder = _accepted_package(mini, tmp_path)
    out, summary = export_task(folder, mini.path, _settings(mini.base_commit), tmp_path / "harbor")
    for rel in ("task.toml", "instruction.md", "environment/Dockerfile", "solution/solve.sh",
                "solution/solution.patch", "tests/test.sh", "tests/grade.py", "tests/fail_to_pass.json",
                "tests/pass_to_pass.json", "tests/files/tests/test_tf_repeat.py"):
        assert (out / rel).is_file(), rel
    assert b"\r" not in (out / "tests" / "test.sh").read_bytes()
    f2p = json.loads((out / "tests" / "fail_to_pass.json").read_text(encoding="utf-8"))
    p2p = json.loads((out / "tests" / "pass_to_pass.json").read_text(encoding="utf-8"))
    assert "tests/test_tf_repeat.py::test_twice" in f2p and len(f2p) == 3
    assert set(p2p) == {"tests/test_core.py::test_greet", "tests/test_tf_repeat.py::test_default_is_once"}
    assert summary["fail_to_pass"] == 3
    meta = tomllib.loads((out / "task.toml").read_text(encoding="utf-8"))
    assert meta["metadata"]["base_commit"] == mini.base_commit and meta["metadata"]["license"] == "MIT"
    docker = (out / "environment" / "Dockerfile").read_text(encoding="utf-8")
    assert mini.base_commit in docker and "tests/" not in docker  # the grader is never baked into the image

    rehearsal = simulate_task(out, mini.path)
    assert rehearsal["ok"] and rehearsal["nop"]["reward"] == 0.0 and rehearsal["oracle"]["reward"] == 1.0

    def reward(change: dict) -> float:
        with Workspace(mini) as ws:
            ws.write_files(change)
            return grade(ws.dir, out / "tests", tmp_path / "logs")["reward"]

    half = CORE.replace('def greet(self) -> str:\n        return f"hello {self.name}"',
                        'def greet(self, times: int = 1) -> str:\n'
                        '        return ", ".join([f"hello {self.name}"] * times)')
    assert reward({"src/mini/core.py": half}) == pytest.approx(1 / 3, abs=1e-3)
    broken = CORE.replace('f"hello {self.name}"', 'f"hi {self.name}"')
    # editing the existing test does not help: the grader restores it first
    assert reward({"src/mini/core.py": broken,
                   "tests/test_core.py": "def test_greet():\n    pass\n"}) == 0.0


def test_export_refuses_a_different_commit_and_upstream_check_spots_existing_features(mini, tmp_path):
    _, _, folder = _accepted_package(mini, tmp_path)
    with pytest.raises(ExportError, match="settings name"):
        export_task(folder, mini.path, _settings("0" * 40), tmp_path / "harbor")
    assert upstream_check(folder, mini.path, mini.base_commit)["new_tests_fail_upstream"]
    newer = apply_blocks(CORE, parse_blocks(SEARCH_REPLACE))
    (mini.path / "src" / "mini" / "core.py").write_text(newer, encoding="utf-8", newline="\n")
    git(mini.path, "commit", "-q", "-am", "feature arrives upstream")
    head = git(mini.path, "rev-parse", "HEAD")
    assert not upstream_check(folder, mini.path, head)["new_tests_fail_upstream"]
