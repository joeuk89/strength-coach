from coach.core.registries.schemes import SCHEMES


def test_linear_carries_its_two_params_with_their_registry_defaults() -> None:
    linear = SCHEMES.get("linear")

    assert {p.name: p.default for p in linear.params} == {
        "misses_before_reset": 2,
        "reset_factor": 0.9,
    }
    assert linear.rpe_on == "every_working"


def test_the_assistance_ladder_drives_one_working_group_from_its_required_rungs() -> None:
    ladder = SCHEMES.get("assistance_ladder")

    assert [(p.name, p.required) for p in ladder.params] == [("rungs", True)]
    assert ladder.set_types == ("working",)
    assert ladder.set_groups == "one_working"


def test_top_backoff_requires_rpe_on_the_top_group_only() -> None:
    top_backoff = SCHEMES.get("top_backoff")

    assert top_backoff.rpe_on == "top"
    assert top_backoff.set_groups == "top_then_backoffs"
    assert top_backoff.set_types == ("warm_up", "working")


def test_wave_531_holds_the_published_waves_and_takes_count_only() -> None:
    wave = SCHEMES.get("wave_531")

    assert wave.params == ()
    assert wave.set_groups == "count_only"
    assert wave.describe()["holds"] == {
        "waves": [[65, 75, 85], [70, 80, 90], [75, 85, 95]],
        "reps": ["5+", "3+", "1+"],
    }


def test_hold_reads_no_rpe_and_permits_activation() -> None:
    hold = SCHEMES.get("hold")

    assert hold.rpe_on == "none"
    assert "activation" in hold.set_types


def test_the_session_schemes_name_their_params() -> None:
    emom = SCHEMES.get("emom_density")

    assert emom.level == "session"
    assert [p.name for p in emom.params] == [
        "minutes",
        "minutes_cap",
        "minutes_step",
        "reps",
        "reps_cap",
        "rpe_target",
    ]
    assert [p.name for p in SCHEMES.get("circuit_rounds").params] == [
        "rounds",
        "rounds_cap",
        "time_cap_minutes",
        "reps",
        "rpe_target",
    ]


def test_every_row_describes_its_reads_and_opening_position() -> None:
    rows = {row["name"]: row for row in SCHEMES.rows()}

    assert rows["double_progression"]["opening"] == "start_load at the bottom of the rep range"
    assert rows["linear"]["params"] == [
        {"name": "misses_before_reset", "type": "integer", "default": 2},
        {"name": "reset_factor", "type": "fraction", "default": 0.9},
    ]
    assert rows["top_backoff"]["params"] == [
        {"name": "pct_of_top", "type": "percent", "required": True}
    ]
    assert all(row["reads"] for row in rows.values())


def test_the_exercise_ladder_names_its_rung_table_and_the_five_criterion_keys() -> None:
    ladder = SCHEMES.get("exercise_ladder")

    assert ladder.describe() == {
        "name": "exercise_ladder",
        "level": "line",
        "params": [
            {
                "name": "rungs",
                "type": "rungs",
                "required": True,
                "keys": ["exercise", "cues", "sets", "advance"],
            },
            {
                "name": "advance",
                "type": "criterion",
                "default": {"exposures": 2},
                "keys": ["reps", "duration_s", "rpe_at_most", "exposures", "manual"],
            },
        ],
        "set_types": ["working"],
        "set_groups": "one_working",
        "rpe_on": "every_working",
        "opening": "the first rung",
        "reads": "reps or duration at RPE on the standing rung",
        "reads_training_max": False,
        "cadence_signals": ["cadence_slow"],
    }
