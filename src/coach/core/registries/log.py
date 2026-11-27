from dataclasses import dataclass
from typing import Literal

from coach.core.registries.registry import Registry, Row, terms

WORKOUT_SOURCES = terms("workout-sources", "hevy", "manual")
TOMBSTONE_KINDS = terms("tombstone-kinds", "gone", "back")
IMPORT_PULLS = terms("import-pulls", "event", "full")
REPAIRABLE = ("reps", "rpe", "weight_kg", "set_type")


@dataclass(frozen=True)
class AnnotationParam:
    name: str
    required: bool
    about: str

    def describe(self) -> Row:
        return {"name": self.name, "required": self.required, "about": self.about}


@dataclass(frozen=True)
class AnnotationKind:
    name: str
    target: Literal["workout", "planned_session"]
    params: tuple[AnnotationParam, ...] = ()

    def describe(self) -> Row:
        return {
            "name": self.name,
            "target": self.target,
            "params": [param.describe() for param in self.params],
        }


POSITION = (
    "the set's position in the workout, counted from 0 across every exercise's sets in logged order"
)
# core/exposure.py and the match writer read these param names; rename them together.
ANNOTATION_KINDS = Registry(
    "annotation-kinds",
    (
        AnnotationKind(
            "discount",
            "workout",
            (AnnotationParam("position", False, f"{POSITION}; every set when left out"),),
        ),
        AnnotationKind(
            "repair",
            "workout",
            (
                AnnotationParam("position", True, POSITION),
                AnnotationParam("field", True, f"the field corrected: {', '.join(REPAIRABLE)}"),
                AnnotationParam("value", True, "the field's corrected value"),
            ),
        ),
        AnnotationKind(
            "load_mode",
            "workout",
            (AnnotationParam("load_mode", True, "the load mode the logged loads are read in"),),
        ),
        AnnotationKind("void", "workout"),
        AnnotationKind("trained_unlogged", "planned_session"),
        AnnotationKind("cancelled", "planned_session"),
        AnnotationKind("miss_tag", "planned_session"),
        AnnotationKind(
            "match",
            "workout",
            (
                AnnotationParam(
                    "planned_session",
                    True,
                    "planned_session:<date>/<session id>, the session the workout trained",
                ),
            ),
        ),
    ),
)
WEIGH_IN_SOURCES = terms("weigh-in-sources", "check_in", "hevy", "manual")
SLEEP_NIGHT_SOURCES = terms("sleep-night-sources", "check_in", "manual")
STATUS_SPAN_KINDS = terms("status-span-kinds", "ill", "injured", "travel", "no_training")
