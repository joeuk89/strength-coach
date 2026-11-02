import datetime
from dataclasses import dataclass

from coach.core.clock import Clock
from coach.core.ledger_draft import ExerciseRecord, parse_ledger_draft
from coach.services.ledger import Stamp, write_records
from coach.store import drafts
from coach.store.connection import Connection
from coach.store.transaction import transaction


@dataclass(frozen=True)
class RecordResult:
    draft_hash: str
    ids: dict[str, list[str]]
    withdrawn: list[str]
    dry_run: bool = False
    no_op: bool = False


def record(
    conn: Connection, data: bytes, *, file: str, clock: Clock, dry_run: bool = False
) -> RecordResult:
    """Write a ledger Draft outside a check-in. A Draft whose hash is already stored writes
    nothing and returns the ids it wrote (verbs.md, "Re-run safety"). A dry run writes and
    rolls back."""
    draft = parse_ledger_draft(data, verb="record", file=file)
    with transaction(conn, commit=not dry_run):
        stored = drafts.written_by(conn, draft.hash)
        if stored:
            exercise_ids = [r.id for r in draft.records if isinstance(r, ExerciseRecord)]
            if exercise_ids:
                stored["exercise"] = exercise_ids
            withdrawn = drafts.withdrawn_by_draft(conn, draft.hash)
            return RecordResult(draft.hash, stored, withdrawn, dry_run=dry_run, no_op=True)
        recorded_at = clock.now().astimezone(datetime.UTC).isoformat(timespec="seconds")
        written = write_records(
            conn, draft, Stamp(draft.hash, recorded_at, "manual", clock.today())
        )
    return RecordResult(draft.hash, written.ids, written.withdrawn, dry_run=dry_run)
