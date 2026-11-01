from dataclasses import asdict, dataclass

from coach.cli.declaration import Call, Instance, Json, Outcome
from coach.cli.hevy_key import api_key
from coach.core.clock import Clock
from coach.core.flag import Flag
from coach.services.hevy_import import import_hevy
from coach.store.connection import Connection
from coach.store.rebuild import Rebuilt

_COUNT: Json = {"type": "integer"}
REBUILT_PROPERTIES: Json = {"schema_version": _COUNT}
PULL_PROPERTIES: Json = {
    "kind": {"enum": ["event", "full"]},
    "window": {
        "type": "object",
        "properties": {"since": {"type": ["string", "null"]}, "until": {"type": "string"}},
    },
    "workouts": {
        "type": "object",
        "properties": {k: _COUNT for k in ("new", "versioned", "gone", "back")},
    },
    "weigh_ins": _COUNT,
    "routines": _COUNT,
    "folders": _COUNT,
}
PULL_SCHEMA: Json = {
    "description": "the Hevy pull this verb ran first; absent with no [hevy] table",
    "type": "object",
    "properties": {
        **PULL_PROPERTIES,
        "rebuilt": {"type": "object", "properties": REBUILT_PROPERTIES},
    },
}


@dataclass(frozen=True)
class Pulled:
    summary: Json
    warnings: tuple[Flag, ...]


def with_pull(outcome: Outcome, pulled: Pulled | None) -> Outcome:
    if pulled is None:
        return outcome
    return Outcome(
        {**outcome.result, "pull": pulled.summary}, warnings=(*pulled.warnings, *outcome.warnings)
    )


def pull(
    call: Call,
    conn: Connection,
    instance: Instance,
    clock: Clock,
    *,
    full: bool = False,
    rebuilt: Rebuilt | None = None,
) -> Pulled | None:
    if instance.config.hevy is None:
        return None
    key = api_key(call.env, instance.root / ".env")
    client = call.make_client(key, instance.audit_path, clock)
    result = import_hevy(conn, client, clock, full=full, units=instance.units)
    summary: Json = {
        "kind": result.kind,
        "window": {"since": result.since, "until": result.at},
        "workouts": asdict(result.workouts),
        "weigh_ins": result.weigh_ins,
        "routines": result.routines,
        "folders": result.folders,
    }
    if rebuilt is not None:
        summary["rebuilt"] = rebuilt_json(rebuilt)
    return Pulled(summary, result.warnings)


def rebuilt_json(rebuilt: Rebuilt | None) -> Json | None:
    return None if rebuilt is None else {"schema_version": rebuilt.schema_version}
