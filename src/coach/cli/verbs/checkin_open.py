import datetime
from contextlib import closing

from coach.cli.declaration import Argument, ArgValue, Call, Declaration, Example, Json, Outcome
from coach.cli.instance import open_instance_store
from coach.core.check_in_card import CardField
from coach.core.errors import Invalid
from coach.services.checkin_open import checkin_open

TIERS = ("light", "deep")


def run(call: Call) -> Outcome:
    assert call.instance is not None and call.clock is not None
    athlete = call.instance.config.athlete
    tier = call.args.get("tier")
    if tier is not None and tier not in TIERS:
        raise Invalid("invalid_argument", f"--tier {tier!r} is not one of {', '.join(TIERS)}")
    with closing(open_instance_store(call.instance)) as conn:
        card = checkin_open(
            conn,
            call.clock,
            units=athlete.units,
            bodyweight_units=athlete.bodyweight_units,
            date=_date(call.args.get("date")),
            tier=None if tier is None else str(tier),
            cadence_days=athlete.checkin_cadence_days,
        )
    return Outcome(
        {
            "tier": card.tier,
            "window": {"start": card.window.start.isoformat(), "end": card.window.end.isoformat()},
            "catch_up": card.catch_up,
            "card": [_field(f) for f in card.fields],
        },
        warnings=card.warnings,
    )


def _field(found: CardField) -> Json:
    return {
        "field": found.name,
        **found.facts,
        "asks": [
            {"ask": ask.kind, **({"about": ask.about} if ask.about else {})} for ask in found.asks
        ],
    }


def _date(value: ArgValue | None) -> datetime.date | None:
    if value is None:
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError as error:
        raise Invalid("invalid_argument", f"--date {value!r} is not a date") from error


DECLARATION = Declaration(
    name="checkin open",
    summary=(
        "The check-in card at a date: header, sessions, week kind, Block with the fatigue "
        "triggers and the light-week proposal, adherence, dose, lifts, readiness, sleep, weight "
        "and Phase, activities, niggles, follow-ups, notes and the deep tier, in that order, each "
        "prefilled from the store with `asks` for what only the athlete knows; a field with "
        "nothing to say is left out. The outside-plan codes it owns come in warnings[]."
    ),
    writes="none",
    needs_instance=True,
    arguments=(
        Argument("--date", "the check-in's date (default today)"),
        Argument("--tier", "deep raises the derived tier; it never lowers it"),
    ),
    output={
        "type": "object",
        "properties": {
            "tier": {"enum": list(TIERS)},
            "window": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "format": "date"},
                    "end": {"type": "string", "format": "date"},
                },
                "required": ["start", "end"],
            },
            "catch_up": {"type": "boolean"},
            "card": {
                "type": "array",
                "description": "the fields in card order, each with its facts and its asks",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "asks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "ask": {"type": "string"},
                                    "about": {"type": "string"},
                                },
                                "required": ["ask"],
                            },
                        },
                    },
                    "required": ["field", "asks"],
                },
            },
        },
        "required": ["tier", "window", "catch_up", "card"],
    },
    run=run,
    examples=(
        Example(("checkin", "open"), "Open today's check-in card."),
        Example(
            ("checkin", "open", "--date", "2026-11-01", "--tier", "deep"),
            "Open the card for 1 Nov 2026 at the deep tier.",
        ),
    ),
)
