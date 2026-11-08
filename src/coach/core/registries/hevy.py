from coach.core.registries.registry import terms

ROUTINE_STATUSES = terms("routine-statuses", "active", "retired", "missing", "unverified")

# Hevy's closed enums for a created exercise template, from its OpenAPI `CustomExerciseType`,
# `EquipmentCategory` and `MuscleGroup`.
HEVY_EXERCISE_TYPES = terms(
    "hevy-exercise-types",
    "weight_reps",
    "reps_only",
    "bodyweight_reps",
    "bodyweight_assisted_reps",
    "duration",
    "weight_duration",
    "distance_duration",
    "short_distance_weight",
)
HEVY_EQUIPMENT = terms(
    "hevy-equipment",
    "none",
    "barbell",
    "dumbbell",
    "kettlebell",
    "machine",
    "plate",
    "resistance_band",
    "suspension",
    "other",
)
HEVY_MUSCLE_GROUPS = terms(
    "hevy-muscle-groups",
    "abdominals",
    "shoulders",
    "biceps",
    "triceps",
    "forearms",
    "quadriceps",
    "hamstrings",
    "calves",
    "glutes",
    "abductors",
    "adductors",
    "lats",
    "upper_back",
    "traps",
    "lower_back",
    "chest",
    "cardio",
    "neck",
    "full_body",
    "other",
)
