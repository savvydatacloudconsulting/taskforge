"""Feature recipes: reusable patterns for new features.

A recipe is domain-neutral. It tells the AI what KIND of behaviour to add
(a limit, an eligibility rule, a threshold ...) and the AI adapts it to the
repository it is shown. Recipes can be combined, so tasks differ in behaviour
and interactions, not just in names.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    family: str
    guidance: str
    tags: frozenset[str]
    params: dict[str, tuple] = field(default_factory=dict)


RECIPES: list[Recipe] = [
    Recipe(
        "quantity_limit", "Cap how much of something is allowed", "bounds",
        "Add a hard cap on a quantity the code already tracks (items, uses, attempts, size). Exceeding it must be "
        "rejected with a specific error and leave state unchanged. Decide how the cap applies (per item, per owner, in total).",
        frozenset({"rule:limit", "flow:reject", "state:unchanged-on-error"}), {"limit": (2, 3, 5, 8, 10, 25)},
    ),
    Recipe(
        "eligibility_gate", "Allow an operation only for eligible input", "rules",
        "Add a rule that decides whether an EXISTING operation is allowed, based on an attribute of the input "
        "(a category, a flag, a type). Ineligible input is rejected clearly; eligible input behaves exactly as before.",
        frozenset({"rule:eligibility", "flow:reject", "data:attribute"}),
    ),
    Recipe(
        "threshold_effect", "Change behaviour once a threshold is crossed", "numeric",
        "Add behaviour that only kicks in once a numeric value reaches a threshold (a total, a count, an age). "
        "Define precisely what happens exactly AT the threshold and just below it.",
        frozenset({"rule:threshold", "numeric:comparison", "flow:branch"}), {"threshold": (3, 5, 10, 50, 100, 500)},
    ),
    Recipe(
        "tiered_rates", "Apply different rates in tiers", "numeric",
        "Introduce tiers: the value is split into bands and each band uses a different rate, amount or rule. "
        "Specify band edges and how values on an edge are treated.",
        frozenset({"rule:tiers", "numeric:piecewise", "flow:loop"}),
    ),
    Recipe(
        "rounding_policy", "Define an exact rounding or precision policy", "numeric",
        "Introduce a precise rounding or precision policy for a calculated number (round half up, banker's rounding, "
        "floor to a unit, minimum charge). State the policy with worked examples that include halves and tiny values.",
        frozenset({"numeric:rounding", "rule:policy", "numeric:arithmetic"}),
    ),
    Recipe(
        "time_window", "Make a rule valid only within a time window", "time",
        "Add a rule that is only active in a time window (start/end, inclusive or exclusive). The current time MUST be "
        "passed in as a parameter (never read the real clock) so tests are deterministic.",
        frozenset({"rule:time-window", "data:time", "flow:branch"}),
    ),
    Recipe(
        "validation_rejection", "Reject malformed input with precise errors", "rules",
        "Add input validation to an existing entry point: specific malformed inputs raise specific errors with "
        "specific messages. Valid input must behave exactly as before.",
        frozenset({"rule:validation", "flow:reject", "data:text"}),
    ),
    Recipe(
        "audit_trail", "Record and expose a history of events", "state",
        "Record an event each time an existing operation succeeds (and optionally fails) and expose a way to read the "
        "history back, in order, with a clear shape for each entry. Failed or no-op calls must be specified too.",
        frozenset({"state:history", "api:query", "flow:append"}),
    ),
    Recipe(
        "dedup_merge", "Merge or de-duplicate repeated input", "state",
        "Handle repeated or equivalent input deliberately: duplicates are merged, ignored or counted, according to a "
        "clearly stated rule that depends on what is being repeated.",
        frozenset({"state:merge", "rule:dedup", "flow:branch"}),
    ),
    Recipe(
        "rule_stacking", "Combine two rules with a precedence and a cap", "rules",
        "Add two independent adjustments that can both apply to the same thing, and define how they combine "
        "(order, which wins, maximum total effect). Include a case where both apply and one where only one does.",
        frozenset({"rule:stacking", "rule:precedence", "numeric:arithmetic", "flow:branch"}),
    ),
]
BY_ID = {r.id: r for r in RECIPES}


@dataclass
class Plan:
    recipes: list[Recipe]
    params: dict[str, object]

    @property
    def ids(self) -> list[str]:
        return [r.id for r in self.recipes]

    @property
    def slug(self) -> str:
        return "+".join(self.ids)

    @property
    def tags(self) -> set[str]:
        out: set[str] = set()
        for r in self.recipes:
            out |= set(r.tags)
        return out

    def describe(self) -> str:
        lines = []
        for r in self.recipes:
            lines.append(f"- **{r.title}** ({r.id}): {r.guidance}")
        if len(self.recipes) > 1:
            lines.append("- Combine the ideas above in ONE coherent feature: they must interact, "
                         "and at least one requirement must only make sense when both apply.")
        for k, v in self.params.items():
            lines.append(f"- Suggested value for `{k}`: {v} (adapt if it does not fit the code)")
        return "\n".join(lines)


def plan_batch(n: int, seed: int = 0, only: list[str] | None = None) -> list[Plan]:
    """Choose n plans. Every recipe is used once before any repeats, and about
    40% of tasks are two-recipe combinations from different families."""
    rng = random.Random(seed)
    pool = [BY_ID[i] for i in only] if only else list(RECIPES)
    if not pool:
        raise ValueError("no recipes selected")
    order = pool[:]
    rng.shuffle(order)
    n_combo = round(n * 0.4) if len(pool) > 1 else 0
    n_single = n - n_combo
    plans: list[Plan] = []
    for i in range(n_single):
        plans.append(_with_params(rng, [order[i % len(order)]]))
    for i in range(n_combo):
        first = order[(n_single + i) % len(order)]
        others = [r for r in pool if r.family != first.family] or [r for r in pool if r.id != first.id]
        second = rng.choice(others)
        plans.append(_with_params(rng, [first, second]))
    rng.shuffle(plans)
    return plans


def _with_params(rng: random.Random, recipes: list[Recipe]) -> Plan:
    params: dict[str, object] = {}
    for r in recipes:
        for k, choices in r.params.items():
            params[k] = rng.choice(choices)
    return Plan(recipes, params)
