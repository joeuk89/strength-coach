from pathlib import Path

from support.fixture_instances import coach, instance, rebuilt

__all__ = ["instance", "rebuilt"]


def test_the_cards_lift_rows_follow_the_list_rule(instance: Path) -> None:
    card = coach("checkin", "open", "--full").envelope["result"]["card"]
    every = next(f for f in card if f["field"] == "lifts")

    lifts = next(
        f for f in coach("checkin", "open").envelope["result"]["card"] if f["field"] == "lifts"
    )

    assert len(every["rows"]) == every["count"] == 4
    assert every["truncated"] is False
    assert lifts["count"] == 4
    assert lifts["truncated"] is True
    assert lifts["rows"] == every["rows"][: len(lifts["rows"])]
