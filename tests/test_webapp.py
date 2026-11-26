"""The local web page: security rules, the recorded and paste flows, and the 'cheat the checker' buttons."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from taskforge.controls import FEATURE_TEST_PATH, GOOD_TESTS, INSTRUCTION, _good_cart
from taskforge.generator import format_response
from taskforge.webapp import App, _DropAssertions, make_server

from conftest import ROOT

TOKEN = "test-token"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    app = App(root=ROOT, out_dir=tmp_path_factory.mktemp("ui_out"))
    srv = make_server(app, port=0, token=TOKEN)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def call(base, path, body=None, token=TOKEN, headers=None):
    h = {"X-TaskForge-Token": token} if token else {}
    data = None
    if body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    h.update(headers or {})
    req = urllib.request.Request(base + path, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode()
            return r.status, (json.loads(text) if r.headers["Content-Type"].startswith("application/json") else text)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def wait(base, job, until=("done", "error", "cancelled"), seconds=240):
    deadline = time.time() + seconds
    while time.time() < deadline:
        status, snap = call(base, f"/api/job?id={job}")
        assert status == 200, snap
        if snap["state"] in until:
            return snap
        time.sleep(0.3)
    raise AssertionError("the run did not finish in time")


# ------------------------------------------------------------------ security

def test_page_is_served_with_the_token(server):
    status, page = call(server, "/", token=None)
    assert status == 200 and f'const TOKEN = "{TOKEN}"' in page and "__TOKEN__" not in page


def test_api_needs_the_token(server):
    assert call(server, "/api/info", token=None)[0] == 403
    assert call(server, "/api/info", token="wrong")[0] == 403
    assert call(server, "/api/run", body={"mode": "recorded"}, token=None)[0] == 403


def test_foreign_host_header_is_refused(server):
    assert call(server, "/", token=None, headers={"Host": "evil.example"})[0] == 403
    assert call(server, "/api/info", headers={"Host": "evil.example"})[0] == 403


def test_post_must_be_json_and_files_are_not_served(server):
    status, _ = call(server, "/api/run", body={}, headers={"Content-Type": "text/plain"})
    assert status == 415
    for path in ("/README.md", "/../pyproject.toml", "/report/nope", "/evidence/shop/report.html"):
        assert call(server, path)[0] == 404, path


# ---------------------------------------------------------------------- info

def test_info_lists_examples_recipes_and_recorded_tasks(server):
    status, info = call(server, "/api/info")
    assert status == 200
    assert {"shop", "library"} <= set(info["examples"]) and len(info["recipes"]) == 10
    ids = {r["id"] for r in info["recorded"]}
    assert "shop__time_window__01" in ids and len(ids) == 14
    status, report = call(server, "/report/shop", token=None)
    assert status == 200 and "TaskForge report" in report


def test_analyze_and_friendly_errors(server):
    status, a = call(server, "/api/analyze", {"repo": "shop"})
    assert status == 200 and a["language"] == "python" and a["baseline"]["status"] == "pass"
    assert call(server, "/api/analyze", {"repo": "relative/folder"})[0] == 400
    assert call(server, "/api/run", {"mode": "paste", "repo": "shop", "recipes": []})[0] == 400
    assert call(server, "/api/run", {"mode": "recorded", "recorded_id": "nope"})[0] == 400
    assert call(server, "/api/job?id=nope")[0] == 404


# --------------------------------------------------------------------- flows

@pytest.fixture(scope="module")
def recorded_job(server):
    status, r = call(server, "/api/run", {"mode": "recorded", "recorded_id": "shop__time_window__01"})
    assert status == 200, r
    return r["job"], wait(server, r["job"])


def test_recorded_exam_runs_all_six_steps(recorded_job):
    _, snap = recorded_job
    assert snap["state"] == "done", snap["error"]
    assert "## Requirements" in snap["draft"]["instruction"] and "diff --git" in snap["draft"]["patch"]
    assert {k: v["status"] for k, v in snap["proofs"].items()} == {
        "baseline": "pass", "fails_before": "pass", "passes_after": "pass", "nothing_breaks": "pass",
        "tests_have_teeth": "pass"}
    assert snap["mutants"] and any(m["caught"] for m in snap["mutants"]) and all(m["code"] for m in snap["mutants"])
    result = snap["result"]
    assert result["status"] == "accepted" and "base_commit" in result["task_toml"]
    assert {"instruction.md", "task.toml", "solution/solution.patch", "validation/proofs.json"} <= set(result["files"])


@pytest.mark.parametrize("kind,failed", [
    ("passing_tests", "fails_before"), ("broken_solution", "passes_after"), ("weak_tests", "tests_have_teeth"),
])
def test_checker_is_not_fooled(server, recorded_job, kind, failed):
    job, _ = recorded_job
    status, r = call(server, "/api/sabotage", {"job": job, "kind": kind})
    assert status == 200, r
    snap = wait(server, r["job"])
    assert snap["state"] == "done", snap["error"]
    assert snap["result"]["status"] == "rejected" and failed in snap["result"]["failed"], snap["proofs"]


def test_paste_mode_waits_for_the_reply_and_blocks_other_runs(server):
    status, r = call(server, "/api/run", {"mode": "paste", "repo": "shop", "recipes": ["quantity_limit"]})
    assert status == 200, r
    job = r["job"]
    snap = wait(server, job, until=("waiting", "error"))
    assert snap["state"] == "waiting" and "quantity_limit" in snap["prompt"] and "## FILE shop/cart.py" in snap["prompt"]
    assert call(server, "/api/run", {"mode": "recorded", "recorded_id": "shop__time_window__01"})[0] == 409
    assert call(server, "/api/answer", {"job": job, "reply": "  "})[0] == 400
    shop = ROOT / "examples" / "shop"
    reply = format_response("Limit units", INSTRUCTION, {"shop/cart.py": _good_cart(shop)}, {FEATURE_TEST_PATH: GOOD_TESTS})
    assert call(server, "/api/answer", {"job": job, "reply": reply})[0] == 200
    snap = wait(server, job)
    assert snap["state"] == "done" and snap["result"]["status"] == "accepted", snap
    assert snap["result"]["task_id"] == "shop__quantity_limit__01"


def test_paste_mode_can_be_cancelled(server):
    _, r = call(server, "/api/run", {"mode": "paste", "repo": "library", "recipes": ["time_window"]})
    wait(server, r["job"], until=("waiting", "error"))
    assert call(server, "/api/cancel", {"job": r["job"]})[0] == 200
    assert wait(server, r["job"])["state"] == "cancelled"
    assert call(server, "/api/answer", {"job": r["job"], "reply": "x"})[0] == 400


def test_drop_assertions_makes_valid_weak_tests():
    import ast

    source = "import pytest\n\ndef test_a(x):\n    assert x == 1\n    with pytest.raises(ValueError):\n        x.boom()\n    x.keep()\n"
    out = ast.unparse(ast.fix_missing_locations(_DropAssertions().visit(ast.parse(source))))
    compile(out, "<t>", "exec")
    assert "assert" not in out and "raises" not in out and "x.keep()" in out
