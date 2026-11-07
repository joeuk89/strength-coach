from coach.core.registries.agent import RECORD_KINDS, VIEWS
from coach.core.registries.errors import ERRORS
from coach.core.registries.flags import FLAGS
from coach.core.registries.hevy import ROUTINE_STATUSES
from coach.core.registries.ledger import (
    CHECK_IN_STATUSES,
    CHECK_IN_TIERS,
    CONSTRAINT_KINDS,
    DECISION_KINDS,
    FOLLOW_UP_EVENTS,
    GOAL_KINDS,
    GOAL_STATUSES,
    NIGGLE_STATUSES,
    READINESS,
    REASONS,
)
from coach.core.registries.log import (
    ANNOTATION_KINDS,
    IMPORT_PULLS,
    SLEEP_NIGHT_SOURCES,
    STATUS_SPAN_KINDS,
    TOMBSTONE_KINDS,
    WEIGH_IN_SOURCES,
    WORKOUT_SOURCES,
)
from coach.core.registries.phase import PHASE
from coach.core.registries.program import (
    EQUIPMENT_KINDS,
    EXERCISE_SOURCES,
    LOAD_MODES,
    SESSION_KINDS,
    SET_TYPES,
    VERSION_KINDS,
)
from coach.core.registries.registry import Entry, Registry
from coach.core.registries.schemes import SCHEMES
from coach.core.registries.week import OVERRIDE_KINDS, PLAN_STATUSES

# `coach schema` lists the names in this order: the registries the agent reads most first, then
# one per remaining CHECK list in `schema.sql`, then the error codes.
REGISTRIES: tuple[Registry[Entry], ...] = (
    SCHEMES,
    FLAGS,
    RECORD_KINDS,
    VIEWS,
    DECISION_KINDS,
    OVERRIDE_KINDS,
    REASONS,
    ANNOTATION_KINDS,
    CONSTRAINT_KINDS,
    SET_TYPES,
    LOAD_MODES,
    EQUIPMENT_KINDS,
    PHASE,
    VERSION_KINDS,
    SESSION_KINDS,
    EXERCISE_SOURCES,
    PLAN_STATUSES,
    WORKOUT_SOURCES,
    TOMBSTONE_KINDS,
    IMPORT_PULLS,
    WEIGH_IN_SOURCES,
    SLEEP_NIGHT_SOURCES,
    STATUS_SPAN_KINDS,
    CHECK_IN_STATUSES,
    CHECK_IN_TIERS,
    READINESS,
    NIGGLE_STATUSES,
    FOLLOW_UP_EVENTS,
    GOAL_KINDS,
    GOAL_STATUSES,
    ROUTINE_STATUSES,
    ERRORS,
)


def find(name: str) -> Registry[Entry] | None:
    return next((r for r in REGISTRIES if r.name == name), None)
