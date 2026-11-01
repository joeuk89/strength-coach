"""Exposures resolved on read (docs/spec/cutover.md, "Exercise resolution on read"): a logged
set's Exercise through its template id, annotations applied in id order."""

import datetime
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import cast

from coach.core.config import Units
from coach.core.load import Load, LoadMode, from_hevy_kg
from coach.core.log import StoredSet

EXPOSURE_SET_TYPES = ("working", "test")
REPAIRABLE = ("reps", "rpe", "weight_kg", "set_type")


@dataclass(frozen=True)
class Matched:
    """The planned session a workout fulfilled, whether its week was a light week, and the
    exercise ids of the lines that took the return band in it."""

    session_id: str
    light_week: bool = False
    return_band_lines: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ExposureSet:
    position: int
    set_type: str
    load: Load | None
    reps: int | None
    rpe: float | None


@dataclass(frozen=True)
class Exposure:
    workout_id: str
    exercise_id: str
    date: datetime.date
    sets: tuple[ExposureSet, ...]
    match: Matched | None = None
    annotations: tuple[str, ...] = ()

    @property
    def ref(self) -> str:
        return f"exposure:{self.workout_id}/{self.exercise_id}"

    @property
    def working(self) -> tuple[ExposureSet, ...]:
        return tuple(s for s in self.sets if s.set_type == "working")

    @property
    def session_id(self) -> str | None:
        return None if self.match is None else self.match.session_id

    @property
    def top_load(self) -> Load | None:
        """The heaviest working load; under assistance, the least assistance."""
        loads = [s.load for s in self.working if s.load is not None]
        if not loads:
            return None
        if loads[0].mode == "assisted":
            return min(loads, key=lambda load: load.amount)
        return max(loads, key=lambda load: load.amount)


@dataclass(frozen=True)
class LibraryEntry:
    exercise_id: str
    load_mode: LoadMode


@dataclass(frozen=True)
class LoggedWorkout:
    id: str
    date: datetime.date
    sets: tuple[StoredSet, ...]
    match: Matched | None = None


@dataclass(frozen=True)
class Annotation:
    """One live annotation: neither withdrawn nor itself a withdrawal."""

    id: str
    kind: str
    target: str
    params: Mapping[str, object]

    @property
    def number(self) -> int:
        return int(self.id.removeprefix("a-"))


def resolve(
    workouts: Iterable[LoggedWorkout],
    library: Mapping[str, LibraryEntry],
    annotations: Iterable[Annotation],
    units: Units,
) -> tuple[Exposure, ...]:
    """One Exposure per exercise per workout with at least one working set left."""
    ordered = sorted(annotations, key=lambda a: a.number)
    exposures: list[Exposure] = []
    for workout in workouts:
        for exercise_id, (mode, sets) in _by_exercise(workout, library).items():
            corrected = _Corrected(mode, sets)
            for annotation in ordered:
                if annotation.target in (
                    f"workout:{workout.id}",
                    f"workout:{workout.id}/{exercise_id}",
                ):
                    corrected.apply(annotation)
            exposure = Exposure(
                workout.id,
                exercise_id,
                workout.date,
                corrected.exposure_sets(units),
                workout.match,
                tuple(corrected.applied),
            )
            if exposure.working:
                exposures.append(exposure)
    return tuple(exposures)


def _by_exercise(
    workout: LoggedWorkout, library: Mapping[str, LibraryEntry]
) -> dict[str, tuple[LoadMode, list[StoredSet]]]:
    found: defaultdict[str, list[StoredSet]] = defaultdict(list)
    modes: dict[str, LoadMode] = {}
    for logged in workout.sets:
        entry = library.get(logged.hevy_template_id or "")
        if entry is not None:
            found[entry.exercise_id].append(logged)
            modes[entry.exercise_id] = entry.load_mode
    return {exercise_id: (modes[exercise_id], sets) for exercise_id, sets in found.items()}


class _Corrected:
    def __init__(self, mode: LoadMode, sets: list[StoredSet]) -> None:
        self.mode: LoadMode = mode
        self.sets = list(sets)
        self.applied: list[str] = []

    def apply(self, annotation: Annotation) -> None:
        position = annotation.params.get("position")
        match annotation.kind:
            case "void":
                self.sets = []
            case "discount":
                self.sets = [
                    s for s in self.sets if position is not None and s.position != position
                ]
            case "repair" if annotation.params.get("field") in REPAIRABLE:
                field = str(annotation.params["field"])
                value = annotation.params["value"]
                self.sets = [
                    replace(s, **{field: value}) if s.position == position else s for s in self.sets
                ]
            case "load_mode":
                self.mode = cast(LoadMode, annotation.params["load_mode"])
            case _:
                return
        self.applied.append(annotation.id)

    def exposure_sets(self, units: Units) -> tuple[ExposureSet, ...]:
        return tuple(
            ExposureSet(
                s.position, s.set_type, from_hevy_kg(s.weight_kg, self.mode, units), s.reps, s.rpe
            )
            for s in self.sets
            if s.set_type in EXPOSURE_SET_TYPES
        )
