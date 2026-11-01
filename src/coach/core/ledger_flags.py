from coach.core.flag import Flag, Scope, raise_flag


def niggle_unconstrained(niggle_id: str, opened: str) -> Flag:
    return raise_flag(
        "niggle_unconstrained",
        Scope("instance"),
        {"niggle_id": niggle_id, "opened": opened},
        f"niggle {niggle_id}, open since {opened}, carries no constraint; give it one with a "
        "[[niggle]] event, or resolve it",
    )


def followup_due(follow_up_id: str, due: str) -> Flag:
    return raise_flag(
        "followup_due",
        Scope("instance"),
        {"follow_up_id": follow_up_id, "due": due},
        f"follow-up {follow_up_id} was due {due}; keep, defer, resolve or drop it",
    )


def training_max_unused(exercise_id: str, scheme: str | None, decision_id: str) -> Flag:
    """A `training_max` Decision on an exercise whose scheme does not read one (overrides.md)."""
    return raise_flag(
        "training_max_unused",
        Scope("exercise", exercise_id=exercise_id),
        {"scheme": scheme, "decision_id": decision_id},
        f"training max {decision_id} on {exercise_id} is read by no line"
        + (f": its scheme is {scheme}" if scheme else ""),
    )
