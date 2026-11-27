import pytest

import click

SINGLE_STRING = "'formats' must be a sequence of format strings, not a single string."


def _error(exc_type, formats):
    with pytest.raises(exc_type) as excinfo:
        click.DateTime(formats)

    return str(excinfo.value)


@pytest.mark.parametrize("formats", ["%Y-%m-%d", ""])
def test_single_string_rejected(formats):
    assert _error(TypeError, formats) == SINGLE_STRING


@pytest.mark.parametrize(
    ("formats", "index", "type_name"),
    [
        ([None], 0, "NoneType"),
        (["%Y", 5], 1, "int"),
        (("%Y", "%m", b"%d"), 2, "bytes"),
    ],
)
def test_non_string_item_rejected(formats, index, type_name):
    expected = f"Format at index {index} must be a string, not {type_name}."
    assert _error(TypeError, formats) == expected


@pytest.mark.parametrize("fmt", ["%", "%Y%", "%%%", "date%", "%Y-%%%"])
def test_incomplete_directive_rejected(fmt):
    expected = f"Format {fmt!r} ends with an incomplete directive."
    assert _error(ValueError, [fmt]) == expected


@pytest.mark.parametrize("fmt", ["", "YYYY-MM-DD", "%%", "%%Y", "100%%"])
def test_format_without_directive_rejected(fmt):
    expected = f"Format {fmt!r} has no '%' directive."
    assert _error(ValueError, ["%Y", fmt]) == expected


def test_literal_percent_boundaries():
    formats = ["%%%Y", "%Y%%"]
    date_type = click.DateTime(formats)

    assert date_type.formats is formats
    assert date_type.convert("%2024", None, None).year == 2024
    assert date_type.convert("2023%", None, None).year == 2023
    assert _error(ValueError, [*formats, "%%%%"]) == (
        "Format '%%%%' has no '%' directive."
    )


def test_repeated_format_rejected():
    assert _error(ValueError, ["%Y", "%m", "%Y"]) == (
        "Format '%Y' is listed more than once."
    )
    assert _error(ValueError, ("%d/%m", "%d/%m")) == (
        "Format '%d/%m' is listed more than once."
    )


def test_comparison_of_repeats_is_exact():
    formats = ("%y", "%Y")

    assert click.DateTime(formats).formats is formats
    assert _error(ValueError, [*formats, "%y"]) == (
        "Format '%y' is listed more than once."
    )


@pytest.mark.parametrize(
    ("formats", "exc_type", "message"),
    [
        (["bad", 1], ValueError, "Format 'bad' has no '%' directive."),
        ([1, "bad"], TypeError, "Format at index 0 must be a string, not int."),
        (
            ["%Y", "%Y", "%"],
            ValueError,
            "Format '%Y' is listed more than once.",
        ),
        (
            ["%Y", "x%", "%Y"],
            ValueError,
            "Format 'x%' ends with an incomplete directive.",
        ),
    ],
)
def test_first_offending_item_is_reported(formats, exc_type, message):
    assert _error(exc_type, formats) == message


def test_error_raised_at_declaration():
    with pytest.raises(ValueError) as excinfo:

        @click.command()
        @click.option("--when", type=click.DateTime(["dd/mm/yyyy"]))
        def cli(when):
            pass

    assert str(excinfo.value) == "Format 'dd/mm/yyyy' has no '%' directive."
