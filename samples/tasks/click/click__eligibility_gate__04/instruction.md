## Background
`click.File` always treats the special value `-` as standard input or standard output, depending on the mode. Some commands cannot work with a standard stream, for example because they need to reopen the file by name or write next to it. These commands need a way to declare that only a real file path is eligible. `click.Path` has an `allow_dash` setting, but `click.File` has none.

## Requirements
1. `click.File` accepts a new keyword argument `allow_dash`, which defaults to `True`, and stores it in an attribute of the same name.
2. With `allow_dash=True` (or omitted), behaviour is unchanged: `-` refers to the standard stream matching the mode.
3. With `allow_dash=False`, converting the value `-` fails with `click.BadParameter` and the message given below. This applies to every mode (read, write, append, text and binary) and to every `lazy` setting.
4. The rejection covers every form of the value whose file system path is exactly `-`: the string `"-"`, the bytes `b"-"`, and a path-like object such as `pathlib.Path("-")`.
5. The rejection applies no matter where the value comes from, including the command line, a parameter default and an environment variable. The command callback does not run, and the command exits with the usual usage error exit code `2`.
6. A rejected value does not create or open any file.
7. With `allow_dash=False`, all other values behave as before. This includes ordinary paths, paths that merely contain a dash (such as the string `"./-"`, which names a file called `-`), and already open file objects, which are passed through unchanged.

## Public interface
- `click.File(mode="r", encoding=None, errors="strict", lazy=None, atomic=False, allow_dash=True)`
- Attribute `File.allow_dash: bool`
- Error type: `click.BadParameter`
- Error message (exact): `'-' is not allowed: a file path is required.`

## Examples
```python
@click.command()
@click.option("--config", type=click.File("r", allow_dash=False))
def cli(config):
    click.echo(config.read())
```

```
$ cli --config -
...
Error: Invalid value for '--config': '-' is not allowed: a file path is required.

$ cli --config settings.ini
(prints the file contents)
```
