import pytest
from support.program_drafts import WORKED_DRAFT, a_draft, a_line, a_session, toml

from coach.core.errors import Invalid
from coach.core.program.form import SchemeRef, SetGroup
from coach.core.program.parse import parse_program_draft


def test_the_worked_draft_parses_into_its_sessions_lines_and_schedule() -> None:
    draft = parse_program_draft(WORKED_DRAFT.encode(), file="v1.toml")

    form = draft.form
    assert draft.unknown_keys == ()
    assert draft.hash.startswith("sha256:")
    assert (form.kind, form.emphasis, form.location) == ("redesign", "hypertrophy", "home")
    assert form.schedule.rotation == ("A", "B")
    assert form.schedule.weeks["B"]["sat"] == "b-sat-push"
    assert [s.id for s in form.sessions] == [
        "pt-tuesday",
        "a-mon-lower",
        "b-sat-push",
        "a-sat-pull",
    ]
    assert form.dose is None and form.deload is None
    coach_led = form.sessions[0]
    assert coach_led.location == "gym"
    assert coach_led.estimated_sets == {
        "chest": 4,
        "lats": 4,
        "biceps": 3,
        "quadriceps": 4,
        "glutes": 3,
        "abdominals": 3,
    }
    squat = form.sessions[1].lines[0]
    assert squat.sets == (
        SetGroup(1, "warm_up", reps=5),
        SetGroup(1, "warm_up", reps=3),
        SetGroup(4, reps=(6, 8), rpe=8),
    )
    assert squat.start_load == 120
    ladder = form.sessions[3].lines[2]
    assert ladder.scheme == SchemeRef("assistance_ladder", {"rungs": [60, 50, 40, 30, 20, 10, 0]})
    assert form.sessions[1].lines[5].sets == (SetGroup(3, duration_s=30),)
    assert form.acknowledgements[0].flag == "scheme_off_emphasis@line:a-sat-pull/pull_up"


def test_an_open_top_and_a_single_rep_count_parse() -> None:
    line = a_line(sets=[{"count": 1, "reps": "8+"}, {"count": 2, "reps": 5, "rpe": 7.5}])

    form = parse_program_draft(toml(a_draft(a_session("push", line))), file="d.toml").form

    assert form.sessions[0].lines[0].sets == (SetGroup(1, reps="8+"), SetGroup(2, reps=5, rpe=7.5))


def test_unknown_keys_anywhere_are_collected_with_their_paths() -> None:
    line = a_line(colour="red")
    draft = a_draft(a_session("push", line, mood="good"), notes="x")

    parsed = parse_program_draft(toml(draft), file="d.toml")

    assert parsed.unknown_keys == (
        "notes",
        "session.push.line.bb_bench_press.colour",
        "session.push.mood",
    )


@pytest.mark.parametrize(
    ("draft", "why"),
    [
        (a_draft(kind="patch"), "kind"),
        (a_draft(emphasis="power"), "emphasis"),
        (a_draft(a_session("push", a_line(sets=[{"count": 0, "reps": 5}]))), "count"),
        (a_draft(a_session("push", a_line(sets=[{"count": 2, "reps": [8, 6]}]))), "reps"),
        (a_draft(a_session("push", a_line(rest_s=None))), "rest_s"),
        (a_draft(a_session("push", tier="sometimes")), "tier"),
    ],
)
def test_a_malformed_value_is_an_invalid_argument_naming_it(
    draft: dict[str, object], why: str
) -> None:
    with pytest.raises(Invalid) as raised:
        parse_program_draft(toml(draft), file="d.toml")

    assert raised.value.code == "invalid_argument"
    assert why in raised.value.message


def test_a_draft_that_is_not_toml_is_an_invalid_argument() -> None:
    with pytest.raises(Invalid):
        parse_program_draft(b"name = ", file="d.toml")


def test_the_form_document_parses_back_to_the_same_form() -> None:
    form = parse_program_draft(WORKED_DRAFT.encode(), file="v1.toml").form

    again = parse_program_draft(toml(form.to_document()), file="again.toml").form

    assert again == form


@pytest.mark.parametrize("kind", ["lifting", "conditioning", "practice"])
def test_a_session_of_a_kind_that_trains_lines_needs_at_least_one_line(kind: str) -> None:
    session = a_session("push", kind=kind, tier="optional")
    del session["line"]

    with pytest.raises(Invalid) as raised:
        parse_program_draft(toml(a_draft(session)), file="v1.toml")

    assert raised.value.code == "invalid_argument"
    assert "line" in raised.value.message


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("muscles", "chest"),
        ("muscles", {"primary": ["chest"]}),
        ("muscles", {"primary": "chest", "secondary": []}),
        ("name", 5),
        ("name", ""),
        ("hevy_title", []),
        ("load_mode", "rocket"),
        ("equipment_kind", "spaceship"),
    ],
)
def test_a_malformed_declared_exercise_value_stops_the_read(key: str, value: object) -> None:
    draft = a_draft(exercise={"custom_ring_push_up": {key: value}})

    with pytest.raises(Invalid) as raised:
        parse_program_draft(toml(draft), file="d.toml")

    assert raised.value.code == "invalid_argument"
    assert f"exercise.custom_ring_push_up.{key}" in raised.value.message


def test_a_declared_exercise_keeps_its_typed_values() -> None:
    muscles = {"primary": ["chest"], "secondary": ["triceps"]}
    draft = a_draft(exercise={"custom_ring_push_up": {"name": "Ring push-up", "muscles": muscles}})

    form = parse_program_draft(toml(draft), file="d.toml").form

    assert form.exercises["custom_ring_push_up"] == {"name": "Ring push-up", "muscles": muscles}
