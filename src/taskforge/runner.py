"""Runs commands inside throwaway workspaces.

Every check runs in a fresh copy of the repository at its base commit, in a
temporary directory, with a timeout and with secret-looking environment
variables removed. (Docker would add stronger isolation; see docs/LIMITATIONS.md.)
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .package import RepoConfig
from .patchutil import safe_relpath

IGNORE_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "node_modules", ".venv", "venv", "env", "dist", "build", ".idea", ".vscode",
    "taskforge_out",
}
SECRET_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.I)
MAX_OUTPUT = 4_000_000  # large suites print one summary line per test; keep them all
FIXED_DATE = "2000-01-01T00:00:00+00:00"
OUTCOME_RE = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)[ \t]+(\S.*?)[ \t]*$", re.M)


class PatchError(RuntimeError):
    pass


class GitError(RuntimeError):
    pass


@dataclass
class RunResult:
    cmd: str
    returncode: int
    stdout: str
    duration: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def tail(self, n: int = 1500) -> str:
        return self.stdout[-n:]


def command_tokens(template: str, files: list[str] | tuple[str, ...] = ()) -> list[str]:
    tokens: list[str] = []
    for tok in shlex.split(template, posix=True):
        if tok == "{python}":
            tokens.append(sys.executable)
        elif tok == "{files}":
            tokens.extend(files)
        else:
            tokens.append(tok)
    # pytest: print one outcome line per test, and do not write cache files
    for i, tok in enumerate(tokens):
        if tok == "pytest" or tok.endswith("pytest"):
            extra = []
            if not any(t.startswith("-r") for t in tokens):
                extra += ["-rA"]
            if "no:cacheprovider" not in tokens:
                extra += ["-p", "no:cacheprovider"]
            tokens[i + 1:i + 1] = extra
            break
    return tokens


def feature_command(repo: RepoConfig, files: list[str]) -> list[str]:
    if repo.feature_test_command:
        return command_tokens(repo.feature_test_command, files)
    if "pytest" in repo.test_command:
        return command_tokens(repo.test_command, []) + list(files)
    return command_tokens(repo.test_command, [])  # suite-level: cannot isolate feature tests


def clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not SECRET_RE.search(k)}
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONUTF8": "1",
        "NO_COLOR": "1",
    })
    env.pop("PYTHONPATH", None)
    return env


def scrub_paths(text: str, cwd: Path) -> str:
    """Hide machine-specific paths (the temp workspace and the user's home) in captured output,
    so saved evidence and AI prompts neither leak personal paths nor differ between machines."""
    home = str(Path.home())
    for raw, repl in ((str(cwd), "<repo>"), (home, "~")):
        for variant in {raw, raw.replace("\\", "/"), raw.replace("\\", "\\\\")}:
            text = text.replace(variant, repl)
    # pytest's temporary folders carry the user name and a run counter
    return re.sub(r"pytest-of-[^\\/\s'\"]+([\\/]+)pytest-\d+", r"pytest-of-user\1pytest-0", text)


def run_tokens(tokens: list[str], cwd: Path, timeout: int, extra_env: dict[str, str] | None = None) -> RunResult:
    exe = tokens[0]
    if not os.path.isabs(exe):
        found = shutil.which(exe)
        if found:
            tokens = [found] + tokens[1:]
    start = time.monotonic()
    try:
        p = subprocess.run(
            tokens, cwd=str(cwd), env={**clean_env(), **(extra_env or {})}, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
        out = scrub_paths((p.stdout or "") + (p.stderr or ""), cwd)
        return RunResult(" ".join(tokens), p.returncode, out[-MAX_OUTPUT:], time.monotonic() - start)
    except subprocess.TimeoutExpired as e:
        partial = (e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
        return RunResult(" ".join(tokens), -9, scrub_paths(partial, cwd)[-MAX_OUTPUT:], time.monotonic() - start, timed_out=True)
    except FileNotFoundError as e:
        return RunResult(" ".join(tokens), 127, f"command not found: {e}", time.monotonic() - start)


def _node_id(rest: str) -> str:
    """The node id at the start of a summary line. Parametrised ids may contain spaces and even
    " - ", so cut the trailing failure message only where the [parameter] brackets are closed."""
    if rest.startswith("["):  # "SKIPPED [1] file:line: reason" has no node id
        return rest.split()[0]
    start = 0
    while (cut := rest.find(" - ", start)) != -1:
        head = rest[:cut]
        if "[" not in head or head.endswith("]"):
            return head
        start = cut + 1
    return rest


def parse_outcomes(output: str) -> dict[str, str]:
    """Map pytest node ids to PASSED/FAILED/... from a ``-rA`` summary."""
    return {_node_id(m.group(2)): m.group(1) for m in OUTCOME_RE.finditer(output)}


# ---------------------------------------------------------------- git helpers

def _git(args: list[str], cwd: Path, check: bool = True, extra_env: dict | None = None, input_text: str | None = None):
    base = ["git", "-c", "core.autocrlf=false", "-c", "core.safecrlf=false", "-c", "core.filemode=false",
            "-c", "user.name=taskforge", "-c", "user.email=taskforge@example.invalid", "-c", "commit.gpgsign=false"]
    env = os.environ.copy()
    env.update(extra_env or {})
    p = subprocess.run(base + args, cwd=str(cwd), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", input=input_text)
    if check and p.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {(p.stderr or p.stdout).strip()[:500]}")
    return p


def is_git_root(path: Path) -> bool:
    p = _git(["rev-parse", "--show-toplevel"], path, check=False)
    return p.returncode == 0 and Path(p.stdout.strip()).resolve() == path.resolve()


def head_commit(path: Path) -> str:
    return _git(["rev-parse", "HEAD"], path).stdout.strip()


def is_dirty(path: Path) -> bool:
    return bool(_git(["status", "--porcelain"], path).stdout.strip())


def _copy_tree(src: Path, dst: Path) -> None:
    """Copy a tree, skipping junk. Text files are normalised to LF so that the
    snapshot hash is the same on Windows, macOS and Linux."""
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS and not d.endswith(".egg-info"))
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for name in sorted(files):
            if name.endswith((".pyc", ".pyo")):
                continue
            data = (Path(root) / name).read_bytes()
            if b"\0" not in data:
                try:
                    data = data.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
                except UnicodeDecodeError:
                    pass
            (dst / rel / name).write_bytes(data)


def _commit_snapshot(repo_dir: Path) -> str:
    env = {"GIT_AUTHOR_DATE": FIXED_DATE, "GIT_COMMITTER_DATE": FIXED_DATE}
    _git(["init", "-q"], repo_dir)
    _git(["add", "-A"], repo_dir)
    _git(["commit", "-q", "--allow-empty", "-m", "taskforge snapshot"], repo_dir, extra_env=env)
    return head_commit(repo_dir)


def _force_remove(func, path, exc_info):  # noqa: ARG001
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def remove_tree(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=lambda f, p, e: _force_remove(f, p, e))
    else:
        shutil.rmtree(path, onerror=_force_remove)


def snapshot_commit(path: Path) -> str:
    """The deterministic commit id a plain (non-git) folder gets when snapshotted."""
    tmp = Path(tempfile.mkdtemp(prefix="tf_snap_"))
    try:
        _copy_tree(path, tmp)
        return _commit_snapshot(tmp)
    finally:
        remove_tree(tmp)


# ------------------------------------------------------------------ workspace

class Workspace:
    """A throwaway checkout of the repository at its base commit."""

    def __init__(self, repo: RepoConfig):
        self.repo = repo
        self.root = Path(tempfile.mkdtemp(prefix="tf_ws_"))
        self.dir = self.root / "repo"
        try:
            if repo.snapshot:
                _copy_tree(repo.path, self.dir)
                got = _commit_snapshot(self.dir)
                if got != repo.base_commit:
                    raise GitError(
                        f"repository content changed since the task was made (snapshot {got[:10]} != {repo.base_commit[:10]})")
            else:
                _git(["clone", "-q", "--no-hardlinks", str(repo.path), str(self.dir)], self.root)
                _git(["checkout", "-q", repo.base_commit], self.dir)
        except Exception:
            remove_tree(self.root)
            raise

    def __enter__(self) -> "Workspace":
        return self

    def __exit__(self, *exc) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self.root.exists():
            remove_tree(self.root)

    # files
    def write_files(self, files: dict[str, str]) -> None:
        for rel, content in files.items():
            rel = safe_relpath(rel)
            target = self.dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.replace("\r\n", "\n").encode("utf-8"))

    def read(self, rel: str) -> str:
        return (self.dir / safe_relpath(rel)).read_text(encoding="utf-8")

    def exists(self, rel: str) -> bool:
        return (self.dir / safe_relpath(rel)).exists()

    def list_files(self) -> list[str]:
        out = _git(["ls-files"], self.dir).stdout.splitlines()
        return sorted(out)

    # patches
    def apply_patch(self, patch: str) -> None:
        if not patch.strip():
            raise PatchError("empty patch")
        patch_file = self.root / "change.patch"
        patch_file.write_bytes(patch.replace("\r\n", "\n").encode("utf-8"))
        p = _git(["apply", "--whitespace=nowarn", str(patch_file)], self.dir, check=False)
        if p.returncode != 0:
            raise PatchError((p.stderr or p.stdout).strip()[:800])

    def make_patch(self, paths: list[str]) -> str:
        """The unified diff of the given paths against the base commit."""
        paths = [safe_relpath(p) for p in paths]
        _git(["add", "-A", "--"] + paths, self.dir)
        p = _git(["diff", "--cached", "--binary", "--no-color", "--no-ext-diff", "HEAD", "--"] + paths, self.dir)
        _git(["reset", "-q"], self.dir)
        text = p.stdout
        return text if text.endswith("\n") or not text else text + "\n"

    # running
    def env(self) -> dict[str, str]:
        """Extra environment for commands run in this workspace."""
        if not self.repo.pythonpath:
            return {}
        return {"PYTHONPATH": str(self.dir / safe_relpath(self.repo.pythonpath))}

    def run(self, tokens: list[str], timeout: int | None = None,
            extra_env: dict[str, str] | None = None) -> RunResult:
        env = self.env()
        for key, value in (extra_env or {}).items():
            env[key] = os.pathsep.join([value, env[key]]) if key == "PYTHONPATH" and key in env else value
        return run_tokens(tokens, self.dir, timeout or self.repo.timeout, env)

    def run_setup(self) -> RunResult | None:
        if not self.repo.setup_command:
            return None
        return self.run(command_tokens(self.repo.setup_command))

    def run_tests(self, timeout: int | None = None) -> RunResult:
        return self.run(command_tokens(self.repo.test_command), timeout)

    def run_feature_tests(self, files: list[str], timeout: int | None = None) -> RunResult:
        return self.run(feature_command(self.repo, files), timeout)
