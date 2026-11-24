"""AI backends. The generator only needs one thing: text in, text out.

  claude   runs the Claude Code CLI headless (uses your Claude subscription, no API key)
  api      calls the Anthropic Messages API (needs ANTHROPIC_API_KEY)
  replay   re-uses recorded answers, offline (for demos, tests and judges)

``CachedBackend`` wraps any backend: identical prompts are answered from disk
(saves money and makes runs repeatable) and ``max_calls`` caps spending.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_SYSTEM = (
    "You are an expert software engineer who writes benchmark tasks for evaluating AI coding systems. "
    "You write complete, correct, minimal code and you follow the requested output format exactly, "
    "with no commentary outside it."
)


class LLMError(RuntimeError):
    pass


class BudgetExceeded(LLMError):
    pass


class ReplayMiss(LLMError):
    pass


class NeedsAnswer(LLMError):
    """The manual backend wrote a prompt file and is waiting for someone to answer it."""


class Backend:
    name = "backend"

    def __init__(self) -> None:
        self.calls = 0
        self.chars_in = 0
        self.chars_out = 0

    def complete(self, prompt: str, system: str = DEFAULT_SYSTEM) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def stats(self) -> dict:
        return {"backend": self.name, "calls": self.calls, "chars_in": self.chars_in, "chars_out": self.chars_out}


class ClaudeCodeBackend(Backend):
    """Uses ``claude -p`` (Claude Code, headless). Tools are disabled: it only writes text."""

    name = "claude"

    def __init__(self, model: str | None = None, timeout: int = 900, exe: str | None = None):
        super().__init__()
        self.model = model or os.environ.get("TASKFORGE_MODEL") or None
        self.timeout = timeout
        self.exe = exe or shutil.which("claude")
        if not self.exe:
            raise LLMError("the 'claude' command was not found; install Claude Code or use --backend api")

    def complete(self, prompt: str, system: str = DEFAULT_SYSTEM) -> str:
        cmd = [self.exe, "-p", "--output-format", "text", "--tools", "", "--no-session-persistence",
               "--system-prompt", system]
        if self.model:
            cmd += ["--model", self.model]
        self.calls += 1
        self.chars_in += len(prompt)
        with tempfile.TemporaryDirectory(prefix="tf_claude_") as cwd:  # neutral folder: no project files, no CLAUDE.md
            try:
                p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=self.timeout, cwd=cwd)
            except subprocess.TimeoutExpired as e:
                raise LLMError(f"claude timed out after {self.timeout}s") from e
        if p.returncode != 0 or not p.stdout.strip():
            raise LLMError(f"claude failed (exit {p.returncode}): {(p.stderr or p.stdout).strip()[:500]}")
        self.chars_out += len(p.stdout)
        return p.stdout


class AnthropicBackend(Backend):
    """Anthropic Messages API over plain HTTPS (no extra packages)."""

    name = "api"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str | None = None, api_key: str | None = None, max_tokens: int = 16000, retries: int = 3):
        super().__init__()
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set (see .env.example)")
        self.model = model or os.environ.get("TASKFORGE_MODEL") or "claude-sonnet-5-5"
        self.max_tokens = max_tokens
        self.retries = retries

    def complete(self, prompt: str, system: str = DEFAULT_SYSTEM) -> str:
        body = json.dumps({"model": self.model, "max_tokens": self.max_tokens, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
        headers = {"content-type": "application/json", "x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        self.calls += 1
        self.chars_in += len(prompt)
        last = ""
        for attempt in range(self.retries):
            req = urllib.request.Request(self.URL, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    data = json.loads(r.read().decode("utf-8"))
                text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
                if not text.strip():
                    raise LLMError("the API returned no text")
                self.chars_out += len(text)
                return text
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
                if e.code in (429, 500, 502, 503, 529) and attempt < self.retries - 1:
                    time.sleep(2 ** attempt * 2)
                    continue
                break
            except urllib.error.URLError as e:
                last = str(e)
                time.sleep(2 ** attempt)
        raise LLMError(f"API call failed: {last}")


class CachedBackend(Backend):
    """Answer repeated prompts from disk. With ``inner=None`` it is a pure replay."""

    def __init__(self, inner: Backend | None, cache_dir: Path, max_calls: int | None = None):
        super().__init__()
        self.inner = inner
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_calls = max_calls
        self.hits = 0
        self.name = "replay" if inner is None else f"{inner.name}+cache"

    @staticmethod
    def key(prompt: str, system: str) -> str:
        return hashlib.sha256((system + "\n␞\n" + prompt).encode("utf-8")).hexdigest()[:24]

    def complete(self, prompt: str, system: str = DEFAULT_SYSTEM) -> str:
        k = self.key(prompt, system)
        f = self.dir / f"{k}.txt"
        if f.exists():
            self.hits += 1
            return f.read_text(encoding="utf-8")
        if self.inner is None:
            raise ReplayMiss(f"no recorded answer for this prompt ({k}); run once with a live backend and --record-dir")
        if self.max_calls is not None and self.inner.calls >= self.max_calls:
            raise BudgetExceeded(f"stopped after {self.max_calls} AI calls (--max-calls)")
        text = self.inner.complete(prompt, system)
        f.write_text(text, encoding="utf-8", newline="\n")
        return text

    def stats(self) -> dict:
        s = self.inner.stats() if self.inner else {"backend": "replay", "calls": 0, "chars_in": 0, "chars_out": 0}
        s["cache_hits"] = self.hits
        return s


class ManualBackend(Backend):
    """File-based exchange for people (or any AI chat) with no API access.

    A new prompt is written to ``<dir>/pending/<key>.prompt.txt`` and the call raises
    NeedsAnswer. Put the reply in ``<dir>/<key>.txt`` and run again. The answers use the
    same layout as the replay backend, so a finished folder can be replayed offline.
    """

    name = "manual"

    def __init__(self, directory: Path):
        super().__init__()
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.pending: dict[str, Path] = {}

    def complete(self, prompt: str, system: str = DEFAULT_SYSTEM) -> str:
        k = CachedBackend.key(prompt, system)
        answer = self.dir / f"{k}.txt"
        if answer.exists():
            self.hits += 1
            return answer.read_text(encoding="utf-8")
        pend = self.dir / "pending"
        pend.mkdir(exist_ok=True)
        f = pend / f"{k}.prompt.txt"
        f.write_text(f"[SYSTEM]\n{system}\n\n[USER]\n{prompt}", encoding="utf-8", newline="\n")
        self.pending[k] = f
        raise NeedsAnswer(k)

    def stats(self) -> dict:
        return {"backend": "manual", "calls": 0, "cache_hits": self.hits, "pending": len(self.pending),
                "chars_in": 0, "chars_out": 0}


class ScriptedBackend(Backend):
    """Returns canned answers in order. For tests."""

    name = "scripted"

    def __init__(self, answers: list[str]):
        super().__init__()
        self.answers = list(answers)
        self.prompts: list[str] = []

    def complete(self, prompt: str, system: str = DEFAULT_SYSTEM) -> str:
        self.prompts.append(prompt)
        self.calls += 1
        if not self.answers:
            raise LLMError("scripted backend ran out of answers")
        return self.answers.pop(0)


def make_backend(kind: str, *, model: str | None = None, cache_dir: Path | None = None,
                 replay_dir: Path | None = None, max_calls: int | None = None) -> Backend:
    if kind == "manual":
        if not replay_dir:
            raise LLMError("--backend manual needs --replay-dir (the exchange folder)")
        return ManualBackend(Path(replay_dir))
    if kind == "replay":
        if not replay_dir:
            raise LLMError("--backend replay needs --replay-dir")
        return CachedBackend(None, Path(replay_dir))
    if kind == "claude":
        inner: Backend = ClaudeCodeBackend(model=model)
    elif kind == "api":
        inner = AnthropicBackend(model=model)
    else:
        raise LLMError(f"unknown backend '{kind}' (choose claude, api, manual or replay)")
    if cache_dir:
        return CachedBackend(inner, Path(cache_dir), max_calls=max_calls)
    if max_calls is not None:
        return CachedBackend(inner, Path(tempfile.mkdtemp(prefix="tf_cache_")), max_calls=max_calls)
    return inner
