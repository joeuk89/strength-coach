from support.clock import FixedClock
from support.programs import a_config
from support.scenarios import a_session

from coach.services.publish import publish
from coach.store.connection import open_store


def test_publish_returns_the_export_files_and_the_rows_per_table() -> None:
    conn = open_store(":memory:")
    a_session(conn, "push_a")

    publication = publish(conn, FixedClock(), engine_version="0.4.0", config=a_config())

    exported = publication.export
    assert exported.rows["session"] == 1
    assert exported.rows["workout"] == 0
    assert exported.files["session.jsonl"] == '{"id":"push_a","introduced_in":"pv-1"}\n'
    assert '"engine_version": "0.4.0"' in exported.files["manifest.json"]


def test_publish_renders_every_page_beside_the_export() -> None:
    publication = publish(
        open_store(":memory:"), FixedClock(), engine_version="0.4.0", config=a_config()
    )

    assert set(publication.pages) == {
        "README.md",
        "pages/week.md",
        "pages/athlete.md",
        "pages/progress.md",
    }
