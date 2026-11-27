"""Understanding a repository: language, test command, commit, and a code map
small enough to put in a prompt."""

from __future__ import annotations

import ast
import os
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath

from .package import RepoConfig
from .patchutil import is_test_path
from .runner import IGNORE_DIRS, head_commit, is_dirty, is_git_root, snapshot_commit

EXT_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".java": "java", ".go": "go",
    ".rs": "rust", ".rb": "ruby", ".cs": "csharp", ".php": "php",
}
LANG_EXT = {}
for _e, _l in EXT_LANG.items():
    LANG_EXT.setdefault(_l, set()).add(_e)
LANG_EXT["javascript"].add(".mjs")


def iter_files(path: Path):
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS and not d.endswith(".egg-info"))
        for name in sorted(files):
            full = Path(root) / name
            yield full.relative_to(path).as_posix(), full


def detect_language(path: Path) -> str:
    counts = Counter(EXT_LANG[Path(rel).suffix] for rel, _ in iter_files(path) if Path(rel).suffix in EXT_LANG)
    return counts.most_common(1)[0][0] if counts else "unknown"


def infer_test_command(path: Path, language: str) -> str | None:
    if language == "python":
        return "{python} -m pytest -q"
    if language in ("javascript", "typescript"):
        pkg = path / "package.json"
        if pkg.exists() and '"test"' in pkg.read_text(encoding="utf-8", errors="replace"):
            return "npm test --silent"
        return "node --test"
    if language == "go":
        return "go test ./..."
    if language == "rust":
        return "cargo test --quiet"
    if language == "java":
        if (path / "pom.xml").exists():
            return "mvn -q test"
        if (path / "build.gradle").exists() or (path / "build.gradle.kts").exists():
            return "gradle test --quiet"
    return None


def resolve_repo(
    path: str | Path, *, name: str | None = None, test_command: str | None = None,
    feature_test_command: str | None = None, setup_command: str | None = None,
    language: str | None = None, allow_dirty: bool = False, timeout: int = 120,
) -> RepoConfig:
    p = Path(path).resolve()
    if not p.is_dir():
        raise FileNotFoundError(f"repository folder not found: {p}")
    lang = language or detect_language(p)
    cmd = test_command or infer_test_command(p, lang)
    if not cmd:
        raise ValueError(f"cannot infer a test command for language '{lang}'; pass --test-command")
    if is_git_root(p):
        if is_dirty(p) and not allow_dirty:
            raise ValueError("the repository has uncommitted changes; commit them or pass --allow-dirty")
        commit, snapshot = head_commit(p), False
    else:
        commit, snapshot = snapshot_commit(p), True
    return RepoConfig(
        path=p, name=name or p.name, language=lang, base_commit=commit, test_command=cmd,
        feature_test_command=feature_test_command, setup_command=setup_command, snapshot=snapshot, timeout=timeout,
        pythonpath=detect_src_layout(p) if lang == "python" else None,
    )


def detect_src_layout(path: Path) -> str | None:
    """"src" when the packages live under src/ (tests must import them from there)."""
    src = path / "src"
    if src.is_dir() and any((child / "__init__.py").is_file() for child in src.iterdir() if child.is_dir()):
        return "src"
    return None


# ------------------------------------------------------------- code map

def python_outline(source: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "(unparseable)"
    out: list[str] = []

    def sig(node) -> str:
        args = ast.unparse(node.args)
        ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        return f"def {node.name}({args}){ret}"

    def walk(nodes, indent):
        for n in nodes:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = (ast.get_docstring(n) or "").splitlines()
                out.append(f"{indent}{sig(n)}" + (f"  # {doc[0]}" if doc else ""))
            elif isinstance(n, ast.ClassDef):
                doc = (ast.get_docstring(n) or "").splitlines()
                out.append(f"{indent}class {n.name}" + (f"  # {doc[0]}" if doc else ""))
                walk(n.body, indent + "    ")

    walk(tree.body, "")
    return "\n".join(out) or "(no definitions)"


def generic_outline(source: str, limit: int = 60) -> str:
    keys = ("function ", "class ", "def ", "func ", "public ", "export ", "module.exports", "fn ", "struct ")
    lines = [ln.rstrip() for ln in source.splitlines() if ln.lstrip().startswith(keys)]
    return "\n".join(lines[:limit]) or "\n".join(source.splitlines()[:20])


def outline(rel: str, source: str) -> str:
    return python_outline(source) if rel.endswith(".py") else generic_outline(source)


@dataclass
class RepoContext:
    tree: list[str]
    sources: dict[str, str]          # non-test source files (full text)
    tests: dict[str, str]            # test files (full text)
    test_dir: str
    full_text: str = ""
    overflow: bool = False           # True when not every source file fits in the budget
    shown_full: list[str] = field(default_factory=list)


def load_context(repo: RepoConfig, workspace_dir: Path | None = None) -> RepoContext:
    root = workspace_dir or repo.path
    exts = LANG_EXT.get(repo.language, set())
    tree, sources, tests = [], {}, {}
    for rel, full in iter_files(root):
        tree.append(rel)
        if Path(rel).suffix in exts:
            try:
                text = full.read_text(encoding="utf-8").replace("\r\n", "\n")
            except UnicodeDecodeError:
                continue
            if is_test_path(rel):
                tests[rel] = text
            elif not repo.pythonpath or rel.startswith(repo.pythonpath + "/"):
                sources[rel] = text  # in a src layout, docs and example scripts are not the library
    test_dir = "tests"
    for rel in tests:
        parts = rel.split("/")
        if len(parts) > 1:
            test_dir = parts[0] if parts[0].lower() in ("tests", "test", "__tests__", "spec") else "/".join(parts[:-1])
            break
    return RepoContext(tree=tree, sources=sources, tests=tests, test_dir=test_dir)


def python_definitions(source: str, name: str) -> list[tuple[int, int]]:
    """Line ranges (1-based, inclusive, decorators included) of every definition called ``name``,
    which may be dotted ("Class.method"). Overloads give more than one range."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    nodes: list = list(tree.body)
    parts = name.split(".")
    found: list = []
    for depth, part in enumerate(parts):
        found = [n for n in nodes
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == part]
        if depth < len(parts) - 1:
            nodes = [child for n in found for child in n.body]
    return [(min([n.lineno] + [d.lineno for d in n.decorator_list]), n.end_lineno) for n in found]


def _module_header(source: str, limit: int = 120) -> str:
    """The lines before the first top-level definition: imports and module constants."""
    out = []
    for line in source.splitlines()[:limit]:
        if line.startswith(("def ", "class ", "async def ", "@")):
            break
        out.append(line)
    return "\n".join(out).rstrip()


def render_selection(ctx: RepoContext, selected: list[str], budget: int = 110_000) -> RepoContext:
    """For large repositories: show the selected files or definitions in full, outline everything else.

    ``selected`` entries are paths, or "path::Name" for one class, function or "Class.method".
    """
    whole: list[str] = []
    wanted: dict[str, list[str]] = {}
    for entry in selected:
        path, _, symbol = entry.partition("::")
        if path not in ctx.sources:
            continue
        if symbol:
            wanted.setdefault(path, []).append(symbol)
        elif path not in whole:
            whole.append(path)

    parts = ["## File tree", "\n".join(sorted(ctx.sources) + sorted(ctx.tests)), ""]
    used = 0
    shown: list[str] = []
    for rel in whole:
        text = ctx.sources[rel].rstrip()
        if used + len(text) <= budget:
            parts += [f"## FILE {rel} (full content)", "```python", text, "```", ""]
            used += len(text)
            shown.append(rel)
    for rel, symbols in wanted.items():
        if rel in shown:
            continue
        source = ctx.sources[rel]
        lines = source.splitlines()
        header_done = False
        covered: list[tuple[int, int]] = []
        for symbol in symbols:
            for start, end in python_definitions(source, symbol):
                if any(a <= start and end <= b for a, b in covered):
                    continue
                block = "\n".join(lines[start - 1:end])
                if used + len(block) > budget:
                    continue
                if not header_done:
                    parts += [f"## FILE {rel} (top of the file)", "```python", _module_header(source), "```", ""]
                    header_done = True
                parts += [f"## EXCERPT {rel} :: {symbol} (lines {start}-{end}, exact current code)",
                          "```python", block, "```", ""]
                used += len(block)
                covered.append((start, end))
                shown.append(f"{rel}::{symbol}")
    parts.append("## Outlines of all source files (names and signatures only)")
    for rel in sorted(ctx.sources):
        if rel not in shown:
            parts += [f"### {rel}", outline(rel, ctx.sources[rel]), ""]
    if ctx.tests:
        stems = [PurePosixPath(s.partition("::")[0]).stem.lstrip("_") for s in shown]
        names = sorted(ctx.tests)
        sample = next((t for s in stems for t in names if PurePosixPath(t).name.startswith(f"test_{s}")),
                      next((t for t in names if PurePosixPath(t).name.startswith("test_")), names[0]))
        parts += [f"## Existing tests ({len(ctx.tests)} files): " + ", ".join(names),
                  f"## Start of the existing test file {sample} (style reference)", "```python",
                  ctx.tests[sample][:5000].rstrip(), "```"]
    return replace(ctx, full_text="\n".join(parts), overflow=True, shown_full=shown)


def render_context(ctx: RepoContext, budget: int = 60_000, force_full: list[str] | None = None) -> RepoContext:
    """Fill ``ctx.full_text``: whole files while they fit, outlines for the rest."""
    force_full = force_full or []
    parts = ["## File tree", "\n".join(ctx.tree[:400]), ""]
    used = sum(len(p) for p in parts)
    full, outlined = [], []
    order = sorted(ctx.sources, key=lambda r: (r not in force_full, len(ctx.sources[r])))
    for rel in order:
        size = len(ctx.sources[rel])
        if rel in force_full or used + size <= budget:
            full.append(rel)
            used += size
        else:
            outlined.append(rel)
    for rel in sorted(full):
        parts += [f"## FILE {rel} (full content)", "```", ctx.sources[rel].rstrip(), "```", ""]
    if outlined:
        parts.append("## Files shown as outlines only (their full content is NOT available; do not modify them)")
        for rel in sorted(outlined):
            parts += [f"### {rel}", outline(rel, ctx.sources[rel]), ""]
    if ctx.tests:
        sample = sorted(ctx.tests)[0]
        parts += [f"## Existing tests ({len(ctx.tests)} files): " + ", ".join(sorted(ctx.tests)[:20]),
                  f"## Example test file {sample} (style reference)", "```", ctx.tests[sample][:3500].rstrip(), "```"]
    ctx.full_text = "\n".join(parts)
    ctx.overflow = bool(outlined)
    ctx.shown_full = sorted(full)
    return ctx
