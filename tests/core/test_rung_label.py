import datetime

import pytest

from coach.core.exercise_ladder import StandingRung, climb_offer, rung_label
from coach.core.exposure import Exposure, ExposureSet, Matched
from coach.core.flag import Flag, Scope
from coach.core.prescription import RungNaming
from coach.core.program.form import ExerciseLadder, Line, Rung, SchemeRef, SetGroup

TEMPO = (SetGroup(4, reps=4, rpe=8),)
NAMES = {
    "pull_up_negative": "Pull-up negative",
    "weighted_negative": "Weighted negative",
    "board": "Balance board: stand",
    "board_tilts": "Balance board: tilts",
}
NAMING = RungNaming("kg", NAMES)
PULL = ExerciseLadder(
    (
        Rung("pull_up_negative", TEMPO, "lower for 4 s"),
        Rung("pull_up_negative", TEMPO, "lower for 6 s"),
        Rung("weighted_negative", TEMPO, "lower for 6 s", start_load=5),
        Rung("pull_up_negative", (SetGroup(1, type="warm_up", reps=2), SetGroup(5, reps=(3, 5)))),
    )
)
BOARD = ExerciseLadder(
    (
        Rung("board", (SetGroup(2, duration_s=45, rpe=6),), "feet apart"),
        Rung("board_tilts", (SetGroup(2, duration_s=60, rpe=6),), "tilt slowly"),
        Rung("board", (SetGroup(1, reps="8+"),)),
        Rung("board", (SetGroup(3, reps="8+"),)),
    )
)


def a_line(ladder: ExerciseLadder, start_load: float | None = None) -> Line:
    return Line(
        exercise=ladder.rungs[0].exercise,
        sets=(),
        rest_s=120,
        scheme=SchemeRef("exercise_ladder", {}, ladder),
        start_load=start_load,
    )


def label(
    ladder: ExerciseLadder, index: int, standing: int, start_load: float | None = None
) -> str:
    return rung_label(a_line(ladder, start_load), ladder, index, standing=standing, naming=NAMING)


def test_a_rung_on_the_standing_rungs_exercise_reads_its_index_dose_and_cues() -> None:
    assert label(PULL, 2, standing=1) == "rung 2 · 4×4 @8 · lower for 6 s"


def test_a_rung_on_another_exercise_is_named_with_its_load_after_the_dose() -> None:
    assert (
        label(PULL, 3, standing=2) == "rung 3 · Weighted negative · 4×4 @8 · 5 kg · lower for 6 s"
    )


def test_a_timed_rung_reads_its_duration() -> None:
    assert label(BOARD, 2, standing=1) == "rung 2 · Balance board: tilts · 2×60 s @6 · tilt slowly"


def test_the_standing_rung_reads_without_its_name() -> None:
    assert label(BOARD, 2, standing=2) == "rung 2 · 2×60 s @6 · tilt slowly"


def test_the_name_is_measured_from_the_standing_rung_not_the_rung_before() -> None:
    assert label(PULL, 2, standing=3) == "rung 2 · Pull-up negative · 4×4 @8 · lower for 6 s"


def test_an_empty_segment_leaves_no_separator_and_a_warm_up_is_not_the_dose() -> None:
    assert label(PULL, 4, standing=1) == "rung 4 · 5×3–5"


@pytest.mark.parametrize(
    ("index", "dose"),
    [(3, "8+"), (4, "3×8+")],
)
def test_a_rep_out_reads_as_the_routine_note_reads_it(index: int, dose: str) -> None:
    assert label(BOARD, index, standing=3) == f"rung {index} · {dose}"


def test_the_first_rung_reads_the_lines_start_load() -> None:
    assert label(BOARD, 1, standing=1, start_load=12.5) == (
        "rung 1 · 2×45 s @6 · 12.5 kg · feet apart"
    )


def test_a_load_reads_in_the_athletes_units() -> None:
    naming = RungNaming("lb", NAMES)
    line = a_line(PULL)

    found = rung_label(line, PULL, 3, standing=1, naming=naming)

    assert found == "rung 3 · Weighted negative · 4×4 @8 · 5 lb · lower for 6 s"


def test_an_exercise_missing_from_the_library_shows_its_id() -> None:
    naming = RungNaming("kg", {})
    line = a_line(PULL)

    found = rung_label(line, PULL, 3, standing=1, naming=naming)

    assert found == "rung 3 · weighted_negative · 4×4 @8 · 5 kg · lower for 6 s"


CORE = ExerciseLadder(
    (
        Rung("dead_bug", (SetGroup(3, reps=10, rpe=8),)),
        Rung("ab_wheel", (SetGroup(3, reps=8, rpe=8),), "brace"),
    )
)
TOPPED = ExerciseLadder((*CORE.rungs, Rung("hanging_leg_raise", (SetGroup(3, reps=6, rpe=8),))))
OFFER_NAMES = RungNaming("kg", {"ab_wheel": "Ab Wheel"})
MONDAY = datetime.date(2026, 11, 2)


def a_clean_log(exercise: str, day: int, reps: int) -> Exposure:
    return Exposure(
        f"w-{day}",
        exercise,
        datetime.date(2026, 10, day),
        tuple(ExposureSet(i, "working", None, reps, 8) for i in range(3)),
        Matched("lower"),
    )


def offer(ladder: ExerciseLadder, standing: int, exercise: str, reps: int) -> Flag:
    found = climb_offer(
        a_line(ladder),
        ladder,
        StandingRung(standing, None),
        (a_clean_log(exercise, 19, reps), a_clean_log(exercise, 26, reps)),
        scope=Scope("line", MONDAY, session_id="lower", exercise_id="dead_bug"),
        on=MONDAY,
        naming=OFFER_NAMES,
    )
    assert found is not None
    return found


def test_rung_met_keeps_the_next_rungs_exercise_and_gains_its_index() -> None:
    assert offer(CORE, 1, "dead_bug", 10).params == {
        "rung": 1,
        "next": "ab_wheel",
        "next_rung": 2,
        "exposures": ["exposure:w-19/dead_bug", "exposure:w-26/dead_bug"],
    }


def test_rung_mets_message_offers_the_next_rung_by_its_label() -> None:
    assert offer(CORE, 1, "dead_bug", 10).message == (
        "rung 1 met its criterion on 2 exposures; rung 2 · Ab Wheel · 3×8 @8 · brace is offered"
    )


def test_rung_met_keeps_the_hash_a_stored_acknowledgement_holds() -> None:
    assert offer(CORE, 1, "dead_bug", 10).params_hash == (
        "sha256:d7d9f74205c5b13012ac4d2bcf56fca26cb7037186bdd2d773018657d2f0523d"
    )


def test_ladder_top_keeps_the_hash_a_stored_acknowledgement_holds() -> None:
    found = offer(TOPPED, 3, "hanging_leg_raise", 6)

    assert found.code == "ladder_top"
    assert found.params_hash == (
        "sha256:25a4183e6bbee161b88d43664a706180e1ef2bd717c0a6b978acfb3dfc685122"
    )
