import datetime
from typing import cast

from coach.core.flag import Acknowledgement, FlagKey
from coach.core.registries.ledger import Reason
from coach.store import decisions
from coach.store.connection import Connection


def leave_warning_decisions(conn: Connection, on: datetime.date) -> tuple[Acknowledgement, ...]:
    """`leave_warning` Decisions in force on `on` (validation.md, "Longer than a week")."""
    return tuple(
        Acknowledgement(
            FlagKey.parse(str(params["flag"])),
            str(params["params_hash"]),
            cast(Reason, row["because"]),
            str(row["text"]),
            tuple(str(ref) for ref in cast(list[object], row["evidence"])),
            source="decision",
        )
        for row in decisions.in_force(conn, on.isoformat())
        if row["kind"] == "leave_warning"
        for params in (cast(dict[str, object], row["params"]),)
    )
