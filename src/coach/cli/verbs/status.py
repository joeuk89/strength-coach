import datetime
from contextlib import closing

from coach.cli.declaration import Call, Declaration, Example, Json, Outcome
from coach.cli.instance import open_instance_store
from coach.cli.kit import read_kit_files
from coach.services.status import CurrentGoal, status
from coach.store.export import on_disk
from coach.store.phases import OpenPhase


def run(call: Call) -> Outcome:
    assert call.instance is not None and call.clock is not None
    with closing(open_instance_store(call.instance)) as conn:
        result = status(
            conn,
            call.clock,
            engine_version=call.engine_version,
            pin=call.instance.pin,
            hevy_on=call.instance.config.hevy is not None,
            kits=read_kit_files(call.instance),
            exported=on_disk(call.instance.export_path),
        )
    return Outcome(
        {
            "engine": {"version": result.engine_version, "pin": result.pin},
            "hevy": {
                "on": result.hevy_on,
                "last_import": result.last_import,
                "last_import_age_days": result.last_import_age_days,
            },
            "workouts": result.workouts,
            "schema_version": result.schema_version,
            "kit": [
                {"location": kit.location, "kit": kit.kit, "tables": kit.tables}
                for kit in result.kit
            ],
            "export": {
                "behind_store": result.export.behind_store,
                "store_behind_export": result.export.store_behind_export,
            },
            "program": (
                None
                if result.program is None
                else {
                    "version": result.program.version,
                    "kind": result.program.kind,
                    "emphasis": result.program.emphasis,
                    "adopted": result.program.adopted,
                }
            ),
            "goal": _goal(result.goal),
            "phase": _phase(result.phase),
        },
        warnings=result.warnings,
    )


def _goal(goal: CurrentGoal | None) -> Json | None:
    if goal is None:
        return None
    return {"id": goal.id, "kind": goal.kind, "priority_lifts": list(goal.priority_lifts)}


def _phase(phase: OpenPhase | None) -> Json | None:
    if phase is None:
        return None
    value = phase.until.value
    shown = value.isoformat() if isinstance(value, datetime.date) else value
    return {"id": phase.id, "kind": phase.kind, "until": {"kind": phase.until.kind, "value": shown}}


DECLARATION = Declaration(
    name="status",
    summary=(
        "Where the instance stands: the engine version against its pin, Hevy on or off and "
        "the age of the last import, workouts stored by source, the schema version, each "
        "plate-pool location's kit tables current or stale, whether the export is behind "
        "the store or the store behind it, the program version in force, the current Goal and "
        "the open Phase."
    ),
    writes="none",
    needs_instance=True,
    output={
        "type": "object",
        "properties": {
            "engine": {
                "type": "object",
                "properties": {"version": {"type": "string"}, "pin": {"type": "string"}},
                "required": ["version", "pin"],
            },
            "hevy": {
                "type": "object",
                "properties": {
                    "on": {"type": "boolean"},
                    "last_import": {"type": ["string", "null"]},
                    "last_import_age_days": {"type": ["integer", "null"]},
                },
                "required": ["on", "last_import", "last_import_age_days"],
            },
            "workouts": {
                "type": "object",
                "properties": {"hevy": {"type": "integer"}, "manual": {"type": "integer"}},
                "required": ["hevy", "manual"],
            },
            "schema_version": {"type": "integer"},
            "kit": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "kit": {"type": "string"},
                        "tables": {"enum": ["current", "stale"]},
                    },
                    "required": ["location", "kit", "tables"],
                },
            },
            "export": {
                "type": "object",
                "properties": {
                    "behind_store": {"type": "boolean"},
                    "store_behind_export": {"type": "boolean"},
                },
                "required": ["behind_store", "store_behind_export"],
            },
            "program": {
                "description": "the Program version in force, or null before the first",
                "type": ["object", "null"],
                "properties": {
                    "version": {"type": "string"},
                    "kind": {"type": "string"},
                    "emphasis": {"type": "string"},
                    "adopted": {"type": "string"},
                },
            },
            "goal": {
                "type": ["object", "null"],
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string"},
                    "priority_lifts": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "kind", "priority_lifts"],
            },
            "phase": {
                "type": ["object", "null"],
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string"},
                    "until": {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string"},
                            "value": {
                                "type": ["string", "number", "null"],
                                "description": "a date, a bodyweight, or null for coachs_call",
                            },
                        },
                        "required": ["kind", "value"],
                    },
                },
                "required": ["id", "kind", "until"],
            },
        },
        "required": [
            "engine",
            "hevy",
            "workouts",
            "schema_version",
            "kit",
            "export",
            "program",
            "goal",
            "phase",
        ],
    },
    run=run,
    examples=(Example(("status",), "Where the instance stands."),),
)
