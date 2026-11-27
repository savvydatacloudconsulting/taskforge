import io
import pathlib

import pytest

import click
from click.testing import CliRunner

MESSAGE = "'-' is not allowed: a file path is required."


def test_allow_dash_attribute():
    assert click.File(allow_dash=False).allow_dash is False
    assert click.File(allow_dash=True).allow_dash is True
    assert click.File().allow_dash is True


@pytest.mark.parametrize("mode", ["r", "rb", "w", "wb", "a"])
def test_dash_rejected_on_command_line(mode):
    calls = []

    @click.command()
    @click.option("--target", type=click.File(mode, allow_dash=False))
    def cli(target):
        calls.append(target)

    result = CliRunner().invoke(cli, ["--target", "-"])

    assert result.exit_code == 2
    assert f"Invalid value for '--target': {MESSAGE}" in result.output
    assert calls == []


@pytest.mark.parametrize("lazy", [None, True, False])
@pytest.mark.parametrize("value", ["-", b"-", pathlib.Path("-")])
def test_every_form_of_dash_rejected(value, lazy):
    file_type = click.File("r", lazy=lazy, allow_dash=False)

    with pytest.raises(click.BadParameter) as excinfo:
        file_type.convert(value, None, None)

    assert excinfo.value.message == MESSAGE


@pytest.mark.parametrize(
    ("option_attrs", "env"),
    [
        ({"default": "-"}, {}),
        ({"envvar": "TF_SOURCE"}, {"TF_SOURCE": "-"}),
    ],
)
def test_dash_rejected_from_other_sources(option_attrs, env):
    calls = []

    @click.command()
    @click.option(
        "--source", type=click.File("r", allow_dash=False), **option_attrs
    )
    def cli(source):
        calls.append(source)

    result = CliRunner().invoke(cli, [], env=env, input="data")

    assert result.exit_code == 2
    assert MESSAGE in result.output
    assert calls == []


@pytest.mark.parametrize("lazy", [True, False])
def test_rejected_dash_creates_no_file(tmp_path, monkeypatch, lazy):
    monkeypatch.chdir(tmp_path)
    file_type = click.File("w", lazy=lazy, allow_dash=False)

    with pytest.raises(click.BadParameter):
        file_type.convert("-", None, None)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("name", ["data.txt", "my-data.txt", "-.txt", "./-"])
def test_real_paths_still_accepted(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    (tmp_path / name).write_text("content", encoding="utf-8")

    @click.command()
    @click.argument("source", type=click.File("r", allow_dash=False))
    def cli(source):
        click.echo(source.read())

    result = CliRunner().invoke(cli, ["--", name])

    assert result.exit_code == 0
    assert result.output == "content\n"


def test_open_file_object_passed_through():
    stream = io.StringIO("content")
    file_type = click.File("r", allow_dash=False)

    assert file_type.convert(stream, None, None) is stream


def test_dash_still_reads_stdin_when_allowed():
    @click.command()
    @click.argument("source", type=click.File("r", allow_dash=True))
    def cli(source):
        click.echo(source.read())

    result = CliRunner().invoke(cli, ["-"], input="from stdin")

    assert result.exit_code == 0
    assert result.output == "from stdin\n"
