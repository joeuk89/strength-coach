from dataclasses import dataclass
from typing import Literal

type WorkoutSource = Literal["hevy", "manual"]
type TombstoneKind = Literal["gone", "back"]
type TombstoneSource = Literal["event", "full"]


@dataclass(frozen=True)
class StoredSet:
    position: int
    hevy_template_id: str | None
    hevy_title: str | None
    set_type: str
    weight_kg: float | None
    reps: int | None
    duration_s: int | None
    distance_m: float | None
    rpe: float | None
    note: str | None


@dataclass(frozen=True)
class WorkoutVersion:
    id: str
    updated_at: str
    source: WorkoutSource
    date: str
    title: str | None
    routine_id: str | None
    minutes: int | None
    notes: str | None
    raw: str | None
    sets: tuple[StoredSet, ...]


@dataclass(frozen=True)
class Tombstone:
    workout_id: str
    noticed_at: str
    kind: TombstoneKind
    source: TombstoneSource


@dataclass(frozen=True)
class WeighIn:
    id: str
    date: str
    kg: float
    source: str


@dataclass(frozen=True)
class ImportRun:
    id: str
    at: str
    since: str | None
    kind: str
    summary: dict[str, int]
