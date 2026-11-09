import base64
import dataclasses
import re
import zlib

from coach.core.config import ImplementChoice
from coach.core.exercise_ladder import RungShape
from coach.core.pages import PageLine, PlatePoolKit, RoutinePage
from coach.core.rack import ListedRack, RackRow
from coach.render.routine_page import routine_page

INVENTORY = b'{"plates": [{"lb": 45, "count": 4}, {"lb": 25, "count": 2}]}\n'
HOME = PlatePoolKit(
    location="home",
    implements={
        "barbell": "barbell",
        "dumbbell": "dumbbell",
        "leg_attachment": "leg",
        "bodyweight": "vest",
    },
    implement={
        "barbell": ImplementChoice(hardware="collar-clamp"),
        "dumbbell": ImplementChoice(hardware="screw-standard"),
        "leg": ImplementChoice(),
        "vest": ImplementChoice(),
    },
    short_hash="3f9a01bc",
    inventory=INVENTORY,
)
SQUAT = PageLine(
    exercise_id="bb_back_squat",
    name="Back Squat (Barbell)",
    equipment_kind="barbell",
    set_groups=(
        {"type": "warm_up", "count": 1, "reps": 5, "load": 95, "load_kg": 43.09},
        {"type": "working", "count": 4, "range": [6, 8], "rpe": 8, "load": 175, "load_kg": 79.38},
    ),
)
CURL = PageLine(
    exercise_id="db_curl",
    name="Bicep Curl (Dumbbell)",
    equipment_kind="dumbbell",
    set_groups=({"type": "working", "count": 3, "range": [10, 12], "load": 30, "load_kg": 13.61},),
)
LEG_CURL = PageLine(
    exercise_id="leg_curl",
    name="Leg Curl",
    equipment_kind="leg_attachment",
    set_groups=({"type": "working", "count": 3, "range": [10, 12], "load": 40, "load_kg": 18.14},),
)
PULL_UP = PageLine(
    exercise_id="pull_up",
    name="Pull Up",
    equipment_kind="bodyweight",
    set_groups=({"type": "working", "count": 3, "range": [5, 8]},),
)


def a_page(location: str = "home", kit: PlatePoolKit | None = HOME) -> RoutinePage:
    return RoutinePage(
        session_id="lower",
        title="Lower A",
        week="2026-11-02",
        location=location,
        lines=(SQUAT, CURL, LEG_CURL, PULL_UP),
        kit=kit,
    )


def links(text: str) -> list[str]:
    return re.findall(r"\((https://[^)]+)\)", text)


def test_a_plate_pool_routine_page_links_each_loaded_line_with_the_kit_hash() -> None:
    text = routine_page(a_page(), units="lb")

    line_links = [link for link in links(text) if "kit=3f9a01bc" in link]
    assert line_links == [
        "https://joeuk89.github.io/plate-pool/?barbell=175lb&barbell.hardware=collar-clamp&kit=3f9a01bc",
        "https://joeuk89.github.io/plate-pool/?dumbbell=30lb&dumbbell.hardware=screw-standard&kit=3f9a01bc",
        "https://joeuk89.github.io/plate-pool/?leg=40lb&kit=3f9a01bc",
    ]


def test_a_handle_rounded_single_is_linked_by_its_single_key() -> None:
    single = {**HOME.implement, "dumbbell": ImplementChoice(hardware="none", single=True)}
    kit = dataclasses.replace(HOME, implement=single)

    text = routine_page(a_page(kit=kit), units="lb")

    assert (
        "https://joeuk89.github.io/plate-pool/?dumbbell.single=30lb&dumbbell.hardware=none&kit=3f9a01bc"
        in links(text)
    )


SPLIT_DUMBBELL = ListedRack(
    (
        RackRow(30, hardware="screw-standard"),
        RackRow(70, hardware="screw-standard"),
        RackRow(100, hardware="screw-long"),
    )
)


def a_curl_at(load: float) -> PageLine:
    working = {"type": "working", "count": 3, "range": [10, 12], "load": load}
    return dataclasses.replace(CURL, set_groups=(working,))


def a_curl_link(load: float, hardware: str | tuple[str, ...] | None) -> str:
    kit = dataclasses.replace(
        HOME,
        implement={**HOME.implement, "dumbbell": ImplementChoice(hardware=hardware)},
        racks={"dumbbell": SPLIT_DUMBBELL},
    )
    page = dataclasses.replace(a_page(kit=kit), lines=(a_curl_at(load),))
    return next(link for link in links(routine_page(page, units="lb")) if "kit=" in link)


def test_a_hardware_list_links_the_hardware_of_the_row_the_heaviest_load_lands_on() -> None:
    choice = ("screw-standard", "screw-long")

    assert a_curl_link(100, choice).endswith(
        "?dumbbell=100lb&dumbbell.hardware=screw-long&kit=3f9a01bc"
    )
    assert a_curl_link(70, choice).endswith(
        "?dumbbell=70lb&dumbbell.hardware=screw-standard&kit=3f9a01bc"
    )


def test_a_hardware_list_links_its_first_id_for_a_load_no_row_has() -> None:
    link = a_curl_link(85, ("screw-long", "screw-standard"))

    assert link.endswith("?dumbbell=85lb&dumbbell.hardware=screw-long&kit=3f9a01bc")


def test_a_hardware_string_links_its_one_id_whatever_row_the_load_lands_on() -> None:
    assert a_curl_link(100, "screw-standard").endswith(
        "?dumbbell=100lb&dumbbell.hardware=screw-standard&kit=3f9a01bc"
    )


def test_an_implement_with_no_hardware_links_no_hardware() -> None:
    assert a_curl_link(100, None).endswith("?dumbbell=100lb&kit=3f9a01bc")


def test_a_plate_pool_routine_page_carries_one_set_up_link_with_the_inventory_inline() -> None:
    text = routine_page(a_page(), units="lb")

    set_up = [link for link in links(text) if "kit=3f9a01bc" not in link]
    assert len(set_up) == 1
    assert set_up[0].startswith("https://joeuk89.github.io/plate-pool/#inventory=")
    encoded = set_up[0].removeprefix("https://joeuk89.github.io/plate-pool/#inventory=")
    assert "=" not in encoded
    padded = encoded + "=" * (-len(encoded) % 4)
    assert zlib.decompress(base64.urlsafe_b64decode(padded), -15) == INVENTORY


def test_a_grid_routine_page_carries_no_plate_pool_link() -> None:
    text = routine_page(a_page("gym", kit=None), units="lb")

    assert links(text) == []
    assert "175 lb" in text


def test_a_routine_page_states_loads_in_athlete_units_and_is_headed_by_its_routine_title() -> None:
    text = routine_page(a_page(), units="lb")

    assert "# Lower A" in text
    assert "4×6–8 @8 at 175 lb" in text
    assert "79.38" not in text
    assert "hand edits are overwritten" in text.splitlines()[0]


def test_a_ladder_line_prints_every_rung_under_it_with_the_standing_rung_marked() -> None:
    board = PageLine(
        exercise_id="custom_balance_board_stand",
        name="Balance board: two feet, still",
        equipment_kind="bodyweight",
        set_groups=({"type": "working", "count": 2, "duration_s": 30, "rpe": 5},),
        ladder=(
            RungShape(
                rung=1,
                exercise="custom_balance_board_stand",
                label="rung 1 · 2×30 s @5 · near a wall",
                cues="near a wall",
                set_groups=({"count": 2, "duration_s": 30, "rpe": 5},),
                criterion={"duration_s": 30, "rpe_at_most": 5, "exposures": 2},
                standing=True,
            ),
            RungShape(
                rung=2,
                exercise="custom_balance_board_one_foot",
                label="rung 2 · Balance board: one foot, eyes closed · 4×8 @7",
                cues=None,
                set_groups=({"count": 4, "reps": 8, "rpe": 7},),
                criterion={"manual": True},
                standing=False,
            ),
        ),
    )
    page = RoutinePage("daily-balance", "Balance", None, None, (board,))

    text = routine_page(page, units="lb")

    assert (
        "Ladder:\n\n"
        "- **rung 1 · 2×30 s @5 · near a wall** (standing). "
        "Climb on 30 s at RPE 5 or under, 2 exposures running.\n"
        "- rung 2 · Balance board: one foot, eyes closed · 4×8 @7. "
        "Climb when you and the coach agree."
    ) in text


def test_a_rung_criterion_with_neither_reps_nor_duration_names_only_what_it_holds() -> None:
    rung = RungShape(
        rung=1,
        exercise="push_up",
        label="rung 1 · 3×8+ @8",
        cues=None,
        set_groups=({"count": 3, "reps": "8+", "rpe": 8},),
        criterion={"rpe_at_most": 8, "exposures": 2},
        standing=True,
    )
    line = PageLine(
        exercise_id="push_up",
        name="Push-up",
        equipment_kind="bodyweight",
        set_groups=({"type": "working", "count": 3, "reps": "8+", "rpe": 8},),
        ladder=(rung,),
    )

    text = routine_page(RoutinePage("s", "S", None, None, (line,)), units="lb")

    assert "None" not in text
    assert "Climb on RPE 8 or under, 2 exposures running." in text


def test_a_routine_page_says_the_sessions_name_and_not_its_id() -> None:
    text = routine_page(a_page(), units="lb")

    assert "Session Lower A at home as written for the week of 2026-11-02." in text
    assert "lower" not in text
