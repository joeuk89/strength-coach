from typing import Any

from support.program_drafts import a_draft, a_line, a_session, toml

from coach.core.program.defaults import fill
from coach.core.program.diff import diff
from coach.core.program.form import ProgramForm
from coach.core.program.parse import parse_program_draft


def filled_form(draft: dict[str, object]) -> tuple[ProgramForm, tuple[str, ...]]:
    form = parse_program_draft(toml(draft), file="d.toml").form
    filled = fill(form, priority_lifts=("bb_bench_press",), phase=None, session_minutes=60)
    return filled.form, filled.filled


def test_the_same_form_twice_is_an_empty_diff() -> None:
    form, _ = filled_form(a_draft())

    assert diff(form, form).empty


def test_a_first_version_adds_every_session_and_marks_the_filled_defaults() -> None:
    form, filled = filled_form(a_draft())

    change: Any = diff(None, form, filled).to_json()

    assert change["sessions"]["added"] == ["push"]
    assert change["version"]["dose"] == {
        "from": None,
        "to": {"per_muscle": 10, "lift": {"bb_bench_press": 8}},
        "filled": True,
    }
    assert change["version"]["deload"]["filled"] is True
    assert change["version"]["emphasis"] == {"from": None, "to": "hypertrophy"}
    assert change["filled"] == ["dose", "deload", "session.push.minutes"]


def test_sessions_and_lines_added_removed_and_changed() -> None:
    before, _ = filled_form(
        a_draft(a_session("push", a_line(), a_line("db_curl")), a_session("legs"))
    )
    after, _ = filled_form(
        a_draft(
            a_session("push", a_line(start_load=62.5), a_line("db_fly")),
            a_session("pull", a_line("pull_up")),
        )
    )

    change: Any = diff(before, after).to_json()

    assert change["sessions"] == {
        "added": ["pull"],
        "removed": ["legs"],
        "changed": [
            {
                "id": "push",
                "fields": [],
                "lines": {
                    "added": ["db_fly"],
                    "removed": ["db_curl"],
                    "changed": [{"exercise": "bb_bench_press", "fields": ["start_load"]}],
                },
            }
        ],
    }
    assert change["version"] == {"schedule": change["version"]["schedule"]}


def test_reordering_lines_in_a_session_is_a_line_order_change() -> None:
    before, _ = filled_form(a_draft(a_session("push", a_line(), a_line("bb_back_squat"))))
    after, _ = filled_form(a_draft(a_session("push", a_line("bb_back_squat"), a_line())))

    change = diff(before, after)

    assert not change.empty
    assert [(s.id, s.fields) for s in change.sessions_changed] == [("push", ("line_order",))]


def test_adding_a_line_alone_is_not_a_line_order_change() -> None:
    before, _ = filled_form(a_draft(a_session("push", a_line())))
    after, _ = filled_form(a_draft(a_session("push", a_line("bb_back_squat"), a_line())))

    assert [s.fields for s in diff(before, after).sessions_changed] == [()]


def test_reordering_sessions_is_a_session_order_change() -> None:
    schedule = {"rotation": ["A"], "A": {"mon": "push", "wed": "legs"}}
    push, legs = a_session("push"), a_session("legs", a_line("bb_back_squat"))
    before, _ = filled_form(a_draft(push, legs, schedule=schedule))
    after, _ = filled_form(a_draft(legs, push, schedule=schedule))

    change: Any = diff(before, after).to_json()

    assert change["empty"] is False
    assert change["version"] == {
        "session_order": {"from": ["push", "legs"], "to": ["legs", "push"]}
    }


def test_a_change_to_a_lifts_counted_variants_shows_in_the_dose() -> None:
    bare = {"per_muscle": 10, "lift": {"pull_up": 8}}
    counted = {"per_muscle": 10, "lift": {"pull_up": {"sets": 8, "counts": ["band_pull_up"]}}}
    before, _ = filled_form(a_draft(dose=bare))
    after, _ = filled_form(a_draft(dose=counted))

    change: Any = diff(before, after).to_json()

    assert change["version"]["dose"] == {"from": bare, "to": counted}
