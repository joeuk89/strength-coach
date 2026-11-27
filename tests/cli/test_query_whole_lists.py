from pathlib import Path

from support.fixture_instances import coach, instance, rebuilt

__all__ = ["instance", "rebuilt"]


def test_query_flags_lines_and_routines_return_every_row_with_no_options(
    instance: Path,
) -> None:
    found = {
        view: coach("query", view, *extra).envelope["result"]
        for view, extra in (
            ("flags", ("--severity", "warning")),
            ("lines", ()),
            ("routines", ()),
        )
    }

    assert {view: (len(r["rows"]), r["count"], r["truncated"]) for view, r in found.items()} == {
        "flags": (11, 11, False),
        "lines": (18, 18, False),
        "routines": (11, 11, False),
    }
