from coach.core.flag import Flag, Scope, raise_flag


def niggle_unconstrained(niggle_id: str, opened: str) -> Flag:
    return raise_flag(
        "niggle_unconstrained",
        Scope("instance"),
        {"niggle_id": niggle_id, "opened": opened},
        f"niggle {niggle_id}, open since {opened}, carries no constraint; give it one with a "
        "[[niggle]] event, or resolve it",
    )
