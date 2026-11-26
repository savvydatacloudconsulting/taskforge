"""The local web page for TaskForge: ``taskforge ui``.

It runs the real factory and checker and shows each step as it happens.

Because it executes repository tests and AI-written code, the server only listens on 127.0.0.1, rejects unexpected
Host headers (DNS rebinding) and requires a random per-session token on every API call (so that another web page
open in your browser cannot drive it).
"""

from __future__ import annotations

import ast
import json
import os
import queue
import secrets
import shutil
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .checker import Checker
from .generator import Factory
from .llm import AnthropicBackend, Backend, CachedBackend, ClaudeCodeBackend, DEFAULT_SYSTEM
from .mutate import apply_mutation
from .package import RepoConfig, TaskPackage
from .patchutil import parse_patch, touched_files
from .recipes import RECIPES, make_plan, plan_batch
from .repo import load_context, resolve_repo
from .runner import Workspace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAGE = Path(__file__).with_name("web") / "index.html"
MAX_BODY = 2_000_000
ANSWER_TIMEOUT = 3600
REPORTS = {  # read-only pages the viewer may open
    "shop": "evidence/shop/report.html",
    "library": "evidence/library/report.html",
    "solver-shop": "evidence/solver/shop/solver_report.html",
    "solver-library": "evidence/solver/library/solver_report.html",
}
SABOTAGE = {
    "passing_tests": ("Tests that already pass", "fails_before"),
    "broken_solution": ("A broken solution", "passes_after"),
    "weak_tests": ("Tests with the assertions removed", "tests_have_teeth"),
}


class Cancelled(Exception):
    """Deliberately not an LLMError, so the factory cannot mistake a cancel for a failed AI call."""


class Busy(RuntimeError):
    pass


# --------------------------------------------------------------------- jobs

class Job:
    """One run (making an exam, or trying to cheat the checker) and everything the page shows about it."""

    def __init__(self, kind: str, label: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.label = label
        self.state = "running"  # running | waiting | done | error | cancelled
        self.message = "starting"
        self.repo: dict | None = None
        self.attempt = 0
        self.attempts: list[dict] = []
        self.draft: dict | None = None
        self.proofs: dict[str, dict] = {}
        self.mutants: list[dict] = []
        self.mutants_planned = 0
        self.prompt = ""
        self.result: dict | None = None
        self.error = ""
        self.cancel_requested = False
        self.started = time.time()
        self.lock = threading.RLock()
        self._answers: queue.Queue[str] = queue.Queue(maxsize=1)

    @property
    def active(self) -> bool:
        return self.state in ("running", "waiting")

    def event(self, ev: dict) -> None:
        if self.cancel_requested:
            raise Cancelled("cancelled")
        with self.lock:
            kind = ev.get("type")
            if kind == "attempt":
                self.attempt = ev["number"]
                if ev.get("previous"):
                    self.attempts.append(ev["previous"])
                self.proofs, self.mutants, self.draft = {}, [], None
                self.message = f"attempt {ev['number']}: asking for the exam"
            elif kind == "draft":
                self.draft = {k: ev[k] for k in ("title", "instruction", "patch", "tests")}
                self.message = "draft received, checking it"
            elif kind == "proof_start":
                self.proofs[ev["name"]] = {"status": "running", "detail": ""}
                self.message = f"running check: {ev['name']}"
            elif kind == "proof":
                self.proofs[ev["name"]] = {"status": ev["status"], "detail": ev["detail"],
                                           "tail": str((ev.get("evidence") or {}).get("tail", ""))[-1500:]}
            elif kind == "mutant":
                self.mutants.append(ev["mutant"])
                self.mutants_planned = ev["planned"]
                self.message = f"breaking the solution on purpose: {len(self.mutants)} of {ev['planned']}"

    def ask(self, prompt: str) -> str:
        with self.lock:
            self.prompt, self.state = prompt, "waiting"
            self.message = "waiting for you to paste the AI's reply"
        deadline = time.time() + ANSWER_TIMEOUT
        while time.time() < deadline:
            if self.cancel_requested:
                raise Cancelled("cancelled")
            try:
                reply = self._answers.get(timeout=0.2)
            except queue.Empty:
                continue
            with self.lock:
                self.prompt, self.state, self.message = "", "running", "reading the reply"
            return reply
        raise Cancelled("no reply was pasted in time")

    def answer(self, reply: str) -> None:
        with self.lock:
            if self.state != "waiting":
                raise ValueError("this run is not waiting for a reply")
            if not reply.strip():
                raise ValueError("the reply is empty")
            self.state = "running"
        self._answers.put(reply)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "id": self.id, "kind": self.kind, "label": self.label, "state": self.state, "message": self.message,
                "repo": self.repo, "attempt": self.attempt, "attempts": list(self.attempts), "draft": self.draft,
                "proofs": dict(self.proofs), "mutants": list(self.mutants), "mutants_planned": self.mutants_planned,
                "prompt": self.prompt, "result": self.result, "error": self.error,
                "seconds": round(time.time() - self.started, 1),
            }


class PasteBackend(Backend):
    """Any AI chat: the page shows the prompt, the user pastes the reply."""

    name = "paste"

    def __init__(self, job: Job):
        super().__init__()
        self.job = job

    def complete(self, prompt: str, system: str = DEFAULT_SYSTEM) -> str:
        self.calls += 1
        return self.job.ask(f"{system}\n\n{prompt}")


# ---------------------------------------------------------------- sabotage

class _DropAssertions(ast.NodeTransformer):
    """Turns strong tests into weak ones: every assert and pytest.raises block becomes 'pass'."""

    def visit_Assert(self, node):
        return ast.copy_location(ast.Pass(), node)

    def visit_With(self, node):
        for item in node.items:
            call = item.context_expr
            if isinstance(call, ast.Call) and getattr(call.func, "attr", getattr(call.func, "id", "")) == "raises":
                return ast.copy_location(ast.Pass(), node)
        return self.generic_visit(node)


def sabotage(pkg: TaskPackage, kind: str, cfg: RepoConfig, mutants: list[dict]) -> tuple[TaskPackage, str]:
    """Return a deliberately bad copy of a good task, and a sentence saying what was changed."""
    import dataclasses

    if kind not in SABOTAGE:
        raise ValueError("unknown kind of sabotage")
    if kind == "passing_tests":
        path = pkg.feature_tests[0]
        if pkg.language == "python":
            body = "def test_nothing_new():\n    assert 1 + 1 == 2\n"
        elif pkg.language in ("javascript", "typescript"):
            body = 'const test = require("node:test");\ntest("nothing new", () => {});\n'
        else:
            raise ValueError("this sabotage is available for Python and JavaScript only")
        return (dataclasses.replace(pkg, test_files={path: body}),
                "Replaced the feature tests with a test that passes even without the new feature.")
    if pkg.language != "python":
        raise ValueError("this sabotage is available for Python only")
    if kind == "weak_tests":
        weak = {}
        for path, source in pkg.test_files.items():
            tree = _DropAssertions().visit(ast.parse(source))
            ast.fix_missing_locations(tree)
            weak[path] = ast.unparse(tree) + "\n"
        return (dataclasses.replace(pkg, test_files=weak),
                "Removed every assertion from the feature tests. They still run the code but check nothing.")
    caught = next((m for m in mutants if m.get("caught")), None)
    if caught is None:
        raise ValueError("no caught mutant is available for this task")
    with Workspace(cfg) as ws:
        ws.apply_patch(pkg.solution_patch)
        added = parse_patch(pkg.solution_patch)[caught["file"]].added_lines
        broken = apply_mutation(ws.read(caught["file"]), caught["site"], added)
        ws.write_files({caught["file"]: broken})
        patch = ws.make_patch(touched_files(pkg.solution_patch))
    return (dataclasses.replace(pkg, solution_patch=patch),
            f"Planted a bug in the solution ({caught['file']}, {caught['change']}).")


# -------------------------------------------------------------------- app

class App:
    def __init__(self, root: Path = PROJECT_ROOT, out_dir: Path | None = None):
        self.root = Path(root)
        self.out = Path(out_dir) if out_dir else self.root / "taskforge_out" / "ui"
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    # information -------------------------------------------------------
    def examples(self) -> dict[str, Path]:
        base = self.root / "examples"
        return {p.name: p for p in sorted(base.iterdir()) if p.is_dir()} if base.is_dir() else {}

    def recorded(self) -> list[dict]:
        """Tasks whose AI answers were recorded, so they can be re-run offline."""
        out = []
        for name in self.examples():
            meta_file = self.root / "samples" / "replay" / name / "meta.json"
            if not meta_file.exists():
                continue
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            for i, plan in enumerate(plan_batch(meta["n"], meta["seed"], meta.get("recipes")), start=1):
                task_id = f"{name}__{'_x_'.join(plan.ids)}__{i:02d}"
                saved = self.root / "samples" / "tasks" / name / task_id
                title = TaskPackage.load(saved).title if (saved / "task.toml").exists() else plan.slug
                out.append({"id": task_id, "repo": name, "index": i - 1, "recipes": plan.ids, "title": title})
        return out

    def info(self) -> dict:
        return {
            "examples": list(self.examples()),
            "recipes": [{"id": r.id, "title": r.title, "family": r.family} for r in RECIPES],
            "recorded": self.recorded(),
            "claude_installed": shutil.which("claude") is not None,
            "api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "reports": [k for k, v in REPORTS.items() if (self.root / v).exists()],
            "sabotage": {k: {"title": t, "should_fail": p} for k, (t, p) in SABOTAGE.items()},
        }

    def repo_config(self, repo: str) -> RepoConfig:
        repo = (repo or "").strip().strip('"')
        if not repo:
            raise ValueError("choose a repository")
        examples = self.examples()
        if repo in examples:
            return resolve_repo(examples[repo], name=repo)
        path = Path(repo).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise ValueError("enter the full path of a folder that exists")
        return resolve_repo(path)

    def analyze(self, repo: str) -> dict:
        cfg = self.repo_config(repo)
        with Workspace(cfg) as ws:
            ctx = load_context(cfg, ws.dir)
        base, _ = Checker(cfg).baseline()
        return {
            "name": cfg.name, "language": cfg.language, "commit": cfg.base_commit, "snapshot": cfg.snapshot,
            "test_command": cfg.test_command, "files": len(ctx.tree), "sources": sorted(ctx.sources),
            "tests": sorted(ctx.tests), "baseline": {"status": base.status, "detail": base.detail},
        }

    # jobs ---------------------------------------------------------------
    def _start(self, kind: str, label: str, target, *args) -> Job:
        with self.lock:
            if any(j.active for j in self.jobs.values()):
                raise Busy("another run is still in progress; wait for it or cancel it")
            job = Job(kind, label)
            self.jobs[job.id] = job

        def runner():
            try:
                target(job, *args)
                with job.lock:
                    if job.cancel_requested:
                        job.state, job.message = "cancelled", "cancelled"
                    else:
                        job.state, job.message = "done", "finished"
            except Cancelled as e:
                with job.lock:
                    job.state, job.message = "cancelled", str(e)
            except Exception as e:  # noqa: BLE001 - everything is reported on the page
                with job.lock:
                    job.state, job.error, job.message = "error", str(e), "stopped with an error"

        threading.Thread(target=runner, daemon=True, name=f"taskforge-{job.id}").start()
        return job

    def job(self, job_id: str) -> Job:
        job = self.jobs.get(job_id or "")
        if job is None:
            raise KeyError("unknown run")
        return job

    def cancel(self, job_id: str) -> None:
        self.job(job_id).cancel_requested = True

    def start_exam(self, params: dict) -> Job:
        mode = params.get("mode", "recorded")
        if mode == "recorded":
            item = next((r for r in self.recorded() if r["id"] == params.get("recorded_id")), None)
            if item is None:
                raise ValueError("choose one of the recorded tasks")
            return self._start("exam", item["title"], self._run_recorded, item)
        if mode not in ("paste", "claude", "api"):
            raise ValueError("unknown way of writing the exam")
        recipes = [str(r) for r in params.get("recipes", [])]
        make_plan(recipes)  # validate early
        cfg = self.repo_config(params.get("repo", ""))
        return self._start("exam", " + ".join(recipes), self._run_live, cfg, recipes, mode)

    def _run_recorded(self, job: Job, item: dict) -> None:
        name = item["repo"]
        meta = json.loads((self.root / "samples" / "replay" / name / "meta.json").read_text(encoding="utf-8"))
        cfg = resolve_repo(self.examples()[name], name=name)
        backend = CachedBackend(None, self.root / "samples" / "replay" / name)
        plans = plan_batch(meta["n"], meta["seed"], meta.get("recipes"))
        plan = plans[item["index"]]
        factory = Factory(cfg, backend, self.out / "recorded" / name, seed=meta["seed"],
                          max_attempts=meta.get("attempts", 3), on_event=job.event)
        self._finish(job, cfg, factory, item["id"], plan, [p.slug for p in plans if p is not plan], meta["seed"])

    def _run_live(self, job: Job, cfg: RepoConfig, recipes: list[str], mode: str) -> None:
        backend: Backend = (PasteBackend(job) if mode == "paste"
                            else ClaudeCodeBackend() if mode == "claude" else AnthropicBackend())
        factory = Factory(cfg, backend, self.out / "live" / cfg.name, on_event=job.event)
        factory.load_accepted_signatures()
        number = factory._existing_count() + 1
        task_id = f"{cfg.name}__{'_x_'.join(recipes)}__{number:02d}"
        self._finish(job, cfg, factory, task_id, make_plan(recipes, number), [], 0)

    def _finish(self, job: Job, cfg: RepoConfig, factory: Factory, task_id: str, plan, others, seed: int) -> None:
        with job.lock:
            job.repo = {"name": cfg.name, "path": str(cfg.path), "commit": cfg.base_commit, "language": cfg.language}
            job.message = "reading the repository"
        base, _ = factory.checker.baseline()
        job.event({"type": "proof", "name": "baseline", "status": base.status, "detail": base.detail})
        if base.status == "fail":
            raise RuntimeError("the repository's own tests do not pass, so no exam can be proven fair")
        result = factory.make_task(task_id, plan, others)
        if job.cancel_requested:
            raise Cancelled("cancelled")
        folder = factory.out / ("accepted" if result.status == "accepted" else "rejected") / result.task_id
        files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
        toml = folder / "task.toml"
        if result.attempts and result.attempts[-1].outcome == "llm_error":
            raise RuntimeError(result.attempts[-1].detail)
        with job.lock:
            job.attempts = [vars(a) for a in result.attempts]
            job.result = {
                "status": result.status, "task_id": result.task_id, "title": result.title, "reason": result.reason,
                "folder": str(folder), "files": files, "recipes": result.plan,
                "task_toml": toml.read_text(encoding="utf-8") if toml.exists() else "", "seed": seed,
            }

    def start_sabotage(self, job_id: str, kind: str) -> Job:
        source = self.job(job_id)
        if source.kind != "exam" or not source.result or source.result["status"] != "accepted":
            raise ValueError("make an accepted exam first")
        if kind not in SABOTAGE:
            raise ValueError("unknown kind of sabotage")
        return self._start("sabotage", SABOTAGE[kind][0], self._run_sabotage, source, kind)

    def _run_sabotage(self, job: Job, source: Job, kind: str) -> None:
        pkg = TaskPackage.load(Path(source.result["folder"]))
        cfg = pkg.repo_config(Path(source.repo["path"]))
        with job.lock:
            job.repo = source.repo
            job.message = "preparing a bad copy of the exam"
        bad, what = sabotage(pkg, kind, cfg, source.mutants)
        with job.lock:
            job.draft = {"title": what, "instruction": bad.instruction, "patch": bad.solution_patch, "tests": bad.test_files}
        report = Checker(cfg, seed=source.result["seed"], progress=job.event).check(bad)
        with job.lock:
            job.result = {
                "status": "accepted" if report.accepted else "rejected", "what": what, "kind": kind,
                "should_fail": SABOTAGE[kind][1], "failed": [p.name for p in report.failed_proofs],
            }


# ------------------------------------------------------------------ server

def make_server(app: App, port: int = 8765, token: str | None = None) -> ThreadingHTTPServer:
    token = token or secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        server_version = "TaskForge"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep the terminal quiet
            pass

        # helpers -----------------------------------------------------
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status: int = 200) -> None:
            self._send(status, json.dumps(data).encode("utf-8"), "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            port_ = self.server.server_address[1]
            return self.headers.get("Host", "") in (f"127.0.0.1:{port_}", f"localhost:{port_}")

        def _token_ok(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-TaskForge-Token", ""), token)

        def _guard(self, fn) -> None:
            try:
                self._json(fn())
            except Busy as e:
                self._json({"error": str(e)}, HTTPStatus.CONFLICT)
            except KeyError as e:
                self._json({"error": str(e).strip("'\"")}, HTTPStatus.NOT_FOUND)
            except (ValueError, FileNotFoundError, RuntimeError) as e:
                self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
            except Exception as e:  # noqa: BLE001
                self._json({"error": f"unexpected error: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        # routes --------------------------------------------------------
        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                return self._json({"error": "unexpected host"}, HTTPStatus.FORBIDDEN)
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                page = PAGE.read_text(encoding="utf-8").replace("__TOKEN__", token)
                return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            if url.path.startswith("/report/"):
                rel = REPORTS.get(url.path.removeprefix("/report/"))
                if rel and (app.root / rel).is_file():
                    return self._send(200, (app.root / rel).read_bytes(), "text/html; charset=utf-8")
                return self._json({"error": "no such report"}, HTTPStatus.NOT_FOUND)
            if url.path.startswith("/api/"):
                if not self._token_ok():
                    return self._json({"error": "missing or wrong token; reload the page"}, HTTPStatus.FORBIDDEN)
                if url.path == "/api/info":
                    return self._guard(app.info)
                if url.path == "/api/job":
                    job_id = parse_qs(url.query).get("id", [""])[0]
                    return self._guard(lambda: app.job(job_id).snapshot())
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self.close_connection = True
                return self._json({"error": "request too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            raw = self.rfile.read(length)
            if not self._host_ok():
                return self._json({"error": "unexpected host"}, HTTPStatus.FORBIDDEN)
            if not self._token_ok():
                return self._json({"error": "missing or wrong token; reload the page"}, HTTPStatus.FORBIDDEN)
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._json({"error": "send JSON"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(data, dict):
                    raise ValueError
            except ValueError:
                return self._json({"error": "bad JSON"}, HTTPStatus.BAD_REQUEST)
            path = urlparse(self.path).path
            if path == "/api/analyze":
                return self._guard(lambda: app.analyze(str(data.get("repo", ""))))
            if path == "/api/run":
                return self._guard(lambda: {"job": app.start_exam(data).id})
            if path == "/api/answer":
                return self._guard(lambda: app.job(str(data.get("job"))).answer(str(data.get("reply", ""))) or {"ok": True})
            if path == "/api/cancel":
                return self._guard(lambda: app.cancel(str(data.get("job"))) or {"ok": True})
            if path == "/api/sabotage":
                return self._guard(lambda: {"job": app.start_sabotage(str(data.get("job")), str(data.get("kind"))).id})
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.token = token  # type: ignore[attr-defined]
    return server
