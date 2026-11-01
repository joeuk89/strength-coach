from typing import Literal, get_args

from coach.core.registries.registry import terms

type Reason = Literal[
    "pain", "kit", "stall", "fatigue", "schedule", "athlete_request", "coach_judgement"
]

REASONS = terms("reasons", *get_args(Reason.__value__))
