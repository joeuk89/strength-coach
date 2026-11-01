from pathlib import Path

import pytest

from coach.core.errors import Setup
from coach.hevy.key import api_key


def test_the_environment_wins_over_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HEVY_API_KEY=from-file\n", encoding="utf-8")

    assert api_key({"HEVY_API_KEY": "from-env"}, tmp_path / ".env") == "from-env"


@pytest.mark.parametrize(
    "text",
    [
        "HEVY_API_KEY=from-file\n",
        'HEVY_API_KEY="from-file"\n',
        "# a comment\nexport HEVY_API_KEY='from-file'\n",
        "OTHER=x\n  HEVY_API_KEY = from-file  \n",
    ],
)
def test_dotenv_supplies_the_key_when_the_environment_has_none(tmp_path: Path, text: str) -> None:
    (tmp_path / ".env").write_text(text, encoding="utf-8")

    assert api_key({"HEVY_API_KEY": "  "}, tmp_path / ".env") == "from-file"


@pytest.mark.parametrize("dotenv", [None, "OTHER=x\n", "HEVY_API_KEY=\n"])
def test_no_key_anywhere_is_hevy_key_missing(tmp_path: Path, dotenv: str | None) -> None:
    if dotenv is not None:
        (tmp_path / ".env").write_text(dotenv, encoding="utf-8")

    with pytest.raises(Setup) as raised:
        api_key({}, tmp_path / ".env")

    assert raised.value.code == "hevy_key_missing"
