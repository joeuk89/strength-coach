from collections.abc import Sequence
from dataclasses import dataclass

from coach.cli.declaration import Argument, ArgValue, Declaration
from coach.core.errors import Invalid

DEFAULT_LAST = 10

GLOBAL_OPTIONS = (
    Argument("--fields", "comma list of dotted paths into result; excludes --full"),
    Argument("--full", "the whole record instead of the compact summary", takes_value=False),
    Argument("--last", f"how many of the newest rows a list keeps (default {DEFAULT_LAST})"),
    Argument("--help", "describe the verb instead of running it", takes_value=False),
)


@dataclass(frozen=True)
class Options:
    args: dict[str, ArgValue]
    fields: tuple[str, ...] | None
    full: bool
    last: int
    help: bool


def find_leaf(
    argv: Sequence[str], declarations: Sequence[Declaration]
) -> tuple[Declaration | None, list[str]]:
    """The leaf whose words start argv, longest name first, and the tokens after it."""
    for declaration in sorted(declarations, key=lambda d: -len(d.name.split())):
        words = declaration.name.split()
        if list(argv[: len(words)]) == words:
            return declaration, list(argv[len(words) :])
    if not argv or argv[0] == "--help":
        return None, list(argv[1:])
    raise Invalid("invalid_argument", f"unknown verb {argv[0]!r}; run `coach --help`")


def parse_options(declaration: Declaration | None, tokens: Sequence[str]) -> Options:
    declared = declaration.arguments if declaration else ()
    options = {a.name: a for a in (*declared, *GLOBAL_OPTIONS) if not a.positional}
    positionals = [a for a in declared if a.positional]
    values: dict[str, ArgValue] = {}
    queue = list(tokens)
    while queue:
        token = queue.pop(0)
        if token.startswith("--"):
            name, has_inline, inline = token.partition("=")
            argument = options.get(name)
            if argument is None:
                raise Invalid("invalid_argument", f"unknown option {name}")
            if not argument.takes_value:
                if has_inline:
                    raise Invalid("invalid_argument", f"{name} takes no value")
                values[argument.key] = True
            elif has_inline or queue:
                _set(values, argument, inline if has_inline else queue.pop(0))
            else:
                raise Invalid("invalid_argument", f"{name} needs a value")
        elif positionals:
            values[positionals.pop(0).key] = token
        else:
            raise Invalid("invalid_argument", f"unexpected argument {token!r}")
    return _split_globals(declared, values)


def _set(values: dict[str, ArgValue], argument: Argument, value: str) -> None:
    if argument.repeatable:
        earlier = values.get(argument.key, ())
        assert isinstance(earlier, tuple)
        values[argument.key] = (*earlier, value)
    else:
        values[argument.key] = value


def _split_globals(declared: Sequence[Argument], values: dict[str, ArgValue]) -> Options:
    help_ = values.pop("help", False) is True
    full = values.pop("full", False) is True
    fields = _fields(values.pop("fields", None))
    last = _last(values.pop("last", None))
    if fields is not None and full:
        raise Invalid("invalid_argument", "--fields and --full exclude each other")
    if not help_:
        missing = [a.name for a in declared if a.required and a.key not in values]
        if missing:
            raise Invalid("invalid_argument", f"missing {', '.join(missing)}")
    return Options(args=values, fields=fields, full=full, last=last, help=help_)


def _fields(raw: ArgValue | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    paths = tuple(p.strip() for p in str(raw).split(","))
    if not all(paths):
        raise Invalid("invalid_argument", f"--fields {raw!r} has an empty path")
    return paths


def _last(raw: ArgValue | None) -> int:
    if raw is None:
        return DEFAULT_LAST
    if isinstance(raw, str) and raw.isdigit() and int(raw) > 0:
        return int(raw)
    raise Invalid("invalid_argument", f"--last takes a positive whole number, not {raw!r}")
