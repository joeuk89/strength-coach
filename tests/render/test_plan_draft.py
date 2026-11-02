import dataclasses
import datetime
import tomllib

from support.exposures import an_exposure
from support.prescribe import a_line, a_request

from coach.core.flag import Scope, raise_flag
from coach.core.plan_draft import AthleteNote, PlanDraft
from coach.core.planned_week import RotationPosition
from coach.core.prescribe import prescribe
from coach.core.prescription import PlanOverride
from coach.render.plan_draft import plan_draft

MONDAY = datetime.date(2026, 11, 2)
SQUAT = an_exposure("2026-10-26", *[(120, 8, 8)] * 4, workout_id="h-1", exercise_id="bb_back_squat")


def a_plan_draft(*notes: AthleteNote, supersedes: str | None = None) -> PlanDraft:
    session = prescribe(a_request(a_line(), exposures=(SQUAT,)))
    return PlanDraft(
        week=MONDAY,
        position=RotationPosition("A", "program_adopt"),
        sessions=(session,),
        notes=notes,
        supersedes=supersedes,
    )


def test_the_draft_carries_the_week_the_unconfirmed_position_and_empty_override_arrays() -> None:
    document = tomllib.loads(plan_draft(a_plan_draft(), units="lb"))

    assert document["week"] == MONDAY
    assert document["position"] == {"week": "A", "source": "program_adopt", "confirmed": False}
    assert document["override"] == []
    assert document["acknowledge"] == []
    assert document["note"] == []
    assert [flag["code"] for flag in document["flag"]] == ["rotation_unconfirmed"]
    assert "supersedes" not in document


def test_each_line_carries_its_prescription_steps_and_change() -> None:
    document = tomllib.loads(plan_draft(a_plan_draft(), units="lb"))

    session = document["session"][0]
    assert (session["id"], session["date"], session["location"]) == ("lower", MONDAY, "home")
    line = session["line"][0]
    assert line["exercise"] == "bb_back_squat"
    assert line["derived_from"] == "exposure:h-1/bb_back_squat"
    assert line["change"] == "4×6–8 @8: 120 → 125"
    assert line["sets"][-1] == {
        "type": "working",
        "count": 4,
        "load": 125.0,
        "load_kg": 56.6990,
        "reps": [6, 8],
        "rpe": 8,
    }
    assert line["step"][0] == {"step": "scheme", "from": 120, "to": 125.0, "cause": "hit"}
    assert line["step"][-1]["to"] == [60.0, 90.0]


def test_every_athlete_note_is_carried_verbatim_and_placed_beside_what_it_is_about() -> None:
    notes = (
        AthleteNote(datetime.date(2026, 10, 28), 'Knee felt "tight"\non stairs.', None),
        AthleteNote(datetime.date(2026, 10, 29), "Squat felt heavy.", "exercise:bb_back_squat"),
    )

    document = tomllib.loads(plan_draft(a_plan_draft(*notes), units="lb"))

    assert document["note"] == [
        {"date": datetime.date(2026, 10, 28), "text": 'Knee felt "tight"\non stairs.'},
        {
            "date": datetime.date(2026, 10, 29),
            "text": "Squat felt heavy.",
            "about": "exercise:bb_back_squat",
        },
    ]
    assert document["session"][0]["line"][0]["notes"] == ["Squat felt heavy."]


def test_a_superseding_draft_names_the_plan_it_supersedes() -> None:
    document = tomllib.loads(plan_draft(a_plan_draft(supersedes="wp-2026-11-02"), units="lb"))

    assert document["supersedes"] == "wp-2026-11-02"


def test_a_capped_set_carries_its_rpe_cap() -> None:
    light = PlanOverride("light_week")
    session = prescribe(a_request(a_line(), exposures=(SQUAT,), overrides=(light,)))
    draft = PlanDraft(MONDAY, RotationPosition("A", "program_adopt"), (session,))

    working = tomllib.loads(plan_draft(draft, units="lb"))["session"][0]["line"][0]["sets"][-1]

    assert (working["rpe"], working["rpe_cap"]) == (8, 8)


def test_every_flag_table_carries_the_key_and_params_hash_an_acknowledgement_copies() -> None:
    session = prescribe(a_request(a_line(), exposures=(SQUAT,)))
    squat = Scope("line", MONDAY, session_id="lower", exercise_id="bb_back_squat")
    stall = raise_flag(
        "stall_streak", squat, {"streak": 3, "exposures": ["exposure:h-1/bb_back_squat"]}, "m"
    )
    line = dataclasses.replace(session.lines[0], flags=(stall,))
    session = dataclasses.replace(session, lines=(line,))
    draft = PlanDraft(MONDAY, RotationPosition("A", "program_adopt"), (session,))

    document = tomllib.loads(plan_draft(draft, units="lb"))

    [week_flag] = document["flag"]
    [line_flag] = document["session"][0]["line"][0]["flag"]
    assert (week_flag["key"], week_flag["params_hash"]) == (
        "rotation_unconfirmed@week:2026-11-02",
        "sha256:15a498510e347e58c8eeb3465628f15434d46e9ce0be0adeb0f5fc56f30ddc46",
    )
    assert (line_flag["key"], line_flag["params_hash"]) == (
        "stall_streak@line:2026-11-02/lower/bb_back_squat",
        "sha256:947848d5ce2e2c8d418ac794802e5b2678a1b8ad0f35b43b6e648ce1a68e6af3",
    )
