from coach.core.registries.registry import terms

SET_TYPES = terms("set-types", "warm_up", "working", "activation", "test")
LOAD_MODES = terms(
    "load-modes",
    "total",
    "per_hand_x2",
    "single_implement",
    "bodyweight",
    "assisted",
    "band",
    "duration",
    "distance",
)
EQUIPMENT_KINDS = terms(
    "equipment-kinds",
    "barbell",
    "dumbbell",
    "kettlebell",
    "leg_attachment",
    "vest",
    "machine",
    "cable",
    "band",
    "bodyweight",
)
VERSION_KINDS = terms("version-kinds", "amend", "redesign")
SESSION_KINDS = terms("session-kinds", "lifting", "conditioning", "practice", "coach_led")
EXERCISE_SOURCES = terms("exercise-sources", "catalogue", "draft", "record")
