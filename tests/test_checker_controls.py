"""The checker must accept the good control task and reject every bad one for the right reason."""

import pytest

from taskforge.checker import Checker
from taskforge.controls import build_controls, make_package, render_matrix, run_controls


@pytest.fixture(scope="module")
def outcomes(shop_path):
    return run_controls(shop_path)


def test_controls_cover_every_proof(shop_path):
    controls = build_controls(shop_path)
    failed = {p for c in controls for p, s in c.expected.items() if s == "fail"}
    assert failed == {"fails_before", "passes_after", "nothing_breaks", "tests_have_teeth"}
    assert sum(1 for c in controls if all(v == "pass" for v in c.expected.values())) == 1


@pytest.mark.parametrize("name", [
    "good_quantity_limit", "bad_tests_already_pass", "bad_no_tests_collected", "bad_solution_off_by_one",
    "bad_breaks_existing_tests", "bad_weak_tests", "bad_patch_does_not_apply",
])
def test_each_control_gets_the_expected_verdict(outcomes, name):
    o = next(x for x in outcomes if x.control.name == name)
    assert o.as_expected, o.mismatches
    assert o.report.accepted == (name == "good_quantity_limit")


def test_matrix_renders(outcomes):
    text = render_matrix(outcomes)
    assert "good_quantity_limit" in text and "accepted" in text and "rejected" in text


def test_good_task_mutants_are_all_caught(outcomes):
    good = next(x for x in outcomes if x.control.name == "good_quantity_limit")
    teeth = good.report.proof("tests_have_teeth")
    assert teeth.evidence["kill_rate"] == 1.0 and teeth.evidence["survived"] == []


def test_baseline_must_pass(make_git_repo):
    from taskforge.package import TaskPackage
    from taskforge.repo import resolve_repo

    root = make_git_repo({"a.py": "x = 1\n", "tests/test_a.py": "def test_a():\n    assert 1 == 2\n"})
    cfg = resolve_repo(root)
    report = Checker(cfg).check(TaskPackage(
        "t", "t", [], "i", "p", {"tests/test_new.py": "def test_n():\n    assert True\n"}, "proj", "python",
        cfg.base_commit, cfg.test_command))
    assert not report.accepted and report.baseline.status == "fail" and report.proofs == []


def test_non_python_teeth_is_skipped_not_faked(make_git_repo, shop_repo):
    import dataclasses

    from taskforge.controls import build_controls

    good = next(c for c in build_controls(shop_repo.path) if c.name == "good_quantity_limit")
    pkg = make_package(shop_repo, good, "x")
    pkg = dataclasses.replace(pkg, language="javascript")
    report = Checker(shop_repo).check(pkg)
    teeth = report.proof("tests_have_teeth")
    assert teeth.status == "skipped" and "only implemented for Python" in teeth.detail
