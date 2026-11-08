import datetime
from dataclasses import dataclass

from coach.core.draft_fields import Fields, draft_hash, required
from coach.core.goal import PhaseClose, PhaseOpen, parse_phase_open
from coach.core.ledger_draft import LedgerDraft, ledger_draft_of, load_draft
from coach.core.registries.ledger import CHECK_IN_TIERS, READINESS

HEADER = ("date", "tier", "read", "readiness", "window_start")
VERB = "checkin record"


@dataclass(frozen=True)
class CheckInFile:
    """A `checkin record` file: the row's header, the Phase it opens or closes, and every
    record it carries (check-in.md, "The record file")."""

    date: datetime.date
    tier: str
    read: str
    draft: LedgerDraft
    readiness: str | None = None
    window_start: datetime.date | None = None
    phase: PhaseOpen | PhaseClose | None = None


def parse_check_in_file(data: bytes, *, file: str) -> CheckInFile:
    document = load_draft(data, file)
    header = Fields({k: v for k, v in document.items() if k in HEADER}, file)
    phase = Fields({"phase": document["phase"]}, file) if "phase" in document else None
    records = {k: v for k, v in document.items() if k not in (*HEADER, "phase")}
    draft = ledger_draft_of(records, hash=draft_hash(data), verb=VERB, file=file)
    return header.done(
        CheckInFile(
            date=required(header.date("date", required=True)),
            tier=required(header.term("tier", CHECK_IN_TIERS, required=True)),
            read=required(header.text("read", required=True)),
            draft=draft,
            readiness=header.term("readiness", READINESS),
            window_start=header.date("window_start"),
            phase=_phase(phase.table("phase")) if phase else None,
        )
    )


def _phase(f: Fields | None) -> PhaseOpen | PhaseClose | None:
    if f is None:
        return None
    if not f.has("close"):
        return parse_phase_open(f)
    if f.boolean("close") is not True:
        raise f.wrong("close", "true, or left out to open a Phase")
    return f.done(PhaseClose(required(f.text("because", required=True))))
