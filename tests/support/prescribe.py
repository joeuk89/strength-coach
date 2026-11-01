"""Prescribe requests for core tests: one planned session at `home` against the kit fixture."""

import datetime
from collections.abc import Mapping
from typing import Any

from coach.core.config import RackImplement
from coach.core.exposure import Exposure
from coach.core.kit import parse_kit_tables
from coach.core.load import LoadMode
from coach.core.prescription import (
    ExerciseFacts,
    MatchedActivity,
    PlannedSession,
    PrescribeRequest,
    ProgramVersion,
)
from coach.core.program.form import (
    Deload,
    Dose,
    Line,
    ProgramForm,
    Schedule,
    SchemeRef,
    Session,
    SetGroup,
)
from coach.core.rack import Rack, grid_rack
from support.kit_fixtures import kit_tables

PLANNED = datetime.date(2026, 11, 2)
HOME_RACKS: Mapping[str, Rack] = parse_kit_tables(
    kit_tables(), collars="clamp", dumbbells="pair", units="lb"
).racks


def a_rack(*loads: float) -> Rack:
    return grid_rack(RackImplement(loads))


def working(count: int, reps: int | tuple[int, int], rpe: float | None = 8) -> SetGroup:
    return SetGroup(count, "working", reps, None, rpe)


def warm_up(reps: int) -> SetGroup:
    return SetGroup(1, "warm_up", reps)


def a_line(
    exercise: str = "bb_back_squat",
    *sets: SetGroup,
    scheme: str = "double_progression",
    start_load: float | None = None,
    load_mode: str | None = None,
    **params: Any,
) -> Line:
    return Line(
        exercise=exercise,
        sets=sets or (warm_up(5), warm_up(3), working(4, (6, 8))),
        rest_s=180,
        scheme=SchemeRef(scheme, params),
        load_mode=load_mode,
        start_load=start_load,
    )


EXERCISES = {
    "bb_back_squat": ExerciseFacts("total", "barbell", "squat"),
    "bb_bench_press": ExerciseFacts("total", "barbell", "horizontal_push"),
    "db_lunge": ExerciseFacts("per_hand_x2", "dumbbell", "lunge"),
    "pull_up": ExerciseFacts("bodyweight", "bodyweight", "vertical_pull"),
    "assisted_pull_up": ExerciseFacts("assisted", "machine", "vertical_pull"),
    "goblet_squat": ExerciseFacts("single_implement", "dumbbell", "squat"),
}
DELOAD = Deload(
    hard_weeks_ceiling=6, set_cut_pct=40, load_cut_pct=0, rpe_cap=8, test_priority_lifts=True
)


def a_request(
    *lines: Line,
    exposures: tuple[Exposure, ...] = (),
    racks: Mapping[str, Rack] | None = None,
    on: datetime.date = PLANNED,
    exercises: Mapping[str, ExerciseFacts] | None = None,
    dose: Dose | None = None,
    deload: Deload | None = DELOAD,
    **request: Any,
) -> PrescribeRequest:
    """`request` takes the other request fields: overrides, Decisions, niggle constraints,
    status spans and trained-unlogged dates."""
    lines = lines or (a_line(),)
    session = Session("lower", "Lower", "lifting", "core", lines=lines)
    form = ProgramForm(
        name="Test",
        kind="redesign",
        because="first program",
        emphasis="hypertrophy",
        location="home",
        schedule=Schedule(("A",), {"A": {"mon": "lower"}}),
        sessions=(session,),
        dose=dose,
        deload=deload,
    )
    return PrescribeRequest(
        version=ProgramVersion(form, {**EXERCISES, **(exercises or {})}),
        exposures=exposures,
        racks={"home": HOME_RACKS if racks is None else racks},
        planned=PlannedSession("lower", on, "home", "lifting", lines),
        **request,
    )


def facts(load_mode: LoadMode, equipment_kind: str = "barbell") -> ExerciseFacts:
    return ExerciseFacts(load_mode, equipment_kind, "squat")


def a_rotation_form(*extra: Session) -> ProgramForm:
    """Two rotation weeks: A plans `lower-a` on Monday and `push-a` (at the gym) on Thursday,
    B plans `pull-b` on Tuesday."""
    line = (a_line(),)
    return ProgramForm(
        name="Test",
        kind="redesign",
        because="first program",
        emphasis="hypertrophy",
        location="home",
        schedule=Schedule(
            ("A", "B"),
            {"A": {"mon": "lower-a", "thu": "push-a"}, "B": {"tue": "pull-b"}},
        ),
        sessions=(
            Session("lower-a", "Lower A", "lifting", "core", lines=line),
            Session("push-a", "Push A", "lifting", "core", location="gym", lines=line),
            Session("pull-b", "Pull B", "lifting", "core", lines=line),
            *extra,
        ),
    )


def a_conditioning_request(
    scheme: SchemeRef, *lines: Line, activity: MatchedActivity | None = None
) -> PrescribeRequest:
    """One conditioning session, `cond`, at `home` with no rack for its kettlebell."""
    session = Session(
        "cond", "Conditioning", "conditioning", "optional", scheme=scheme, lines=lines
    )
    form = ProgramForm(
        name="Test",
        kind="redesign",
        because="first program",
        emphasis="hypertrophy",
        location="home",
        schedule=Schedule(("A",), {"A": {"tue": "cond"}}),
        sessions=(session,),
    )
    swing = {"kb_swing": ExerciseFacts("single_implement", "kettlebell", "hinge")}
    return PrescribeRequest(
        version=ProgramVersion(form, swing),
        exposures=(),
        racks={"home": {}},
        planned=PlannedSession("cond", PLANNED, "home", "conditioning", lines),
        activities={} if activity is None else {"cond": activity},
    )
