## Background

`HelpFormatter.write_dl` renders definition lists (used for options and commands) with every entry directly below the previous one. This is compact and readable while descriptions are short, but once some descriptions wrap over several lines it becomes hard to see where one entry ends and the next begins.

Add an opt-in threshold to `write_dl`: once any description in the list is at least that many lines tall, the whole list is rendered with a blank line between entries.

## Requirements

1. `HelpFormatter.write_dl` accepts a new optional argument `spread_threshold`. When it is `None` (the default), the output is the same as today, however long the descriptions are.
2. A description's line count is the number of lines it occupies after being wrapped to the width of the second column (that width is computed as it is today).
3. If at least one row has a line count **greater than or equal to** `spread_threshold`, one empty line is written between **every** pair of consecutive rows in that list, including pairs of short rows and pairs that come before the long row.
4. If every row has a line count below `spread_threshold` (for example exactly `spread_threshold - 1`), the output is the same as without a threshold.
5. The separator is a completely empty line (just a newline, with no indentation), even inside an indented section. No empty line is added before the first row or after the last row.
6. Line counting rules:
   - When a term is too wide for the first column and its description starts on the following line, the term's line does not count.
   - Blank lines between paragraphs inside a description do count.
   - A row with an empty description has a line count of 0. It is still separated from its neighbours when the list is spread out.
7. The decision is made separately for each `write_dl` call.
8. A `spread_threshold` lower than 1 raises `ValueError`, and nothing is written to the formatter.

## Public interface

```python
HelpFormatter.write_dl(
    rows,
    col_max: int = 30,
    col_spacing: int = 2,
    spread_threshold: int | None = None,
) -> None
```

- Raises `ValueError` with the message `spread_threshold must be at least 1.` when `spread_threshold` is less than 1.

## Examples

```python
formatter = click.HelpFormatter(width=40)
long_text = " ".join(["abcdefghi"] * 9)  # wraps to 3 lines here
formatter.write_dl(
    [("-a", "Short."), ("-b", long_text), ("-c", "Tiny.")],
    spread_threshold=3,
)
print(formatter.getvalue(), end="")
```

Output:

```text
-a  Short.

-b  abcdefghi abcdefghi abcdefghi
    abcdefghi abcdefghi abcdefghi
    abcdefghi abcdefghi abcdefghi

-c  Tiny.
```

With `spread_threshold=4`, the same rows are printed without any empty lines.
