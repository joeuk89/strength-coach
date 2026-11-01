import datetime
from dataclasses import dataclass

from coach.core.check_in import check_in_window
from coach.core.check_in_file import CheckInFile, parse_check_in_file
from coach.core.clock import Clock
from coach.core.errors import Invalid
from coach.core.goal import PhaseClose, PhaseOpen
from coach.core.ledger_draft import ExerciseRecord
from coach.services.ledger import Stamp, write_records
from coach.store import check_ins, drafts, observations, phases, week_plans
from coach.store.check_ins import StoredCheckIn
from coach.store.connection import Connection
from coach.store.ids import next_ids
from coach.store.transaction import transaction


@dataclass(frozen=True)
class CheckInRecordResult:
    draft_hash: str
    check_in: str
    tier: str
    window_start: datetime.date
    window_end: datetime.date
    ids: dict[str, list[str]]
    withdrawn: list[str]
    superseded: str | None
    phase_opened: str | None
    phase_closed: str | None


def checkin_record(
    conn: Connection, data: bytes, *, file: str, clock: Clock
) -> CheckInRecordResult:
    """Write the Check-in row and every record its file carries, in one transaction. The same
    file again writes nothing; a changed file for the same date supersedes the row
    (check-in.md, "Correcting")."""
    checkin = parse_check_in_file(data, file=file)
    with transaction(conn):
        stored = check_ins.by_draft(conn, checkin.draft.hash)
        if stored is None:
            stored = _write(conn, checkin, clock)
        return _result(conn, checkin, stored)


def _write(conn: Connection, checkin: CheckInFile, clock: Clock) -> StoredCheckIn:
    replaced = check_ins.current_on(conn, checkin.date)
    previous = check_ins.newest_current(conn, before=checkin.date if replaced else None)
    window = check_in_window(
        checkin.date,
        previous_end=previous.window.end if previous else None,
        first_plan_monday=week_plans.first_week(conn),
        file_start=checkin.window_start,
    )
    id_ = check_ins.next_id(conn, checkin.date)
    recorded_at = clock.now().astimezone(datetime.UTC).isoformat(timespec="seconds")
    check_ins.insert(
        conn,
        {
            "id": id_,
            "date": checkin.date.isoformat(),
            "tier": checkin.tier,
            "window_start": window.start.isoformat(),
            "window_end": window.end.isoformat(),
            "readiness": checkin.readiness,
            "read": checkin.read,
            "status": "current",
            "superseded_by": None,
            "draft_hash": checkin.draft.hash,
            "recorded_at": recorded_at,
        },
    )
    if replaced is not None:
        check_ins.supersede(conn, replaced.id, id_)
    stamp = Stamp(checkin.draft.hash, recorded_at, "check_in", checkin.date, check_in=id_)
    write_records(conn, checkin.draft, stamp)
    _phase(conn, checkin, id_, recorded_at)
    return StoredCheckIn(id_, checkin.date, checkin.tier, window, "current")


def _phase(conn: Connection, checkin: CheckInFile, check_in: str, recorded_at: str) -> None:
    """Opened or closed by the check-in, which is the row's reference (goals.md, "Phase")."""
    ref = f"check_in:{check_in}"
    day = checkin.date.isoformat()
    open_ = phases.open_phase(conn)
    match checkin.phase:
        case PhaseClose(because=because):
            if open_ is None:
                raise Invalid("state_conflict", f"{checkin.draft.file}: [phase] closes none open")
            phases.close(conn, open_.id, closed=day, closed_by=ref, because=because)
        case PhaseOpen() as phase:
            if open_ is not None:
                raise Invalid(
                    "phase_already_open",
                    f"{checkin.draft.file}: Phase {open_.id} ({open_.kind}) is open; close it "
                    "at a check-in before opening another",
                )
            (phase_id,) = next_ids(conn, "phase", "ph-", 1)
            phases.insert(
                conn,
                id_=phase_id,
                phase=phase,
                opened=day,
                opened_by=ref,
                draft_hash=checkin.draft.hash,
                recorded_at=recorded_at,
            )
        case None:
            pass


def _result(conn: Connection, checkin: CheckInFile, stored: StoredCheckIn) -> CheckInRecordResult:
    draft = checkin.draft
    ids = drafts.written_by(conn, draft.hash)
    exercise_ids = [r.id for r in draft.records if isinstance(r, ExerciseRecord)]
    if exercise_ids:
        ids["exercise"] = exercise_ids
    observation_ids = sorted(
        {*ids.get("observation", []), *observations.retired_by(conn, stored.id)}
    )
    if observation_ids:
        ids["observation"] = observation_ids
    ref = f"check_in:{stored.id}"
    return CheckInRecordResult(
        draft_hash=draft.hash,
        check_in=stored.id,
        tier=stored.tier,
        window_start=stored.window.start,
        window_end=stored.window.end,
        ids=ids,
        withdrawn=drafts.withdrawn_by_draft(conn, draft.hash),
        superseded=check_ins.superseded_by(conn, stored.id),
        phase_opened=phases.opened_by(conn, ref),
        phase_closed=phases.closed_by(conn, ref),
    )
