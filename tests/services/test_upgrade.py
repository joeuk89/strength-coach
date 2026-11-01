from support.chains import ENGINE_PLUS_PROBE
from support.scenarios import a_catalogue_without, a_session

from coach.services.upgrade import upgrade
from coach.store.catalogue import seed_catalogue
from coach.store.chain import ENGINE
from coach.store.connection import open_store, open_store_behind, schema_version


def test_upgrade_migrates_merges_the_catalogue_and_exports_at_the_new_version() -> None:
    conn = open_store(":memory:")
    a_catalogue_without(conn, "ab_wheel")
    a_session(conn, "push_a")

    upgraded = upgrade(conn, engine_version="0.4.0", chain=ENGINE_PLUS_PROBE)

    assert upgraded.migrations == ("m0001",)
    assert (upgraded.from_version, upgraded.to_version) == (1, 2)
    assert upgraded.catalogue_added == ("ab_wheel",)
    assert schema_version(conn) == 2
    files = upgraded.export.files
    assert files["session.jsonl"] == '{"id":"push_a","introduced_in":"pv-1"}\n'
    assert files["upgrade_probe.jsonl"] == ""
    assert '"schema_version": 2' in files["manifest.json"]
    assert '"engine_version": "0.4.0"' in files["manifest.json"]


def test_upgrade_at_the_current_version_runs_no_migration_and_still_exports() -> None:
    conn = open_store_behind(":memory:", ENGINE)
    with conn:
        seed_catalogue(conn)

    upgraded = upgrade(conn, engine_version="0.4.0", chain=ENGINE)

    assert upgraded.migrations == ()
    assert upgraded.catalogue_added == ()
    assert '"engine_version": "0.4.0"' in upgraded.export.files["manifest.json"]
