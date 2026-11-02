import dataclasses
import datetime
from collections.abc import Callable

import pytest

from coach.core.errors import Invalid
from coach.core.flag import (
    Acknowledgement,
    AcknowledgementSource,
    Flag,
    FlagKey,
    Scope,
    grouped,
    leave,
    raise_flag,
)

MONDAY = datetime.date(2026, 11, 2)
OHP_LINE = Scope("line", monday=MONDAY, session_id="upper-a", exercise_id="bb_overhead_press")
EXPOSURES = ["exposure:b7e2/bb_overhead_press", "exposure:0c4a/bb_overhead_press"]


def a_stall(streak: int = 2, message: str = "OHP has stalled") -> Flag:
    return raise_flag("stall_streak", OHP_LINE, {"streak": streak, "exposures": EXPOSURES}, message)


@pytest.mark.parametrize(
    ("scope", "key"),
    [
        (OHP_LINE, "stall_streak@line:2026-11-02/upper-a/bb_overhead_press"),
        (
            Scope("line", session_id="a-sat-pull", exercise_id="pull_up"),
            "stall_streak@line:a-sat-pull/pull_up",
        ),
    ],
)
def test_the_key_is_code_at_scope_kind_and_refs(scope: Scope, key: str) -> None:
    flag = raise_flag("stall_streak", scope, {"streak": 3}, "stalled")

    assert flag.key == key


@pytest.mark.parametrize(
    ("code", "scope", "key"),
    [
        (
            "block_ceiling_exceeded",
            Scope("week", monday=MONDAY),
            "block_ceiling_exceeded@week:2026-11-02",
        ),
        ("routine_drift", Scope("routine", routine_id="3f9d"), "routine_drift@routine:3f9d"),
        ("engine_pin_dev", Scope("instance"), "engine_pin_dev@instance"),
        (
            "over_rep_cap",
            Scope("exposure", workout_id="b7e2", exercise_id="bb_bench_press"),
            "over_rep_cap@exposure:b7e2/bb_bench_press",
        ),
        (
            "cadence_slow",
            Scope("exercise", exercise_id="bb_bench_press"),
            "cadence_slow@exercise:bb_bench_press",
        ),
        ("goal_missing", Scope("version", version_id="pv-3"), "goal_missing@version:pv-3"),
        (
            "exercise_unmapped",
            Scope("workout", workout_id="9a1f"),
            "exercise_unmapped@workout:9a1f",
        ),
        (
            "session_over_minutes",
            Scope("session", session_id="upper-a"),
            "session_over_minutes@session:upper-a",
        ),
    ],
)
def test_every_scope_kind_renders_its_refs(code: str, scope: Scope, key: str) -> None:
    assert raise_flag(code, scope, {}, "m").key == key


def test_two_flags_with_one_code_and_scope_have_equal_keys_whatever_their_messages() -> None:
    plain = a_stall(message="OHP has stalled for 3 exposures at 42.5 kg")
    reworded = a_stall(message="The press is stuck")

    assert plain.key == reworded.key
    assert plain.params_hash == reworded.params_hash


def test_a_streak_growing_from_2_to_3_changes_the_params_hash_and_nothing_else() -> None:
    two = a_stall(streak=2).to_json()
    three = a_stall(streak=3).to_json()

    changed = {field for field in two if two[field] != three[field]}
    assert changed == {"params", "params_hash"}
    assert str(three["params_hash"]).startswith("sha256:")


def test_the_params_hash_ignores_key_order() -> None:
    one = raise_flag("stall_streak", OHP_LINE, {"streak": 3, "exposures": EXPOSURES}, "m")
    other = raise_flag("stall_streak", OHP_LINE, {"exposures": EXPOSURES, "streak": 3}, "m")

    assert one.params_hash == other.params_hash


def test_the_flag_shape() -> None:
    flag = a_stall(streak=3, message="OHP has stalled for 3 exposures")

    assert flag.to_json() == {
        "key": "stall_streak@line:2026-11-02/upper-a/bb_overhead_press",
        "code": "stall_streak",
        "severity": "warning",
        "scope": {
            "kind": "line",
            "week": "2026-11-02",
            "session": "upper-a",
            "exercise": "bb_overhead_press",
        },
        "params": {"streak": 3, "exposures": EXPOSURES},
        "params_hash": flag.params_hash,
        "rn": "rn:progression-methods §4",
        "message": "OHP has stalled for 3 exposures",
        "left": None,
    }


def test_the_summary_carries_the_key_and_params_hash_an_acknowledgement_copies() -> None:
    flag = a_stall(streak=3, message="OHP has stalled for 3 exposures")

    assert flag.to_summary() == {
        "key": "stall_streak@line:2026-11-02/upper-a/bb_overhead_press",
        "params_hash": "sha256:6440872b01f6353382fa704f80c63a360f64b7646b8ee8d9f404b5ce6fa94c6a",
        "code": "stall_streak",
        "severity": "warning",
        "message": "OHP has stalled for 3 exposures",
        "left": None,
    }


def test_severity_comes_from_the_registry() -> None:
    flag = raise_flag("load_off_grid", OHP_LINE, {"load": 43}, "off the grid")

    assert flag.severity == "violation"
    assert flag.rn is None


def test_a_code_outside_the_registry_cannot_be_raised() -> None:
    with pytest.raises(KeyError):
        raise_flag("plan_not_current", Scope("instance"), {}, "m")


def test_a_flag_is_raised_only_on_a_scope_its_registry_row_names() -> None:
    with pytest.raises(ValueError, match="scope"):
        raise_flag("stall_streak", Scope("week", monday=MONDAY), {}, "m")


def test_a_flag_carries_only_params_its_registry_row_names() -> None:
    with pytest.raises(ValueError, match="params"):
        raise_flag("stall_streak", OHP_LINE, {"colour": "red"}, "m")


def test_a_per_case_citation_is_picked_by_the_param_it_names() -> None:
    def ceiling(kind: str) -> str | None:
        return raise_flag("recovery_ceiling_exceeded", OHP_LINE, {"ceiling_kind": kind}, "m").rn

    assert ceiling("return_band") == "rn:detraining-return.3"
    assert ceiling("illness") == "rn:detraining-return.4"
    assert ceiling("light_week") == "rn:deloads.10"
    assert ceiling("niggle") is None


def test_a_code_resting_on_several_claims_names_the_one_that_raised_it() -> None:
    week = Scope("week", monday=MONDAY)

    with pytest.raises(ValueError, match="rn"):
        raise_flag("light_week_unprompted", week, {}, "m")
    flag = raise_flag("light_week_unprompted", week, {}, "m", rn="rn:deloads.4")
    assert flag.rn == "rn:deloads.4"
    with pytest.raises(ValueError, match="rn"):
        raise_flag("light_week_unprompted", week, {}, "m", rn="rn:deloads.9")


@pytest.mark.parametrize(
    "scope",
    [
        lambda: Scope("line", session_id="upper-a"),
        lambda: Scope("week"),
        lambda: Scope("instance", session_id="upper-a"),
        lambda: Scope("exposure", workout_id="b7e2"),
        lambda: Scope("week", monday=datetime.date(2026, 11, 3)),
    ],
)
def test_a_scope_holds_exactly_the_refs_its_kind_takes(scope: Callable[[], Scope]) -> None:
    with pytest.raises(ValueError):
        scope()


@pytest.mark.parametrize(
    "key",
    [
        "stall_streak@line:2026-11-02/upper-a/bb_overhead_press",
        "stall_streak@line:upper-a/bb_overhead_press",
        "block_ceiling_exceeded@week:2026-11-02",
        "engine_pin_dev@instance",
        "over_rep_cap@exposure:b7e2/bb_bench_press",
        "session_over_minutes@session:2026-11-02/upper-a",
    ],
)
def test_a_key_parses_back_to_itself(key: str) -> None:
    assert str(FlagKey.parse(key)) == key


@pytest.mark.parametrize(
    "key",
    [
        "Stall@line:a/b",
        "stall_streak",
        "stall_streak@shelf:a",
        "stall_streak@line:a",
        "stall_streak@line:2026-11-03/a/b",
        "stall_streak@line:x/a/b",
        "engine_pin_dev@instance:x",
        "routine_drift@routine",
    ],
)
def test_a_malformed_key_is_invalid(key: str) -> None:
    with pytest.raises(Invalid):
        FlagKey.parse(key)


def an_acknowledgement(
    key: str, params_hash: str, *, source: AcknowledgementSource = "weekplan"
) -> Acknowledgement:
    return Acknowledgement(
        key=FlagKey.parse(key),
        params_hash=params_hash,
        because="stall",
        text="The press is on a hold for the deficit.",
        evidence=("niggle:n-0004",),
        source=source,
    )


def test_an_acknowledgement_leaves_a_warning_with_its_key_and_params_hash() -> None:
    flag = a_stall(streak=2)
    acknowledgement = an_acknowledgement(flag.key, flag.params_hash)

    left = leave(flag, [acknowledgement])

    assert left.to_json()["left"] == {
        "because": "stall",
        "text": "The press is on a hold for the deficit.",
        "source": "weekplan",
        "evidence": ["niggle:n-0004"],
    }


def test_a_grown_streak_returns_the_warning_fresh() -> None:
    acknowledged = a_stall(streak=2)
    acknowledgement = an_acknowledgement(acknowledged.key, acknowledged.params_hash)

    assert leave(a_stall(streak=3), [acknowledgement]).left is None


def test_an_acknowledgement_of_another_key_leaves_nothing() -> None:
    flag = a_stall()
    other = an_acknowledgement(
        "stall_streak@line:2026-11-02/upper-a/bb_bench_press", flag.params_hash
    )

    assert leave(flag, [other]).left is None


def test_a_leave_warning_key_in_calendar_free_form_matches_the_dated_flag() -> None:
    flag = a_stall()
    decision = an_acknowledgement(
        "stall_streak@line:upper-a/bb_overhead_press", flag.params_hash, source="decision"
    )

    left = leave(flag, [decision]).left
    assert left is not None
    assert left.source == "decision"


def test_a_weekplan_acknowledgement_needs_the_dated_key() -> None:
    flag = a_stall()
    undated = an_acknowledgement("stall_streak@line:upper-a/bb_overhead_press", flag.params_hash)

    assert leave(flag, [undated]).left is None


def test_a_version_acknowledgement_leaves_an_adopt_warning_and_never_a_plan_warning() -> None:
    adopt = raise_flag(
        "emphasis_off_goal",
        Scope("version", version_id="pv-2"),
        {"goal_kind": "hypertrophy", "emphasis": "maintenance"},
        "maintenance block",
    )
    stall = a_stall()

    on_version = an_acknowledgement(
        "emphasis_off_goal@version:pv-2", adopt.params_hash, source="version"
    )
    on_stall = an_acknowledgement(stall.key, stall.params_hash, source="version")

    assert leave(adopt, [on_version]).left is not None
    assert leave(stall, [on_stall]).left is None


def test_a_week_scope_cannot_be_the_target_of_a_decision() -> None:
    with pytest.raises(Invalid):
        an_acknowledgement("block_ceiling_exceeded@week:2026-11-02", "sha256:x", source="decision")


def test_a_decision_names_the_calendar_free_key() -> None:
    with pytest.raises(Invalid):
        an_acknowledgement(
            "stall_streak@line:2026-11-02/upper-a/bb_overhead_press", "sha256:x", source="decision"
        )


def test_a_violation_is_never_left() -> None:
    violation = raise_flag("load_off_grid", OHP_LINE, {"load": 43}, "off the grid")
    acknowledgement = an_acknowledgement(violation.key, violation.params_hash)

    assert leave(violation, [acknowledgement]).to_json()["left"] is None


def test_a_violation_cannot_be_built_already_left() -> None:
    violation = raise_flag("load_off_grid", OHP_LINE, {"load": 43}, "off the grid")
    stall = a_stall()
    left = leave(stall, [an_acknowledgement(stall.key, stall.params_hash)]).left

    with pytest.raises(ValueError):
        dataclasses.replace(violation, left=left)


@pytest.mark.parametrize("source", ["weekplan", "decision"])
def test_a_warning_outside_a_plan_is_never_left(source: AcknowledgementSource) -> None:
    drift = raise_flag(
        "routine_drift", Scope("routine", routine_id="r1"), {"drift_class": "load"}, "drifted"
    )
    acknowledgement = an_acknowledgement(drift.key, drift.params_hash, source=source)

    assert leave(drift, [acknowledgement]).left is None


def test_an_activity_cap_exceeded_is_never_left() -> None:
    week = Scope("week", monday=MONDAY)
    capped = raise_flag(
        "activity_cap_exceeded", week, {"cap": 3, "observed": 4}, "over", rn="rn:running-load.5"
    )

    assert leave(capped, [an_acknowledgement(capped.key, capped.params_hash)]).left is None


def a_cadence_slow() -> Flag:
    return raise_flag(
        "cadence_slow",
        Scope("exercise", exercise_id="bb_bench_press"),
        {"scheme": "linear", "blocks": 2},
        "bench is slow",
    )


def test_a_leave_warning_decision_leaves_a_cadence_signal() -> None:
    slow = a_cadence_slow()
    decision = an_acknowledgement(
        "cadence_slow@exercise:bb_bench_press", slow.params_hash, source="decision"
    )

    left = leave(slow, [decision]).left
    assert left is not None
    assert left.source == "decision"


def test_a_weekplan_acknowledgement_does_not_leave_a_cadence_signal() -> None:
    slow = a_cadence_slow()

    assert leave(slow, [an_acknowledgement(slow.key, slow.params_hash)]).left is None


@pytest.mark.parametrize("left", [False, True], ids=["standing", "left"])
def test_a_flag_reads_back_from_its_json(left: bool) -> None:
    flag = a_stall(streak=3)
    if left:
        flag = leave(flag, [an_acknowledgement(flag.key, flag.params_hash)])

    assert Flag.from_json(flag.to_json()) == flag


def test_flags_group_one_row_per_code_in_the_order_each_code_first_appears() -> None:
    week = raise_flag("rotation_unconfirmed", Scope("week", monday=MONDAY), {}, "confirm A")
    squat = Scope("line", monday=MONDAY, session_id="lower-a", exercise_id="bb_back_squat")
    first, second = a_stall(), raise_flag("stall_streak", squat, {"streak": 3}, "squat stalled")

    rows = grouped(flag.to_json() for flag in (first, week, second))

    assert rows == [
        {
            "code": "stall_streak",
            "severity": "warning",
            "count": 2,
            "keys": [
                {
                    "key": "stall_streak@line:2026-11-02/upper-a/bb_overhead_press",
                    "params_hash": first.params_hash,
                },
                {
                    "key": "stall_streak@line:2026-11-02/lower-a/bb_back_squat",
                    "params_hash": second.params_hash,
                },
            ],
        },
        {
            "code": "rotation_unconfirmed",
            "severity": "violation",
            "count": 1,
            "keys": [
                {"key": "rotation_unconfirmed@week:2026-11-02", "params_hash": week.params_hash}
            ],
        },
    ]
