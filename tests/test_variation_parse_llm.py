import io
import json
import subprocess
import urllib.error

import pytest

from taskforge import llm
from taskforge.generator import (ParseError, format_response, lint_instruction, parse_response, validate_parsed)
from taskforge.llm import (AnthropicBackend, BudgetExceeded, CachedBackend, ClaudeCodeBackend, LLMError, ManualBackend,
                           NeedsAnswer, ReplayMiss, ScriptedBackend, make_backend)
from taskforge.variation import MIN_DISTANCE, batch_score, distance, nearest, normalise, signature


def patch(*added: str, path="shop/banner.py") -> str:
    body = "".join(f"+{ln}\n" for ln in added)
    return (f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n"
            f"@@ -0,0 +1,{len(added)} @@\n{body}")


# ------------------------------------------------------------------ variation

def test_normalise_erases_names_numbers_and_strings():
    assert normalise('if price > 100: banner = "Black Friday"') == normalise("if cost > 7: label = 'Christmas'")


def test_cosmetic_variation_is_distance_zero():
    black_friday = signature("a", patch("def banner(day):", "    if day == 'fri':", "        return 'Black Friday sale'", "    return ''"), ["x"])
    christmas = signature("b", patch("def promo(d):", "    if d == 'dec':", "        return 'Christmas sale 25'", "    return ''"), ["x"])
    assert distance(black_friday, christmas) == 0.0
    assert distance(black_friday, christmas) < MIN_DISTANCE


def test_real_behavioural_difference_is_far_apart():
    limit = signature("a", patch("MAX = 10", "def add(cart, n):", "    if cart.count + n > MAX:", "        raise ValueError('limit')",
                                 "    cart.count += n"), ["quantity_limit"], )
    tiers = signature("b", patch("def rate(total):", "    cost = 0", "    for edge, pct in TIERS:", "        if total > edge:",
                                 "            cost += (total - edge) * pct // 100", "    return cost"), ["tiered_rates"])
    assert distance(limit, tiers) > MIN_DISTANCE


def test_nearest_and_batch_score():
    a = signature("a", patch("x = 1", "y = x + 2"), ["r"])
    b = signature("b", patch("if n > 1:", "    raise ValueError()"), ["q"])
    assert nearest(a, [])[1] is None
    assert nearest(a, [b])[1] == "b"
    assert batch_score([a]) is None and batch_score([a, b]) == distance(a, b)


# -------------------------------------------------------------------- parsing

GOOD = format_response("A title", "## Background\n" + "text " * 80 + "\n## Requirements\n1. do it\n",
                       {"shop/x.py": "X = 1\n"}, {"tests/test_tf_x.py": "def test_x():\n    assert True\n"})


def test_parse_roundtrip_and_fence_stripping():
    p = parse_response(GOOD)
    assert p.title == "A title" and p.solution_files == {"shop/x.py": "X = 1\n"}
    fenced = GOOD.replace("X = 1\n", "```python\nX = 1\n```\n")
    assert parse_response(fenced).solution_files["shop/x.py"] == "X = 1\n"


def test_parse_accepts_end_marker_after_every_file():
    """Models often write '=== END ===' after each file; no file may be dropped because of that."""
    text = ("=== FILE solution a/one.py ===\nX = 1\n=== END ===\n"
            "=== FILE solution a/two.py ===\nY = 2\n=== END ===\n"
            "=== FILE solution a/three.py ===\nZ = 3\n=== END ===\n")
    assert parse_response(text).solution_files == {"a/one.py": "X = 1\n", "a/two.py": "Y = 2\n", "a/three.py": "Z = 3\n"}
    once = "=== FILE solution a/one.py ===\nX = 1\n=== FILE solution a/two.py ===\nY = 2\n=== END ===\n"
    assert set(parse_response(once).solution_files) == {"a/one.py", "a/two.py"}
    chatter = "=== FILE solution a/one.py ===\nX = 1\n=== END ===\nHope this helps!\n"
    assert parse_response(chatter).solution_files == {"a/one.py": "X = 1\n"}  # text after END is ignored


@pytest.mark.parametrize("text,msg", [
    ("just some chatter", "markers"),
    (GOOD.replace("=== FILE test tests/test_tf_x.py ===", "=== FILE solution shop/x.py ==="), "twice"),
])
def test_parse_errors(text, msg):
    with pytest.raises(ParseError, match=msg):
        parse_response(text)


def test_validate_parsed_flags_problems(shop_repo):
    existing = {"tests/test_cart.py", "shop/cart.py"}
    ok = parse_response(GOOD)
    assert validate_parsed(ok, shop_repo, existing) == []
    bad = parse_response(format_response("t", "short", {"tests/test_cart.py": "x = 1\n", "../evil.py": "x = 1\n", "shop/s.py": "def (:\n"},
                                         {"tests/test_cart.py": "def test():\n    pass\n", "src/notatest.py": "x=1\n"}))
    errs = " | ".join(validate_parsed(bad, shop_repo, existing))
    for needle in ("Requirements", "looks like a test file", "escapes the repository", "syntax error",
                   "already exists", "not recognised as a test path"):
        assert needle in errs, needle


def test_lint_instruction_catches_leaked_solution():
    p = patch("    if cart_quantity + added_quantity > MAX_PER_LINE_LIMIT:")
    assert lint_instruction("Use this: if cart_quantity + added_quantity > MAX_PER_LINE_LIMIT: ...", p)
    assert lint_instruction("Reject adds that go over the limit.", p) == []


def test_scrub_volatile_makes_failure_text_reproducible():
    from taskforge.generator import scrub_volatile

    a = "obj <Library object at 0x000001E1340BF250> failed in 0.10s at C:\\Temp\\tf_ws_ab12cd\\repo\\tests\\x.py"
    b = "obj <Library object at 0x00007FF6DEADBEEF> failed in 0.37s at C:\\Temp\\tf_ws_zz99yy\\repo\\tests\\x.py"
    assert scrub_volatile(a) == scrub_volatile(b)
    assert "0x..." in scrub_volatile(a) and "<repo>" in scrub_volatile(a)


def test_lint_allows_signatures_in_public_interface_section():
    sig = patch("    category_percents: dict[str, int] | None = None,", "    if cart_quantity + added_quantity > MAX_PER_LINE_LIMIT:")
    spec = ("## Requirements\n1. Apply the discount.\n\n## Public interface\n"
            "    category_percents: dict[str, int] | None = None,\n")
    assert lint_instruction(spec, sig) == []
    leaked = spec + "\n## Examples\nif cart_quantity + added_quantity > MAX_PER_LINE_LIMIT:\n"
    assert lint_instruction(leaked, sig)


# ------------------------------------------------------------------- backends

def test_cached_backend_hits_budget_and_replay(tmp_path):
    inner = ScriptedBackend(["one", "two", "three"])
    b = CachedBackend(inner, tmp_path, max_calls=2)
    assert b.complete("p1") == "one" and b.complete("p1") == "one"  # second is a cache hit
    assert inner.calls == 1 and b.hits == 1
    assert b.complete("p2") == "two"
    with pytest.raises(BudgetExceeded):
        b.complete("p3")
    replay = make_backend("replay", replay_dir=tmp_path)
    assert replay.complete("p2") == "two"
    with pytest.raises(ReplayMiss):
        replay.complete("never recorded")


def test_manual_backend_writes_pending_prompt_then_reads_answer(tmp_path):
    m = ManualBackend(tmp_path)
    with pytest.raises(NeedsAnswer) as e:
        m.complete("hello")
    key = str(e.value)
    assert (tmp_path / "pending" / f"{key}.prompt.txt").read_text().endswith("hello")
    (tmp_path / f"{key}.txt").write_text("the answer")
    assert m.complete("hello") == "the answer"


def test_claude_backend_runs_cli_and_reports_failures(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw["input"]
        return subprocess.CompletedProcess(cmd, 0, stdout="hello", stderr="")

    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    b = ClaudeCodeBackend(exe="claude-fake", model="m1")
    assert b.complete("prompt text") == "hello"
    assert seen["input"] == "prompt text" and "--tools" in seen["cmd"] and "--model" in seen["cmd"]
    monkeypatch.setattr(llm.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="auth expired"))
    with pytest.raises(LLMError, match="auth expired"):
        b.complete("x")


def test_api_backend_parses_response_and_errors(monkeypatch):
    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        lambda req, timeout=0: Resp(json.dumps({"content": [{"type": "text", "text": "hi "}, {"type": "text", "text": "there"}]}).encode()))
    assert AnthropicBackend(api_key="k").complete("p") == "hi there"

    def boom(req, timeout=0):
        raise urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b"nope"))

    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    with pytest.raises(LLMError, match="400"):
        AnthropicBackend(api_key="k").complete("p")


def test_api_backend_needs_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        AnthropicBackend()
