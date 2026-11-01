import datetime
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from coach.core.coaching_records import FollowUpRecord, NiggleRecord
from coach.core.errors import Invalid
from coach.core.ref import Ref
from coach.store import exercises, follow_ups, niggles, refs, sessions
from coach.store.connection import Connection
from coach.store.ids import next_ids


@dataclass(frozen=True)
class Writing:
    """What a coaching record's write needs from the Draft writer."""

    conn: Connection
    stamp: Mapping[str, object]
    today: datetime.date
    resolve: Callable[[Ref], Ref]

    def row(self, **columns: object) -> dict[str, object]:
        return {**columns, **self.stamp}

    def stored_ref(self, ref: Ref, where: str) -> Ref:
        """The ref with any Draft-local key resolved, refused unless it names a stored row."""
        resolved = self.resolve(ref)
        if not refs.exists(self.conn, resolved):
            raise Invalid(
                "invalid_argument", f"{where} cites {resolved}, which names no stored row"
            )
        return resolved


def write_niggle(w: Writing, record: NiggleRecord, niggle_id: str) -> None:
    if record.niggle is None:
        _raise_niggle(w, record, niggle_id)
    elif not niggles.exists(w.conn, niggle_id):
        raise Invalid("invalid_argument", f"[[niggle]] names {niggle_id}, which is not stored")
    for constraint in record.constraints:
        if constraint.exercise:
            _library_exercise(w.conn, constraint.exercise, "[[niggle]] constraint")
    (event_id,) = next_ids(w.conn, "niggle_event", "ne-", 1)
    constraint_ids = next_ids(w.conn, "niggle_constraint", "nc-", len(record.constraints))
    niggles.insert_event(
        w.conn,
        w.row(
            id=event_id,
            niggle_id=niggle_id,
            date=record.date.isoformat(),
            status=record.status,
            text=record.text,
        ),
        [
            {
                "id": id_,
                "kind": c.kind,
                "exercise_id": c.exercise,
                "pattern": c.pattern,
                "value": c.value,
            }
            for id_, c in zip(constraint_ids, record.constraints, strict=True)
        ],
    )


def _raise_niggle(w: Writing, record: NiggleRecord, niggle_id: str) -> None:
    rehab = record.rehab
    if rehab is not None:
        if sessions.exists(w.conn, rehab.session):
            raise Invalid(
                "invalid_argument",
                f"[[niggle]] rehab session {rehab.session!r} is already a session id",
            )
        for line in rehab.lines:
            _library_exercise(w.conn, str(line["exercise_id"]), "[[niggle]] rehab line")
        sessions.insert(w.conn, rehab.session, niggle_id)
    niggles.insert_niggle(
        w.conn,
        {
            "id": niggle_id,
            "opened": (record.opened or record.date).isoformat(),
            "site": record.site,
            "rehab_session_id": rehab.session if rehab else None,
            "draft_hash": w.stamp["draft_hash"],
            "recorded_at": w.stamp["recorded_at"],
        },
    )
    if rehab is not None:
        niggles.insert_rehab_session(
            w.conn,
            {
                "session_id": rehab.session,
                "niggle_id": niggle_id,
                "title": rehab.title,
                "tier": rehab.tier,
                "cadence": rehab.cadence,
                "location": rehab.location,
                "lines": list(rehab.lines),
                "draft_hash": w.stamp["draft_hash"],
                "recorded_at": w.stamp["recorded_at"],
            },
        )


def _library_exercise(conn: Connection, exercise_id: str, where: str) -> None:
    if exercises.get(conn, exercise_id) is None:
        raise Invalid(
            "invalid_argument",
            f"{where} names exercise {exercise_id!r}, which is not in the library",
        )


def write_follow_up(w: Writing, record: FollowUpRecord, follow_up_id: str) -> None:
    if record.followup is None:
        about = w.stored_ref(record.about, "[[followup]] about") if record.about else None
        follow_ups.insert_follow_up(
            w.conn,
            w.row(
                id=follow_up_id,
                raised=record.date.isoformat(),
                text=record.raised_text,
                about=str(about) if about else None,
            ),
        )
    elif not follow_ups.exists(w.conn, follow_up_id):
        raise Invalid("invalid_argument", f"[[followup]] names {follow_up_id}, which is not stored")
    elif record.kind == "deferred":
        _check_deferred(w.conn, follow_up_id, record)
    (event_id,) = next_ids(w.conn, "follow_up_event", "fe-", 1)
    follow_ups.insert_event(
        w.conn,
        w.row(
            id=event_id,
            follow_up_id=follow_up_id,
            date=record.date.isoformat(),
            kind=record.kind,
            due=record.due.isoformat() if record.due else None,
            text=record.text,
        ),
    )


def _check_deferred(conn: Connection, follow_up_id: str, record: FollowUpRecord) -> None:
    previous = follow_ups.last_due(conn, follow_up_id)
    due = record.due.isoformat() if record.due else ""
    if previous is not None and due <= previous:
        raise Invalid(
            "invalid_argument",
            f"[[followup]] deferred {follow_up_id} to {due}, which is not later than its "
            f"due date {previous}; a deferral moves the due date later",
        )
