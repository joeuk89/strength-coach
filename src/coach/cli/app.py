import os
import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import version
from pathlib import Path
from typing import TextIO

from coach.cli import envelope, registry
from coach.cli.argv import GLOBAL_OPTIONS, Options, find_leaf, parse_options
from coach.cli.declaration import Call, Declaration, Instance, Json
from coach.cli.instance import find_root, read_pin
from coach.core.clock import Clock
from coach.core.engine_pin import check_pin
from coach.core.errors import CoachError, Invalid, Refused, Setup, Unreachable
from coach.core.message import Message
from coach.store.connection import SCHEMA_VERSION

EXIT_CLASSES: tuple[tuple[type[CoachError], int], ...] = (
    (Invalid, 1),
    (Refused, 3),
    (Unreachable, 4),
    (Setup, 5),
)


def engine_version() -> str:
    return version("coach")


def main(
    argv: Sequence[str],
    env: Mapping[str, str],
    stdout: TextIO,
    stderr: TextIO,
    *,
    make_client: Callable[[], object] | None = None,
    clock: Clock | None = None,
) -> int:
    verb: str | None = None
    warnings: list[Message] = []
    try:
        declaration, tokens = find_leaf(argv, registry.declarations())
        verb = declaration.name if declaration else None
        options = parse_options(declaration, tokens)
        if declaration is None:
            result = _help()
        elif options.help:
            result = declaration.describe()
        else:
            instance = None
            if declaration.needs_instance:
                instance, pin_warning = _instance()
                if pin_warning:
                    warnings.append(pin_warning)
            call = Call(
                args=options.args,
                full=options.full,
                last=options.last,
                engine_version=engine_version(),
                instance=instance,
                env=env,
                clock=clock,
                make_client=make_client,
            )
            outcome = declaration.run(call)
            warnings.extend(outcome.warnings)
            result = _projected(outcome.result, options)
        _write(stdout, envelope.success(SCHEMA_VERSION, verb, result, warnings))
        return 0
    except CoachError as error:
        failed = Message(error.code, error.message)
        _write(stdout, envelope.failure(SCHEMA_VERSION, verb, failed, warnings))
        return next(code for kind, code in EXIT_CLASSES if isinstance(error, kind))
    except Exception as error:
        traceback.print_exc(file=stderr)
        failed = Message("internal_error", f"{type(error).__name__}: {error}")
        _write(stdout, envelope.failure(SCHEMA_VERSION, verb, failed, warnings))
        return 1


def run() -> int:
    return main(sys.argv[1:], os.environ, sys.stdout, sys.stderr)


def _instance() -> tuple[Instance, Message | None]:
    root = find_root(Path.cwd())
    pin = read_pin(root)
    pin_warning = check_pin(engine_version(), pin)
    return Instance(root=root, pin=pin), pin_warning


def _projected(result: Json, options: Options) -> Json:
    return envelope.project(result, options.fields) if options.fields else result


def _help() -> Json:
    return {
        "usage": "coach <verb> [arguments] [--fields a.b,c | --full] [--last <n>] [--help]",
        "verbs": [_leaf(d) for d in registry.declarations()],
        "options": [{"name": o.name, "help": o.help} for o in GLOBAL_OPTIONS],
    }


def _leaf(declaration: Declaration) -> Json:
    return {"name": declaration.name, "summary": declaration.summary, "writes": declaration.writes}


def _write(stdout: TextIO, document: Json) -> None:
    stdout.write(envelope.render(document, pretty=stdout.isatty()))
