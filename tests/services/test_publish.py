from support.closed_weeks import a_planned_squat_week, monday
from support.plans import SQUAT_LINE, a_squat_program
from support.program_drafts import a_session as a_session_draft
from support.programs import a_config
from support.scenarios import a_session

from coach.services.publish import publish
from coach.store.connection import open_store


def test_publish_returns_the_export_files_and_the_rows_per_table() -> None:
    conn = open_store(":memory:")
    a_session(conn, "push_a")

    publication = publish(conn, engine_version="0.4.0", config=a_config())

    exported = publication.export
    assert exported.rows["session"] == 1
    assert exported.rows["workout"] == 0
    assert exported.files["session.jsonl"] == '{"id":"push_a","introduced_in":"pv-1"}\n'
    assert '"engine_version": "0.4.0"' in exported.files["manifest.json"]


def test_publish_renders_every_page_beside_the_export() -> None:
    publication = publish(open_store(":memory:"), engine_version="0.4.0", config=a_config())

    assert set(publication.pages) == {
        "README.md",
        "pages/week.md",
        "pages/athlete.md",
        "pages/progress.md",
    }


def test_publish_heads_a_coach_led_session_on_the_week_page() -> None:
    conn = a_squat_program(
        a_session_draft("lower", SQUAT_LINE),
        a_session_draft(
            "pt-chest-back",
            title="PT · chest and back",
            kind="coach_led",
            line=None,
            estimated_sets={"chest": 4, "lats": 4},
        ),
        schedule={"rotation": ["A"], "A": {"mon": "lower", "tue": "pt-chest-back"}},
    )
    a_planned_squat_week(conn, monday(0))

    page = publish(conn, engine_version="0.4.0", config=a_config()).pages["pages/week.md"]

    assert (
        "## Tue 2026-11-03: PT · chest and back\n\nCoach-led · estimated sets: chest 4, lats 4\n"
    ) in page
