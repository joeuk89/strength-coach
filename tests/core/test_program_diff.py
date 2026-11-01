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
