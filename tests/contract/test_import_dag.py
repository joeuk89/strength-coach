from pathlib import Path

import pytest
from support.import_dag import violations

SRC = Path(__file__).resolve().parents[2] / "src"


def plant(root: Path, module: str, source: str) -> Path:
    path = root / "coach" / Path(*module.split(".")).with_suffix(".py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return root


def test_the_engine_follows_the_import_dag() -> None:
    assert violations(SRC) == []


@pytest.mark.parametrize(
    ("module", "source"),
    [
        ("core.bad", "import sqlite3\n"),
        ("core.bad", "import os.path\n"),
        ("core.bad", "from pathlib import Path\n"),
        ("core.bad", "import urllib.request\n"),
        ("core.bad", "import subprocess\n"),
        ("core.bad", "import time\n"),
        ("core.bad", "import datetime\nTODAY = datetime.date.today()\n"),
        ("core.bad", "from datetime import datetime\nNOW = datetime.now()\n"),
        ("core.bad", "from coach.store import connection\n"),
        ("core.bad", "from ..store import connection\n"),
        ("render.bad", "import coach.store.connection\n"),
        ("services.bad", "from coach.cli import app\n"),
        ("store.bad", "from coach.services import status\n"),
        ("hevy.bad", "from coach.render import pages\n"),
        ("render.bad", "import sqlite3\n"),
        ("services.bad", "import os\n"),
        ("store.bad", "import requests\n"),
    ],
)
def test_a_planted_forbidden_import_is_caught(tmp_path: Path, module: str, source: str) -> None:
    found = violations(plant(tmp_path, module, source))

    assert len(found) == 1
    assert f"coach/{module.replace('.', '/')}.py" in found[0]


@pytest.mark.parametrize(
    ("module", "source"),
    [
        ("core.ok", "import datetime\nfrom coach.core import errors\n"),
        ("core.ok", "def f(clock):\n    return clock.today()\n"),
        ("store.ok", "import sqlite3\nfrom pathlib import Path\nfrom coach.core import errors\n"),
        ("hevy.ok", "import urllib.request\nfrom coach.core import errors\n"),
        ("render.ok", "from coach.core import errors\n"),
        (
            "services.ok",
            "from coach.store import x\nfrom coach.hevy import y\nfrom coach.render import z\n",
        ),
        ("cli.ok", "import os\nimport subprocess\nfrom coach.services import status\n"),
        ("__main__", "from coach.cli.app import run\n"),
        ("store.ok", "from . import connection\n"),
    ],
)
def test_an_allowed_import_passes(tmp_path: Path, module: str, source: str) -> None:
    assert violations(plant(tmp_path, module, source)) == []
