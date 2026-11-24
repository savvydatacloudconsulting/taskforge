"""Variation score: are the tasks different in BEHAVIOUR, or only in wording?

Two tasks that differ only in names, strings or constants (a "Black Friday"
banner versus a "Christmas" banner) have the same *shape*. We normalise every
identifier, number and string away and compare what is left: keywords,
operators and structure. Near-identical shapes are cosmetic duplicates.
"""

from __future__ import annotations

import hashlib
import itertools
import re
from dataclasses import dataclass, field
from keyword import kwlist

from .patchutil import is_test_path, parse_patch
from .recipes import BY_ID

TOKEN_RE = re.compile(r"""[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|==|!=|<=|>=|//|\*\*|->|[^\s\w]""")
KEYWORDS = set(kwlist)
MIN_DISTANCE = 0.25  # below this, two tasks are treated as near-duplicates


def normalise(text: str) -> list[str]:
    out = []
    for tok in TOKEN_RE.findall(text):
        if tok[0] in "\"'":
            out.append("STR")
        elif tok[0].isdigit():
            out.append("NUM")
        elif tok[0].isalpha() or tok[0] == "_":
            out.append(tok if tok in KEYWORDS else "ID")
        else:
            out.append(tok)
    return out


def shingles(tokens: list[str], k: int = 4) -> set[str]:
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def _jaccard_distance(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return 1.0 - len(a & b) / len(a | b)


@dataclass
class Signature:
    task_id: str
    shape_hash: str
    shingles: set[str]
    tags: set[str]
    symbols: set[str]
    recipes: list[str] = field(default_factory=list)


def signature(task_id: str, patch: str, recipes: list[str]) -> Signature:
    changes = {p: c for p, c in parse_patch(patch).items() if not is_test_path(p)}
    added = "\n".join(line for c in changes.values() for line in c.added_text)
    toks = normalise(added)
    tags = {f"kw:{t}" for t in toks if t in KEYWORDS and t in {
        "if", "elif", "else", "for", "while", "raise", "try", "except", "return", "def", "class", "lambda", "with", "yield"}}
    tags |= {f"op:{t}" for t in toks if t in {"<", ">", "<=", ">=", "==", "!=", "+", "-", "*", "/", "//", "%", "**"}}
    for rid in recipes:
        if rid in BY_ID:
            tags |= set(BY_ID[rid].tags)
    symbols = {f"file:{p}" for p in changes}
    for c in changes.values():
        symbols |= {f"ctx:{x}" for x in c.contexts}
    for line in added.splitlines():
        m = re.match(r"\s*(?:def|class)\s+(\w+)", line)
        if m:
            symbols.add(f"new:{m.group(1)}")
    shape = hashlib.sha1(" ".join(toks).encode()).hexdigest()[:16]
    return Signature(task_id, shape, shingles(toks), tags, symbols, list(recipes))


def distance(a: Signature, b: Signature) -> float:
    """0.0 = same shape; 1.0 = nothing in common."""
    if a.shape_hash == b.shape_hash:
        return 0.0
    return round(0.5 * _jaccard_distance(a.shingles, b.shingles)
                 + 0.25 * _jaccard_distance(a.tags, b.tags)
                 + 0.25 * _jaccard_distance(a.symbols, b.symbols), 4)


def nearest(sig: Signature, others: list[Signature]) -> tuple[float, str | None]:
    if not others:
        return 1.0, None
    d, other = min(((distance(sig, o), o.task_id) for o in others), key=lambda t: t[0])
    return d, other


def matrix(sigs: list[Signature]) -> list[list[float]]:
    return [[0.0 if i == j else distance(a, b) for j, b in enumerate(sigs)] for i, a in enumerate(sigs)]


def batch_score(sigs: list[Signature]) -> float | None:
    """Mean pairwise distance over a set of accepted tasks (None if fewer than two)."""
    if len(sigs) < 2:
        return None
    ds = [distance(a, b) for a, b in itertools.combinations(sigs, 2)]
    return round(sum(ds) / len(ds), 3)
