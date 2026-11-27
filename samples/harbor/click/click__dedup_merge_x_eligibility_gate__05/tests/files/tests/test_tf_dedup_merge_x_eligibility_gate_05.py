import pytest

import click


def _conflict(name):
    return f"Option '{name}' was given conflicting values."


def _mode_cli(**attrs):
    @click.command()
    @click.option("-m", "--mode", **attrs)
    def cli(mode):
        click.echo(repr(mode))

    return cli


@pytest.mark.parametrize(
    "args",
    [
        ["--mode", "fast"],
        ["--mode", "fast", "--mode", "fast"],
        ["-m", "fast", "--mode=fast", "-mfast"],
    ],
)
def test_identical_repeats_are_merged(runner, args):
    result = runner.invoke(_mode_cli(consistent=True), args)
    assert result.exit_code == 0
    assert result.output == "'fast'\n"


@pytest.mark.parametrize(
    "args",
    [
        ["--mode", "fast", "--mode", "slow"],
        ["-m", "fast", "-m", "fast", "--mode=slow"],
        ["--mode", "fast", "--mode", "FAST"],
    ],
)
def test_conflicting_repeats_are_rejected(runner, args):
    result = runner.invoke(_mode_cli(consistent=True), args)
    assert result.exit_code == 2
    assert _conflict("-m") in result.output


def test_error_type(runner):
    result = runner.invoke(
        _mode_cli(consistent=True),
        ["--mode", "a", "--mode", "b"],
        standalone_mode=False,
    )
    assert isinstance(result.exception, click.BadOptionUsage)
    assert result.exception.format_message() == _conflict("-m")


def test_not_consistent_keeps_last_value(runner):
    cli = _mode_cli(consistent=False)
    result = runner.invoke(cli, ["--mode", "fast", "--mode", "slow"])
    assert result.exit_code == 0
    assert result.output == "'slow'\n"
    assert cli.params[0].consistent is False


def test_comparison_happens_before_type_conversion(runner):
    cli = _mode_cli(type=int, consistent=True)
    result = runner.invoke(cli, ["--mode", "1", "--mode", "1"])
    assert result.output == "1\n"
    result = runner.invoke(cli, ["--mode", "1", "--mode", "01"])
    assert result.exit_code == 2
    assert _conflict("-m") in result.output


def test_nargs_compares_whole_group(runner):
    @click.command()
    @click.option("--point", nargs=2, type=int, consistent=True)
    def cli(point):
        click.echo(repr(point))

    result = runner.invoke(cli, ["--point", "1", "2", "--point", "1", "2"])
    assert result.exit_code == 0
    assert result.output == "(1, 2)\n"
    result = runner.invoke(cli, ["--point", "1", "2", "--point", "1", "3"])
    assert result.exit_code == 2
    assert _conflict("--point") in result.output


@pytest.mark.parametrize(
    ("args", "expect"),
    [
        (["--color", "--color"], "True\n"),
        (["--color", "-c"], "True\n"),
        (["--no-color", "--no-color"], "False\n"),
    ],
)
def test_repeated_flag_is_merged(runner, args, expect):
    @click.command()
    @click.option("--color/--no-color", "-c", consistent=True)
    def cli(color):
        click.echo(repr(color))

    result = runner.invoke(cli, args)
    assert result.exit_code == 0
    assert result.output == expect


@pytest.mark.parametrize(
    "args", [["--color", "--no-color"], ["--no-color", "--color"]]
)
def test_opposite_flags_are_rejected(runner, args):
    @click.command()
    @click.option("--color/--no-color", consistent=True)
    def cli(color):
        click.echo(repr(color))

    result = runner.invoke(cli, args)
    assert result.exit_code == 2
    assert _conflict("--color") in result.output


@pytest.mark.parametrize(
    ("args", "last"),
    [(["--upper", "--lower"], "--lower"), (["--lower", "--upper"], "--upper")],
)
def test_one_consistent_switch_guards_the_group(runner, args, last):
    @click.command()
    @click.option("--upper", "transform", flag_value="upper", consistent=True)
    @click.option("--lower", "transform", flag_value="lower")
    def cli(transform):
        click.echo(transform)

    result = runner.invoke(cli, args)
    assert result.exit_code == 2
    assert _conflict(last) in result.output

    result = runner.invoke(cli, [args[0], args[0]])
    assert result.exit_code == 0
    assert result.output == args[0][2:] + "\n"


def test_conflict_runs_no_callbacks(runner):
    calls = []

    def record(ctx, param, value):
        calls.append(value)
        return value

    @click.command()
    @click.option("--mode", consistent=True, callback=record, is_eager=True)
    def cli(mode):
        calls.append("command")

    result = runner.invoke(cli, ["--mode", "a", "--mode", "b"])
    assert result.exit_code == 2
    assert calls == []


def test_envvar_and_default_do_not_conflict(runner):
    cli = _mode_cli(consistent=True, envvar="TF_MODE", default="auto")
    result = runner.invoke(cli, ["--mode", "fast"], env={"TF_MODE": "slow"})
    assert result.exit_code == 0
    assert result.output == "'fast'\n"
    result = runner.invoke(cli, [], env={"TF_MODE": "slow"})
    assert result.output == "'slow'\n"


@pytest.mark.parametrize("attrs", [{"multiple": True}, {"count": True}])
def test_ineligible_options_are_rejected(attrs):
    with pytest.raises(
        TypeError, match="'consistent' is not valid with 'multiple' or 'count'."
    ):
        click.Option(["--item"], consistent=True, **attrs)
