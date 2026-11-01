"""Scenario builders for program adopt. Each writes only through `store` functions."""

from typing import Any

from coach.core.config import Config, parse_config
from coach.store import goals, phases
from coach.store.catalogue import seed_catalogue
from coach.store.connection import Connection
from support.instances import a_coach_toml
from support.ledger import a_store, an_exercise
from support.program_drafts import CUSTOM_EXERCISES, WORKED_GOAL_PRIORITY_LIFTS

RECORDED_AT = "2026-10-30T12:00:00+00:00"
HOME = {
    "kind": "plate-pool",
    "kit": "home",
    "collars": "clamp",
    "dumbbells": "pair",
    "implements": {"barbell": "barbell", "dumbbell": "dumbbell", "kettlebell": "kettlebell"},
}
GYM = {
    "kind": "grid",
    "implements": {"barbell": "bar", "dumbbell": "rack"},
    "implement": {"bar": {"increment": 2.5, "base": 20}, "rack": {"rack": [10, 15, 20, 25]}},
}


def a_config(*, hevy: bool = False, units: str = "lb", **athlete: Any) -> Config:
    document = a_coach_toml(pin="0.3.0", hevy=hevy, location={"home": HOME, "gym": GYM})
    document["athlete"] |= {"units": units, **athlete}
    return parse_config(document)


def a_library_store() -> Connection:
    """The catalogue and the custom exercises the worked Draft and cutover name."""
    conn = a_store()
    with conn:
        seed_catalogue(conn)
    for n, (id_, columns) in enumerate(CUSTOM_EXERCISES.items(), start=1):
        an_exercise(conn, id_, source="record", hevy_template_id=f"C-{n:04d}", **columns)
    return conn


def a_goal(
    conn: Connection,
    kind: str = "hypertrophy",
    priority_lifts: tuple[str, ...] = WORKED_GOAL_PRIORITY_LIFTS,
    *,
    id_: str = "g-0001",
) -> None:
    with conn:
        goals.insert(
            conn,
            id_=id_,
            kind=kind,
            priority_lifts=priority_lifts,
            adopted="2026-10-01",
            draft_hash=f"sha256:{id_}",
            recorded_at=RECORDED_AT,
        )


def a_phase(conn: Connection, kind: str) -> None:
    with conn:
        phases.insert(conn, id_="ph-0001", kind=kind, opened="2026-10-01", opened_by="goal:g-0001")


def the_worked_store() -> Connection:
    conn = a_library_store()
    a_goal(conn)
    a_phase(conn, "maintenance")
    return conn
