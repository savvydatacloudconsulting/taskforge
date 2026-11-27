import pytest

import click


def _summary(group):
    return [(e.action, e.name, e.total) for e in group.registration_history]


def test_limit_of_ten_rejects_the_eleventh_command():
    cli = click.Group("cli", max_commands=10)

    for index in range(10):
        cli.add_command(click.Command(f"cmd{index}"))

    extra = click.Command("extra")

    with pytest.raises(click.CommandLimitError) as excinfo:
        cli.add_command(extra)

    assert isinstance(excinfo.value, RuntimeError)
    assert excinfo.value.command_name == "extra"
    assert excinfo.value.limit == 10
    assert str(excinfo.value) == (
        "Cannot add command 'extra': the limit of 10 commands has been reached."
    )
    assert cli.max_commands == 10
    assert len(cli.commands) == 10
    assert "extra" not in cli.commands

    action, name, command, total = cli.registration_history[-1]
    assert (action, name, total) == ("rejected", "extra", 10)
    assert command is extra
    assert len(cli.registration_history) == 11


def test_replacing_is_allowed_when_full():
    cli = click.Group("cli", max_commands=1)
    first = click.Command("first")
    second = click.Command("second")
    cli.add_command(first)

    with pytest.raises(click.CommandLimitError):
        cli.add_command(second)

    with pytest.raises(click.CommandLimitError):
        cli.add_command(second)

    cli.add_command(second, name="first")
    cli.add_command(second, name="first")

    assert cli.commands == {"first": second}
    assert _summary(cli) == [
        ("added", "first", 1),
        ("rejected", "second", 1),
        ("rejected", "second", 1),
        ("replaced", "first", 1),
        ("replaced", "first", 1),
    ]
    assert isinstance(cli.registration_history[0], click.RegistrationEvent)
    assert cli.registration_history[0].command is first
    assert cli.registration_history[-1].command is second


def test_aliases_count_as_separate_names():
    cli = click.Group("cli", max_commands=1)
    cmd = click.Command("run")
    cli.add_command(cmd)

    with pytest.raises(click.CommandLimitError) as excinfo:
        cli.add_command(cmd, name="alias")

    assert excinfo.value.command_name == "alias"
    assert _summary(cli) == [("added", "run", 1), ("rejected", "alias", 1)]


def test_decorators_respect_the_limit():
    cli = click.Group("cli", max_commands=1)

    @cli.command()
    def first():
        click.echo("first")

    def second():
        pass

    def nested():
        pass

    with pytest.raises(click.CommandLimitError):
        cli.command()(second)

    with pytest.raises(click.CommandLimitError):
        cli.group()(nested)

    assert list(cli.commands) == ["first"]
    assert _summary(cli) == [
        ("added", "first", 1),
        ("rejected", "second", 1),
        ("rejected", "nested", 1),
    ]


def test_zero_limit_rejects_everything():
    cli = click.Group("cli", max_commands=0)

    with pytest.raises(click.CommandLimitError):
        cli.add_command(click.Command("a"))

    assert cli.commands == {}
    assert _summary(cli) == [("rejected", "a", 0)]


def test_negative_limit_is_invalid():
    with pytest.raises(ValueError):
        click.Group("cli", max_commands=-1)


def test_constructor_commands_count_but_are_not_recorded():
    commands = [click.Command("a"), click.Command("b")]
    cli = click.Group("cli", commands=commands, max_commands=2)

    assert cli.registration_history == ()

    with pytest.raises(click.CommandLimitError):
        cli.add_command(click.Command("c"))

    assert _summary(cli) == [("rejected", "c", 2)]


def test_constructor_over_the_limit():
    commands = [click.Command(name) for name in ("z", "y", "x", "w")]

    with pytest.raises(click.CommandLimitError) as excinfo:
        click.Group("cli", commands=commands, max_commands=2)

    assert excinfo.value.command_name == "x"
    assert excinfo.value.limit == 2


def test_removing_a_command_frees_a_slot():
    cli = click.Group("cli", max_commands=1)
    cli.add_command(click.Command("a"))
    del cli.commands["a"]
    cli.add_command(click.Command("b"))

    assert list(cli.commands) == ["b"]
    assert _summary(cli) == [("added", "a", 1), ("added", "b", 1)]


def test_history_without_limit_and_snapshot():
    cli = click.Group("cli")
    cli.add_command(click.Command("a"))
    snapshot = cli.registration_history

    for index in range(11):
        cli.add_command(click.Command(f"cmd{index}"))

    assert cli.max_commands is None
    assert isinstance(snapshot, tuple)
    assert len(snapshot) == 1
    assert len(cli.registration_history) == 12
    assert cli.registration_history[-1].total == 12


def test_other_failures_are_not_recorded():
    cli = click.Group("cli", chain=True, max_commands=0)

    with pytest.raises(TypeError):
        cli.add_command(click.Command(None))

    with pytest.raises(RuntimeError) as excinfo:
        cli.add_command(click.Group("sub"))

    assert not isinstance(excinfo.value, click.CommandLimitError)
    assert cli.registration_history == ()


def test_limit_and_history_are_per_group():
    parent = click.Group("parent", max_commands=1)
    child = click.Group("child")
    parent.add_command(child)
    child.add_command(click.Command("a"))
    child.add_command(click.Command("b"))

    assert child.max_commands is None
    assert _summary(parent) == [("added", "child", 1)]
    assert _summary(child) == [("added", "a", 1), ("added", "b", 2)]
