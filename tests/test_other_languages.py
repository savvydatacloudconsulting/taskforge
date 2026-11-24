"""The pipeline is not tied to Python: a JavaScript repository goes through the same proofs."""

import shutil

import pytest

from taskforge.checker import Checker
from taskforge.package import TaskPackage
from taskforge.repo import resolve_repo
from taskforge.runner import Workspace

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

LIMIT_JS = """\
"use strict";

const MAX_PER_LINE = 5;

class Cart {
  constructor() {
    this.lines = new Map();
  }

  add(sku, quantity = 1) {
    if (!Number.isInteger(quantity) || quantity <= 0) {
      throw new Error("quantity must be positive");
    }
    const next = (this.lines.get(sku) || 0) + quantity;
    if (next > MAX_PER_LINE) {
      throw new Error("limit of 5 per product exceeded");
    }
    this.lines.set(sku, next);
  }

  quantity(sku) {
    return this.lines.get(sku) || 0;
  }

  total(prices) {
    let sum = 0;
    for (const [sku, qty] of this.lines) {
      if (!(sku in prices)) throw new Error(`no price for ${sku}`);
      sum += prices[sku] * qty;
    }
    return sum;
  }
}

module.exports = { Cart };
"""

TEST_JS = """\
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { Cart } = require("../src/cart");

test("five units are allowed", () => {
  const cart = new Cart();
  cart.add("pen", 5);
  assert.strictEqual(cart.quantity("pen"), 5);
});

test("a sixth unit is rejected and nothing changes", () => {
  const cart = new Cart();
  cart.add("pen", 5);
  assert.throws(() => cart.add("pen"), /limit of 5/);
  assert.strictEqual(cart.quantity("pen"), 5);
});
"""


@pytest.fixture(scope="module")
def js_repo(tmp_path_factory):
    from conftest import ROOT

    return resolve_repo(ROOT / "examples" / "jscart", name="jscart", feature_test_command="node --test {files}")


def test_javascript_repo_is_detected(js_repo):
    assert js_repo.language == "javascript" and js_repo.test_command == "node --test"


def test_javascript_task_passes_the_language_neutral_proofs(js_repo):
    with Workspace(js_repo) as ws:
        ws.write_files({"src/cart.js": LIMIT_JS})
        patch = ws.make_patch(["src/cart.js"])
    pkg = TaskPackage("jscart__limit__01", "Limit units", ["quantity_limit"], "## Requirements\n1. cap at 5\n", patch,
                      {"test/tf_limit.test.js": TEST_JS}, "jscart", "javascript", js_repo.base_commit, js_repo.test_command,
                      snapshot=js_repo.snapshot, feature_test_command=js_repo.feature_test_command)
    report = Checker(js_repo).check(pkg)
    status = {p.name: p.status for p in report.proofs}
    assert status == {"fails_before": "pass", "passes_after": "pass", "nothing_breaks": "pass", "tests_have_teeth": "skipped"}, report.to_dict()
    assert report.accepted
    assert "only implemented for Python" in report.proof("tests_have_teeth").detail


ALREADY_PASSING_JS = """\
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { Cart } = require("../src/cart");

test("adding two units works", () => {
  const cart = new Cart();
  cart.add("pen", 2);
  assert.strictEqual(cart.quantity("pen"), 2);
});
"""


def test_javascript_tests_that_already_pass_are_rejected(js_repo):
    pkg = TaskPackage("jscart__bad__01", "x", [], "i", "diff --git a/x b/x\n", {"test/tf_ok.test.js": ALREADY_PASSING_JS},
                      "jscart", "javascript", js_repo.base_commit, js_repo.test_command, snapshot=js_repo.snapshot,
                      feature_test_command=js_repo.feature_test_command)
    assert Checker(js_repo).check(pkg).proof("fails_before").status == "fail"
