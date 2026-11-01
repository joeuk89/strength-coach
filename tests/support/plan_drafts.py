"""The plan Draft the agent hands to `plan apply`: what `plan draft` writes, edited the way the
agent edits it."""

import datetime

from coach.services.plan_draft import plan_draft
from coach.store.connection import Connection
from support.clock import FixedClock
from support.kit_fixtures import kit_files
from support.programs import a_config

NEXT_MONDAY = datetime.date(2026, 11, 2)


def a_plan_draft(
    conn: Connection,
    *,
    overrides: str = "",
    acknowledge: str = "",
    confirmed: bool = True,
    hevy: bool = False,
    week: datetime.date = NEXT_MONDAY,
) -> bytes:
    """The engine's Draft for next week, its position confirmed, with the agent's
    `[[override]]` and `[[acknowledge]]` tables in place of the empty arrays."""
    text = plan_draft(
        conn,
        config=a_config(hevy=hevy),
        kits=(kit_files(),),
        clock=FixedClock(),
        week=week,
    ).text
    if confirmed:
        text = text.replace("confirmed = false", "confirmed = true")
    for name, tables in (("override", overrides), ("acknowledge", acknowledge)):
        if tables:
            text = text.replace(f"{name} = []\n", "", 1) + "\n" + tables
    return text.encode("utf-8")
