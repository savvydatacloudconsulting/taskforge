"""The solver check: an AI that only sees the instruction is judged by the hidden tests."""

import json

import pytest

from taskforge.checker import Checker
from taskforge.controls import FEATURE_TEST_PATH, GOOD_TESTS, _good_cart, _read, build_controls, make_package
from taskforge.llm import ManualBackend, ScriptedBackend
from taskforge.solver import (Solver, build_solver_prompt, solve_all, solver_html, solver_markdown, summarise)


def answer(files: dict[str, str]) -> str:
    return "".join(f"=== FILE solution {p} ===\n{c.rstrip()}\n" for p, c in files.items()) + "=== END ===\n"


@pytest.fixture(scope="module")
def good_pkg(shop_repo, shop_path):
    control = next(c for c in build_controls(shop_path) if c.name == "good_quantity_limit")
    return make_package(shop_repo, control, "shop__quantity_limit__01")


@pytest.fixture(scope="module")
def checker(shop_repo):
    return Checker(shop_repo)


def solver(shop_repo, checker, answers, attempts=1):
    backend = ScriptedBackend(answers)
    return Solver(shop_repo, backend, attempts=attempts, checker=checker), backend


def test_prompt_never_contains_the_tests_or_the_reference_solution(shop_repo, checker, good_pkg):
    s, backend = solver(shop_repo, checker, [answer({"shop/cart.py": _good_cart(shop_repo.path)})])
    s.solve(good_pkg)
    prompt = backend.prompts[0]
    assert "Feature request" in prompt and "limit of 10" in prompt  # the instruction is there
    assert "test_can_add_up_to_the_limit" not in prompt and "test_tf_limit" not in prompt  # hidden tests are not
    assert "new_quantity" not in prompt  # nor the reference solution
    for line in good_pkg.solution_patch.splitlines():
        if line.startswith("+") and not line.startswith("+++") and len(line.strip()) > 25:
            assert line[1:].strip() not in prompt


def test_correct_answer_is_solved_on_first_try(shop_repo, checker, good_pkg):
    s, _ = solver(shop_repo, checker, [answer({"shop/cart.py": _good_cart(shop_repo.path)})])
    r = s.solve(good_pkg)
    assert r.solved and r.first_try and r.attempts[0].outcome == "solved" and r.files_changed == 1


def test_wrong_answer_fails_hidden_tests_and_names_them(shop_repo, checker, good_pkg):
    s, _ = solver(shop_repo, checker, [answer({"shop/cart.py": _good_cart(shop_repo.path, ge=True)})])
    r = s.solve(good_pkg)
    assert not r.solved and r.attempts[0].outcome == "tests_failed"
    assert any("test_can_add_up_to_the_limit" in t for t in r.failing_tests)


def test_answer_that_breaks_existing_tests_is_not_solved(shop_repo, checker, good_pkg, shop_path):
    pricing = _read(shop_path, "shop/pricing.py").replace("+ 50) // 100", "+ 0) // 100", 1)
    s, _ = solver(shop_repo, checker, [answer({"shop/cart.py": _good_cart(shop_repo.path), "shop/pricing.py": pricing})])
    r = s.solve(good_pkg)
    assert not r.solved and r.attempts[0].outcome == "broke_existing"
    assert any("test_tax_rounds_half_up" in t for t in r.failing_tests)


def test_retry_gets_failing_test_feedback_and_can_succeed(shop_repo, checker, good_pkg):
    s, backend = solver(shop_repo, checker, [answer({"shop/cart.py": _good_cart(shop_repo.path, ge=True)}),
                                             answer({"shop/cart.py": _good_cart(shop_repo.path)})], attempts=2)
    r = s.solve(good_pkg)
    assert r.solved and not r.first_try and len(r.attempts) == 2
    assert "did not pass the hidden tests" in backend.prompts[1] and "Hidden tests failed" in backend.prompts[1]


@pytest.mark.parametrize("raw,outcome", [
    ("Sure! Here is my plan.", "parse_error"),
    (answer({"tests/test_x.py": "def test():\n    pass\n"}), "invalid"),          # solvers may not add tests
    (answer({"shop/cart.py": "def broken(:\n"}), "invalid"),                        # syntax error
    (answer({"../outside.py": "x = 1\n"}), "invalid"),                              # path escape
])
def test_bad_answers_are_classified(shop_repo, checker, good_pkg, raw, outcome):
    s, _ = solver(shop_repo, checker, [raw])
    r = s.solve(good_pkg)
    assert not r.solved and r.attempts[0].outcome == outcome


def test_manual_backend_marks_task_pending(shop_repo, checker, good_pkg, tmp_path):
    s = Solver(shop_repo, ManualBackend(tmp_path / "x"), checker=checker)
    r = s.solve(good_pkg)
    assert r.pending and not r.attempts
    assert len(list((tmp_path / "x" / "pending").glob("*.prompt.txt"))) == 1


def test_solve_all_writes_results_and_reports(shop_repo, shop_path, good_pkg, tmp_path):
    folder = tmp_path / "tasks"
    good_pkg.write(folder / good_pkg.task_id)
    backend = ScriptedBackend([answer({"shop/cart.py": _good_cart(shop_repo.path)})])
    data = solve_all(folder, shop_path, backend, tmp_path / "out", label="scripted")
    assert data["summary"]["solved"] == 1 and data["summary"]["solve_rate"] == 1.0
    saved = json.loads((tmp_path / "out" / "solve_results.json").read_text())
    assert saved["solver"] == "scripted" and saved["results"][0]["first_try"] is True
    assert (tmp_path / "out" / "solver_report.md").exists() and (tmp_path / "out" / "solver_report.html").exists()
    assert "quantity_limit" in solver_markdown(saved) or "control" in solver_markdown(saved)
    assert "<table" in solver_html(saved)


def test_summary_handles_empty_and_groups_by_recipe():
    from taskforge.solver import SolveAttempt, SolveResult

    assert summarise([])["solve_rate"] is None
    ok = SolveResult("a", ["r1"], solved=True, attempts=[SolveAttempt(1, "solved", "")])
    no = SolveResult("b", ["r1", "r2"], solved=False, attempts=[SolveAttempt(1, "tests_failed", "")])
    s = summarise([ok, no])
    assert s["by_recipe"]["r1"] == {"tasks": 2, "solved": 1} and s["by_recipe"]["r2"] == {"tasks": 1, "solved": 0}
    assert s["single_recipe"]["rate"] == 1.0 and s["combined_recipes"]["rate"] == 0.0
    assert s["failure_kinds"] == {"tests_failed": 1}
