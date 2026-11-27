"""Warnings that recur unchanged week to week hash only their standing facts, so a
`leave_warning` Decision keeps leaving them (validation.md, "Longer than a week")."""

import datetime

import pytest
from support.exposures import an_exposure
from support.prescribe import a_line, a_request

from coach.core.exposure import Exposure
from coach.core.flag import Acknowledgement, Flag, FlagKey, Scope, leave, raise_flag
from coach.core.prescribe import prescribe
from coach.core.prescription import PlanOverride

LIGHT_WEEK = PlanOverride("light_week")
FIRST = datetime.date(2026, 11, 2)
SECOND = datetime.date(2026, 11, 9)


def squat_on(on: str, load: float, workout_id: str) -> Exposure:
    return an_exposure(on, *[(load, 15, 7)] * 4, workout_id=workout_id, exercise_id="bb_back_squat")


def unchecked(on: datetime.date, *exposures: Exposure) -> Flag:
    session = prescribe(a_request(a_line(), exposures=exposures, on=on, overrides=(LIGHT_WEEK,)))
    return next(f for f in session.lines[0].flags if f.code == "rpe_ceiling_unchecked")


def a_decision(code: str, key: str, params_hash: str) -> Acknowledgement:
    return Acknowledgement(
        FlagKey.parse(f"{code}@{key}"),
        params_hash,
        "coach_judgement",
        "Standing answer while the line stays light.",
        source="decision",
    )


def test_a_leave_warning_on_rpe_ceiling_unchecked_leaves_it_two_weeks_running() -> None:
    first = unchecked(FIRST, squat_on("2026-10-26", 120, "h-1"))
    second = unchecked(
        SECOND, squat_on("2026-10-26", 120, "h-1"), squat_on("2026-11-02", 125, "h-2")
    )
    decision = a_decision("rpe_ceiling_unchecked", "line:lower/bb_back_squat", first.params_hash)

    assert first.params["anchor_exposure"] != second.params["anchor_exposure"]
    assert first.params["clipped_load"] != second.params["clipped_load"]
    assert leave(first, [decision]).left is not None
    assert leave(second, [decision]).left is not None


def test_a_changed_cap_returns_rpe_ceiling_unchecked_fresh() -> None:
    line = Scope("line", FIRST, session_id="lower", exercise_id="bb_back_squat")
    params = {"clipped_load": 120, "anchor_exposure": "exposure:h-1/bb_back_squat"}
    at_8 = raise_flag("rpe_ceiling_unchecked", line, {"cap": 8, **params}, "m")
    at_7 = raise_flag("rpe_ceiling_unchecked", line, {"cap": 7, **params}, "m")

    assert at_8.params_hash != at_7.params_hash


SQUAT = Scope("line", FIRST, session_id="lower", exercise_id="bb_back_squat")
LOWER = Scope("session", FIRST, session_id="lower")


@pytest.mark.parametrize(
    ("code", "scope", "this_week", "next_week"),
    [
        (
            "session_drop_suggested",
            LOWER,
            {"reason": "status_span", "evidence": ["status_span:ss-0001"]},
            {"reason": "status_span", "evidence": ["status_span:ss-0002"]},
        ),
        (
            "override_persisting",
            SQUAT,
            {"kind": "hold", "weeks": 3, "plan_ids": ["wp-2026-10-19", "wp-2026-10-26"]},
            {"kind": "hold", "weeks": 4, "plan_ids": ["wp-2026-10-19", "wp-2026-10-26", "wp-2"]},
        ),
        (
            "increment_over_step",
            SQUAT,
            {"increment": 10, "scheme_step": 5, "from_exposure": "exposure:h-1/bb_back_squat"},
            {"increment": 10, "scheme_step": 5, "from_exposure": "exposure:h-2/bb_back_squat"},
        ),
        (
            "pin_load_capped",
            SQUAT,
            {
                "load": 115,
                "prescribed": 100,
                "ceiling_kind": "niggle",
                "rpe_cap": 7,
                "ref": "niggle:n-0001",
                "outcome": "reduced",
            },
            {
                "load": 115,
                "prescribed": 105,
                "ceiling_kind": "niggle",
                "rpe_cap": 7,
                "ref": "niggle:n-0001",
                "outcome": "reduced",
            },
        ),
    ],
)
def test_a_weekly_recurring_warning_hashes_only_its_standing_facts(
    code: str, scope: Scope, this_week: dict[str, object], next_week: dict[str, object]
) -> None:
    assert (
        raise_flag(code, scope, this_week, "m").params_hash
        == raise_flag(code, scope, next_week, "m").params_hash
    )
