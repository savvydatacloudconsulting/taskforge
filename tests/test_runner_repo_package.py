import sys

import pytest

from taskforge.package import TaskPackage
from taskforge.repo import load_context, render_context, resolve_repo
from taskforge.runner import PatchError, Workspace, command_tokens, parse_outcomes, snapshot_commit

from conftest import git

PYTEST_OUT = """\
PASSED tests/test_a.py::test_one
FAILED tests/test_a.py::test_two - assert 1 == 2
ERROR tests/test_b.py::test_three
SKIPPED [1] tests/test_b.py:9: reason
"""


def test_parse_outcomes():
    out = parse_outcomes(PYTEST_OUT)
    assert out["tests/test_a.py::test_one"] == "PASSED"
    assert out["tests/test_a.py::test_two"] == "FAILED"
    assert out["tests/test_b.py::test_three"] == "ERROR"


def test_scrub_paths_hides_workspace_and_home(tmp_path):
    from pathlib import Path

    from taskforge.runner import scrub_paths

    ws = tmp_path / "tf_ws_x" / "repo"
    text = f"File \"{ws}\\shop\\a.py\" and {str(ws).replace(chr(92), '/')}/b.py and {Path.home()}\\.venvs\\x"
    out = scrub_paths(text, ws)
    assert str(ws) not in out and str(Path.home()) not in out
    assert "<repo>" in out and "~" in out


def test_command_tokens_adds_pytest_flags_and_python():
    toks = command_tokens("{python} -m pytest -q {files}", ["tests/x.py"])
    assert toks[0] == sys.executable
    assert "-rA" in toks and "no:cacheprovider" in toks and toks[-1] == "tests/x.py"


def test_snapshot_commit_is_stable_and_ignores_line_endings(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for d, nl in ((a, "\n"), (b, "\r\n")):
        (d / "pkg").mkdir(parents=True)
        (d / "pkg" / "m.py").write_bytes(f"x = 1{nl}y = 2{nl}".encode())
    assert snapshot_commit(a) == snapshot_commit(a) == snapshot_commit(b)


def test_snapshot_commit_changes_with_content(tmp_path):
    (tmp_path / "m.py").write_text("x = 1\n")
    first = snapshot_commit(tmp_path)
    (tmp_path / "m.py").write_text("x = 2\n")
    assert snapshot_commit(tmp_path) != first


def test_resolve_repo_non_git_folder_is_snapshot(shop_repo):
    assert shop_repo.snapshot and shop_repo.language == "python"
    assert len(shop_repo.base_commit) == 40
    assert "pytest" in shop_repo.test_command


def test_resolve_repo_git_repo_uses_head_and_detects_dirty(make_git_repo):
    root = make_git_repo({"a.py": "x = 1\n", "tests/test_a.py": "def test_a():\n    assert True\n"})
    cfg = resolve_repo(root)
    assert not cfg.snapshot and cfg.base_commit == git(root, "rev-parse", "HEAD")
    (root / "a.py").write_text("x = 2\n")
    with pytest.raises(ValueError, match="uncommitted"):
        resolve_repo(root)
    assert resolve_repo(root, allow_dirty=True).base_commit == cfg.base_commit


def test_resolve_repo_unknown_language_needs_test_command(tmp_path):
    (tmp_path / "notes.txt").write_text("hi")
    with pytest.raises(ValueError, match="test command"):
        resolve_repo(tmp_path)


def test_workspace_patch_roundtrip(shop_repo):
    with Workspace(shop_repo) as ws:
        ws.write_files({"shop/pricing.py": "TAX_RATE_PERCENT = 20\n", "shop/new_module.py": "VALUE = 1\n"})
        patch = ws.make_patch(["shop/pricing.py", "shop/new_module.py"])
    assert "TAX_RATE_PERCENT = 20" in patch and "new file mode" in patch
    with Workspace(shop_repo) as ws:
        ws.apply_patch(patch)
        assert ws.read("shop/new_module.py").strip() == "VALUE = 1"
    with Workspace(shop_repo) as ws, pytest.raises(PatchError):
        ws.apply_patch(patch.replace("TAX_RATE_PERCENT = 10", "TAX_RATE_PERCENT = 99"))


def test_workspace_refuses_changed_snapshot(tmp_path, shop_repo):
    import dataclasses
    stale = dataclasses.replace(shop_repo, base_commit="0" * 40)
    with pytest.raises(Exception, match="changed"):
        Workspace(stale)


def test_workspace_hides_secrets_from_tests(shop_repo, monkeypatch):
    monkeypatch.setenv("MY_SECRET_TOKEN", "hunter2")
    with Workspace(shop_repo) as ws:
        ws.write_files({"tests/test_env.py": "import os\n\n\ndef test_no_secret():\n    assert 'MY_SECRET_TOKEN' not in os.environ\n"})
        res = ws.run_feature_tests(["tests/test_env.py"])
    assert res.ok, res.stdout


def test_context_budget_marks_overflow_and_uses_outlines(shop_repo):
    with Workspace(shop_repo) as ws:
        ctx = load_context(shop_repo, ws.dir)
    render_context(ctx, budget=50_000)
    assert not ctx.overflow and "def add(self, sku: str, quantity: int = 1)" in ctx.full_text
    render_context(ctx, budget=900)
    assert ctx.overflow and "outlines only" in ctx.full_text
    render_context(ctx, budget=900, force_full=["shop/cart.py"])
    assert "shop/cart.py" in ctx.shown_full


def test_package_roundtrip(tmp_path):
    pkg = TaskPackage(
        task_id="demo__x__01", title='A "quoted" title — with unicode', recipes=["a", "b"],
        instruction="## Requirements\n1. Do it.\n", solution_patch="diff --git a/x b/x\n", test_files={"tests/test_x.py": "def test():\n    pass\n"},
        repo_name="demo", language="python", base_commit="a" * 40, test_command="{python} -m pytest -q", snapshot=True,
        feature_test_command="{python} -m pytest -q {files}", setup_command="echo hi", timeout=55, attempts=2,
    )
    pkg.write(tmp_path / "t")
    back = TaskPackage.load(tmp_path / "t")
    assert back == pkg
    assert (tmp_path / "t" / "tests" / "tests" / "test_x.py").exists()
    assert (tmp_path / "t" / "instruction.md").exists() and (tmp_path / "t" / "solution" / "solution.patch").exists()
