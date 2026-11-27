"""Command-line interface: ``taskforge <command>``."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__
from .checker import PROOF_ORDER, Checker, check_package
from .controls import render_matrix, run_controls
from .generator import Factory
from .harbor import ExportError, HarborConfig, export_task, simulate_task, upstream_check
from .llm import LLMError, make_backend
from .package import TaskPackage
from .recipes import RECIPES
from .report import PROOF_LABELS, write_reports
from .repo import detect_language, load_context, resolve_repo
from .runner import PatchError, Workspace
from .solver import solve_all
from .webapp import App, make_server

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYM = {"pass": "PASS", "fail": "FAIL", "skipped": "skip"}


def _say(msg: str = "") -> None:
    print(msg, flush=True)


def _repo_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("repo", help="path to the repository folder")
    p.add_argument("--name", help="name used in task ids (default: folder name)")
    p.add_argument("--language", help="override language detection")
    p.add_argument("--test-command", help="command that runs the repo's tests; {python} = this Python")
    p.add_argument("--feature-test-command", help="command for only the new tests; use {files}")
    p.add_argument("--setup-command", help="command run once in each fresh workspace (e.g. install deps)")
    p.add_argument("--timeout", type=int, default=120, help="seconds allowed per test run")
    p.add_argument("--allow-dirty", action="store_true", help="allow uncommitted changes in a git repository")


def _resolve(a) -> "RepoConfig":  # noqa: F821
    return resolve_repo(
        a.repo, name=a.name, test_command=a.test_command, feature_test_command=a.feature_test_command,
        setup_command=a.setup_command, language=a.language, allow_dirty=a.allow_dirty, timeout=a.timeout,
    )


# ---------------------------------------------------------------- commands

def cmd_recipes(a) -> int:
    for r in RECIPES:
        _say(f"{r.id:22s} [{r.family}]  {r.title}")
    return 0


def cmd_analyze(a) -> int:
    cfg = _resolve(a)
    _say(f"repository : {cfg.name}")
    _say(f"language   : {cfg.language}")
    _say(f"commit     : {cfg.base_commit}" + ("  (snapshot of a non-git folder)" if cfg.snapshot else ""))
    _say(f"tests      : {cfg.test_command}")
    with Workspace(cfg) as ws:
        ctx = load_context(cfg, ws.dir)
    _say(f"files      : {len(ctx.tree)} total, {len(ctx.sources)} source, {len(ctx.tests)} test")
    base, _ = Checker(cfg).baseline()
    _say(f"baseline   : {base.status.upper()}  {base.detail}")
    return 0 if base.status == "pass" else 1


def cmd_generate(a) -> int:
    cfg = _resolve(a)
    out = Path(a.out or f"taskforge_out/{cfg.name}")
    backend = make_backend(
        a.backend, model=a.model, cache_dir=Path(a.record_dir) if a.record_dir else None,
        replay_dir=Path(a.replay_dir) if a.replay_dir else None, max_calls=a.max_calls,
    )
    only = [x.strip() for x in a.recipes.split(",")] if a.recipes else None
    factory = Factory(cfg, backend, out, seed=a.seed, max_attempts=a.attempts, log=_say)
    t0 = time.monotonic()
    try:
        results = factory.run(a.n, only)
    except (LLMError, RuntimeError) as e:
        _say(f"error: {e}")
        return 2
    summary = factory.write_run_summary(results, time.monotonic() - t0)
    paths = write_reports(out)
    _say("")
    if summary.get("pending"):
        pend = Path(a.replay_dir) / "pending"
        _say(f"{summary['pending']} task(s) are waiting for an AI answer. Prompts are in: {pend}")
        _say("Write each reply (exact output format) to <replay-dir>/<key>.txt, where <key> is the prompt file name "
             "without '.prompt.txt', then run the same command again.")
    _say(f"accepted {summary['accepted']} of {summary['requested']} tasks "
         f"(variation score {summary['variation_score']}); AI calls: {summary['ai'].get('calls')}")
    _say(f"report: {paths['html']}")
    return 0


def _print_report(rep) -> None:
    b = rep.baseline
    _say(f"  {'baseline':17s} {SYM.get(b.status, b.status) if b else '-':5s} {b.detail if b else ''}")
    for p in rep.proofs:
        _say(f"  {p.name:17s} {SYM.get(p.status, p.status):5s} {p.detail}")


def cmd_check(a) -> int:
    d = Path(a.task)
    _say(f"checking {d.name} against {a.repo}")
    rep = check_package(d, Path(a.repo), max_mutants=a.max_mutants, min_kill_rate=a.min_kill_rate, seed=a.seed)
    _print_report(rep)
    _say(f"verdict: {'ACCEPTED' if rep.accepted else 'REJECTED'}  ({rep.seconds:.1f}s)")
    if a.update:
        (d / "validation").mkdir(exist_ok=True)
        (d / "validation" / "proofs.json").write_text(json.dumps(rep.to_dict(), indent=2), encoding="utf-8", newline="\n")
    if a.json:
        _say(json.dumps(rep.to_dict(), indent=2))
    return 0 if rep.accepted else 1


def cmd_check_all(a) -> int:
    root = Path(a.folder)
    dirs = sorted(p for p in root.rglob("task.toml"))
    if not dirs:
        _say(f"no task.toml found under {root}")
        return 2
    first = TaskPackage.load(dirs[0].parent)
    checker = Checker(first.repo_config(Path(a.repo)), max_mutants=a.max_mutants, min_kill_rate=a.min_kill_rate, seed=a.seed)
    bad = 0
    _say(f"{'task':44s} " + " ".join(f"{n[:14]:14s}" for n in PROOF_ORDER) + " verdict")
    for t in dirs:
        pkg = TaskPackage.load(t.parent)
        rep = checker.check(pkg)
        cells = " ".join(f"{(SYM.get(rep.proof(n).status, '-') if rep.proof(n) else '-'):14s}" for n in PROOF_ORDER)
        _say(f"{pkg.task_id[:44]:44s} {cells} {'ACCEPTED' if rep.accepted else 'REJECTED'}")
        if a.update:
            (t.parent / "validation").mkdir(exist_ok=True)
            (t.parent / "validation" / "proofs.json").write_text(json.dumps(rep.to_dict(), indent=2), encoding="utf-8", newline="\n")
        bad += 0 if rep.accepted else 1
    _say(f"{len(dirs) - bad} of {len(dirs)} accepted")
    return 0 if bad == 0 else 1


def cmd_solve(a) -> int:
    """Let an AI solve each task from the instruction alone, then judge it with the hidden tests."""
    backend = make_backend(
        a.backend, model=a.model, cache_dir=Path(a.record_dir) if a.record_dir else None,
        replay_dir=Path(a.replay_dir) if a.replay_dir else None, max_calls=a.max_calls,
    )
    out = Path(a.out or f"taskforge_out/solve_{Path(a.folder).name}")
    try:
        data = solve_all(Path(a.folder), Path(a.repo), backend, out, attempts=a.attempts, label=a.label or "", log=_say)
    except (LLMError, RuntimeError) as e:
        _say(f"error: {e}")
        return 2
    s = data["summary"]
    _say("")
    if data["pending"]:
        pend = Path(a.replay_dir) / "pending"
        _say(f"{data['pending']} task(s) are waiting for an AI answer. Prompts are in: {pend}")
        _say("Write each reply (exact output format) to <replay-dir>/<key>.txt, where <key> is the prompt file name "
             "without '.prompt.txt', then run the same command again.")
    _say(f"solved {s['solved']} of {s['tasks']} tasks ({s['solve_rate']}); first try: {s['solved_first_try']}")
    _say(f"report: {out / 'solver_report.html'}")
    return 0


def _task_dirs(folder: Path) -> list[Path]:
    if (folder / "task.toml").exists():
        return [folder]
    found = sorted(p.parent for p in folder.glob("*/task.toml"))
    if not found:
        raise FileNotFoundError(f"no task.toml found in {folder}")
    return found


def cmd_export(a) -> int:
    """Write Harbor 0.25 task folders for accepted task packages."""
    config = HarborConfig.load(Path(a.config))
    summaries, bad = {}, 0
    for task_dir in _task_dirs(Path(a.folder)):
        try:
            out, summary = export_task(task_dir, Path(a.repo), config, Path(a.out))
        except (ExportError, PatchError) as e:
            _say(f"FAILED   {task_dir.name}: {e}")
            bad += 1
            continue
        summaries[out.name] = summary
        _say(f"exported {out.name}: {summary['fail_to_pass']} fail-to-pass, "
             f"{summary['existing_tests_passing_before']} existing tests kept passing")
    if a.evidence:
        Path(a.evidence).parent.mkdir(parents=True, exist_ok=True)
        Path(a.evidence).write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0 if bad == 0 else 1


def cmd_simulate(a) -> int:
    """Rehearse Harbor's nop and oracle checks without Docker."""
    results, bad = [], 0
    _say("local rehearsal of the grading script (no Docker; not a Harbor run)")
    for task_dir in _task_dirs(Path(a.folder)):
        r = simulate_task(task_dir, Path(a.repo))
        results.append(r)
        bad += 0 if r["ok"] else 1
        _say(f"{r['task'][:44]:44s} nop {r['nop']['reward']:<6} oracle {r['oracle']['reward']:<6} "
             f"{'OK' if r['ok'] else 'WRONG'}")
    _say(f"{len(results) - bad} of {len(results)} tasks give nop 0.0 and oracle 1.0")
    if a.evidence:
        Path(a.evidence).parent.mkdir(parents=True, exist_ok=True)
        Path(a.evidence).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0 if bad == 0 else 1


def cmd_upstream(a) -> int:
    """Check that no task's feature already exists in a newer upstream commit."""
    results, bad = [], 0
    for task_dir in _task_dirs(Path(a.folder)):
        r = upstream_check(task_dir, Path(a.repo), a.ref)
        results.append(r)
        bad += 0 if r["new_tests_fail_upstream"] else 1
        verdict = "new (tests fail upstream)" if r["new_tests_fail_upstream"] else "ALREADY EXISTS UPSTREAM"
        _say(f"{r['task'][:44]:44s} {verdict}")
    if a.evidence:
        Path(a.evidence).parent.mkdir(parents=True, exist_ok=True)
        Path(a.evidence).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0 if bad == 0 else 1


def cmd_report(a) -> int:
    paths = write_reports(Path(a.out_dir))
    for k, p in paths.items():
        _say(f"{k:5s} {p}")
    return 0


def cmd_controls(a) -> int:
    shop = Path(a.shop) if a.shop else PROJECT_ROOT / "examples" / "shop"
    outs = run_controls(shop, Path(a.out) if a.out else None)
    table = render_matrix(outs)
    _say(table)
    ok = all(o.as_expected for o in outs)
    _say("")
    _say("checker self-test: " + ("every control task got the expected verdict" if ok else "MISMATCH, see table"))
    if a.out:
        (Path(a.out) / "controls.md").write_text("# Checker self-test (control tasks)\n\n" + table + "\n", encoding="utf-8", newline="\n")
    return 0 if ok else 1


def cmd_demo(a) -> int:
    """Run the whole pipeline offline on a bundled example, replaying recorded AI answers."""
    repo = PROJECT_ROOT / "examples" / a.example
    replay = PROJECT_ROOT / "samples" / "replay" / a.example
    meta_file = replay / "meta.json"
    if not repo.is_dir() or not meta_file.exists():
        _say(f"no bundled demo for '{a.example}' (looked for {repo} and {meta_file})")
        return 2
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    ns = argparse.Namespace(
        repo=str(repo), name=a.example, language=None, test_command=None, feature_test_command=None, setup_command=None,
        timeout=120, allow_dirty=False, out=a.out or f"taskforge_out/demo_{a.example}", backend="replay", model=None,
        record_dir=None, replay_dir=str(replay), max_calls=None, recipes=",".join(meta["recipes"]) if meta.get("recipes") else None,
        seed=meta["seed"], attempts=meta.get("attempts", 3), n=meta["n"],
    )
    return cmd_generate(ns)


def cmd_ui(a) -> int:
    """Start the local web page."""
    try:
        server = make_server(App(), a.port)
    except OSError as e:
        _say(f"error: cannot use port {a.port} ({e}); try --port with another number")
        return 2
    url = f"http://localhost:{server.server_address[1]}"
    _say(f"TaskForge is running at {url}  (only this computer can reach it; press Ctrl+C to stop)")
    if a.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _say("stopped")
    finally:
        server.server_close()
    return 0


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Read KEY=VALUE lines from ./.env (never overriding real environment variables)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #")[0].strip().strip("\"'")
        if key.strip() and value:
            os.environ.setdefault(key.strip(), value)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    parser = argparse.ArgumentParser(prog="taskforge", description="Turn a code repository into verified coding tasks.")
    parser.add_argument("--version", action="version", version=f"taskforge {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("recipes", help="list the feature recipes").set_defaults(fn=cmd_recipes)

    p = sub.add_parser("analyze", help="show what taskforge understands about a repository")
    _repo_args(p)
    p.set_defaults(fn=cmd_analyze)

    p = sub.add_parser("generate", help="generate and verify tasks for a repository")
    _repo_args(p)
    p.add_argument("--out", help="output folder (default: taskforge_out/<name>)")
    p.add_argument("-n", "--n", type=int, default=6, help="how many tasks to attempt")
    p.add_argument("--backend", default=os.environ.get("TASKFORGE_BACKEND", "claude"), choices=["claude", "api", "manual", "replay"])
    p.add_argument("--model", help="model name (backend default if omitted)")
    p.add_argument("--replay-dir", help="folder of recorded AI answers (replay backend)")
    p.add_argument("--record-dir", help="cache AI answers here so reruns are free and repeatable")
    p.add_argument("--max-calls", type=int, help="stop after this many AI calls")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--attempts", type=int, default=3, help="max attempts per task (1 + retries)")
    p.add_argument("--recipes", help="comma-separated recipe ids to use (default: all)")
    p.set_defaults(fn=cmd_generate)

    for name, fn, helptext in (("check", cmd_check, "re-run all proofs for one task package (offline, no AI)"),):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("task", help="task folder (contains task.toml)")
        p.add_argument("--repo", required=True, help="path to the repository the task was made for")
        p.add_argument("--max-mutants", type=int, default=12)
        p.add_argument("--min-kill-rate", type=float, default=0.6)
        p.add_argument("--seed", type=int, default=0, help="which random sample of broken versions to try")
        p.add_argument("--update", action="store_true", help="rewrite validation/proofs.json")
        p.add_argument("--json", action="store_true")
        p.set_defaults(fn=fn)

    p = sub.add_parser("check-all", help="re-run all proofs for every task package under a folder")
    p.add_argument("folder")
    p.add_argument("--repo", required=True)
    p.add_argument("--max-mutants", type=int, default=12)
    p.add_argument("--min-kill-rate", type=float, default=0.6)
    p.add_argument("--seed", type=int, default=0, help="which random sample of broken versions to try")
    p.add_argument("--update", action="store_true")
    p.set_defaults(fn=cmd_check_all)

    p = sub.add_parser("solve", help="let an AI solve each task from the instruction alone and score it with the hidden tests")
    p.add_argument("folder", help="folder of task packages")
    p.add_argument("--repo", required=True, help="path to the repository the tasks were made for")
    p.add_argument("--out", help="output folder (default: taskforge_out/solve_<folder name>)")
    p.add_argument("--backend", default=os.environ.get("TASKFORGE_BACKEND", "claude"), choices=["claude", "api", "manual", "replay"])
    p.add_argument("--model", help="model name (backend default if omitted)")
    p.add_argument("--label", help="name of the solver shown in the report (default: backend name)")
    p.add_argument("--replay-dir", help="folder of recorded answers (manual/replay backends)")
    p.add_argument("--record-dir", help="cache AI answers here so reruns are free and repeatable")
    p.add_argument("--max-calls", type=int, help="stop after this many AI calls")
    p.add_argument("--attempts", type=int, default=1, help="attempts per task; later attempts see the failing test output")
    p.set_defaults(fn=cmd_solve)

    p = sub.add_parser("export", help="write Harbor 0.25 task folders for accepted task packages")
    p.add_argument("folder", help="a task package, or a folder of them")
    p.add_argument("--repo", required=True, help="path to the repository the tasks were made for")
    p.add_argument("--config", required=True, help="Harbor settings, for example configs/click.json")
    p.add_argument("--out", required=True, help="folder for the Harbor tasks")
    p.add_argument("--evidence", help="also write the test counts to this JSON file")
    p.set_defaults(fn=cmd_export)

    for name, fn, helptext in (
        ("simulate", cmd_simulate, "rehearse Harbor's nop and oracle checks without Docker"),
        ("upstream", cmd_upstream, "check that the features do not exist in a newer upstream commit"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("folder", help="a task folder, or a folder of them")
        p.add_argument("--repo", required=True, help="path to the repository")
        p.add_argument("--evidence", help="write the results to this JSON file")
        if name == "upstream":
            p.add_argument("--ref", required=True, help="full hash of the newer upstream commit")
        p.set_defaults(fn=fn)

    p = sub.add_parser("report", help="rebuild report.md / report.html / report.json from a run folder")
    p.add_argument("out_dir")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("controls", help="self-test: prove the checker accepts a good task and rejects bad ones")
    p.add_argument("--shop", help="path to the shop example (default: bundled)")
    p.add_argument("--out", help="also write the control task packages and controls.md here")
    p.set_defaults(fn=cmd_controls)

    p = sub.add_parser("ui", help="open the local web page that makes an exam step by step")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--open", action="store_true", help="also open it in your web browser")
    p.set_defaults(fn=cmd_ui)

    p = sub.add_parser("demo", help="run the full pipeline offline with recorded AI answers")
    p.add_argument("--example", default="shop")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_demo)

    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, FileNotFoundError, LLMError) as e:
        _say(f"error: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
