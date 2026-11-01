import shutil
from pathlib import Path

import pytest
from support.instances import a_coach_toml
from support.kit_fixtures import INVENTORY, TABLES

from coach.cli.declaration import Instance
from coach.cli.kit import require_current_kit
from coach.core.config import parse_config
from coach.core.errors import Setup

HOME = {"kind": "plate-pool", "kit": "home", "collars": "clamp", "dumbbells": "pair"}


def an_instance_at_home(root: Path) -> Instance:
    (root / "kit").mkdir()
    shutil.copyfile(INVENTORY, root / "kit" / "home.json")
    shutil.copyfile(TABLES, root / "kit" / "home.achievable.json")
    return Instance(root, parse_config(a_coach_toml(pin="0.3.0", location={"home": HOME})))


def test_current_kit_tables_let_a_rounding_verb_run(tmp_path: Path) -> None:
    require_current_kit(an_instance_at_home(tmp_path))


def test_a_missing_tables_file_stops_a_rounding_verb_with_kit_tables_stale(
    tmp_path: Path,
) -> None:
    instance = an_instance_at_home(tmp_path)
    (tmp_path / "kit" / "home.achievable.json").unlink()

    with pytest.raises(Setup) as raised:
        require_current_kit(instance)

    assert raised.value.code == "kit_tables_stale"
    assert "location home" in raised.value.message
    assert "npx plate-pool achievable --inventory kit/home.json" in raised.value.message
