from dataclasses import dataclass

from coach.core.registries.registry import Registry, Row, terms

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


@dataclass(frozen=True)
class Pattern:
    name: str
    heavy: bool = False
    compound: bool = False

    def describe(self) -> Row:
        return {"name": self.name, "heavy": self.heavy, "compound": self.compound}


@dataclass(frozen=True)
class Muscle:
    name: str
    dosed: bool

    def describe(self) -> Row:
        return {"name": self.name, "dosed": self.dosed}


PATTERNS = Registry(
    "patterns",
    (
        Pattern("squat", heavy=True, compound=True),
        Pattern("hinge", heavy=True, compound=True),
        Pattern("lunge", compound=True),
        Pattern("horizontal_push", compound=True),
        Pattern("vertical_push", compound=True),
        Pattern("horizontal_pull", compound=True),
        Pattern("vertical_pull", compound=True),
        Pattern("core"),
        Pattern("carry"),
        Pattern("conditioning"),
        Pattern("balance"),
        Pattern("calf_raise"),
        Pattern("elbow_flexion"),
        Pattern("elbow_extension"),
        Pattern("hip_abduction"),
        Pattern("hip_adduction"),
        Pattern("knee_extension"),
        Pattern("knee_flexion"),
        Pattern("shoulder_raise"),
    ),
)
# Dosed muscles first: the dose rule reports them in this order.
MUSCLES = Registry(
    "muscles",
    (
        Muscle("chest", dosed=True),
        Muscle("lats", dosed=True),
        Muscle("upper_back", dosed=True),
        Muscle("front_delts", dosed=True),
        Muscle("side_delts", dosed=True),
        Muscle("rear_delts", dosed=True),
        Muscle("biceps", dosed=True),
        Muscle("triceps", dosed=True),
        Muscle("quadriceps", dosed=True),
        Muscle("hamstrings", dosed=True),
        Muscle("glutes", dosed=True),
        Muscle("calves", dosed=True),
        Muscle("abdominals", dosed=True),
        Muscle("adductors", dosed=False),
        Muscle("abductors", dosed=False),
        Muscle("lower_back", dosed=False),
        Muscle("forearms", dosed=False),
        Muscle("traps", dosed=False),
    ),
)
# rn:concurrent-training.5: a heavy squat or hinge session drives the next-day activity rule.
HEAVY_PATTERNS = tuple(p.name for p in PATTERNS.entries if p.heavy)
# A compound lift is multi-joint: the patterns RPE drift reads (rn:autoregulation.4).
COMPOUND_PATTERNS = tuple(p.name for p in PATTERNS.entries if p.compound)
DOSED_MUSCLES = tuple(m.name for m in MUSCLES.entries if m.dosed)
