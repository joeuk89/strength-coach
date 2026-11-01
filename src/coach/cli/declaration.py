from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from coach.cli.terminal import Terminal
from coach.core.clock import Clock
from coach.core.config import Config, Units
from coach.core.flag import Flag
from coach.core.message import Message
from coach.hevy.protocol import HevyClient
from coach.store.rebuild import Rebuilt

type Writes = Literal["none", "store", "hevy", "git"]
type Json = dict[str, object]
type ArgValue = str | bool | tuple[str, ...]
type OverBudget = Callable[[Mapping[str, ArgValue]], bool]
# The real client's wiring: the API key, the Write audit path and the clock (ADR 0019).
type MakeClient = Callable[[str, Path, Clock], HevyClient]


@dataclass(frozen=True)
class Argument:
    """A positional argument when `name` is a bare word, an option when it starts with `--`."""

    name: str
    help: str
    takes_value: bool = True
    required: bool = False
    repeatable: bool = False

    @property
    def positional(self) -> bool:
        return not self.name.startswith("--")

    @property
    def key(self) -> str:
        return self.name.removeprefix("--").replace("-", "_")


@dataclass(frozen=True)
class Example:
    argv: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class Instance:
    root: Path
    config: Config

    @property
    def pin(self) -> str:
        return self.config.engine.version

    @property
    def units(self) -> Units:
        return self.config.athlete.units

    @property
    def bodyweight_units(self) -> Units:
        return self.config.athlete.bodyweight_units

    @property
    def checkin_cadence_days(self) -> int:
        return self.config.athlete.checkin_cadence_days

    @property
    def store_path(self) -> Path:
        return self.root / ".coach" / "coach.db"

    @property
    def export_path(self) -> Path:
        return self.root / "export"

    @property
    def audit_path(self) -> Path:
        return self.root / "hevy" / "writes.jsonl"


@dataclass(frozen=True)
class Call:
    args: Mapping[str, ArgValue]
    full: bool
    last: int
    engine_version: str
    env: Mapping[str, str]
    make_client: MakeClient
    terminal: Terminal


@dataclass(frozen=True)
class InstanceCall(Call):
    instance: Instance
    clock: Clock
    rebuilt: Rebuilt | None = None


@dataclass(frozen=True)
class Outcome:
    result: Json
    warnings: tuple[Message | Flag, ...] = ()


@dataclass(frozen=True)
class InInstance:
    """The run of a verb that needs an instance: the CLI finds and loads it before the call."""

    run: Callable[[InstanceCall], Outcome]


def never(args: Mapping[str, ArgValue]) -> bool:
    return False


def always(args: Mapping[str, ArgValue]) -> bool:
    return True


def on_dry_run(args: Mapping[str, ArgValue]) -> bool:
    return args.get("dry_run") is True


@dataclass(frozen=True)
class Declaration:
    name: str
    summary: str
    writes: Writes
    output: Json
    run: Callable[[Call], Outcome] | InInstance
    arguments: tuple[Argument, ...] = ()
    examples: tuple[Example, ...] = ()
    # The one verb that writes [engine]: it runs on an engine newer than the pin (ADR 0007).
    moves_pin: bool = False
    # Output the agent must act on in full may run over the 3 KB budget (verbs.md).
    over_budget: OverBudget = never

    def input_schema(self) -> Json:
        properties: Json = {
            argument.key: {**_input_type(argument), "description": argument.help}
            for argument in self.arguments
        }
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": properties,
            "required": [a.key for a in self.arguments if a.required],
            "additionalProperties": False,
        }

    def describe(self) -> Json:
        return {
            "name": self.name,
            "summary": self.summary,
            "writes": self.writes,
            "usage": self.usage(),
            "input": self.input_schema(),
            "output": self.output,
            "examples": [
                {"argv": ["coach", *example.argv], "description": example.description}
                for example in self.examples
            ],
        }

    def usage(self) -> str:
        return " ".join(["coach", self.name, *(_usage_word(a) for a in self.arguments)])


def _input_type(argument: Argument) -> Json:
    if argument.repeatable:
        return {"type": "array", "items": {"type": "string"}}
    return {"type": "string" if argument.takes_value else "boolean"}


def _usage_word(argument: Argument) -> str:
    if argument.positional:
        word = f"<{argument.name}>"
    elif argument.takes_value:
        word = f"{argument.name} <{argument.key}>"
    else:
        word = argument.name
    if argument.repeatable:
        word = f"{word} ..."
    return word if argument.required else f"[{word}]"
