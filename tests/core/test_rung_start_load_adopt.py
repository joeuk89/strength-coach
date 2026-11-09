import datetime
from dataclasses import replace
from typing import Any

import pytest
from support.program_drafts import a_draft, a_ladder_line, a_rung, a_session, toml

from coach.core.exposure import Exposure, ExposureSet
from coach.core.flag import Flag
from coach.core.goal import Goal
from coach.core.load import Load
from coach.core.program.checks import AdoptContext, violations
from coach.core.program.parse import ParsedDraft, parse_program_draft
from coach.core.program.warnings import adopt_warnings
from coach.core.rack import ListedRack, RackRow

LIBRARY: dict[str, dict[str, object]] = {
    "negative_pull_up": {"load_mode": "bodyweight", "equipment_kind": "bodyweight"},
    "chin_up": {"load_mode": "bodyweight", "equipment_kind": "bodyweight"},
    "dead_hang": {"load_mode": "duration", "equipment_kind": "bodyweight"},
    "weighted_negative": {"load_mode": "total", "equipment_kind": "vest"},
    "db_negative": {"load_mode": "per_hand_x2", "equipment_kind": "dumbbell"},
    "assisted_negative": {"load_mode": "assisted", "equipment_kind": "machine"},
}
RACKS = {
    "vest": ListedRack(tuple(RackRow(load) for load in (5, 10, 15))),
    "dumbbell": ListedRack(tuple(RackRow(load) for load in (10, 20))),
}
CONTEXT = AdoptContext(
    version_id="pv-1",
    library=LIBRARY,
    racks={"home": RACKS},
    goal=Goal(kind="hypertrophy", because="first goal", priority_lifts=(), why=""),
)
REPS = [{"count": 3, "reps": 4, "rpe": 8}]


def a_ladder(*rungs: dict[str, Any], exercise: str = "negative_pull_up") -> dict[str, Any]:
    return a_ladder_line(exercise, a_rung(sets=REPS), *rungs)


def weighted(start_load: float | None = 5, exercise: str = "weighted_negative") -> dict[str, Any]:
    return a_rung(exercise, sets=REPS, start_load=start_load)


LOGGED_CONTEXT = replace(
    CONTEXT,
    last_exposures={
        "weighted_negative": Exposure(
            workout_id="w-1",
            exercise_id="weighted_negative",
            date=datetime.date(2026, 10, 1),
            sets=(ExposureSet(0, "working", Load(15, "total"), 4, 8),),
        )
    },
)


def parsed_form(*lines: dict[str, Any], location: str | None = None) -> ParsedDraft:
    draft = a_draft(a_session("pull", *lines, location=location))
    return parse_program_draft(toml(draft), file="d.toml")


def flags_of(
    *lines: dict[str, Any], context: AdoptContext = CONTEXT, location: str | None = None
) -> list[Flag]:
    parsed = parsed_form(*lines, location=location)
    return list(violations(parsed.form, context, parsed.unknown_keys))


def test_a_load_bearing_later_rung_with_a_start_load_adopts() -> None:
    assert flags_of(a_ladder(weighted())) == []


def test_a_load_bearing_later_rung_with_no_start_load_is_start_load_missing() -> None:
    [flag] = flags_of(a_ladder(weighted(None)))

    assert flag.key == "start_load_missing@line:pull/negative_pull_up"
    assert flag.params == {"exercise_id": "weighted_negative", "rung": 2}


def test_a_rungs_earlier_exposures_do_not_waive_its_start_load() -> None:
    [flag] = flags_of(a_ladder(weighted(None)), context=LOGGED_CONTEXT)

    assert flag.code == "start_load_missing"


def test_each_load_bearing_rung_with_no_start_load_raises_its_own_flag() -> None:
    flags = flags_of(a_ladder(weighted(None), weighted(None, "db_negative")))

    assert [f.params for f in flags] == [
        {"exercise_id": "weighted_negative", "rung": 2},
        {"exercise_id": "db_negative", "rung": 3},
    ]


def test_an_assisted_rung_is_load_bearing_and_off_any_rack() -> None:
    [flag] = flags_of(a_ladder(weighted(None, "assisted_negative")))
    assert flag.code == "start_load_missing"

    assert flags_of(a_ladder(weighted(47, "assisted_negative"))) == []


@pytest.mark.parametrize("exercise", ["chin_up", "dead_hang"])
def test_a_start_load_on_a_rung_that_bears_no_load_is_unknown_key(exercise: str) -> None:
    [flag] = flags_of(a_ladder(weighted(5, exercise)))

    assert flag.code == "unknown_key"
    assert flag.params == {
        "key_path": "session.pull.line.negative_pull_up.scheme.rungs.2.start_load"
    }


def test_a_start_load_on_the_first_rung_is_unknown_key() -> None:
    line = a_ladder_line(
        "weighted_negative",
        a_rung(sets=REPS, start_load=5),
        a_rung("chin_up", sets=REPS),
    )

    [flag] = flags_of({**line, "start_load": 5})

    assert flag.code == "unknown_key"
    assert flag.params == {
        "key_path": "session.pull.line.weighted_negative.scheme.rungs.1.start_load"
    }


def test_a_rung_start_load_off_the_rack_is_start_load_off_rack() -> None:
    [flag] = flags_of(a_ladder(weighted(7)))

    assert flag.key == "start_load_off_rack@line:pull/negative_pull_up"
    assert flag.params == {
        "rung": 2,
        "start_load": 7,
        "location": "home",
        "nearest_rows": [5, 10],
    }


def test_the_rack_is_read_in_the_rungs_exercise_and_the_sessions_location() -> None:
    gym = {"dumbbell": ListedRack((RackRow(30),))}
    context = replace(CONTEXT, racks={**CONTEXT.racks, "gym": gym})

    [flag] = flags_of(a_ladder(weighted(10, "db_negative")), context=context, location="gym")

    assert flag.code == "start_load_off_rack"
    assert flag.params["location"] == "gym"
    assert flag.params["nearest_rows"] == [30]


def test_a_rungs_kind_the_location_does_not_supply_is_equipment_unsupplied() -> None:
    context = replace(CONTEXT, racks={"home": {"dumbbell": RACKS["dumbbell"]}})

    [flag] = flags_of(a_ladder(weighted()), context=context)

    assert flag.code == "equipment_unsupplied"
    assert flag.params == {"equipment_kind": "vest", "location": "home"}


def test_a_later_rung_reads_its_own_exercises_mode_not_the_lines() -> None:
    line = a_ladder(a_rung("chin_up", sets=REPS), exercise="db_negative")

    assert flags_of({**line, "start_load": 10, "load_mode": "total"}) == []


def test_the_lines_own_start_load_rule_is_unchanged_on_a_ladder() -> None:
    line = a_ladder_line("db_negative", a_rung(sets=REPS), a_rung("chin_up", sets=REPS))

    [flag] = flags_of(line)

    assert flag.code == "start_load_missing"
    assert flag.params == {"exercise_id": "db_negative"}


def test_a_rung_start_load_beside_logged_history_warns_no_start_load_ignored() -> None:
    warnings = adopt_warnings(parsed_form(a_ladder(weighted())).form, LOGGED_CONTEXT)

    assert "start_load_ignored" not in [f.code for f in warnings]
