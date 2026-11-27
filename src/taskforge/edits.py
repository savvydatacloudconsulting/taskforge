"""Search-and-replace edits, so that a change to a very large file does not need the whole file back.

    <<<<<<< SEARCH
    exact lines of the current file
    =======
    the lines that replace them
    >>>>>>> REPLACE

Each SEARCH text must match exactly one place. Trailing spaces are ignored.
"""

from __future__ import annotations

SEARCH, DIVIDER, REPLACE = "<<<<<<< SEARCH", "=======", ">>>>>>> REPLACE"


class EditError(ValueError):
    pass


def parse_blocks(body: str) -> list[tuple[list[str], list[str]]]:
    blocks: list[tuple[list[str], list[str]]] = []
    search: list[str] = []
    new: list[str] = []
    state = "outside"
    for line in body.split("\n"):
        mark = line.rstrip()
        if state == "outside":
            if mark == SEARCH:
                search, new, state = [], [], "search"
            elif mark.strip() and not mark.startswith("```"):
                raise EditError(f"text outside a SEARCH/REPLACE block: {mark[:60]!r}")
        elif state == "search":
            if mark == DIVIDER:
                state = "replace"
            elif mark in (SEARCH, REPLACE):
                raise EditError("a SEARCH block is missing its '=======' line")
            else:
                search.append(line)
        else:
            if mark == REPLACE:
                if not any(s.strip() for s in search):
                    raise EditError("a SEARCH block is empty")
                blocks.append((search, new))
                state = "outside"
            elif mark == SEARCH:
                raise EditError("a REPLACE block is missing its '>>>>>>> REPLACE' line")
            else:
                new.append(line)
    if state != "outside":
        raise EditError("the last SEARCH/REPLACE block is not closed")
    if not blocks:
        raise EditError("no SEARCH/REPLACE block found")
    return blocks


def apply_blocks(original: str, blocks: list[tuple[list[str], list[str]]]) -> str:
    lines = original.split("\n")
    for number, (search, new) in enumerate(blocks, start=1):
        want = [s.rstrip() for s in search]
        n = len(want)
        hits = [i for i in range(len(lines) - n + 1)
                if lines[i].rstrip() == want[0] and [x.rstrip() for x in lines[i:i + n]] == want]
        if len(hits) != 1:
            first = next((s.strip() for s in want if s.strip()), "")[:60]
            problem = "does not match the current file" if not hits else f"matches {len(hits)} places"
            raise EditError(f"SEARCH block {number} (starting {first!r}) {problem}; copy more surrounding lines exactly")
        i = hits[0]
        lines[i:i + n] = new
    return "\n".join(lines)
