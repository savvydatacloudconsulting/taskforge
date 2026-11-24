"""Small helpers for reading unified diffs and checking file paths."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")

TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec", "specs"}


@dataclass
class FileChange:
    path: str
    added_lines: set[int] = field(default_factory=set)  # line numbers in the NEW file
    added_text: list[str] = field(default_factory=list)
    contexts: set[str] = field(default_factory=set)  # hunk headers (enclosing function names)


def parse_patch(patch: str) -> dict[str, FileChange]:
    """Return the added lines of every file touched by a unified diff."""
    changes: dict[str, FileChange] = {}
    current: FileChange | None = None
    new_ln = 0
    in_hunk = False
    for raw in patch.splitlines():
        if raw.startswith("diff --git "):
            current = None
            in_hunk = False
            continue
        if not in_hunk and raw.startswith("+++ "):
            target = raw[4:].split("\t")[0].strip()
            if target == "/dev/null":
                current = None
            else:
                path = target[2:] if target.startswith("b/") else target
                current = changes.setdefault(path, FileChange(path))
            continue
        m = HUNK_RE.match(raw)
        if m:
            in_hunk = True
            new_ln = int(m.group(1))
            ctx = m.group(2).strip()
            if current is not None and ctx:
                current.contexts.add(ctx)
            continue
        if current is None or not in_hunk:
            continue
        if raw.startswith("+"):
            current.added_lines.add(new_ln)
            current.added_text.append(raw[1:])
            new_ln += 1
        elif raw.startswith("-") or raw.startswith("\\"):
            continue
        else:
            new_ln += 1
    return changes


def touched_files(patch: str) -> list[str]:
    return sorted(parse_patch(patch))


def is_test_path(path: str) -> bool:
    p = PurePosixPath(path)
    name = p.name
    if any(part.lower() in TEST_DIR_NAMES for part in p.parts[:-1]):
        return True
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith("_test.go")
        or ".test." in name
        or ".spec." in name
        or name.endswith("Test.java")
        or name.endswith("Tests.cs")
    )


def safe_relpath(path: str) -> str:
    """Validate a repo-relative POSIX path. Raises ValueError when unsafe."""
    if not path or path != path.strip():
        raise ValueError(f"empty or padded path: {path!r}")
    if "\\" in path or path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise ValueError(f"path must be relative with forward slashes: {path!r}")
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts) or ".git" in parts:
        raise ValueError(f"path escapes the repository or is not normalised: {path!r}")
    return str(PurePosixPath(path))
