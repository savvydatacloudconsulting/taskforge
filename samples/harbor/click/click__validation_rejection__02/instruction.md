## Background
`click.DateTime(formats=...)` accepts anything as `formats`. Mistakes such as passing one string instead of a list, or writing a format with no `%` directive, are not reported when the type is declared. They only show up later as confusing conversion failures for the end user. These mistakes should be rejected as soon as the type is constructed.

## Requirements
1. Passing a single `str` as `formats` (including the empty string) raises `TypeError`.
2. Every item in `formats` must be a `str`. A non-string item raises `TypeError` naming its zero-based index and its type.
3. A format must not end with an incomplete directive, meaning a `%` with nothing after it. The pair `%%` is a literal percent sign and is matched from left to right, so `"%Y%"` and `"%%%"` are incomplete, while `"%Y%%"` is not. A violation raises `ValueError`.
4. A format must contain at least one directive other than the literal `%%`. For example `""`, `"YYYY-MM-DD"` and `"%%Y"` raise `ValueError`, while `"%%%Y"` is accepted.
5. The same format string must not be listed more than once. A repeat raises `ValueError`. Comparison is exact, so `"%y"` and `"%Y"` are different formats.
6. Items are checked in list order and the error is raised for the first offending item. For a single item, the rules apply in the order of requirements 2, 3, 4, 5.
7. Valid input behaves as before. `formats=None` and an empty list or tuple still select the three default formats, and a valid list or tuple is stored unchanged in the `formats` attribute.

## Public interface
`click.DateTime(formats: Sequence[str] | None = None)` keeps its signature. The exception messages are exactly as follows, where `{fmt!r}` is the `repr` of the offending format, `{index}` is its position and `{type_name}` is `type(item).__name__`.

| Case | Exception | Message |
| --- | --- | --- |
| single string | `TypeError` | `'formats' must be a sequence of format strings, not a single string.` |
| non-string item | `TypeError` | `Format at index {index} must be a string, not {type_name}.` |
| incomplete directive | `ValueError` | `Format {fmt!r} ends with an incomplete directive.` |
| no directive | `ValueError` | `Format {fmt!r} has no '%' directive.` |
| repeated format | `ValueError` | `Format {fmt!r} is listed more than once.` |

## Examples
```python
click.DateTime(["%d/%m/%Y", "%Y-%m-%d"])  # accepted

click.DateTime("%Y-%m-%d")
# TypeError: 'formats' must be a sequence of format strings, not a single string.

click.DateTime(["%Y-%m-%d", "dd/mm/yyyy"])
# ValueError: Format 'dd/mm/yyyy' has no '%' directive.
```
