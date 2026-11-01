import base64
import re
import zlib

from coach.core.pages import PageLine, PlatePoolKit, RoutinePage
from coach.render.routine_page import routine_page

INVENTORY = b'{"plates": [{"lb": 45, "count": 4}, {"lb": 25, "count": 2}]}\n'
HOME = PlatePoolKit(
    location="home",
    collars="clamp",
    dumbbells="pair",
    implements={"barbell": "barbell", "dumbbell": "dumbbell", "bodyweight": "vest"},
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
        lines=(SQUAT, CURL, PULL_UP),
        kit=kit,
    )


def links(text: str) -> list[str]:
    return re.findall(r"\((https://[^)]+)\)", text)


def test_a_plate_pool_routine_page_links_each_loaded_line_with_the_kit_hash() -> None:
    text = routine_page(a_page(), units="lb")

    line_links = [link for link in links(text) if "kit=3f9a01bc" in link]
    assert line_links == [
        "https://joeuk89.github.io/plate-pool/?barbell=175lb&collars=clamp&kit=3f9a01bc",
        "https://joeuk89.github.io/plate-pool/?dumbbells=30lb&kit=3f9a01bc",
    ]


def test_a_plate_pool_routine_page_carries_one_set_up_link_with_the_inventory_inline() -> None:
    text = routine_page(a_page(), units="lb")

    set_up = [link for link in links(text) if "kit=3f9a01bc" not in link]
    assert len(set_up) == 1
    encoded = set_up[0].removeprefix("https://joeuk89.github.io/plate-pool/?kit=")
    padded = encoded + "=" * (-len(encoded) % 4)
    assert zlib.decompress(base64.urlsafe_b64decode(padded)) == INVENTORY


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
