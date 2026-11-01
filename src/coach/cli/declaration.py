from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from coach.cli.terminal import Terminal
from coach.core.clock import Clock
from coach.core.config import Config
from coach.core.message import Message
from coach.store.rebuild import Rebuilt

type Writes = Literal["none", "store", "hevy", "git"]
type Json = dict[str, object]


@dataclass(frozen=True)
class Argument:
    """A positional argument when `name` is a bare word, an option when it starts with `--`."""

    name: str
    help: str
    takes_value: bool = True
    required: bool = False

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
    def store_path(self) -> Path:
        return self.root / ".coach" / "coach.db"

    @property
    def export_path(self) -> Path:
        return self.root / "export"


@dataclass(frozen=True)
class Call:
    args: Mapping[str, str | bool]
    full: bool
    last: int
    engine_version: str
    instance: Instance | None
    env: Mapping[str, str]
    clock: Clock | None
    make_client: Callable[[], object] | None
    terminal: Terminal
    rebuilt: Rebuilt | None = None


@dataclass(frozen=True)
class Outcome:
    result: Json
    warnings: tuple[Message, ...] = ()


@dataclass(frozen=True)
class Declaration:
    name: str
    summary: str
    writes: Writes
    needs_instance: bool
    output: Json
    run: Callable[[Call], Outcome]
    arguments: tuple[Argument, ...] = ()
    examples: tuple[Example, ...] = ()

    def input_schema(self) -> Json:
        properties: Json = {
            argument.key: {
                "type": "string" if argument.takes_value else "boolean",
                "description": argument.help,
            }
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


def _usage_word(argument: Argument) -> str:
    if argument.positional:
        word = f"<{argument.name}>"
    elif argument.takes_value:
        word = f"{argument.name} <{argument.key}>"
    else:
        word = argument.name
    return word if argument.required else f"[{word}]"
