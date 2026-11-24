"""Control tasks: a self-test for the checker.

One hand-written GOOD task and several deliberately BAD ones. A trustworthy
checker must accept the good task and reject each bad task for the right
reason. ``taskforge controls`` builds them against the bundled ``shop`` example
and prints the result matrix; the same data is used by the test-suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .checker import Checker, CheckReport
from .package import TaskPackage
from .repo import resolve_repo
from .runner import Workspace

INSTRUCTION = """\
## Background
Customers can currently add any quantity of a product to a cart.

## Requirements
1. A single product line in a cart may never hold more than 10 units.
2. `Cart.add` raises `ValueError` whose message contains `limit of 10` when an add would push a line above 10.
3. A rejected add leaves the cart unchanged.
4. The limit applies per product, not to the cart as a whole.

## Public interface
- `shop.cart.MAX_PER_LINE` (int, value `10`)
- `Cart.add(sku, quantity=1)` raises `ValueError("limit of 10 per product exceeded")`

## Examples
`cart.add("PEN", 10)` works; a further `cart.add("PEN", 1)` raises `ValueError`.
"""

GOOD_TESTS = '''\
import pytest


def test_can_add_up_to_the_limit(cart):
    cart.add("PEN", 10)
    assert cart.quantity("PEN") == 10


def test_one_call_over_the_limit_is_rejected(cart):
    with pytest.raises(ValueError, match="limit of 10"):
        cart.add("PEN", 11)
    assert cart.quantity("PEN") == 0


def test_limit_applies_across_calls_and_cart_is_unchanged(cart):
    cart.add("PEN", 6)
    with pytest.raises(ValueError, match="limit of 10"):
        cart.add("PEN", 5)
    assert cart.quantity("PEN") == 6


def test_limit_is_per_product(cart):
    cart.add("PEN", 10)
    cart.add("MUG", 10)
    assert cart.quantity("PEN") == 10 and cart.quantity("MUG") == 10


def test_removing_makes_room_again(cart):
    cart.add("BOOK", 10)
    cart.remove("BOOK", 4)
    cart.add("BOOK", 4)
    assert cart.quantity("BOOK") == 10
    with pytest.raises(ValueError):
        cart.add("BOOK", 1)
'''

FEATURE_TEST_PATH = "tests/test_tf_limit.py"


@dataclass
class Control:
    name: str
    description: str
    expected: dict[str, str]  # proof -> expected status ("pass"/"fail"/"skipped")
    solution: dict[str, str] = field(default_factory=dict)
    tests: dict[str, str] = field(default_factory=dict)
    corrupt_patch: bool = False


def _read(shop: Path, rel: str) -> str:
    return (shop / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def _good_cart(shop: Path, ge: bool = False) -> str:
    src = _read(shop, "shop/cart.py")
    src = src.replace("from .catalog import Catalog, Product\n",
                      "from .catalog import Catalog, Product\n\nMAX_PER_LINE = 10\n", 1)
    old = "        self._lines[sku] = self._lines.get(sku, 0) + quantity\n"
    cmp_ = ">=" if ge else ">"
    new = ("        new_quantity = self._lines.get(sku, 0) + quantity\n"
           f"        if new_quantity {cmp_} MAX_PER_LINE:\n"
           "            raise ValueError(f\"limit of {MAX_PER_LINE} per product exceeded\")\n"
           "        self._lines[sku] = new_quantity\n")
    assert old in src
    return src.replace(old, new, 1)


def build_controls(shop: Path) -> list[Control]:
    good_cart = _good_cart(shop)
    pricing = _read(shop, "shop/pricing.py")
    ok = {"fails_before": "pass", "passes_after": "pass", "nothing_breaks": "pass", "tests_have_teeth": "pass"}
    return [
        Control("good_quantity_limit", "A correct task: clear feature, matching solution, strong tests.", ok,
                {"shop/cart.py": good_cart}, {FEATURE_TEST_PATH: GOOD_TESTS}),
        Control("bad_tests_already_pass", "Tests only check behaviour that already exists.",
                {"fails_before": "fail", "passes_after": "pass", "nothing_breaks": "pass", "tests_have_teeth": "fail"},
                {"shop/cart.py": good_cart},
                {FEATURE_TEST_PATH: "import pytest\n\n\ndef test_zero_quantity_rejected(cart):\n"
                 "    with pytest.raises(ValueError):\n        cart.add(\"PEN\", 0)\n"}),
        Control("bad_no_tests_collected", "The test file contains no test functions.",
                {"fails_before": "fail", "passes_after": "fail", "nothing_breaks": "skipped", "tests_have_teeth": "skipped"},
                {"shop/cart.py": good_cart},
                {FEATURE_TEST_PATH: "def check_limit(cart):\n    assert True\n"}),
        Control("bad_solution_off_by_one", "The reference solution rejects exactly 10 units (>= instead of >).",
                {"fails_before": "pass", "passes_after": "fail", "nothing_breaks": "skipped", "tests_have_teeth": "skipped"},
                {"shop/cart.py": _good_cart(shop, ge=True)}, {FEATURE_TEST_PATH: GOOD_TESTS}),
        # The stray pricing change is also untested, so the teeth proof (rightly) fails as well.
        Control("bad_breaks_existing_tests", "The solution is right but also breaks tax rounding elsewhere.",
                {"fails_before": "pass", "passes_after": "pass", "nothing_breaks": "fail", "tests_have_teeth": "fail"},
                {"shop/cart.py": good_cart, "shop/pricing.py": pricing.replace("+ 50) // 100", "+ 0) // 100", 1)},
                {FEATURE_TEST_PATH: GOOD_TESTS}),
        Control("bad_weak_tests", "Tests only look at the constant, so broken logic would go unnoticed.",
                {"fails_before": "pass", "passes_after": "pass", "nothing_breaks": "pass", "tests_have_teeth": "fail"},
                {"shop/cart.py": good_cart},
                {FEATURE_TEST_PATH: "from shop import cart as cart_module\n\n\n"
                 "def test_limit_constant():\n    assert cart_module.MAX_PER_LINE == 10\n"}),
        Control("bad_patch_does_not_apply", "The reference patch no longer matches the repository.",
                {"fails_before": "pass", "passes_after": "fail", "nothing_breaks": "skipped", "tests_have_teeth": "skipped"},
                {"shop/cart.py": good_cart}, {FEATURE_TEST_PATH: GOOD_TESTS}, corrupt_patch=True),
    ]


def make_package(ws_repo, control: Control, task_id: str) -> TaskPackage:
    """Build a TaskPackage by applying the control's solution files in a workspace and diffing."""
    with Workspace(ws_repo) as ws:
        ws.write_files(control.solution)
        patch = ws.make_patch(list(control.solution))
    if control.corrupt_patch:
        patch = patch.replace("self.catalog.get(sku)", "self.catalog.fetch(sku)", 1)
    return TaskPackage(
        task_id=task_id, title=control.description, recipes=["control"], instruction=INSTRUCTION,
        solution_patch=patch, test_files=control.tests, repo_name=ws_repo.name, language=ws_repo.language,
        base_commit=ws_repo.base_commit, test_command=ws_repo.test_command, snapshot=ws_repo.snapshot,
        feature_test_command=ws_repo.feature_test_command, timeout=ws_repo.timeout,
    )


@dataclass
class ControlOutcome:
    control: Control
    report: CheckReport
    mismatches: list[str]

    @property
    def as_expected(self) -> bool:
        return not self.mismatches


def run_controls(shop: Path, out_dir: Path | None = None, **checker_kwargs) -> list[ControlOutcome]:
    repo = resolve_repo(shop, name="shop")
    checker = Checker(repo, **checker_kwargs)
    outcomes = []
    for control in build_controls(Path(shop)):
        pkg = make_package(repo, control, f"control__{control.name}")
        report = checker.check(pkg)
        mismatches = []
        for proof, want in control.expected.items():
            got = report.proof(proof)
            got_status = got.status if got else "missing"
            if got_status != want:
                mismatches.append(f"{proof}: expected {want}, got {got_status}")
        if out_dir is not None:
            d = pkg.write(Path(out_dir) / control.name)
            import json
            (d / "validation" / "proofs.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        outcomes.append(ControlOutcome(control, report, mismatches))
    return outcomes


def render_matrix(outcomes: list[ControlOutcome]) -> str:
    names = ["fails_before", "passes_after", "nothing_breaks", "tests_have_teeth"]
    sym = {"pass": "PASS", "fail": "FAIL", "skipped": "skip", "missing": "-"}
    rows = ["| Control task | " + " | ".join(names) + " | Verdict | As expected |", "|---|" + "---|" * (len(names) + 2)]
    for o in outcomes:
        cells = []
        for n in names:
            p = o.report.proof(n)
            cells.append(sym[p.status] if p else "-")
        verdict = "accepted" if o.report.accepted else "rejected"
        rows.append(f"| {o.control.name} | " + " | ".join(cells) + f" | {verdict} | {'yes' if o.as_expected else 'NO: ' + '; '.join(o.mismatches)} |")
    return "\n".join(rows)
