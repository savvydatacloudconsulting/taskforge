import pytest

import click

WORD = "abcdefghi"
# With a width of 40 and two character terms, three words fit on each line.
LINE = " ".join([WORD] * 3)


def words(count):
    return " ".join([WORD] * count)


def render(rows, **kwargs):
    formatter = click.HelpFormatter(width=40)
    formatter.write_dl(rows, **kwargs)
    return formatter.getvalue()


def test_spreads_all_rows_at_threshold():
    rows = [("-a", "Short."), ("-b", words(9)), ("-c", "Tiny."), ("-d", "End.")]

    assert render(rows, spread_threshold=3) == (
        f"-a  Short.\n\n-b  {LINE}\n    {LINE}\n    {LINE}\n\n-c  Tiny.\n\n-d  End.\n"
    )


def test_compact_just_below_threshold():
    rows = [("-a", "Short."), ("-b", words(6)), ("-c", "Tiny.")]
    expected = f"-a  Short.\n-b  {LINE}\n    {LINE}\n-c  Tiny.\n"

    assert render(rows, spread_threshold=3) == expected
    assert render(rows, spread_threshold=2) == (
        f"-a  Short.\n\n-b  {LINE}\n    {LINE}\n\n-c  Tiny.\n"
    )


def test_none_never_spreads():
    rows = [("-a", words(12)), ("-b", "Tiny.")]

    assert render(rows, spread_threshold=None) == (
        f"-a  {LINE}\n    {LINE}\n    {LINE}\n    {LINE}\n-b  Tiny.\n"
    )


def test_long_term_line_is_not_counted():
    rows = [("--very-long-name", words(4)), ("-b", "Tiny.")]
    pad = " " * 12
    two_words = words(2)
    first = f"--very-long-name\n{pad}{two_words}\n{pad}{two_words}\n"
    second = "-b" + " " * 10 + "Tiny.\n"

    assert render(rows, col_max=10, spread_threshold=3) == first + second
    assert render(rows, col_max=10, spread_threshold=2) == first + "\n" + second


def test_paragraph_blank_lines_are_counted():
    rows = [("-a", "One.\n\nTwo."), ("-b", "Tiny.")]

    assert render(rows, spread_threshold=3) == (
        "-a  One.\n    \n    Two.\n\n-b  Tiny.\n"
    )
    assert render(rows, spread_threshold=4) == (
        "-a  One.\n    \n    Two.\n-b  Tiny.\n"
    )


def test_separator_is_empty_inside_section_and_decided_per_call():
    formatter = click.HelpFormatter(width=40)

    with formatter.section("Options"):
        formatter.write_dl(
            [("-a", words(9)), ("-b", "Tiny.")],
            spread_threshold=3,
        )

    with formatter.section("Commands"):
        formatter.write_dl([("go", "Go."), ("up", "Up.")], spread_threshold=3)

    assert formatter.getvalue() == (
        f"Options:\n  -a  {LINE}\n      {LINE}\n      {LINE}\n\n  -b  Tiny.\n"
        "\nCommands:\n  go  Go.\n  up  Up.\n"
    )


def test_single_row_gets_no_surrounding_blank_lines():
    assert render([("-a", words(6))], spread_threshold=1) == (
        f"-a  {LINE}\n    {LINE}\n"
    )


def test_empty_descriptions():
    assert render([("-a", ""), ("-b", "")], spread_threshold=1) == "-a\n-b\n"
    assert render([("-a", ""), ("-b", "Tiny."), ("-c", "")], spread_threshold=1) == (
        "-a\n\n-b  Tiny.\n\n-c\n"
    )


@pytest.mark.parametrize("threshold", [0, -1])
def test_threshold_below_one_is_rejected(threshold):
    formatter = click.HelpFormatter(width=40)

    with pytest.raises(ValueError, match="spread_threshold must be at least 1."):
        formatter.write_dl([("-a", "Short.")], spread_threshold=threshold)

    assert formatter.getvalue() == ""
