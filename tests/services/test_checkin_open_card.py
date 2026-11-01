from typing import cast

from support.check_in_cards import (
    a_planned_two_session_week,
    a_two_session_program,
    field_of,
    monday,
    opened,
)
from support.plans import squat_logged

from coach.core.check_in_card import Ask


def test_one_closing_week_gives_the_card_its_fields_in_order_with_the_empty_ones_dropped() -> None:
    conn = a_two_session_program()
    a_planned_two_session_week(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 8, 8)] * 4)

    card = opened(conn)

    assert [f.name for f in card.fields] == [
        "header",
        "sessions",
        "week_kind",
        "block",
        "adherence",
        "dose",
        "lifts",
        "readiness",
        "sleep",
        "weight_phase",
    ]
    assert field_of(card, "header").facts == {
        "window": {"start": "2026-11-02", "end": "2026-11-08"},
        "tier": "light",
        "catch_up": False,
        "plan_in_force": "wp-2026-11-02",
    }


def test_a_matched_session_is_prefilled_and_only_the_miss_is_asked_a_tag() -> None:
    conn = a_two_session_program()
    a_planned_two_session_week(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 8, 8)] * 4)

    sessions = field_of(opened(conn), "sessions")

    lower, push = cast(list[dict[str, object]], sessions.facts["core"])
    assert (lower["state"], lower["workout"], lower["session_rpe"]) == ("matched", "h-1", 8.0)
    assert push["state"] == "missed"
    assert sessions.asks == (Ask("miss_tag", "planned_session:2026-11-04/push"),)


def test_the_week_kind_line_reads_the_week_this_check_in_closes() -> None:
    conn = a_two_session_program()
    a_planned_two_session_week(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 8, 8)] * 4)

    assert field_of(opened(conn), "week_kind").facts == {
        "weeks": [
            {"monday": "2026-11-02", "kind": "partial", "trained": "1/2", "gate_passed": "1/2"}
        ]
    }


def test_deep_raises_the_tier_and_adds_the_deep_field() -> None:
    conn = a_two_session_program()
    a_planned_two_session_week(conn, monday(0))

    card = opened(conn, tier="deep")

    assert card.tier == "deep"
    assert card.fields[-1].name == "deep_tier"
