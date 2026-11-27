## Background
When a single-value option or a flag is given several times on the command line, Click silently keeps the last occurrence. For some options (a target environment, `--force/--no-force`, a set of feature switches) a contradicting repeat is almost certainly a mistake, while an identical repeat (for example from a shell alias that already adds the option) is harmless. Options need an opt-in setting that merges identical repeats and rejects conflicting ones.

## Requirements
1. `click.Option` (and therefore `@click.option`) accepts a keyword argument `consistent`, default `False`. It is stored as the attribute `Option.consistent`. When no involved option is consistent, behaviour is unchanged: the last occurrence wins.
2. Only options that store one value are eligible. Creating an option with `consistent=True` together with `multiple=True` or `count=True` raises `TypeError`.
3. For a consistent option that takes a value, repeated command-line occurrences with identical values are merged: the command receives that value as if it had been given once. This holds for any mix of the option's spellings (`-m fast`, `-mfast`, `--mode fast`, `--mode=fast`).
4. Values are compared as the strings typed on the command line, before type conversion. With `type=int`, `--level 1 --level 01` is a conflict. With `nargs` greater than 1, the whole group of strings of one occurrence must equal that of the other.
5. For flags, what is compared is the value the occurrence stores, not its spelling. Repeating the same flag, or mixing its aliases, is merged. Giving both sides of a boolean pair such as `--color/--no-color` is a conflict, in either order.
6. A conflict is a usage error (`click.BadOptionUsage`, exit code 2). It is raised while the command line is parsed, so neither parameter callbacks nor the command callback run.
7. Several options may share one parameter name (feature switches). They share one stored value. A later occurrence that would change that value is rejected if the later option, or any option that appeared earlier on the command line for the same name, is consistent. So marking only one switch of a pair is enough to reject the pair in either order.
8. Only command-line occurrences are compared. A value from an environment variable or a default never conflicts with the command line, which takes precedence as before.

## Public interface
- `click.Option(..., consistent: bool = False)`, also usable as `@click.option(..., consistent=True)`.
- Invalid combination: `TypeError` with the message `'consistent' is not valid with 'multiple' or 'count'.`
- Conflict: `click.BadOptionUsage` with the message `Option '<name>' was given conflicting values.`, where `<name>` is the first declared name of the option whose occurrence caused the conflict. For `--color/--no-color` this is `--color` whichever side comes last.

## Examples
```python
@click.command()
@click.option("-m", "--mode", consistent=True)
def cli(mode):
    click.echo(mode)
```

- `cli -m fast --mode=fast` prints `fast`.
- `cli --mode fast --mode slow` exits with code 2 and reports `Option '-m' was given conflicting values.`

```python
@click.command()
@click.option("--upper", "transform", flag_value="upper", consistent=True)
@click.option("--lower", "transform", flag_value="lower")
def cli(transform):
    click.echo(transform)
```

- `cli --upper --upper` prints `upper`.
- `cli --upper --lower` reports `Option '--lower' was given conflicting values.`
- `cli --lower --upper` reports `Option '--upper' was given conflicting values.`
