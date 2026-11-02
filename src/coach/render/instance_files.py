"""The files `init` writes and `upgrade` regenerates (docs/spec/instance.md)."""

import json
import re
from collections.abc import Iterable

from coach.core.config import (
    Config,
    GridImplement,
    GridLocation,
    ImplementChoice,
    IncrementImplement,
    Location,
    PlatePoolLocation,
)
from coach.core.hevy_api import HEVY_HOST, WORKOUTS_PATH
from coach.render.toml import TomlValue, dumps

PIN_LINE = re.compile(r"\s*version\s*=")

GITIGNORE = ".coach/\n.env\n.claude/settings.local.json\n"

LOCATIONS_HEADING = (
    "\n## Locations: the kit skill writes them. One example of each kind, loads in the\n"
    "## athlete's units.\n"
)

EXAMPLE_LOCATIONS: tuple[Location, ...] = (
    PlatePoolLocation(
        "home",
        kit="home",
        implements={"barbell": "barbell", "dumbbell": "dumbbell"},
        implement={
            "barbell": ImplementChoice(hardware="collar-clamp"),
            "dumbbell": ImplementChoice(hardware="screw-standard"),
        },
    ),
    GridLocation(
        "gym",
        implements={"barbell": "bar", "machine": "stack", "cable": "stack"},
        implement={
            "bar": IncrementImplement(2.5, base=20, max=180),
            "stack": IncrementImplement(5),
        },
    ),
)


def coach_toml(config: Config) -> str:
    document: dict[str, TomlValue] = {
        "engine": {"version": config.engine.version},
        "athlete": {
            "units": config.athlete.units,
            "bodyweight_units": config.athlete.bodyweight_units,
            "week_starts": config.athlete.week_starts,
            "timezone": config.athlete.timezone,
            "available_days": list(config.athlete.available_days),
            "session_minutes": config.athlete.session_minutes,
            "checkin_cadence_days": config.athlete.checkin_cadence_days,
        },
    }
    if config.hevy is not None:
        document["hevy"] = {}
    if config.locations:
        document["location"] = _locations(config.locations)
    example = dumps({"location": _locations(EXAMPLE_LOCATIONS)})
    commented = "\n".join(f"# {line}" if line else "#" for line in example.splitlines())
    return dumps(document) + LOCATIONS_HEADING + commented + "\n"


def claude_md(engine_version: str) -> str:
    return f"""# Strength coach instance

This directory is one athlete's coach instance, run by coach engine {engine_version}. It holds
data only; the engine, its skills and its hooks come from the installed package and plugin.

- `coach status` opens a session: where things stand and what needs attention.
- `coach --help` lists the verbs; `coach schema <verb>` gives one verb's arguments and output.
- A list stops at 10 rows and a result at the size budget, and each says when it was cut:
  `--last <n>` keeps n rows, `--full` keeps everything.
- The athlete's own account of themselves is the profile, `profile.md`.
- A verb that takes a document reads a Draft the agent writes first, at
  `.coach/drafts/<date>-<kind>.toml`.
- The athlete says yes before any verb records anything.
- A question outside the skills is read-only: answer it from the profile, `coach status`,
  `coach progress` and `coach query`, and record nothing.
- Order, numbers, thresholds and exit codes live in the engine: each verb's result, warnings
  and `error.code` say them, and `coach schema` gives every argument and file shape.

This file and `.claude/settings.json` are generated; `coach upgrade` rewrites both.
"""


def settings_json(asked_verbs: Iterable[str]) -> str:
    """Permission rules: allow coach, ask on the Writing verbs, deny Hevy workouts (ADR 0007)."""
    settings = {
        "permissions": {
            "allow": ["Bash(coach:*)"],
            "ask": [f"Bash(coach {verb}:*)" for verb in sorted(asked_verbs)],
            "deny": [
                f"Bash(*{HEVY_HOST}{WORKOUTS_PATH}*)",
                f"WebFetch(domain:{HEVY_HOST})",
            ],
        }
    }
    return json.dumps(settings, indent=2) + "\n"


def _locations(locations: Iterable[Location]) -> dict[str, TomlValue]:
    return {location.name: _location(location) for location in locations}


def _location(location: Location) -> dict[str, TomlValue]:
    if isinstance(location, PlatePoolLocation):
        return {
            "kind": "plate-pool",
            "kit": location.kit,
            "implements": dict(location.implements),
            "implement": {name: _choice(choice) for name, choice in location.implement.items()},
        }
    return {
        "kind": "grid",
        "implements": dict(location.implements),
        "implement": {name: _implement(rule) for name, rule in location.implement.items()},
    }


def _choice(choice: ImplementChoice) -> dict[str, TomlValue]:
    table: dict[str, TomlValue] = {}
    if choice.hardware is not None:
        table["hardware"] = choice.hardware
    if choice.single:
        table["single"] = True
    return table


def _implement(rule: GridImplement) -> dict[str, TomlValue]:
    if isinstance(rule, IncrementImplement):
        table: dict[str, TomlValue] = {"increment": rule.increment}
        if rule.base:
            table["base"] = rule.base
        if rule.max is not None:
            table["max"] = rule.max
        return table
    return {"rack": list(rule.rack)}


def with_pin(coach_toml_text: str, version: str) -> str:
    """`coach_toml_text` with `[engine] version` moved to `version`; every other byte kept."""
    lines = coach_toml_text.splitlines(keepends=True)
    table = None
    for number, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            table = stripped.split("#", 1)[0].strip()
        elif table == "[engine]" and PIN_LINE.match(line):
            ending = "\n" if line.endswith("\n") else ""
            lines[number] = f"version = {json.dumps(version)}{ending}"
            return "".join(lines)
    raise ValueError("coach.toml has no [engine] version line")
