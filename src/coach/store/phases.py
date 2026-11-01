from coach.core.registries.phase import PHASE
from coach.store.connection import Connection


def open_kind(conn: Connection) -> str | None:
    found = conn.execute("SELECT kind FROM phase WHERE closed IS NULL").fetchone()
    return found[0] if found else None


def insert(
    conn: Connection,
    *,
    id_: str,
    kind: str,
    opened: str,
    opened_by: str,
    until_kind: str = "coachs_call",
    because: str = "opened with the goal",
    draft_hash: str = "sha256:phase",
    recorded_at: str = "2026-11-01T12:00:00+00:00",
) -> None:
    """An open Phase at its kind's registry rate."""
    conn.execute(
        "INSERT INTO phase VALUES (?, ?, ?, ?, NULL, ?, ?, ?, NULL, NULL, NULL, ?, ?)",
        (
            id_,
            kind,
            PHASE.get(kind).default_rate_pct_bw_per_week,
            until_kind,
            opened,
            opened_by,
            because,
            draft_hash,
            recorded_at,
        ),
    )
