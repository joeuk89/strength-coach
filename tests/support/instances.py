from pathlib import Path
from typing import Any

from coach.cli.generated import generated_files
from coach.render.toml import dumps

ATHLETE: dict[str, Any] = {
    "units": "kg",
    "bodyweight_units": "kg",
    "week_starts": "monday",
    "timezone": "Europe/London",
    "available_days": ["monday", "wednesday", "friday"],
    "session_minutes": 60,
}


def a_coach_toml(*, pin: str, hevy: bool = False, **tables: Any) -> dict[str, Any]:
    document: dict[str, Any] = {"engine": {"version": pin}, "athlete": dict(ATHLETE)}
    if hevy:
        document["hevy"] = {}
    document.update(tables)
    return document


def an_instance(root: Path, *, pin: str, hevy: bool = False, **tables: Any) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    document = a_coach_toml(pin=pin, hevy=hevy, **tables)
    (root / "coach.toml").write_text(dumps(document), encoding="utf-8")
    for relative, text in generated_files(pin).items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(text, encoding="utf-8")
    return root
