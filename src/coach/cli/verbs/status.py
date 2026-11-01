import datetime
from contextlib import closing

from coach.cli.declaration import Call, Declaration, Example, Json, Outcome
from coach.cli.generated import drifted
from coach.cli.instance import open_instance_store
from coach.cli.kit import read_kit_files
from coach.core.check_in import CheckInDue
from coach.core.engine_pin import generated_file_drift
from coach.services.status import BlockStatus, CurrentGoal, PlanInForce, WeekPosition, status
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
            units=call.instance.config.athlete.units,
            bodyweight_units=call.instance.config.athlete.bodyweight_units,
            locations=call.instance.config.locations,
            cadence_days=call.instance.config.athlete.checkin_cadence_days,
        )
    pin = call.instance.pin
    drift = tuple(
        generated_file_drift(relative, pin) for relative in drifted(call.instance.root, pin)
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
            "store_schema_version": result.store_schema_version,
            "kit": [
                {"location": kit.location, "kit": kit.kit, "tables": kit.tables}
                for kit in result.kit
            ],
            "plan": _plan(result.plan),
            "rotation": _rotation(result.rotation),
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
            "block": _block(result.block),
            "check_in": _check_in(result.check_in),
            "niggles": _ids(result.niggles),
            "follow_ups_due": _ids(result.follow_ups_due),
            "decisions": {kind: _ids(ids) for kind, ids in result.decisions.items()},
            "observations": _ids(result.observations),
            "export": {
                "behind_store": result.export.behind_store,
                "store_behind_export": result.export.store_behind_export,
            },
        },
        warnings=(*result.warnings, *drift),
    )


def _check_in(due: CheckInDue) -> Json:
    window = due.window
    return {
        "due": due.due,
        "due_on": due.due_on.isoformat() if due.due_on else None,
        "tier": due.tier,
        "catch_up": due.catch_up,
        "window": (
            None
            if window is None
            else {"start": window.start.isoformat(), "end": window.end.isoformat()}
        ),
    }


def _ids(ids: tuple[str, ...]) -> Json:
    return {"count": len(ids), "ids": list(ids)}


def _plan(plan: PlanInForce | None) -> Json | None:
    if plan is None:
        return None
    return {
        "id": plan.id,
        "week": plan.week,
        "approved_at": plan.approved_at,
        "hash": plan.write_plan_hash,
        "routines": {
            "verified": plan.routines_verified,
            "unverified": list(plan.routines_unverified),
        },
    }


def _rotation(rotation: WeekPosition | None) -> Json | None:
    if rotation is None:
        return None
    return {
        "week": rotation.week.isoformat(),
        "position": rotation.position.week,
        "source": rotation.position.source,
    }


def _block(block: BlockStatus | None) -> Json | None:
    if block is None:
        return None
    return {
        "id": block.id,
        "hard_weeks": block.hard_weeks,
        "ceiling": block.ceiling,
        "light_week_pending": block.light_week_pending,
    }


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


STRING: Json = {"type": "string"}
DATE: Json = {"type": "string", "format": "date"}
INTEGER: Json = {"type": "integer"}
BOOLEAN: Json = {"type": "boolean"}
STRINGS: Json = {"type": "array", "items": STRING}
IDS: Json = {"$ref": "#/$defs/ids"}


def _object(nullable: bool = False, **properties: Json) -> Json:
    return {"type": ["object", "null"] if nullable else "object", "properties": properties}


def _nullable(kind: str) -> Json:
    return {"type": [kind, "null"]}


OUTPUT: Json = {
    "type": "object",
    "$defs": {"ids": _object(count=INTEGER, ids=STRINGS)},
    "properties": {
        "engine": _object(version=STRING, pin=STRING),
        "hevy": _object(
            on=BOOLEAN, last_import=_nullable("string"), last_import_age_days=_nullable("integer")
        ),
        "workouts": _object(hevy=INTEGER, manual=INTEGER),
        "store_schema_version": INTEGER,
        "kit": {
            "type": "array",
            "items": _object(location=STRING, kit=STRING, tables={"enum": ["current", "stale"]}),
        },
        "plan": _object(
            True,
            id=STRING,
            week=DATE,
            approved_at=STRING,
            hash=STRING,
            routines=_object(verified=INTEGER, unverified=STRINGS),
        ),
        "rotation": _object(
            True,
            week=DATE,
            position=STRING,
            source={"enum": ["plan_in_force", "previous_plan", "program_adopt"]},
        ),
        "program": _object(True, version=STRING, kind=STRING, emphasis=STRING, adopted=STRING),
        "goal": _object(True, id=STRING, kind=STRING, priority_lifts=STRINGS),
        "phase": _object(
            True,
            id=STRING,
            kind=STRING,
            until=_object(kind=STRING, value={"type": ["string", "number", "null"]}),
        ),
        "check_in": _object(
            due=BOOLEAN,
            due_on=_nullable("string"),
            tier={"enum": ["light", "deep"]},
            catch_up=BOOLEAN,
            window=_object(True, start=DATE, end=DATE),
        ),
        "niggles": IDS,
        "follow_ups_due": IDS,
        "decisions": {"type": "object", "additionalProperties": IDS},
        "observations": IDS,
        "export": _object(behind_store=BOOLEAN, store_behind_export=BOOLEAN),
    },
    "required": [
        "engine",
        "hevy",
        "workouts",
        "store_schema_version",
        "kit",
        "plan",
        "rotation",
        "program",
        "goal",
        "phase",
        "check_in",
        "niggles",
        "follow_ups_due",
        "decisions",
        "observations",
        "export",
    ],
}


DECLARATION = Declaration(
    name="status",
    summary=(
        "Where we stand: engine pin, Hevy, workouts, kit, the WeekPlan, rotation and program "
        "in force, Goal, Phase, Block, check-in, niggles, follow-ups, Decisions, "
        "Observations, export."
    ),
    writes="none",
    needs_instance=True,
    output=OUTPUT,
    run=run,
    examples=(Example(("status",), "Where the instance stands."),),
)
