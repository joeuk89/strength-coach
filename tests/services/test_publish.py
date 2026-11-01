from support.scenarios import a_session

from coach.services.publish import publish
from coach.store.connection import open_store


def test_publish_returns_the_export_files_and_the_rows_per_table() -> None:
    conn = open_store(":memory:")
    a_session(conn, "push_a")

    publication = publish(conn, engine_version="0.4.0")

    assert publication.rows["session"] == 1
    assert publication.rows["workout"] == 0
    assert publication.files["session.jsonl"] == '{"id":"push_a","introduced_in":"pv-1"}\n'
    assert '"engine_version": "0.4.0"' in publication.files["manifest.json"]
