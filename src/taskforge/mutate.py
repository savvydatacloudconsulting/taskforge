"""A small mutation engine for Python.

It makes deliberately broken copies ("mutants") of the lines a solution added.
If the feature tests still pass on a mutant, the tests are too weak to notice
that behaviour change, and the task fails the "tests have teeth" proof.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

COMPARE_SWAP = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}
BINOP_SWAP = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv,
    ast.FloorDiv: ast.Mult,
    ast.Div: ast.Mult,
}
BOOLOP_SWAP = {ast.And: ast.Or, ast.Or: ast.And}
AUG_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add}


@dataclass(frozen=True)
class MutationSite:
    index: int
    lineno: int
    operator: str
    description: str


class _Mutator(ast.NodeTransformer):
    """Walks the tree in a fixed order. In count mode it records the sites;
    in apply mode it changes the site whose index equals ``target``."""

    def __init__(self, lines: set[int] | None, target: int | None):
        self.lines = lines
        self.target = target
        self.sites: list[MutationSite] = []
        self._i = 0
        self.applied = False

    def _eligible(self, node: ast.AST) -> bool:
        if not hasattr(node, "lineno"):  # nodes we created ourselves are never mutated again
            return False
        return self.lines is None or node.lineno in self.lines

    def _site(self, node: ast.AST, operator: str, description: str) -> bool:
        """Register a site; return True when this is the one to mutate."""
        idx = self._i
        self._i += 1
        self.sites.append(MutationSite(idx, node.lineno, operator, description))
        if self.target == idx:
            self.applied = True
            return True
        return False

    def visit_Compare(self, node: ast.Compare):
        if self._eligible(node) and type(node.ops[0]) in COMPARE_SWAP:
            old = type(node.ops[0])
            new = COMPARE_SWAP[old]
            if self._site(node, "compare", f"line {node.lineno}: comparison {old.__name__} -> {new.__name__}"):
                node.ops[0] = new()
        return self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp):
        if self._eligible(node) and type(node.op) in BINOP_SWAP:
            old = type(node.op)
            new = BINOP_SWAP[old]
            if self._site(node, "arithmetic", f"line {node.lineno}: arithmetic {old.__name__} -> {new.__name__}"):
                node.op = new()
        return self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp):
        if self._eligible(node) and type(node.op) in BOOLOP_SWAP:
            old = type(node.op)
            new = BOOLOP_SWAP[old]
            if self._site(node, "logic", f"line {node.lineno}: logic {old.__name__} -> {new.__name__}"):
                node.op = new()
        return self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign):
        if self._eligible(node) and type(node.op) in AUG_SWAP:
            old = type(node.op)
            new = AUG_SWAP[old]
            if self._site(node, "augassign", f"line {node.lineno}: update {old.__name__} -> {new.__name__}"):
                node.op = new()
        return self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp):
        if self._eligible(node) and isinstance(node.op, ast.Not):
            if self._site(node, "negation", f"line {node.lineno}: removed 'not'"):
                return self.generic_visit(node.operand)
        return self.generic_visit(node)

    def _negate_test(self, node, label: str):
        if self._eligible(node):
            if self._site(node, "condition", f"line {node.lineno}: negated {label} condition"):
                node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
        return self.generic_visit(node)

    def visit_If(self, node: ast.If):
        return self._negate_test(node, "if")

    def visit_IfExp(self, node: ast.IfExp):
        return self._negate_test(node, "conditional-expression")

    def visit_Constant(self, node: ast.Constant):
        if not self._eligible(node):
            return node
        v = node.value
        if isinstance(v, bool):
            if self._site(node, "constant", f"line {node.lineno}: flipped {v} -> {not v}"):
                return ast.copy_location(ast.Constant(value=not v), node)
        elif isinstance(v, int):
            if self._site(node, "constant", f"line {node.lineno}: constant {v} -> {v + 1}"):
                return ast.copy_location(ast.Constant(value=v + 1), node)
        elif isinstance(v, float):
            if self._site(node, "constant", f"line {node.lineno}: constant {v} -> {v + 1.0}"):
                return ast.copy_location(ast.Constant(value=v + 1.0), node)
        return node

    def visit_Return(self, node: ast.Return):
        if self._eligible(node) and node.value is not None:
            is_none = isinstance(node.value, ast.Constant) and node.value.value is None
            if not is_none and self._site(node, "return", f"line {node.lineno}: return value replaced by None"):
                node.value = ast.Constant(value=None)
                return node
        return self.generic_visit(node)


def find_sites(source: str, lines: set[int] | None = None) -> list[MutationSite]:
    """List every mutation site on the given lines (all lines when None)."""
    tree = ast.parse(source)
    m = _Mutator(lines, None)
    m.visit(tree)
    return m.sites


def apply_mutation(source: str, index: int, lines: set[int] | None = None) -> str:
    """Return the source with the mutation at ``index`` applied.

    Raises ValueError when the index does not exist or the result is invalid Python.
    """
    tree = ast.parse(source)
    m = _Mutator(lines, index)
    tree = m.visit(tree)
    if not m.applied:
        raise ValueError(f"no mutation site with index {index}")
    ast.fix_missing_locations(tree)
    out = ast.unparse(tree) + "\n"
    compile(out, "<mutant>", "exec")  # raises SyntaxError if the mutant is not valid
    return out
