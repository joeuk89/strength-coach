from coach.core.registries.registry import terms

WORKOUT_SOURCES = terms("workout-sources", "hevy", "manual")
TOMBSTONE_KINDS = terms("tombstone-kinds", "gone", "back")
IMPORT_PULLS = terms("import-pulls", "event", "full")
ANNOTATION_KINDS = terms(
    "annotation-kinds",
    "discount",
    "repair",
    "load_mode",
    "void",
    "trained_unlogged",
    "cancelled",
    "miss_tag",
    "match",
)
WEIGH_IN_SOURCES = terms("weigh-in-sources", "check_in", "hevy", "manual")
SLEEP_NIGHT_SOURCES = terms("sleep-night-sources", "check_in", "manual")
STATUS_SPAN_KINDS = terms("status-span-kinds", "ill", "injured", "travel", "no_training")
