from pathlib import Path

import pytest
from support.standing_codes import SCENARIOS

from coach.core.registries.flags import OUTSIDE_WARNINGS

STANDING_CODES = [code.name for code in OUTSIDE_WARNINGS]


def test_every_warning_outside_a_plan_has_a_status_scenario() -> None:
    assert sorted(SCENARIOS) == sorted(STANDING_CODES)


@pytest.mark.parametrize("code", STANDING_CODES)
def test_status_reports_the_code_while_it_stands_and_drops_it_once_cleared(
    code: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = SCENARIOS.get(code)
    assert scenario is not None, f"no status scenario seeds {code}"

    standing = scenario(tmp_path, monkeypatch)

    assert code in standing.raised
    assert code not in standing.cleared
