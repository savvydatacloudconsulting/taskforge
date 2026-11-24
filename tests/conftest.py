from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def shop_path() -> Path:
    return ROOT / "examples" / "shop"


@pytest.fixture(scope="session")
def shop_repo(shop_path):
    from taskforge.repo import resolve_repo

    return resolve_repo(shop_path, name="shop")


def git(cwd: Path, *args: str) -> str:
    p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
                       cwd=cwd, capture_output=True, text=True, check=True)
    return p.stdout.strip()


@pytest.fixture
def make_git_repo(tmp_path):
    """Create a small real git repository from {relative path: content}."""

    def _make(files: dict[str, str], name: str = "proj") -> Path:
        root = tmp_path / name
        root.mkdir()
        for rel, content in files.items():
            f = root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content, encoding="utf-8", newline="\n")
        git(root, "init", "-q")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "init")
        return root

    return _make
