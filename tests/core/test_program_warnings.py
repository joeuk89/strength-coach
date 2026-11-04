import datetime
from typing import Any

from support.program_drafts import a_draft, a_line, a_session, toml

from coach.core.exposure import Exposure, ExposureSet
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.goal import Goal
from coach.core.load import Load
from coach.core.program.checks import AdoptContext, OpenBlock
from coach.core.program.parse import parse_program_draft
from coach.core.program.warnings import adopt_warnings, leave_warnings

LIBRARY: dict[str, dict[str, object]] = {
    "bb_bench_press": {
        "load_mode": "total",
        "muscles": {"primary": ["chest"], "secondary": ["triceps", "front_delts"]},
    },
}


def a_goal(kind: str = "hypertrophy", priority_lifts: tuple[str, ...] = ()) -> Goal:
    return Goal(kind=kind, because="first goal", priority_lifts=priority_lifts, why="")


def a_context(**fields: Any) -> AdoptContext:
    values: dict[str, Any] = {
        "version_id": "pv-1",
        "library": LIBRARY,
        "racks": {"home": {}},
        "goal": a_goal(),
    }
    values.update(fields)
    return AdoptContext(**values)


def warnings_of(draft: dict[str, Any], context: AdoptContext | None = None) -> list[Flag]:
    form = parse_program_draft(toml(draft), file="d.toml").form
    return list(adopt_warnings(form, context or a_context()))


def the(code: str, flags: list[Flag]) -> list[tuple[str, dict[str, object]]]:
    return [(flag.key, dict(flag.params)) for flag in flags if flag.code == code]


def test_a_maintenance_version_under_a_hypertrophy_goal_warns_emphasis_off_goal() -> None:
    flags = warnings_of(a_draft(emphasis="maintenance"))

    assert the("emphasis_off_goal", flags) == [
        ("emphasis_off_goal@version:pv-1", {"goal_kind": "hypertrophy", "emphasis": "maintenance"})
    ]
    assert the("emphasis_off_goal", warnings_of(a_draft())) == []


HYPERTROPHY_BAND = ["double_progression", "assistance_ladder", "hold"]
PRIORITY_BAND = [
    "top_backoff",
    "wave_531",
    "linear",
    "assistance_ladder",
    "double_progression in 3-6 reps",
]
BENCH_PRIORITY = a_context(goal=a_goal(priority_lifts=("bb_bench_press",)))


def bench(**fields: Any) -> dict[str, Any]:
    return a_draft(a_session("push", a_line(**fields)))


def test_a_hypertrophy_line_outside_its_band_warns_scheme_off_emphasis() -> None:
    flags = warnings_of(bench(scheme={"name": "linear"}))

    assert the("scheme_off_emphasis", flags) == [
        (
            "scheme_off_emphasis@line:push/bb_bench_press",
            {"scheme": "linear", "emphasis": "hypertrophy", "expected_band": HYPERTROPHY_BAND},
        )
    ]
    assert the("scheme_off_emphasis", warnings_of(bench())) == []


def test_a_priority_lift_takes_the_priority_band_under_every_emphasis() -> None:
    held = warnings_of(bench(scheme={"name": "hold"}), BENCH_PRIORITY)
    linear = warnings_of(bench(scheme={"name": "linear"}), BENCH_PRIORITY)
    strength = a_draft(a_session("push", a_line(scheme={"name": "hold"})), emphasis="strength")

    assert the("scheme_off_emphasis", held) == [
        (
            "scheme_off_emphasis@line:push/bb_bench_press",
            {"scheme": "hold", "emphasis": "hypertrophy", "expected_band": PRIORITY_BAND},
        )
    ]
    assert the("scheme_off_emphasis", linear) == []
    assert [k for k, _ in the("scheme_off_emphasis", warnings_of(strength, BENCH_PRIORITY))] == [
        "scheme_off_emphasis@line:push/bb_bench_press"
    ]
    assert [f.rn for f in held if f.code == "scheme_off_emphasis"] == ["rn:goal-programming §4"]


def test_double_progression_on_a_priority_lift_fits_only_inside_three_to_six_reps() -> None:
    def off(reps: object) -> bool:
        sets = [{"count": 3, "reps": reps, "rpe": 8}]
        return bool(the("scheme_off_emphasis", warnings_of(bench(sets=sets), BENCH_PRIORITY)))

    assert [off([3, 6]), off(5), off([4, 8]), off("5+"), off(2)] == [
        False,
        False,
        True,
        True,
        True,
    ]


def priority(*lifts: str) -> AdoptContext:
    return a_context(goal=a_goal(priority_lifts=lifts))


def test_a_priority_lift_on_no_line_warns_priority_lift_absent() -> None:
    flags = warnings_of(bench(), priority("bb_bench_press", "pull_up"))

    assert the("priority_lift_absent", flags) == [
        ("priority_lift_absent@version:pv-1", {"exercise_id": "pull_up"})
    ]
    assert the("priority_lift_absent", warnings_of(bench(), priority("bb_bench_press"))) == []


def test_a_priority_lift_behind_a_working_line_warns_priority_lift_not_first() -> None:
    rows = a_line("bb_bent_over_row")
    activation = a_line(
        "band_pull_apart",
        sets=[{"count": 2, "type": "activation", "reps": 10}],
        scheme={"name": "hold"},
    )
    behind = a_draft(a_session("pull", rows, a_line("pull_up")))
    first = a_draft(a_session("pull", activation, a_line("pull_up"), rows))
    both = a_draft(a_session("pull", a_line("bb_bench_press"), a_line("pull_up")))
    lifts = priority("bb_bench_press", "pull_up")

    assert the("priority_lift_not_first", warnings_of(behind, lifts)) == [
        ("priority_lift_not_first@session:pull", {"exercise_id": "pull_up", "position": 2})
    ]
    assert the("priority_lift_not_first", warnings_of(first, lifts)) == []
    assert the("priority_lift_not_first", warnings_of(both, lifts)) == []


def dosed(per_muscle: int, emphasis: str = "hypertrophy", **lift: int) -> dict[str, Any]:
    return a_draft(dose={"per_muscle": per_muscle, "lift": lift}, emphasis=emphasis)


def test_a_dose_target_outside_its_band_warns_dose_off_band_with_the_phase() -> None:
    high = warnings_of(dosed(25))
    lift = warnings_of(dosed(12, bb_bench_press=4))
    surplus = warnings_of(dosed(12), a_context(phase="surplus"))

    assert the("dose_off_band", high) == [
        (
            "dose_off_band@dose:pv-1/per_muscle",
            {"target_of": "per_muscle", "target": 25, "band": [10, 20], "phase": None},
        )
    ]
    assert the("dose_off_band", lift)[0][1] == {
        "target_of": "bb_bench_press",
        "target": 4,
        "band": [5, 15],
        "phase": None,
    }
    assert the("dose_off_band", surplus)[0][1]["band"] == [15, 20]
    assert the("dose_off_band", warnings_of(dosed(12, bb_bench_press=8))) == []
    assert the("dose_off_band", warnings_of(dosed(4, "maintenance", bb_bench_press=3))) == []


def test_every_off_band_lift_target_warns_on_its_own_key() -> None:
    flags = warnings_of(dosed(12, pull_up=1, bb_deadlift=4))

    assert the("dose_off_band", flags) == [
        (
            "dose_off_band@dose:pv-1/pull_up",
            {"target_of": "pull_up", "target": 1, "band": [5, 15], "phase": None},
        ),
        (
            "dose_off_band@dose:pv-1/bb_deadlift",
            {"target_of": "bb_deadlift", "target": 4, "band": [5, 15], "phase": None},
        ),
    ]


def test_an_off_band_muscle_target_and_lift_target_warn_on_two_keys() -> None:
    flags = warnings_of(dosed(25, bb_deadlift=4))

    assert [key for key, _ in the("dose_off_band", flags)] == [
        "dose_off_band@dose:pv-1/per_muscle",
        "dose_off_band@dose:pv-1/bb_deadlift",
    ]


def test_acknowledging_one_of_two_off_band_targets_leaves_the_other_standing() -> None:
    entry = {"flag": "dose_off_band@dose:pv-1/pull_up", "because": "coach_judgement", "text": "x"}
    draft = {**dosed(12, pull_up=1, bb_deadlift=4), "acknowledge": [entry]}
    form = parse_program_draft(toml(draft), file="d.toml").form

    left = leave_warnings(adopt_warnings(form, a_context()), form.acknowledgements)

    standing = {f.key: f.left is not None for f in left if f.code == "dose_off_band"}
    assert standing == {
        "dose_off_band@dose:pv-1/pull_up": True,
        "dose_off_band@dose:pv-1/bb_deadlift": False,
    }


def test_a_deload_off_the_emphasis_shape_warns_deload_off_emphasis() -> None:
    deload = {
        "hard_weeks_ceiling": 5,
        "set_cut_pct": 30,
        "load_cut_pct": 0,
        "rpe_cap": 8,
        "test_priority_lifts": True,
    }

    hypertrophy = warnings_of(a_draft(deload=deload))
    strength = warnings_of(a_draft(deload=deload, emphasis="strength"))

    assert the("deload_off_emphasis", hypertrophy) == [
        (
            "deload_off_emphasis@version:pv-1",
            {
                "deload_policy": {
                    "set_cut_pct": 30,
                    "load_cut_pct": 0,
                    "rpe_cap": 8,
                    "test_priority_lifts": True,
                },
                "expected_shape": {
                    "set_cut_pct": 40,
                    "load_cut_pct": 0,
                    "rpe_cap": 8,
                    "test_priority_lifts": True,
                },
            },
        )
    ]
    assert the("deload_off_emphasis", strength) == []


EVERY_MUSCLE_BUT_HAMSTRINGS = [
    "chest",
    "lats",
    "upper_back",
    "front_delts",
    "side_delts",
    "rear_delts",
    "biceps",
    "triceps",
    "quadriceps",
    "glutes",
    "calves",
    "abdominals",
]
MUSCLE_LIBRARY: dict[str, dict[str, object]] = {
    "complex": {
        "load_mode": "total",
        "muscles": {"primary": EVERY_MUSCLE_BUT_HAMSTRINGS, "secondary": []},
    },
    "rdl": {"load_mode": "total", "muscles": {"primary": ["glutes"], "secondary": ["hamstrings"]}},
}


def muscle_gaps(*sessions: dict[str, Any]) -> list[tuple[str, dict[str, object]]]:
    draft = a_draft(a_session("full", a_line("complex")), *sessions)
    return the("muscle_no_hard_sets", warnings_of(draft, a_context(library=MUSCLE_LIBRARY)))


def test_a_muscle_no_core_session_trains_hard_warns_muscle_no_hard_sets() -> None:
    easy = a_line("rdl", sets=[{"count": 3, "reps": 8, "rpe": 5}])
    coach_led = {
        "id": "pt",
        "title": "PT",
        "kind": "coach_led",
        "tier": "core",
        "estimated_sets": {"hamstrings": 3},
    }

    assert muscle_gaps() == [
        (
            "muscle_no_hard_sets@version:pv-1",
            {"muscle": "hamstrings", "sessions_searched": ["full"]},
        )
    ]
    assert muscle_gaps(a_session("legs", a_line("rdl"))) == []
    assert muscle_gaps(a_session("legs", easy))[0][1]["muscle"] == "hamstrings"
    assert muscle_gaps(a_session("legs", a_line("rdl"), tier="optional"))[0][1] == {
        "muscle": "hamstrings",
        "sessions_searched": ["full"],
    }
    assert muscle_gaps(coach_led) == []


def test_a_session_whose_rest_and_sets_run_past_its_minutes_warns_session_over_minutes() -> None:
    def over(minutes: int, *sets: dict[str, Any]) -> list[tuple[str, dict[str, object]]]:
        line = a_line(sets=list(sets), rest_s=120)
        flags = warnings_of(a_draft(a_session("push", line, minutes=minutes)))
        return the("session_over_minutes", flags)

    working = {"count": 4, "reps": [6, 8], "rpe": 8}
    held = {"count": 3, "duration_s": 60, "rpe": 8}

    assert over(10, working) == [
        ("session_over_minutes@session:push", {"estimate": 11, "minutes": 10})
    ]
    assert over(11, working) == []
    assert over(8, held) == [("session_over_minutes@session:push", {"estimate": 9, "minutes": 8})]


def test_a_session_on_a_weekday_the_athlete_cannot_train_warns_session_on_unavailable_day() -> None:
    draft = a_draft(a_session("push"), a_session("pull", a_line("bb_bent_over_row")))
    days = ("monday", "thursday")

    flags = warnings_of(draft, a_context(available_days=days))

    assert the("session_on_unavailable_day", flags) == [
        (
            "session_on_unavailable_day@session:pull",
            {"session_id": "pull", "weekday": "wednesday", "available_days": list(days)},
        )
    ]


def test_every_session_a_weekday_lists_on_an_unavailable_day_warns() -> None:
    draft = a_draft(
        a_session("push"),
        a_session("pull", a_line("bb_bent_over_row")),
        schedule={"rotation": ["A"], "A": {"mon": ["push", "pull"]}},
    )
    days = ("tuesday",)

    flags = warnings_of(draft, a_context(available_days=days))

    assert the("session_on_unavailable_day", flags) == [
        (
            f"session_on_unavailable_day@session:{id_}",
            {"session_id": id_, "weekday": "monday", "available_days": ["tuesday"]},
        )
        for id_ in ("push", "pull")
    ]


def test_supersetted_lines_with_different_rests_warn_superset_rest_differs() -> None:
    def paired(*rests: int) -> list[tuple[str, dict[str, object]]]:
        lines = [
            a_line(exercise, rest_s=rest, superset="arms")
            for exercise, rest in zip(("db_curl", "db_pushdown", "db_fly"), rests, strict=False)
        ]
        return the("superset_rest_differs", warnings_of(a_draft(a_session("arms", *lines))))

    assert paired(60, 90) == [
        ("superset_rest_differs@session:arms", {"superset": "arms", "rest_values": [60, 90]})
    ]
    assert paired(0, 90) == []
    assert paired(0, 90, 90) == []


def test_a_redesign_while_a_block_is_open_warns_block_open_at_redesign() -> None:
    open_block = a_context(open_block=OpenBlock("b-2026-10-05", 3))

    assert the("block_open_at_redesign", warnings_of(a_draft(), open_block)) == [
        ("block_open_at_redesign@version:pv-1", {"block_id": "b-2026-10-05", "hard_weeks": 3})
    ]
    assert the("block_open_at_redesign", warnings_of(a_draft(kind="amend"), open_block)) == []
    assert the("block_open_at_redesign", warnings_of(a_draft())) == []


def an_exposure(load: float | None) -> Exposure:
    sets = (ExposureSet(0, "working", None if load is None else Load(load, "total"), 5, 8),)
    return Exposure("w-0007", "bb_bench_press", datetime.date(2026, 10, 20), sets)


def test_a_start_load_beside_a_different_last_exposure_warns_start_load_ignored() -> None:
    def ignored(load: float | None) -> list[tuple[str, dict[str, object]]]:
        context = a_context(last_exposures={"bb_bench_press": an_exposure(load)})
        return the("start_load_ignored", warnings_of(bench(start_load=60), context))

    assert ignored(65) == [
        (
            "start_load_ignored@line:push/bb_bench_press",
            {
                "start_load": 60,
                "last_exposure_load": 65,
                "exposure": "exposure:w-0007/bb_bench_press",
            },
        )
    ]
    assert ignored(60) == []
    assert the("start_load_ignored", warnings_of(bench(start_load=60))) == []


def test_a_session_the_previous_version_had_warns_session_retired_with_its_routine() -> None:
    previous = parse_program_draft(
        toml(a_draft(a_session("push"), a_session("pull", a_line("bb_bent_over_row")))),
        file="pv-1.toml",
    ).form

    unmapped = warnings_of(a_draft(), a_context(previous=previous))
    mapped = warnings_of(a_draft(), a_context(previous=previous, routines={"pull": "r-9"}))

    assert the("session_retired", unmapped) == [
        ("session_retired@version:pv-1", {"session_id": "pull", "routine_id": None})
    ]
    assert the("session_retired", mapped)[0][1] == {"session_id": "pull", "routine_id": "r-9"}
    same = parse_program_draft(toml(a_draft()), file="pv-1.toml").form
    assert the("session_retired", warnings_of(a_draft(), a_context(previous=same))) == []


ACKNOWLEDGED = {
    "flag": "scheme_off_emphasis@line:push/bb_bench_press",
    "because": "coach_judgement",
    "text": "a technique block",
}


def left_by(entry: dict[str, Any]) -> list[tuple[str, object]]:
    draft = a_draft(a_session("push", a_line(scheme={"name": "linear"})), acknowledge=[entry])
    form = parse_program_draft(toml(draft), file="d.toml").form
    flags = leave_warnings(adopt_warnings(form, a_context()), form.acknowledgements)
    return [(f.key, f.left and f.left.to_json()) for f in flags if f.code == "scheme_off_emphasis"]


def test_an_acknowledgement_leaves_the_warning_its_key_names() -> None:
    assert left_by(ACKNOWLEDGED) == [
        (
            "scheme_off_emphasis@line:push/bb_bench_press",
            {
                "because": "coach_judgement",
                "text": "a technique block",
                "source": "version",
                "evidence": [],
            },
        )
    ]


def test_an_acknowledgement_whose_params_hash_no_longer_matches_is_not_left() -> None:
    [(_, left)] = left_by(ACKNOWLEDGED)
    raised = warnings_of(bench(scheme={"name": "linear"}))
    current = next(f.params_hash for f in raised if f.code == "scheme_off_emphasis")

    assert left_by({**ACKNOWLEDGED, "params_hash": current}) == [
        ("scheme_off_emphasis@line:push/bb_bench_press", left)
    ]
    assert left_by({**ACKNOWLEDGED, "params_hash": "sha256:" + "0" * 64}) == [
        ("scheme_off_emphasis@line:push/bb_bench_press", None)
    ]


def a_form(draft: dict[str, Any]) -> Any:
    return parse_program_draft(toml(draft), file="d.toml").form


def a_signal(code: str, scheme: str, may_schemes: list[str]) -> Flag:
    return raise_flag(
        code,
        Scope("exercise", exercise_id="bb_bench_press"),
        {"scheme": scheme, "metric": {}, "may_schemes": may_schemes, "may": "", "never": ""},
        "signal",
    )


TOP_BACKOFF = {"name": "top_backoff", "pct_of_top": 85}
TOP_SETS = [{"count": 1, "reps": 5, "rpe": 8}, {"count": 3, "reps": 5, "rpe": 7}]
WAVE_SETS = [{"count": 3, "reps": 5}]


def moved(previous: dict[str, Any], now: dict[str, Any], *signals: Flag) -> list[Any]:
    context = a_context(
        version_id="pv-2",
        previous=a_form(bench(**previous)),
        signals={s.scope.exercise_id: s for s in signals},
    )
    return the("scheme_change_off_signal", warnings_of(bench(**now), context))


def test_moving_top_backoff_to_wave_531_under_an_open_cadence_slow_raises_nothing() -> None:
    slow = a_signal("cadence_slow", "top_backoff", ["wave_531"])
    previous = {"scheme": TOP_BACKOFF, "sets": TOP_SETS}
    now = {"scheme": {"name": "wave_531"}, "sets": WAVE_SETS}

    assert moved(previous, now, slow) == []


def test_the_same_move_with_no_signal_warns_scheme_change_off_signal() -> None:
    previous = {"scheme": TOP_BACKOFF, "sets": TOP_SETS}
    now = {"scheme": {"name": "wave_531"}, "sets": WAVE_SETS}

    assert moved(previous, now) == [
        (
            "scheme_change_off_signal@line:push/bb_bench_press",
            {
                "previous_scheme": "top_backoff",
                "new_scheme": "wave_531",
                "signal_key": None,
                "may_schemes": [],
            },
        )
    ]


def test_a_move_outside_the_signals_may_schemes_warns_scheme_change_off_signal() -> None:
    slow = a_signal("cadence_slow", "double_progression", [])

    assert moved({}, {"scheme": {"name": "linear"}}, slow) == [
        (
            "scheme_change_off_signal@line:push/bb_bench_press",
            {
                "previous_scheme": "double_progression",
                "new_scheme": "linear",
                "signal_key": "cadence_slow@exercise:bb_bench_press",
                "may_schemes": [],
            },
        )
    ]


def test_an_unchanged_scheme_or_an_exercise_new_to_the_version_raises_nothing() -> None:
    new_exercise = a_context(
        version_id="pv-2", previous=a_form(a_draft(a_session("push", a_line("db_curl"))))
    )
    linear = bench(scheme={"name": "linear"})

    assert moved({}, {}) == []
    assert the("scheme_change_off_signal", warnings_of(linear, new_exercise)) == []


VERTICAL_PULL: dict[str, object] = {
    "pattern": "vertical_pull",
    "muscles": {"primary": ["lats"], "secondary": []},
}
PULL_LIBRARY: dict[str, dict[str, object]] = LIBRARY | {
    "bb_bench_press": {**LIBRARY["bb_bench_press"], "pattern": "horizontal_push"},
    "pull_up": VERTICAL_PULL,
    "lat_pulldown": {
        **VERTICAL_PULL,
        "muscles": {"primary": ["lats"], "secondary": ["biceps"]},
    },
    "straight_arm_pulldown": {**VERTICAL_PULL, "pattern": "shoulder_extension"},
}
PULL_UP_PRIORITY = a_context(library=PULL_LIBRARY, goal=a_goal(priority_lifts=("pull_up",)))


def counting(*variants: str, **draft: Any) -> dict[str, Any]:
    lift = {"pull_up": {"sets": 8, "counts": list(variants)}}
    return a_draft(
        a_session("pull", a_line("pull_up")), dose={"per_muscle": 10, "lift": lift}, **draft
    )


def test_a_variant_sharing_the_lifts_pattern_and_primary_muscles_raises_nothing() -> None:
    flags = warnings_of(counting("lat_pulldown"), PULL_UP_PRIORITY)

    assert the("counted_variant_off_pattern", flags) == []
    assert the("dose_off_band", flags) == []


def test_a_variant_off_the_lifts_pattern_or_muscles_warns_counted_variant_off_pattern() -> None:
    flags = warnings_of(counting("lat_pulldown", "bb_bench_press"), PULL_UP_PRIORITY)
    pattern_only = warnings_of(counting("straight_arm_pulldown"), PULL_UP_PRIORITY)

    assert the("counted_variant_off_pattern", flags) == [
        (
            "counted_variant_off_pattern@version:pv-1",
            {
                "lift": "pull_up",
                "variant": "bb_bench_press",
                "patterns": ["vertical_pull", "horizontal_push"],
                "primary_muscles": [["lats"], ["chest"]],
            },
        )
    ]
    assert [p["variant"] for _, p in the("counted_variant_off_pattern", pattern_only)] == [
        "straight_arm_pulldown"
    ]


def test_an_acknowledgement_leaves_counted_variant_off_pattern() -> None:
    entry = {
        "flag": "counted_variant_off_pattern@version:pv-1",
        "because": "coach_judgement",
        "text": "the coach counts it on purpose",
    }
    form = a_form(counting("bb_bench_press", acknowledge=[entry]))

    flags = leave_warnings(adopt_warnings(form, PULL_UP_PRIORITY), form.acknowledgements)

    [flag] = [f for f in flags if f.code == "counted_variant_off_pattern"]
    assert flag.left is not None


def test_a_lifts_counted_variants_on_lines_never_stand_in_for_the_lift() -> None:
    lift = {"pull_up": {"sets": 8, "counts": ["lat_pulldown"]}}
    draft = a_draft(
        a_session("pull", a_line("lat_pulldown")), dose={"per_muscle": 10, "lift": lift}
    )

    assert the("priority_lift_absent", warnings_of(draft, PULL_UP_PRIORITY)) == [
        ("priority_lift_absent@version:pv-1", {"exercise_id": "pull_up"})
    ]
