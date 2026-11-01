import datetime
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from coach.core.mirror import (
    BodyMeasurement,
    ExerciseTemplate,
    Folder,
    Routine,
    Workout,
    WorkoutEvent,
)

type Payload = dict[str, object]
type RoutineDiff = Callable[[Routine], tuple[str, ...]]


@dataclass(frozen=True)
class WriteContext:
    """What the Write audit records beside each write's body (ADR 0011, "Write audit")."""

    week_plan_id: str
    write_plan_hash: str
    routine_id: str | None


@dataclass(frozen=True)
class ReadBack:
    routine: Routine
    diff: tuple[str, ...]

    @property
    def verified(self) -> bool:
        return not self.diff


class HevyClient(Protocol):
    """The one seam to Hevy: four allow-listed writes, the GETs, and the Write audit."""

    def open_audit(self) -> None: ...

    def create_routine(self, body: Payload, context: WriteContext) -> Routine: ...

    def update_routine(self, routine_id: str, body: Payload, context: WriteContext) -> Routine: ...

    def create_folder(self, body: Payload, context: WriteContext) -> Folder: ...

    def create_exercise_template(self, body: Payload, context: WriteContext) -> str: ...

    def workouts(self) -> tuple[Workout, ...]: ...

    def workout_events(self, since: datetime.datetime) -> tuple[WorkoutEvent, ...]: ...

    def routines(self) -> tuple[Routine, ...]: ...

    def routine(self, routine_id: str) -> Routine: ...

    def read_back(self, routine_id: str, context: WriteContext, diff: RoutineDiff) -> ReadBack:
        """GET the routine, diff it against what was sent, and append the verify line."""
        ...

    def folders(self) -> tuple[Folder, ...]: ...

    def exercise_templates(self) -> tuple[ExerciseTemplate, ...]: ...

    def body_measurements(self) -> tuple[BodyMeasurement, ...]: ...
