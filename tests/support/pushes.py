"""A squat week pushed to the fake Hevy through `plan apply`."""

from coach.services.plan_apply import apply, dry_run
from coach.store import routine_map
from coach.store.connection import Connection
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.kit_fixtures import kit_files
from support.plan_drafts import a_plan_draft
from support.plans import a_squat_program, squat_logged
from support.programs import a_config


def push(conn: Connection, hevy: FakeHevy, data: bytes) -> None:
    config, kits = a_config(hevy=True), (kit_files(),)
    digest = dry_run(
        conn, data, file="p.toml", config=config, kits=kits, clock=FixedClock()
    ).write_plan_hash
    apply(
        conn,
        hevy,
        data,
        file="p.toml",
        expect=digest,
        config=config,
        kits=kits,
        clock=FixedClock(),
    )


def a_pushed_week() -> tuple[Connection, FakeHevy, str]:
    """Returns the store, the fake Hevy and the routine id `lower` was pushed to."""
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    hevy = FakeHevy(FixedClock())
    push(conn, hevy, a_plan_draft(conn, hevy=True))
    return conn, hevy, routine_map.mapped(conn)["lower"]
