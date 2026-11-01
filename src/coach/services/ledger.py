import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field

from coach.core.coaching_records import (
    AnnotationRecord,
    DecisionRecord,
    FollowUpRecord,
    NiggleRecord,
)
from coach.core.errors import Invalid
from coach.core.ledger_draft import (
    EXERCISE_EDITABLE,
    EXERCISE_IDENTITY,
    NEW_EXERCISE_REQUIRED,
    ActivityRecord,
    ExerciseRecord,
    LedgerDraft,
    LedgerRecord,
    LoggedSetRecord,
    NoteRecord,
    ObservationRecord,
    SleepNightRecord,
    StatusSpanRecord,
    WeighInRecord,
    WorkoutRecord,
    kind_of,
)
from coach.core.ref import Ref
from coach.core.withdrawal import withdrawable
from coach.services.coaching_ledger import (
    Writing,
    write_annotation,
    write_decision,
    write_follow_up,
    write_niggle,
)
from coach.store import exercises, notes, observations, readings, refs, workouts
from coach.store.connection import Connection
from coach.store.ids import next_ids

# schema.md, "Ids". An Athlete note's prefix is not in that table: `an-`, since `n-` is a niggle's.
ID_PREFIX = {
    "niggle": ("niggle", "n-"),
    "followup": ("follow_up", "f-"),
    "decision": ("decision", "d-"),
    "annotation": ("annotation", "a-"),
    "note": ("athlete_note", "an-"),
    "weigh_in": ("weigh_in", "wi-"),
    "sleep_night": ("sleep_night", "sn-"),
    "activity": ("activity", "ac-"),
    "status_span": ("status_span", "ss-"),
    "workout": ("workout", "w-"),
    "observation": ("observation", "o-"),
}
# What a withdrawing row restates from the row it withdraws (schema.md, "Views").
RESTATED = {
    "weigh_in": ("date", "kg", "source"),
    "sleep_night": ("night", "hours", "source"),
    "status_span": ("kind", "from_date", "to_date"),
}


@dataclass(frozen=True)
class Stamp:
    """What every row a Draft writes carries beside its own fields."""

    draft_hash: str
    recorded_at: str
    reading_source: str
    today: datetime.date
    check_in: str | None = None


@dataclass
class Written:
    ids: dict[str, list[str]] = field(default_factory=lambda: {})
    withdrawn: list[str] = field(default_factory=lambda: [])


def write_records(conn: Connection, draft: LedgerDraft, stamp: Stamp) -> Written:
    """Every record of a ledger Draft, inside the caller's transaction."""
    return _Writer(conn, draft, stamp).write()


class _Writer:
    def __init__(self, conn: Connection, draft: LedgerDraft, stamp: Stamp) -> None:
        self.conn = conn
        self.draft = draft
        self.stamp = stamp
        self.ids = self._assign_ids()
        self.writing = Writing(
            conn,
            {
                "check_in": stamp.check_in,
                "draft_hash": stamp.draft_hash,
                "recorded_at": stamp.recorded_at,
            },
            stamp.today,
            self._resolve,
        )

    def write(self) -> Written:
        written = Written()
        for record, id_ in zip(self.draft.records, self.ids, strict=True):
            written.ids.setdefault(kind_of(record), []).append(id_)
        records = sorted(enumerate(self.draft.records), key=lambda p: _write_order(p[1]))
        for index, record in records:
            withdrawn = self._write(record, self.ids[index])
            if withdrawn:
                written.withdrawn.append(withdrawn)
        self._check_duplicates()
        return written

    def _assign_ids(self) -> list[str]:
        named = [_named_id(r) for r in self.draft.records]
        kinds = [kind_of(r) for r, n in zip(self.draft.records, named, strict=True) if n is None]
        fresh = {
            kind: next_ids(self.conn, *ID_PREFIX[kind], kinds.count(kind)) for kind in ID_PREFIX
        }
        return [
            n if n is not None else fresh[kind_of(r)].pop(0)
            for r, n in zip(self.draft.records, named, strict=True)
        ]

    def _resolve(self, ref: Ref) -> Ref:
        key = ref.local_key
        return ref if key is None else ref.resolved(self.ids[self.draft.keys()[key]])

    def _stamped(self, row: Mapping[str, object]) -> dict[str, object]:
        return {
            **row,
            "check_in": self.stamp.check_in,
            "draft_hash": self.stamp.draft_hash,
            "recorded_at": self.stamp.recorded_at,
        }

    def _write(self, record: LedgerRecord, id_: str) -> str | None:
        match record:
            case (
                WeighInRecord(withdraws=str(target))
                | SleepNightRecord(withdraws=str(target))
                | StatusSpanRecord(withdraws=str(target))
            ):
                return self._withdraw(kind_of(record), id_, target)
            case NiggleRecord():
                write_niggle(self.writing, record, id_)
            case FollowUpRecord():
                write_follow_up(self.writing, record, id_)
            case DecisionRecord():
                write_decision(self.writing, record, id_)
            case AnnotationRecord():
                return write_annotation(self.writing, record, id_)
            case NoteRecord():
                self._note(record, id_)
            case WeighInRecord():
                row = {"id": id_, "date": _iso(record.date), "kg": record.kg}
                self._reading("weigh_in", row)
            case SleepNightRecord():
                row = {"id": id_, "night": _iso(record.night), "hours": record.hours}
                self._reading("sleep_night", row)
            case ActivityRecord():
                self._activity(record, id_)
            case StatusSpanRecord():
                self._status_span(record, id_)
            case WorkoutRecord():
                self._workout(record, id_)
            case ExerciseRecord():
                self._exercise(record)
            case ObservationRecord(retire=str(target)):
                self._retire_observation(target, record)
            case ObservationRecord():
                self._observation(record, id_)
        return None

    def _note(self, record: NoteRecord, id_: str) -> None:
        about = self._resolve(record.about) if record.about else None
        if about and not refs.exists(self.conn, about):
            raise Invalid("draft_ref_unresolved", f"[[note]] about {about} names no stored record")
        row = {"id": id_, "date": _iso(record.date), "text": record.text, "about": _text(about)}
        notes.insert(self.conn, self._stamped(row))

    def _reading(self, table: str, row: Mapping[str, object]) -> None:
        readings.insert(
            self.conn, table, self._stamped({**row, "source": self.stamp.reading_source})
        )

    def _activity(self, record: ActivityRecord, id_: str) -> None:
        row: dict[str, object] = {
            "id": id_,
            "date": _iso(record.date),
            "kind": record.kind,
            "minutes": record.minutes,
            "distance_km": record.distance_km,
            "rpe": record.rpe,
            "quality": int(record.quality),
            "text": record.text,
        }
        readings.insert(self.conn, "activity", self._stamped(row))

    def _status_span(self, record: StatusSpanRecord, id_: str) -> None:
        row: dict[str, object] = {
            "id": id_,
            "kind": record.kind,
            "from_date": _iso(record.from_date),
            "to_date": _iso(record.to_date),
            "text": record.text,
        }
        readings.insert(self.conn, "status_span", self._stamped(row))

    def _withdraw(self, table: str, id_: str, target: str) -> str:
        withdrawn = withdrawable(
            table,
            target,
            readings.get(self.conn, table, target),
            readings.withdrawn_by(self.conn, table, target),
        )
        row: dict[str, object] = {"id": id_, "withdraws": target}
        row.update({column: withdrawn[column] for column in RESTATED[table]})
        readings.insert(self.conn, table, self._stamped(row))
        return target

    def _workout(self, record: WorkoutRecord, id_: str) -> None:
        if record.session_id and not workouts.session_exists(self.conn, record.session_id):
            raise Invalid(
                "draft_ref_unresolved",
                f"[[workout]] names session {record.session_id!r}, "
                "which no program version or niggle has raised",
            )
        sets = [self._logged_set(position, s) for position, s in enumerate(record.sets)]
        row = workouts.WorkoutRow(
            id=id_,
            updated_at=self.stamp.recorded_at,
            source="manual",
            date=_iso(record.date) or "",
            title=record.title,
            routine_id=None,
            session_id=record.session_id,
            minutes=record.minutes,
            session_rpe=record.session_rpe,
            notes=record.notes,
            raw=None,
            check_in=self.stamp.check_in,
            draft_hash=self.stamp.draft_hash,
            recorded_at=self.stamp.recorded_at,
        )
        workouts.insert(self.conn, row, sets)

    def _logged_set(self, position: int, record: LoggedSetRecord) -> workouts.SetRow:
        exercise = exercises.get(self.conn, record.exercise)
        if exercise is None:
            raise Invalid(
                "unknown_exercise",
                f"[[workout]] set names exercise {record.exercise!r}, which is not in the library",
            )
        if exercise["hevy_template_id"] is None:
            raise Invalid(
                "hevy_template_missing",
                f"exercise {record.exercise!r} has no hevy_template_id, so a logged set cannot "
                "resolve to it; give it one with an [[exercise]] row first",
            )
        return workouts.SetRow(
            position=position,
            hevy_template_id=str(exercise["hevy_template_id"]),
            hevy_title=str(exercise["hevy_title"] or exercise["name"]),
            set_type=record.set_type,
            weight_kg=record.weight_kg,
            reps=record.reps,
            duration_s=record.duration_s,
            distance_m=record.distance_m,
            rpe=record.rpe,
            note=record.note,
        )

    def _exercise(self, record: ExerciseRecord) -> None:
        template = record.fields.get("hevy_template_id")
        if isinstance(template, str):
            holder = exercises.carrying_template(self.conn, template)
            if holder and holder != record.id:
                raise Invalid(
                    "state_conflict",
                    f"[[exercise]] {record.id}: hevy_template_id {template} is already {holder}'s",
                )
        stored = exercises.get(self.conn, record.id)
        if stored is None:
            missing = [name for name in NEW_EXERCISE_REQUIRED if name not in record.fields]
            if missing:
                raise Invalid(
                    "invalid_argument",
                    f"[[exercise]] {record.id} is not in the library, so it declares every "
                    f"column; missing {', '.join(missing)}",
                )
            exercises.insert(self.conn, {"id": record.id, **record.fields, "source": "record"})
            return
        renamed = [
            n for n in EXERCISE_IDENTITY if n in record.fields and record.fields[n] != stored[n]
        ]
        if renamed:
            raise Invalid(
                "state_conflict",
                f"[[exercise]] {record.id}: {', '.join(renamed)} stay as the library has them",
            )
        changed = {
            name: record.fields[name]
            for name in EXERCISE_EDITABLE
            if name in record.fields and record.fields[name] != stored[name]
        }
        if changed:
            exercises.update(self.conn, record.id, changed)

    def _observation(self, record: ObservationRecord, id_: str) -> None:
        evidence = [
            str(self.writing.stored_ref(ref, "[[observation]] evidence")) for ref in record.evidence
        ]
        row = {"id": id_, "raised": _iso(self.stamp.today), "text": record.text}
        observations.insert(self.conn, self._stamped({**row, "evidence": evidence}))

    def _retire_observation(self, target: str, record: ObservationRecord) -> None:
        stored = observations.get(self.conn, target)
        if stored is None:
            raise Invalid("draft_ref_unresolved", f"[[observation]] retires {target}, not stored")
        if stored["retired_at"] is not None:
            raise Invalid(
                "state_conflict",
                f"[[observation]] retires {target}, already retired at "
                f"{stored['retired_check_in']}",
            )
        observations.retire(
            self.conn,
            target,
            retired_at=str(_iso(self.stamp.today)),
            because=str(record.because),
            check_in=str(self.stamp.check_in),
        )

    def _check_duplicates(self) -> None:
        for table in ("weigh_in", "sleep_night"):
            for duplicate in readings.duplicates(self.conn, table):
                raise Invalid(
                    "reading_duplicate",
                    f"{table} {duplicate.day} from {duplicate.source} has two live rows, "
                    f"{' and '.join(duplicate.ids)}; withdraw one in the Draft",
                )


def _named_id(record: LedgerRecord) -> str | None:
    """The stored id a record names rather than takes fresh."""
    match record:
        case ExerciseRecord():
            return record.id
        case (
            NiggleRecord(niggle=str(named))
            | FollowUpRecord(followup=str(named))
            | ObservationRecord(retire=str(named))
        ):
            return named
        case _:
            return None


# Exercises, then niggles, follow-ups and workouts: the records later ones may cite.
WRITE_ORDER = {"exercise": 0, "niggle": 1, "followup": 1, "workout": 1}


def _write_order(record: LedgerRecord) -> int:
    return WRITE_ORDER.get(kind_of(record), 2)


def _iso(day: datetime.date | None) -> str | None:
    return day.isoformat() if day else None


def _text(ref: Ref | None) -> str | None:
    return str(ref) if ref else None
