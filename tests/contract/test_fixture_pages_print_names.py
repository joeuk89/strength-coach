import json
import re
from pathlib import Path

import pytest
from support.fixture_instance import FIXTURE

from coach.core.registries.ledger import MILESTONE_TARGET_KINDS
from coach.core.registries.program import MUSCLES
from coach.core.registries.registry import Titled
from coach.core.registries.schemes import CADENCE_SIGNALS, SCHEMES

ATHLETE_PAGES = sorted(
    [
        FIXTURE / "pages" / "athlete.md",
        FIXTURE / "pages" / "progress.md",
        *(FIXTURE / "pages" / "check-ins").glob("*.md"),
    ]
)
BLOCK_ID = re.compile(r"\bb-\d{4}-\d{2}-\d{2}\b")


def exported(table: str, column: str) -> set[str]:
    lines = (FIXTURE / "export" / f"{table}.jsonl").read_text().splitlines()
    return {str(json.loads(line)[column]) for line in lines}


def raw_codes() -> set[str]:
    titled: list[Titled] = [
        *SCHEMES.entries,
        *CADENCE_SIGNALS.entries,
        *MILESTONE_TARGET_KINDS.entries,
        *MUSCLES.entries,
    ]
    return {e.name for e in titled if e.title != e.name} | {"per_muscle"}


def ids_and_codes() -> set[str]:
    """A session id that is also a display name, as `calves` is a muscle's, is not an id here."""
    titles = {e.title for e in (*SCHEMES.entries, *MUSCLES.entries)}
    ids = exported("exercise", "id") | exported("program_session", "session_id")
    return (ids - titles) | raw_codes()


@pytest.mark.parametrize("path", ATHLETE_PAGES, ids=lambda p: p.relative_to(FIXTURE).as_posix())
def test_an_athlete_page_of_the_fixture_instance_prints_no_id_or_raw_code(path: Path) -> None:
    text = path.read_text()
    tokens = set(re.findall(r"[\w-]+", text))

    assert sorted(tokens & ids_and_codes()) == []
    assert BLOCK_ID.findall(text) == []
