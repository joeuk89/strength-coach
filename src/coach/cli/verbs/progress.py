from contextlib import closing

from coach.cli.declaration import Declaration, Example, InInstance, InstanceCall, Json, Outcome
from coach.cli.instance import open_instance_store
from coach.core.progress import (
    AdherenceRead,
    BestSet,
    DoseWeek,
    GoalRead,
    LiftProgress,
    LineHistory,
    MilestoneRead,
    PhaseRead,
)
from coach.services.progress import progress


def run(call: InstanceCall) -> Outcome:
    athlete = call.instance.config.athlete
    with closing(open_instance_store(call.instance)) as conn:
        found = progress(
            conn,
            on=call.clock.today(),
            units=athlete.units,
            bodyweight_units=athlete.bodyweight_units,
            full=call.full,
        )
    block = found.block
    result: Json = {
        "block": None
        if block is None
        else {"id": block.id, "start": block.start.isoformat(), "end": block.end.isoformat()},
        "priority_lifts": [_lift(lift) for lift in found.lifts],
        "milestones": [_milestone(m) for m in found.milestones],
        "dose": {"target": dict(found.dose_target), "weeks": [_week(w) for w in found.dose]},
        "adherence": _adherence(found.adherence),
        "phase": _phase(found.phase),
        "goal": _goal(found.goal),
    }
    if call.full:
        result["history"] = [_history(h) for h in found.history]
    return Outcome(result, warnings=found.signals)


def _lift(lift: LiftProgress) -> Json:
    return {
        "exercise": lift.exercise_id,
        "scheme": lift.scheme,
        "e1rm_now": lift.e1rm_now,
        "e1rm_by_block": [{"block": b, "e1rm": e} for b, e in lift.e1rm_by_block],
        "change_over_block": lift.change_over_block,
        "change_over_three": lift.change_over_three,
        "best": _best(lift.best),
        "stall_streak": lift.stall_streak,
        "resets": lift.resets,
        "signal": lift.signal,
    }


def _best(best: BestSet | None) -> Json | None:
    if best is None:
        return None
    return {"date": best.date.isoformat(), "load": best.load, "reps": best.reps}


def _milestone(read: MilestoneRead) -> Json:
    return {
        "exercise": read.milestone.exercise,
        "target": read.milestone.target.describe(),
        "reached": None if read.reached is None else read.reached.isoformat(),
        "to_go": read.to_go if read.computable else "not computable",
    }


def _week(week: DoseWeek) -> Json:
    return {
        "week": week.monday.isoformat(),
        "kind": week.kind,
        "muscles": dict(week.muscles),
        "lifts": dict(week.lifts),
    }


def _adherence(read: AdherenceRead | None) -> Json | None:
    if read is None:
        return None
    return {
        "core": {"planned": read.core_planned, "trained": read.core_trained},
        "optional_trained": read.optional_trained,
        "misses_by_tag": dict(read.misses),
    }


def _phase(read: PhaseRead | None) -> Json | None:
    if read is None:
        return None
    return {
        "kind": read.kind,
        "target_rate": read.target_rate,
        "observed_rate": read.observed_rate,
        "until": dict(read.until),
        "met": read.met,
    }


def _goal(read: GoalRead | None) -> Json | None:
    if read is None:
        return None
    return {"kind": read.kind, "adopted": read.adopted, "why": read.why}


def _history(line: LineHistory) -> Json:
    return {
        "exercise": line.exercise_id,
        "session": line.session_id,
        "exposures": [
            {"date": day.isoformat(), "sets": [[load, reps] for load, reps in sets]}
            for day, sets in line.exposures
        ],
    }


NULLABLE_NUMBER: Json = {"type": ["number", "null"]}

DECLARATION = Declaration(
    name="progress",
    summary=(
        "The block-boundary report: per priority lift the e1RM now and at the end of each of "
        "the last three closed Blocks, its change over the closed Block and over those three, "
        "the best set, the stall streak and resets under the current scheme and any cadence "
        "signal; each milestone's reached date or what is to go; hard sets by muscle and "
        "priority lift for each week of the closed Block against target; core adherence and "
        "misses by tag; the Phase and its 14-day bodyweight trend; the Goal with its `why` "
        "verbatim. --full adds each line's history since the closed Block opened. Open cadence "
        "signals come in warnings[], each carrying the moves a version may make."
    ),
    writes="none",
    output={
        "type": "object",
        "properties": {
            "block": {
                "description": "the newest closed Block, or null before one closes",
                "type": ["object", "null"],
                "properties": {
                    "id": {"type": "string"},
                    "start": {"type": "string", "format": "date"},
                    "end": {"type": "string", "format": "date"},
                },
            },
            "priority_lifts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "exercise": {"type": "string"},
                        "scheme": {"type": ["string", "null"]},
                        "e1rm_now": NULLABLE_NUMBER,
                        "e1rm_by_block": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "block": {"type": "string"},
                                    "e1rm": NULLABLE_NUMBER,
                                },
                            },
                        },
                        "change_over_block": NULLABLE_NUMBER,
                        "change_over_three": NULLABLE_NUMBER,
                        "best": {"type": ["object", "null"]},
                        "stall_streak": {"type": "integer"},
                        "resets": {"type": "integer"},
                        "signal": {"enum": ["cadence_slow", "cadence_fast", None]},
                    },
                },
            },
            "milestones": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "exercise": {"type": "string"},
                        "target": {"type": "object"},
                        "reached": {"type": ["string", "null"], "format": "date"},
                        "to_go": {
                            "description": "load, reps or multiple to go; null once reached",
                            "type": ["object", "string", "null"],
                        },
                    },
                },
            },
            "dose": {
                "type": "object",
                "properties": {
                    "target": {"type": "object"},
                    "weeks": {"type": "array", "items": {"type": "object"}},
                },
            },
            "adherence": {"type": ["object", "null"]},
            "phase": {"type": ["object", "null"]},
            "goal": {
                "type": ["object", "null"],
                "properties": {
                    "kind": {"type": "string"},
                    "adopted": {"type": "string", "format": "date"},
                    "why": {"type": "string"},
                },
            },
            "history": {
                "description": "with --full only: each line's exposures since the Block opened",
                "type": "array",
                "items": {"type": "object"},
            },
        },
        "required": [
            "block",
            "priority_lifts",
            "milestones",
            "dose",
            "adherence",
            "phase",
            "goal",
        ],
    },
    run=InInstance(run),
    examples=(
        Example(("progress",), "Where the athlete stands against the Goal."),
        Example(("progress", "--full"), "The same with each line's history."),
    ),
)
