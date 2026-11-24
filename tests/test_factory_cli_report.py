"""End-to-end tests of the factory loop with scripted AI answers (no network, no real AI)."""

import json

import pytest

from taskforge.checker import Checker
from taskforge.cli import main
from taskforge.controls import FEATURE_TEST_PATH, GOOD_TESTS, INSTRUCTION, _good_cart, build_controls, make_package
from taskforge.generator import Factory, format_response
from taskforge.llm import ScriptedBackend
from taskforge.report import load, to_html, to_markdown, write_reports

ONLY = ["quantity_limit"]


def answer(shop_repo, solution=None, tests=None, title="Limit units per product", instruction=INSTRUCTION):
    sol = solution if solution is not None else {"shop/cart.py": _good_cart(shop_repo.path)}
    return format_response(title, instruction, sol, tests if tests is not None else {FEATURE_TEST_PATH: GOOD_TESTS})


WEAK_TESTS = {FEATURE_TEST_PATH: "from shop import cart as c\n\n\ndef test_const():\n    assert c.MAX_PER_LINE == 10\n"}


def factory(shop_repo, tmp_path, answers, **kw):
    backend = ScriptedBackend(answers)
    f = Factory(shop_repo, backend, tmp_path / "out", seed=0, checker=Checker(shop_repo, max_mutants=6), **kw)
    return f, backend


def test_good_answer_is_accepted_and_written(shop_repo, tmp_path):
    f, backend = factory(shop_repo, tmp_path, [answer(shop_repo)])
    (r,) = f.run(1, ONLY)
    assert r.status == "accepted" and len(r.attempts) == 1
    folder = tmp_path / "out" / "accepted" / r.task_id
    for rel in ("task.toml", "instruction.md", "solution/solution.patch", f"tests/{FEATURE_TEST_PATH}",
                "validation/proofs.json", "validation/attempts.json"):
        assert (folder / rel).exists(), rel
    assert json.loads((folder / "validation" / "proofs.json").read_text())["accepted"] is True


def test_weak_tests_trigger_a_retry_with_feedback_then_pass(shop_repo, tmp_path):
    f, backend = factory(shop_repo, tmp_path, [answer(shop_repo, tests=WEAK_TESTS), answer(shop_repo)])
    (r,) = f.run(1, ONLY)
    assert r.status == "accepted" and [a.outcome for a in r.attempts] == ["proof_failed", "accepted"]
    retry_prompt = backend.prompts[1]
    assert "Your previous attempt was rejected" in retry_prompt and "tests_have_teeth" in retry_prompt
    assert "still passed your tests" in retry_prompt  # lists the surviving mutants


def test_unfixable_task_is_rejected_with_a_reason(shop_repo, tmp_path):
    bad = answer(shop_repo, tests=WEAK_TESTS)
    f, _ = factory(shop_repo, tmp_path, [bad, bad], max_attempts=2)
    (r,) = f.run(1, ONLY)
    assert r.status == "rejected" and "failed proof" in r.reason and len(r.attempts) == 2
    folder = tmp_path / "out" / "rejected" / r.task_id
    assert (folder / "validation" / "attempts.json").exists() and (folder / "task.toml").exists()


def test_unparseable_answer_is_retried_then_rejected(shop_repo, tmp_path):
    f, _ = factory(shop_repo, tmp_path, ["I cannot help with that.", "still no format"], max_attempts=2)
    (r,) = f.run(1, ONLY)
    assert r.status == "rejected" and [a.outcome for a in r.attempts] == ["parse_error", "parse_error"]
    assert (tmp_path / "out" / "rejected" / r.task_id / "raw_response.txt").exists()


def test_cosmetic_duplicate_is_rejected(shop_repo, tmp_path):
    good = answer(shop_repo)
    f, _ = factory(shop_repo, tmp_path, [good, good, good, good], max_attempts=2)
    first, second = f.run(2, ONLY)
    assert first.status == "accepted"
    assert second.status == "rejected" and "cosmetic duplicate" in second.reason and second.nearest_task == first.task_id


def test_instruction_that_leaks_the_solution_is_refused(shop_repo, tmp_path):
    leaky = INSTRUCTION + "\n## Examples\n        new_quantity = self._lines.get(sku, 0) + quantity\n"
    f, _ = factory(shop_repo, tmp_path, [answer(shop_repo, instruction=leaky)], max_attempts=1)
    (r,) = f.run(1, ONLY)
    assert r.status == "rejected" and "leaks" in r.reason


def test_editing_an_existing_test_file_is_refused(shop_repo, tmp_path):
    f, _ = factory(shop_repo, tmp_path, [answer(shop_repo, tests={"tests/test_cart.py": GOOD_TESTS})], max_attempts=1)
    (r,) = f.run(1, ONLY)
    assert r.status == "rejected" and "already exists" in r.attempts[0].detail


def test_manual_backend_pending_task_is_not_written(shop_repo, tmp_path):
    from taskforge.llm import ManualBackend

    f = Factory(shop_repo, ManualBackend(tmp_path / "x"), tmp_path / "out", checker=Checker(shop_repo, max_mutants=3))
    assert f.run(1, ONLY) == [] and f.pending == 1
    assert list((tmp_path / "x" / "pending").glob("*.prompt.txt"))
    assert not (tmp_path / "out" / "accepted").exists()


def test_reports_are_built_from_disk(shop_repo, tmp_path):
    f, _ = factory(shop_repo, tmp_path, [answer(shop_repo), answer(shop_repo, tests=WEAK_TESTS)], max_attempts=1)
    results = f.run(2, ["quantity_limit"])
    f.write_run_summary(results, 1.0)
    paths = write_reports(tmp_path / "out")
    data = load(tmp_path / "out")
    assert data["summary"]["total"] == 2 and data["summary"]["accepted"] == 1 and data["summary"]["rejected"] == 1
    md, html = to_markdown(data), to_html(data)
    assert "Rejected tasks and why" in md and "<table" in html and all(p.exists() for p in paths.values())


def test_cli_recipes_analyze_and_check(shop_path, tmp_path, capsys):
    assert main(["recipes"]) == 0 and "quantity_limit" in capsys.readouterr().out
    assert main(["analyze", str(shop_path)]) == 0 and "PASS" in capsys.readouterr().out
    from taskforge.repo import resolve_repo

    repo = resolve_repo(shop_path, name="shop")
    controls = {c.name: c for c in build_controls(shop_path)}
    for name, code in (("good_quantity_limit", 0), ("bad_weak_tests", 1)):
        make_package(repo, controls[name], name).write(tmp_path / name)
        assert main(["check", str(tmp_path / name), "--repo", str(shop_path), "--max-mutants", "6"]) == code
    out = capsys.readouterr().out
    assert "ACCEPTED" in out and "REJECTED" in out


def test_cli_errors_are_friendly(tmp_path, capsys):
    assert main(["analyze", str(tmp_path / "nope")]) == 2
    assert "error:" in capsys.readouterr().out
    assert main(["generate", str(tmp_path), "--backend", "replay"]) == 2
