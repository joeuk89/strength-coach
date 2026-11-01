import datetime
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

from coach.core.coaching_records import (
    AnnotationRecord,
    DecisionRecord,
    FollowUpRecord,
    NiggleRecord,
    supersede_subject,
)
from coach.core.draft_fields import required
from coach.core.errors import Invalid
from coach.core.ref import Ref
from coach.store import annotations, decisions, exercises, follow_ups, niggles, refs, sessions
from coach.store.connection import Connection
from coach.store.ids import next_ids

# overrides.md, "Decision kinds": an override Decision lasts at most eight weeks.
OVERRIDE_DECISION_DAYS = 56
# Refs to things with no table: a Block is derived and a research note is not in the store.
UNSTORED_REF_KINDS = ("block", "rn")


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
        if resolved.kind in UNSTORED_REF_KINDS:
            return resolved
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


def write_decision(w: Writing, record: DecisionRecord, decision_id: str) -> None:
    if record.session and not sessions.exists(w.conn, record.session):
        raise Invalid(
            "invalid_argument",
            f"[[decision]] names session {record.session!r}, "
            "which no program version or niggle has raised",
        )
    if record.exercise:
        _library_exercise(w.conn, record.exercise, "[[decision]]")
    evidence = [str(w.stored_ref(ref, "[[decision]] evidence")) for ref in record.evidence]
    until = _until(w.today, record)
    target = _retired_target(w.conn, record) if record.kind == "retire" else None
    decisions.insert_decision(
        w.conn,
        w.row(
            id=decision_id,
            kind=record.kind,
            session_id=record.session,
            exercise_id=record.exercise,
            params=dict(record.params),
            until=until.isoformat() if until else None,
            because=record.because,
            text=record.text,
            evidence=evidence,
        ),
    )
    if target is not None:
        decisions.retire(w.conn, target, decision_id)
    subject = supersede_subject(record.kind, record.session, record.exercise, record.params)
    if subject is not None:
        superseded = [
            str(row["id"])
            for row in decisions.in_force(w.conn)
            if row["id"] != decision_id
            and supersede_subject(
                str(row["kind"]),
                row["session_id"],
                row["exercise_id"],
                cast(Mapping[str, object], row["params"]),
            )
            == subject
        ]
        decisions.supersede(w.conn, superseded, decision_id)


def _until(today: datetime.date, record: DecisionRecord) -> datetime.date | None:
    if record.kind == "override":
        latest = today + datetime.timedelta(days=OVERRIDE_DECISION_DAYS)
        if record.until and record.until > latest:
            raise Invalid(
                "invalid_argument",
                f"[[decision]] override until {record.until} is more than eight weeks out; "
                f"the latest is {latest}",
            )
    if record.kind == "decline_ceiling":
        sunday = today + datetime.timedelta(days=6 - today.weekday())
        if record.until and record.until != sunday:
            raise Invalid(
                "invalid_argument",
                f"[[decision]] decline_ceiling lasts to the Sunday of the week it is made in, "
                f"{sunday}; drop until or give that date",
            )
        return sunday
    return record.until


def _retired_target(conn: Connection, record: DecisionRecord) -> str:
    target = str(record.params["decision"])
    stored = decisions.get(conn, target)
    if stored is None or stored["kind"] == "retire":
        raise Invalid("invalid_argument", f"[[decision]] retire names {target}, no stored Decision")
    ended = stored["superseded_by"] or stored["retired_by"]
    if ended:
        raise Invalid(
            "invalid_argument", f"[[decision]] retire names {target}, already ended by {ended}"
        )
    return target


def write_annotation(w: Writing, record: AnnotationRecord, annotation_id: str) -> str | None:
    """Write the annotation; return the id it withdraws, if it is a withdrawal."""
    if record.withdraws is not None:
        _withdraw_annotation(w, annotation_id, record.withdraws)
        return record.withdraws
    target = w.stored_ref(required(record.target), "[[annotation]] target")
    params = dict(record.params) if record.params else None
    if params and record.kind == "match":
        planned = Ref.parse(str(params["planned_session"]))
        params["planned_session"] = str(w.stored_ref(planned, "[[annotation]] match"))
    annotations.insert_annotation(
        w.conn,
        w.row(
            id=annotation_id,
            kind=record.kind,
            target=str(target),
            params=params,
            because=record.because,
            text=record.text,
            withdraws=None,
        ),
    )
    return None


def _withdraw_annotation(w: Writing, annotation_id: str, target: str) -> None:
    withdrawn = annotations.get(w.conn, target)
    if withdrawn is None:
        raise Invalid("invalid_argument", f"[[annotation]] withdraws {target}, which is not stored")
    if withdrawn["withdraws"] is not None:
        raise Invalid(
            "invalid_argument", f"{target} is itself a withdrawal; it cannot be withdrawn"
        )
    earlier = annotations.withdrawn_by(w.conn, target)
    if earlier:
        raise Invalid("invalid_argument", f"{target} is already withdrawn by {earlier}")
    # schema.md, "Views": a withdrawing row restates the withdrawn row's required columns.
    annotations.insert_annotation(
        w.conn,
        w.row(
            id=annotation_id,
            kind=withdrawn["kind"],
            target=withdrawn["target"],
            because=withdrawn["because"],
            withdraws=target,
        ),
    )
