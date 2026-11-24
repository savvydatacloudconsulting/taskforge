import pytest

from taskforge.mutate import apply_mutation, find_sites
from taskforge.patchutil import is_test_path, parse_patch, safe_relpath

SRC = """\
LIMIT = 10


def check(n, flag):
    if n > LIMIT and flag:
        return n - 1
    total = n + 2
    return total
"""

PATCH = """\
diff --git a/app/core.py b/app/core.py
index 111..222 100644
--- a/app/core.py
+++ b/app/core.py
@@ -3,3 +3,6 @@ def check(n):
 keep = 1
+added_one = 2
+if added_one > 1:
+    pass
 tail = 3
diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+def f():
+    return 1
"""


def test_sites_are_found_and_limited_to_given_lines():
    all_sites = find_sites(SRC)
    assert len(all_sites) >= 7
    only_line_5 = find_sites(SRC, {5})
    assert {s.lineno for s in only_line_5} == {5}
    assert {s.operator for s in only_line_5} >= {"compare", "logic", "condition"}


def test_site_order_is_deterministic():
    assert [s.description for s in find_sites(SRC)] == [s.description for s in find_sites(SRC)]


def test_every_mutant_is_valid_python_and_different():
    for site in find_sites(SRC):
        mutated = apply_mutation(SRC, site.index)
        compile(mutated, "<m>", "exec")
        assert mutated.strip() != SRC.strip()


def test_mutation_changes_behaviour():
    site = next(s for s in find_sites(SRC, {5}) if s.operator == "compare")
    ns: dict = {}
    exec(apply_mutation(SRC, site.index, {5}), ns)  # > becomes >=
    assert ns["check"](10, True) == 9  # original returns 12 for n == LIMIT


def test_unknown_index_raises():
    with pytest.raises(ValueError):
        apply_mutation(SRC, 999)


def test_parse_patch_reads_added_lines_and_new_files():
    ch = parse_patch(PATCH)
    assert ch["app/core.py"].added_lines == {4, 5, 6}
    assert ch["app/core.py"].added_text == ["added_one = 2", "if added_one > 1:", "    pass"]
    assert "def check(n):" in next(iter(ch["app/core.py"].contexts))
    assert ch["new.py"].added_lines == {1, 2}


@pytest.mark.parametrize("path,expected", [
    ("tests/test_x.py", True), ("src/pkg/test_cart.py", True), ("src/cart_test.go", True),
    ("web/app.spec.ts", True), ("src/cart.py", False), ("src/contest.py", False), ("latest/notes.py", False),
])
def test_is_test_path(path, expected):
    assert is_test_path(path) is expected


@pytest.mark.parametrize("bad", ["", "../x.py", "/etc/passwd", "C:/x.py", "a\\b.py", ".git/config", "a/./b.py", " pad.py"])
def test_safe_relpath_rejects_unsafe(bad):
    with pytest.raises(ValueError):
        safe_relpath(bad)


def test_safe_relpath_accepts_normal_paths():
    assert safe_relpath("shop/cart.py") == "shop/cart.py"
