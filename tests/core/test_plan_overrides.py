import datetime
import tomllib

import pytest

from coach.core.errors import Invalid
from coach.core.overrides import override_conflicts, parse_plan_overrides
from coach.core.prescription import PlanOverride
from coach.core.program.form import SetGroup

WEEK = datetime.date(2026, 11, 2)
REASON = 'because = "schedule"\ntext = "Away."\n'

# The three overrides of the plan Draft shape in the override catalogue.
CATALOGUE_DRAFT = """\
[[override]]
kind = "light_week"
load_cut_pct = 10
because = "fatigue"
text = "Sixth hard week and the squat drifted two sessions running."

[[override]]
kind = "swap_exercise"
session = "a-mon-lower"
exercise = "bb_back_squat"
to = "goblet_squat"
start_load = 24
because = "pain"
text = "Knee niggle flares under the bar; the goblet keeps the pattern."
evidence = ["niggle:n-0004"]

[[override]]
kind = "pin_load"
session = "b-sat-push"
exercise = "bb_bench_press"
load = 100
because = "coach_judgement"
text = "Open the new block two steps under the model; the last exposure was a grinder."
evidence = ["exposure:b7e2c1a0-5d3f-4e8a-9c21-7f0a4d6b9e13/bb_bench_press"]
"""


def parsed(text: str) -> tuple[PlanOverride, ...]:
    return parse_plan_overrides(tomllib.loads(text), file="plan.toml")


def an_override(kind: str, body: str = "") -> str:
    return f'[[override]]\nkind = "{kind}"\n{body}{REASON}'


def test_the_catalogue_draft_parses_each_scope_from_the_refs_present() -> None:
    light, swap, pin = parsed(CATALOGUE_DRAFT)

    assert light == PlanOverride(
        "light_week",
        params={"load_cut_pct": 10},
        because="fatigue",
        text="Sixth hard week and the squat drifted two sessions running.",
    )
    assert (swap.kind, swap.session_id, swap.exercise_id) == (
        "swap_exercise",
        "a-mon-lower",
        "bb_back_squat",
    )
    assert swap.params == {"to": "goblet_squat", "start_load": 24}
    assert swap.evidence == ("niggle:n-0004",)
    assert (pin.session_id, pin.exercise_id, pin.params) == (
        "b-sat-push",
        "bb_bench_press",
        {"load": 100},
    )


def test_session_kinds_read_their_params() -> None:
    move, add, relocate, minimum = parsed(
        an_override("move_session", 'session = "lower"\nto = 2026-11-04\n')
        + an_override("add_session", 'session = "lower"\ndate = 2026-11-06\nlocation = "gym"\n')
        + an_override("relocate_session", 'session = "upper"\nlocation = "gym"\n')
        + an_override("minimum_week", 'keep = ["lower", "upper"]\n')
    )

    assert move.params == {"to": datetime.date(2026, 11, 4)}
    assert (add.session_id, add.date, add.params) == (
        "lower",
        datetime.date(2026, 11, 6),
        {"location": "gym"},
    )
    assert relocate.params == {"location": "gym"}
    assert minimum.params == {"keep": ("lower", "upper")}


def test_restate_sets_reads_the_lines_whole_set_groups() -> None:
    [restate] = parsed(
        an_override(
            "restate_sets",
            'session = "lower"\nexercise = "bb_back_squat"\n'
            'sets = [{ count = 1, type = "warm_up", reps = 5 },'
            " { count = 3, reps = 5, rpe = 7 }]\n",
        )
    )

    assert restate.params == {
        "sets": (SetGroup(1, "warm_up", 5), SetGroup(3, "working", 5, None, 7))
    }


@pytest.mark.parametrize(
    ("body", "wanted"),
    [
        (an_override("pin_load", 'session = "lower"\nexercise = "bb_back_squat"\n'), "load"),
        (an_override("hold", 'session = "lower"\n'), "exercise"),
        (an_override("drop_session"), "session"),
        (an_override("light_week", 'session = "lower"\n'), "session"),
        (an_override("minimum_week", 'keep = ["a", "b", "c"]\n'), "keep"),
        (an_override("hold", 'session = "lower"\nexercise = "x"\nload = 3\n'), "load"),
        ('[[override]]\nkind = "hold"\nsession = "s"\nexercise = "x"\ntext = "t"\n', "because"),
        (an_override("nap_session", 'session = "lower"\n'), "kind"),
    ],
)
def test_a_malformed_override_is_refused_naming_the_field(body: str, wanted: str) -> None:
    with pytest.raises(Invalid) as raised:
        parsed(body)

    assert wanted in raised.value.message


def test_two_overrides_of_one_kind_on_one_line_conflict_naming_both() -> None:
    hold = an_override("hold", 'session = "lower"\nexercise = "bb_back_squat"\n')

    [flag] = override_conflicts(parsed(hold + hold), WEEK)

    assert flag.code == "override_conflict"
    assert flag.severity == "violation"
    assert flag.key == "override_conflict@line:2026-11-02/lower/bb_back_squat"
    assert flag.params == {"kinds": ["hold", "hold"]}


def test_minimum_week_beside_light_week_conflicts_on_the_week() -> None:
    overrides = parsed(
        an_override("light_week") + an_override("minimum_week", 'keep = ["lower"]\n')
    )

    [flag] = override_conflicts(overrides, WEEK)

    assert flag.key == "override_conflict@week:2026-11-02"
    assert flag.params == {"kinds": ["light_week", "minimum_week"]}


def test_hold_beside_a_pin_on_one_line_conflicts() -> None:
    line = 'session = "lower"\nexercise = "bb_back_squat"\n'
    overrides = parsed(an_override("hold", line) + an_override("pin_load", line + "load = 100\n"))

    assert [f.params for f in override_conflicts(overrides, WEEK)] == [
        {"kinds": ["hold", "pin_load"]}
    ]


def test_overrides_the_precedence_table_allows_raise_nothing() -> None:
    overrides = parsed(
        an_override("add_session", 'session = "lower"\ndate = 2026-11-03\n')
        + an_override("add_session", 'session = "lower"\ndate = 2026-11-05\n')
        + an_override("drop_session", 'session = "upper"\n')
        + an_override("move_session", 'session = "upper"\nto = 2026-11-04\n')
        + an_override("swap_exercise", 'session = "lower"\nexercise = "a"\nto = "b"\n')
        + an_override("pin_load", 'session = "lower"\nexercise = "a"\nload = 50\n')
        + an_override("hold", 'session = "lower"\nexercise = "c"\n')
        + an_override("light_week")
    )

    assert override_conflicts(overrides, WEEK) == ()
