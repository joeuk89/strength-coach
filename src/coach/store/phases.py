import datetime
from dataclasses import dataclass

from coach.core.goal import PhaseOpen, Until
from coach.core.phase_trend import PhaseInForce
from coach.store.connection import Connection

BODYWEIGHT_UNTILS = ("bodyweight_at_or_below", "bodyweight_at_or_above")


@dataclass(frozen=True)
class OpenPhase:
    id: str
    kind: str
    until: Until


def open_phase(conn: Connection) -> OpenPhase | None:
    found = conn.execute(
        "SELECT id, kind, until_kind, until_value FROM phase WHERE closed IS NULL"
    ).fetchone()
    if found is None:
        return None
    id_, kind, until_kind, until_value = found
    return OpenPhase(id_, kind, Until(until_kind, _until_value(until_kind, until_value)))


def in_force(conn: Connection) -> PhaseInForce | None:
    """The open Phase with its target rate and the day it opened."""
    found = conn.execute(
        "SELECT id, kind, rate_pct_bw_per_week, until_kind, until_value, opened FROM phase "
        "WHERE closed IS NULL"
    ).fetchone()
    if found is None:
        return None
    id_, kind, rate, until_kind, until_value, opened = found
    until = Until(until_kind, _until_value(until_kind, until_value))
    return PhaseInForce(id_, kind, rate, until, datetime.date.fromisoformat(opened))


def insert(
    conn: Connection,
    *,
    id_: str,
    phase: PhaseOpen,
    opened: str,
    opened_by: str,
    draft_hash: str,
    recorded_at: str,
) -> None:
    conn.execute(
        "INSERT INTO phase (id, kind, rate_pct_bw_per_week, until_kind, until_value, opened, "
        "opened_by, opened_because, closed, closed_by, closed_because, draft_hash, recorded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)",
        (
            id_,
            phase.kind,
            phase.rate_pct_bw_per_week,
            phase.until.kind,
            _until_text(phase.until.value),
            opened,
            opened_by,
            phase.because,
            draft_hash,
            recorded_at,
        ),
    )


def close(conn: Connection, id_: str, *, closed: str, closed_by: str, because: str) -> None:
    """Closed in place: the phase is a state table (schema.md, "Updated in place")."""
    conn.execute(
        "UPDATE phase SET closed = ?, closed_by = ?, closed_because = ? WHERE id = ?",
        (closed, closed_by, because, id_),
    )


def opened_by(conn: Connection, ref: str) -> str | None:
    found = conn.execute("SELECT id FROM phase WHERE opened_by = ?", (ref,)).fetchone()
    return found[0] if found else None


def closed_by(conn: Connection, ref: str) -> str | None:
    found = conn.execute("SELECT id FROM phase WHERE closed_by = ?", (ref,)).fetchone()
    return found[0] if found else None


def _until_text(value: datetime.date | float | None) -> str | None:
    if isinstance(value, datetime.date):
        return value.isoformat()
    return None if value is None else repr(value)


def _until_value(kind: str, text: str | None) -> datetime.date | float | None:
    if text is None:
        return None
    if kind in BODYWEIGHT_UNTILS:
        return float(text)
    return datetime.date.fromisoformat(text)
