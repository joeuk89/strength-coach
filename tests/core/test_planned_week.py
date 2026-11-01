import datetime

from support.prescribe import a_line

from coach.core.planned_week import RotationPosition, infer_position, planned_sessions
from coach.core.prescription import StatusSpan
from coach.core.program.form import ProgramForm, Schedule, Session

MONDAY = datetime.date(2026, 11, 2)
LINE = (a_line(),)


def a_form(*extra: Session) -> ProgramForm:
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
            Session("lower-a", "Lower A", "lifting", "core", lines=LINE),
            Session("push-a", "Push A", "lifting", "core", location="gym", lines=LINE),
            Session("pull-b", "Pull B", "lifting", "core", lines=LINE),
            *extra,
        ),
    )


def planned(
    form: ProgramForm, position: str = "A", spans: tuple[StatusSpan, ...] = ()
) -> list[tuple[str, str]]:
    sessions = planned_sessions(form, position=position, monday=MONDAY, spans=spans)
    return [(s.date.isoformat(), s.session_id) for s in sessions]


def test_weekly_sessions_fall_on_their_weekday_of_the_rotation_week() -> None:
    assert planned(a_form()) == [("2026-11-02", "lower-a"), ("2026-11-05", "push-a")]
    assert planned(a_form(), "B") == [("2026-11-03", "pull-b")]


def test_a_session_takes_its_own_location_or_the_versions() -> None:
    sessions = planned_sessions(a_form(), position="A", monday=MONDAY)

    assert [(s.session_id, s.location) for s in sessions] == [
        ("lower-a", "home"),
        ("push-a", "gym"),
    ]


def test_a_standing_session_is_planned_once_on_the_monday_and_a_daily_one_every_day() -> None:
    form = a_form(
        Session("mobility", "Mobility", "practice", "optional", cadence="standing", lines=LINE),
        Session("hang", "Hang", "practice", "optional", cadence="daily", lines=LINE),
    )

    found = planned(form)

    assert found.count(("2026-11-02", "mobility")) == 1
    assert [day for day, session in found if session == "hang"] == [
        (MONDAY + datetime.timedelta(days=n)).isoformat() for n in range(7)
    ]


def test_an_open_niggles_rehab_session_is_planned_by_its_cadence() -> None:
    rehab = Session("knee-rehab", "Knee rehab", "rehab", "optional", "standing", lines=LINE)

    found = planned_sessions(a_form(), position="A", monday=MONDAY, rehab=(rehab,))

    assert ("knee-rehab", "rehab", "home", MONDAY) in [
        (s.session_id, s.kind, s.location, s.date) for s in found
    ]


def test_a_no_training_span_over_the_whole_week_plans_nothing() -> None:
    span = StatusSpan("no_training", datetime.date(2026, 10, 30), datetime.date(2026, 11, 8))

    assert planned(a_form(), spans=(span,)) == []


def test_a_no_training_span_over_part_of_the_week_plans_the_week() -> None:
    span = StatusSpan("no_training", MONDAY, MONDAY)
    ill = StatusSpan("ill", MONDAY, None)

    assert len(planned(a_form(), spans=(span, ill))) == 2


ROTATION = ("A", "B", "C")


def test_with_no_plan_the_position_is_the_one_the_version_was_adopted_at() -> None:
    assert infer_position(ROTATION, adopted="B") == RotationPosition("B", "program_adopt")


def test_after_an_approved_plan_the_position_is_the_next_rotation_week() -> None:
    assert infer_position(ROTATION, adopted="A", previous="C") == RotationPosition(
        "A", "previous_plan"
    )


def test_a_superseding_draft_keeps_the_position_of_the_plan_in_force() -> None:
    assert infer_position(ROTATION, adopted="A", previous="A", in_force="B") == RotationPosition(
        "B", "plan_in_force"
    )


def test_a_previous_position_the_rotation_lacks_falls_back_to_the_adopted_one() -> None:
    assert infer_position(ROTATION, adopted="A", previous="Z") == RotationPosition(
        "A", "program_adopt"
    )
