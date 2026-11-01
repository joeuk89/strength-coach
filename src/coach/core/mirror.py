from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

SetType = Literal["warm_up", "working"]


@dataclass(frozen=True)
class Page[T]:
    items: tuple[T, ...]
    page_count: int


@dataclass(frozen=True)
class LoggedSet:
    position: int
    hevy_template_id: str | None
    hevy_title: str | None
    set_type: SetType
    raw_set_type: str
    weight_kg: float | None
    reps: int | None
    duration_s: int | None
    distance_m: float | None
    rpe: float | None
    note: str | None


@dataclass(frozen=True)
class Workout:
    id: str
    updated_at: str
    title: str | None
    routine_id: str | None
    started_at: str
    ended_at: str | None
    notes: str | None
    sets: tuple[LoggedSet, ...]
    raw: str


@dataclass(frozen=True)
class WorkoutEvent:
    kind: Literal["updated", "deleted"]
    workout_id: str
    workout: Workout | None
    deleted_at: str | None


@dataclass(frozen=True)
class RoutineSet:
    index: int
    set_type: str
    weight_kg: float | None
    reps: int | None
    rep_range: tuple[int, int] | None
    duration_s: int | None
    distance_m: float | None


@dataclass(frozen=True)
class RoutineExercise:
    index: int
    hevy_template_id: str
    title: str | None
    rest_s: int | None
    notes: str | None
    superset_id: int | None
    sets: tuple[RoutineSet, ...]


@dataclass(frozen=True)
class Routine:
    id: str
    title: str
    folder_id: str | None
    updated_at: str
    notes: str | None
    exercises: tuple[RoutineExercise, ...]
    raw: str


@dataclass(frozen=True)
class Folder:
    id: str
    title: str
    index: int | None
    updated_at: str | None


@dataclass(frozen=True)
class ExerciseTemplate:
    id: str
    title: str
    exercise_type: str | None
    primary_muscle_group: str | None
    secondary_muscle_groups: tuple[str, ...]
    equipment: str | None
    is_custom: bool


@dataclass(frozen=True)
class BodyMeasurement:
    date: str
    weight_kg: float | None
    lean_mass_kg: float | None
    fat_percent: float | None


type FolderRole = Literal["program", "standing", "retired"]

# ADR 0011, "Routines and folders": the three folders the engine keeps, by exact title.
ENGINE_FOLDER_TITLES: dict[FolderRole, str] = {
    "program": "Program",
    "standing": "Standing",
    "retired": "Retired",
}


@dataclass(frozen=True)
class MirroredRoutine:
    hevy_id: str
    updated_at: str
    title: str
    folder_id: str | None
    raw: str


@dataclass(frozen=True)
class MirroredFolder:
    role: FolderRole
    hevy_id: str
    title: str


def engine_folders(folders: Iterable[Folder]) -> tuple[MirroredFolder, ...]:
    """The Hevy folders that hold an engine title alone; a title two folders share is left for
    `plan apply` to refuse."""
    found = list(folders)
    mirrored: list[MirroredFolder] = []
    for role, title in ENGINE_FOLDER_TITLES.items():
        matches = [f for f in found if f.title == title]
        if len(matches) == 1:
            mirrored.append(MirroredFolder(role, matches[0].id, title))
    return tuple(mirrored)
