import datetime
from typing import cast

from support.check_in_cards import field_of, opened
from support.clock import FixedClock, at
from support.history import a_logged_workout
from support.ladders import (
    CORE_LADDER,
    TEMPLATES,
    a_ladder_program,
    a_met_rung,
    ladder_rung_decision,
    leave_warning,
    logged,
    the_prompts_flag,
)
from support.plans import (
    SQUAT_LINE,
    a_squat_program,
    an_acknowledgement,
    an_approved_plan,
    squat_logged,
)
from support.program_drafts import a_ladder_line, a_rung, a_session

from coach.core.check_in_card import Ask
from coach.services.checkin_record import checkin_record
from coach.services.record import record
from coach.store.connection import Connection

FIRST_SUNDAY = datetime.date(2026, 11, 8)


type Row = dict[str, object]


def ladder_rows(conn: Connection, on: datetime.date = FIRST_SUNDAY) -> list[Row]:
    return cast(list[Row], field_of(opened(conn, on), "ladders").facts["rows"])


def test_the_ladders_field_follows_lifts_with_the_standing_rung_and_its_exposure_count() -> None:
    conn = a_ladder_program()
    logged(conn, "dead_bug", "2026-11-08", 10)

    card = opened(conn)

    names = [f.name for f in card.fields]
    assert names[names.index("ladders") - 1 : names.index("ladders") + 1] == ["lifts", "ladders"]
    assert field_of(card, "ladders").facts["rows"] == [
        {
            "session": "lower",
            "line": "dead_bug",
            "rung": 1,
            "exercise": "dead_bug",
            "rungs": 3,
            "exposures": 1,
            "needed": 2,
            "met": False,
            "held": False,
            "next": "ab_wheel",
            "label": "rung 1 · 3×10 @8 · first cues",
            "next_label": "rung 2 · Ab Wheel Rollout · 3×8 @8 · ab_wheel cues",
        }
    ]
    assert field_of(card, "ladders").asks == ()


def test_a_met_rung_says_met_and_names_the_next_rung() -> None:
    conn = a_ladder_program()
    logged(conn, "dead_bug", "2026-11-02", 10)
    logged(conn, "dead_bug", "2026-11-05", 10)

    [row] = ladder_rows(conn)

    assert (row["exposures"], row["met"], row["next"]) == (2, True, "ab_wheel")


def test_a_set_short_of_the_criterion_breaks_the_run_of_exposures() -> None:
    conn = a_ladder_program()
    logged(conn, "dead_bug", "2026-11-02", 10)
    logged(conn, "dead_bug", "2026-11-05", 9)

    [row] = ladder_rows(conn)

    assert (row["exposures"], row["met"]) == (0, False)


def test_a_manual_rung_asks_whether_the_athlete_is_ready_for_the_next_rung() -> None:
    manual = a_ladder_line(
        "dead_bug",
        a_rung(sets=[{"count": 3, "reps": 10, "rpe": 8}], advance={"manual": True}),
        a_rung("ab_wheel", sets=[{"count": 3, "reps": 8, "rpe": 8}]),
    )
    conn = a_ladder_program(manual)
    logged(conn, "dead_bug", "2026-11-02", 10)
    logged(conn, "dead_bug", "2026-11-05", 10)

    ladders = field_of(opened(conn), "ladders")

    [row] = cast(list[Row], ladders.facts["rows"])
    assert (row["met"], row["needed"], row["next"]) == (False, None, "ab_wheel")
    assert ladders.asks == (Ask("ready_for_next_rung", "line:lower/dead_bug"),)


def test_a_leave_warning_holds_the_met_rung_the_prompt_shows_left() -> None:
    conn = a_met_rung()
    raised = the_prompts_flag(conn)
    [before] = ladder_rows(conn)

    leave_warning(conn, raised)

    [after] = ladder_rows(conn)
    assert (raised.left, before["met"], before["held"]) == (None, True, False)
    assert the_prompts_flag(conn).left is not None
    assert (after["met"], after["held"]) == (True, True)


def test_a_further_qualifying_exposure_leaves_the_rung_held() -> None:
    conn = a_met_rung()
    leave_warning(conn, the_prompts_flag(conn))

    logged(conn, "dead_bug", "2026-11-05", 10)

    [row] = ladder_rows(conn)
    assert (row["met"], row["held"]) == (True, True)


def test_moving_the_rung_clears_the_hold() -> None:
    conn = a_met_rung()
    leave_warning(conn, the_prompts_flag(conn))
    record(conn, ladder_rung_decision(2).encode(), file="d.toml", clock=FixedClock())
    logged(conn, "ab_wheel", "2026-11-02", 8)
    logged(conn, "ab_wheel", "2026-11-05", 8)

    [row] = ladder_rows(conn)

    assert (row["rung"], row["met"], row["held"]) == (2, True, False)


def test_a_leave_warning_past_its_until_no_longer_holds_the_rung() -> None:
    conn = a_met_rung()
    leave_warning(conn, the_prompts_flag(conn), until="2026-11-07")

    [row] = ladder_rows(conn)

    assert (row["met"], row["held"]) == (True, False)


def test_a_leave_warning_holds_ladder_top_on_the_last_rung() -> None:
    conn = a_ladder_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    record(conn, ladder_rung_decision(3).encode(), file="d.toml", clock=FixedClock())
    logged(conn, "hanging_leg_raise", "2026-10-31", 6)
    logged(conn, "hanging_leg_raise", "2026-11-01", 6)
    [before] = ladder_rows(conn)

    leave_warning(conn, the_prompts_flag(conn, "ladder_top"))

    [after] = ladder_rows(conn)
    assert (before["met"], before["held"]) == (True, False)
    assert (after["met"], after["held"]) == (True, True)


def test_a_plan_acknowledgement_holds_the_rung_until_a_later_plan_drops_it() -> None:
    conn = a_met_rung()
    raised = the_prompts_flag(conn)
    plan_id = an_approved_plan(conn, "2026-11-02")
    an_acknowledgement(conn, plan_id, raised.key, raised.params_hash)
    next_monday = FIRST_SUNDAY + datetime.timedelta(days=1)

    assert raised.key == "rung_met@line:2026-11-02/lower/dead_bug"
    assert ladder_rows(conn)[0]["held"] is True
    assert ladder_rows(conn, next_monday)[0]["held"] is True

    an_approved_plan(conn, "2026-11-09")

    assert ladder_rows(conn, next_monday)[0]["held"] is False


def test_a_card_with_no_ladder_line_drops_the_field() -> None:
    conn = a_squat_program()

    assert "ladders" not in [f.name for f in opened(conn).fields]


def test_a_ladder_rung_in_the_check_in_draft_moves_the_next_card_to_the_new_rung_at_zero() -> None:
    conn = a_ladder_program()
    logged(conn, "dead_bug", "2026-11-02", 10)
    logged(conn, "dead_bug", "2026-11-05", 10)
    draft = 'date = 2026-11-08\ntier = "light"\nread = "Two clean weeks."\n' + (
        ladder_rung_decision(2)
    )
    checkin_record(conn, draft.encode(), file="c.toml", clock=FixedClock(at(FIRST_SUNDAY)))

    [row] = ladder_rows(conn, FIRST_SUNDAY + datetime.timedelta(days=7))

    assert row == {
        "session": "lower",
        "line": "dead_bug",
        "rung": 2,
        "exercise": "ab_wheel",
        "rungs": 3,
        "exposures": 0,
        "needed": 2,
        "met": False,
        "held": False,
        "next": "hanging_leg_raise",
        "label": "rung 2 · 3×8 @8 · ab_wheel cues",
        "next_label": "rung 3 · Hanging Leg Raise · 3×6 @8 · hanging_leg_raise cues",
    }


def test_the_cards_ladders_row_on_a_practice_ladder_on_its_last_rung_says_met() -> None:
    conn = a_squat_program(
        a_session("lower", SQUAT_LINE),
        a_session("drill", CORE_LADDER, kind="practice", tier="optional"),
    )
    record(
        conn, ladder_rung_decision(3, session="drill").encode(), file="d.toml", clock=FixedClock()
    )
    for on in ("2026-11-04", "2026-11-05"):
        a_logged_workout(
            conn,
            f"h-drill-{on}",
            on,
            (TEMPLATES["hanging_leg_raise"], ((None, 6, 8),) * 3),
            session_id="drill",
        )

    assert ladder_rows(conn) == [
        {
            "session": "drill",
            "line": "dead_bug",
            "rung": 3,
            "exercise": "hanging_leg_raise",
            "rungs": 3,
            "exposures": 2,
            "needed": 2,
            "met": True,
            "held": False,
            "next": None,
            "label": "rung 3 · 3×6 @8 · hanging_leg_raise cues",
            "next_label": None,
        }
    ]
