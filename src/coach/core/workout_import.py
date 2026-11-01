import datetime
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from coach.core.instant import parse_instant, utc_instant
from coach.core.log import StoredSet, Tombstone, TombstoneSource, WorkoutVersion
from coach.core.mirror import Workout, WorkoutEvent

# ADR 0011, "Import": the event pull reaches back this far past the last import.
EVENT_OVERLAP = datetime.timedelta(minutes=10)


@dataclass(frozen=True)
class Presence:
    """What the store holds for one Hevy workout id: its versions and whether it is gone."""

    versions: frozenset[str]
    gone: bool = False


@dataclass(frozen=True)
class Changes:
    versions: tuple[WorkoutVersion, ...]
    tombstones: tuple[Tombstone, ...]
    new: int
    versioned: int

    def count(self, kind: str) -> int:
        return sum(1 for t in self.tombstones if t.kind == kind)


def event_since(last_import: datetime.datetime) -> datetime.datetime:
    return last_import - EVENT_OVERLAP


def full_pull_changes(
    stored: Mapping[str, Presence],
    pulled: Iterable[Workout],
    noticed_at: datetime.datetime,
    zone: datetime.tzinfo,
) -> Changes:
    """A full pull: every listed workout is present, every stored one not listed is gone."""
    pull = _PullChanges(stored, utc_instant(noticed_at), zone, "full")
    listed: set[str] = set()
    for workout in pulled:
        listed.add(workout.id)
        pull.present(workout)
    for workout_id in sorted(set(stored) - listed):
        pull.absent(workout_id)
    return pull.changes()


def event_pull_changes(
    stored: Mapping[str, Presence],
    events: Iterable[WorkoutEvent],
    noticed_at: datetime.datetime,
    zone: datetime.tzinfo,
) -> Changes:
    """An event pull, applied oldest first whatever Hevy's page order: an update is present, a
    delete is gone."""
    pull = _PullChanges(stored, utc_instant(noticed_at), zone, "event")
    for event in sorted(events, key=_event_moment):
        if event.workout is not None:
            pull.present(event.workout)
        else:
            pull.absent(event.workout_id)
    return pull.changes()


def _event_moment(event: WorkoutEvent) -> datetime.datetime:
    if event.workout is not None:
        return parse_instant(event.workout.updated_at)
    if event.deleted_at is not None:
        return parse_instant(event.deleted_at)
    return datetime.datetime.max.replace(tzinfo=datetime.UTC)


def version_of(workout: Workout, zone: datetime.tzinfo) -> WorkoutVersion:
    started = parse_instant(workout.started_at)
    ended = parse_instant(workout.ended_at) if workout.ended_at else None
    return WorkoutVersion(
        id=workout.id,
        updated_at=utc_instant(parse_instant(workout.updated_at)),
        source="hevy",
        date=started.astimezone(zone).date().isoformat(),
        title=workout.title,
        routine_id=workout.routine_id,
        minutes=round((ended - started).total_seconds() / 60) if ended else None,
        notes=workout.notes,
        raw=workout.raw,
        sets=tuple(
            StoredSet(
                position=s.position,
                hevy_template_id=s.hevy_template_id,
                hevy_title=s.hevy_title,
                set_type=s.set_type,
                weight_kg=s.weight_kg,
                reps=s.reps,
                duration_s=s.duration_s,
                distance_m=s.distance_m,
                rpe=s.rpe,
                note=s.note,
            )
            for s in workout.sets
        ),
    )


class _PullChanges:
    """Applies a pull's presence changes in turn, then writes at most one tombstone per workout:
    the net change against what the store held before the pull."""

    def __init__(
        self,
        stored: Mapping[str, Presence],
        noticed_at: str,
        zone: datetime.tzinfo,
        source: TombstoneSource,
    ) -> None:
        self._stored = stored
        self._presence = dict(stored)
        self._noticed_at = noticed_at
        self._zone = zone
        self._source: TombstoneSource = source
        self._versions: list[WorkoutVersion] = []
        self._touched: dict[str, None] = {}
        self._new = 0
        self._versioned = 0

    def present(self, workout: Workout) -> None:
        version = version_of(workout, self._zone)
        known = self._presence.get(workout.id)
        versions = known.versions if known else frozenset[str]()
        if version.updated_at not in versions:
            self._versions.append(version)
            if known is None:
                self._new += 1
            else:
                self._versioned += 1
        self._presence[workout.id] = Presence(versions | {version.updated_at})
        self._touched[workout.id] = None

    def absent(self, workout_id: str) -> None:
        known = self._presence.get(workout_id)
        if known is None or known.gone:
            return
        self._presence[workout_id] = Presence(known.versions, gone=True)
        self._touched[workout_id] = None

    def changes(self) -> Changes:
        return Changes(tuple(self._versions), self._tombstones(), self._new, self._versioned)

    def _tombstones(self) -> tuple[Tombstone, ...]:
        tombstones: list[Tombstone] = []
        for workout_id in self._touched:
            before = self._stored.get(workout_id)
            was_gone = before is not None and before.gone
            now_gone = self._presence[workout_id].gone
            if was_gone != now_gone:
                kind = "gone" if now_gone else "back"
                tombstones.append(Tombstone(workout_id, self._noticed_at, kind, self._source))
        return tuple(tombstones)
