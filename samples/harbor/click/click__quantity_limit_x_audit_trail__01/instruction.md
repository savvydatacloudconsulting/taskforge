## Background

Applications that let plugins register subcommands on a `click.Group` have no way to stop the group from growing without bound, and no way to find out afterwards which registrations happened, which ones overwrote an existing command, and which ones were refused. Add an optional cap on the number of subcommands a group accepts, together with an ordered history of registration attempts.

## Requirements

1. `click.Group` accepts a new keyword argument `max_commands` (default `None`, meaning no limit) and stores it as `group.max_commands`. A negative value raises `ValueError`. `0` is valid.
2. The limit applies to each group separately and counts the names in `group.commands` at the time of the call. The same command object registered under two names counts twice. Commands passed to the constructor count toward the limit. Removing an entry from `group.commands` frees its slot.
3. If the constructor receives more than `max_commands` commands, it raises `click.CommandLimitError`. Its `command_name` is the name of the first command, in the order given, that does not fit.
4. `Group.add_command` (and therefore the `group.command()` and `group.group()` decorators) raises `click.CommandLimitError` when the name is not yet registered and the group already holds `max_commands` or more names. `group.commands` is left unchanged.
5. Registering under a name that is already registered replaces that command and is always allowed, even when the group is full.
6. `group.registration_history` is a tuple of `click.RegistrationEvent` entries, oldest first. Each call to `add_command` that reaches the registry appends exactly one entry:
   - `"added"` when a new name was registered,
   - `"replaced"` when an existing name was registered again (also when it is the same command object),
   - `"rejected"` when the call was refused because of the limit. Every refused attempt is recorded, including repeated ones.
7. Each entry holds the `action`, the `name` used for the registration, the `command` object that was passed in, and `total`, the number of names in `group.commands` after the attempt (a rejected attempt does not change it).
8. The history is recorded for every group, with or without a limit. Commands passed to the constructor create no entries.
9. Calls that fail for another reason record nothing: a command without a name (`TypeError`), or adding a group to a group in chain mode (the existing `RuntimeError`, which takes precedence over the limit).
10. A tuple previously read from `registration_history` does not change when later registrations happen.

## Public interface

- `click.Group(..., max_commands: int | None = None)`
- `Group.max_commands: int | None`
- `Group.registration_history` — read-only property returning `tuple[RegistrationEvent, ...]`.
- `click.RegistrationEvent` — a named tuple with the fields, in this order: `action: str`, `name: str`, `command: click.Command`, `total: int`.
- `click.CommandLimitError(command_name: str, limit: int)` — a subclass of `RuntimeError` with the attributes `command_name` and `limit`. `str(error)` is exactly `Cannot add command 'NAME': the limit of LIMIT commands has been reached.`, where `'NAME'` is the `repr` of the command name.

## Examples

```python
cli = click.Group("cli", max_commands=1)
first = click.Command("first")
second = click.Command("second")

cli.add_command(first)

try:
    cli.add_command(second)
except click.CommandLimitError as e:
    print(e)  # Cannot add command 'second': the limit of 1 commands has been reached.

cli.add_command(second, name="first")  # replacing is allowed

[(e.action, e.name, e.total) for e in cli.registration_history]
# [("added", "first", 1), ("rejected", "second", 1), ("replaced", "first", 1)]
```
