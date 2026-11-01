import datetime
from typing import cast

from coach.cli.declaration import (
    Argument,
    ArgValue,
    Declaration,
    Example,
    InInstance,
    InstanceCall,
    Json,
    Outcome,
    always,
)
from coach.cli.instance import open_instance_store
from coach.cli.pull import PULL_SCHEMA
from coach.core.check_in_card import CardField
from coach.core.errors import Invalid
from coach.core.registries.ledger import READINESS
from coach.services.checkin_open import checkin_open

TIERS = ("light", "deep")


def run(call: InstanceCall) -> Outcome:
    tier = call.args.get("tier")
    if tier is not None and tier not in TIERS:
        raise Invalid("invalid_argument", f"--tier {tier!r} is not one of {', '.join(TIERS)}")
    readiness = call.args.get("readiness")
    if readiness is not None and readiness not in READINESS:
        raise Invalid(
            "invalid_argument",
            f"--readiness {readiness!r} is not one of {', '.join(READINESS.names())}",
        )
    with open_instance_store(call.instance) as conn:
        card = checkin_open(
            conn,
            call.clock,
            units=call.instance.units,
            bodyweight_units=call.instance.bodyweight_units,
            date=_date(call.args.get("date")),
            tier=None if tier is None else str(tier),
            readiness=None if readiness is None else str(readiness),
            cadence_days=call.instance.checkin_cadence_days,
        )
    return Outcome(
        {
            "tier": card.tier,
            "window": {"start": card.window.start.isoformat(), "end": card.window.end.isoformat()},
            "catch_up": card.catch_up,
            "card": [_field(f, None if call.full else call.last) for f in card.fields],
        },
        warnings=card.warnings,
    )


def _field(found: CardField, last: int | None) -> Json:
    return {
        "field": found.name,
        **found.facts,
        **_row_list(found.facts.get("rows"), last),
        "asks": [
            {"ask": ask.kind, **({"about": ask.about} if ask.about else {})} for ask in found.asks
        ],
    }


def _row_list(rows: object, last: int | None) -> Json:
    """A field's `rows` follow the list rule (verbs.md, "Envelope and budget")."""
    if not isinstance(rows, list):
        return {}
    every = cast(list[object], rows)
    kept = every if last is None else every[:last]
    return {"rows": kept, "count": len(every), "truncated": len(kept) < len(every)}


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
    writes="store",
    pulls_first=True,
    over_budget=always,
    arguments=(
        Argument("--date", "the check-in's date (default today)"),
        Argument("--tier", "deep raises the derived tier; it never lowers it"),
        Argument(
            "--readiness",
            "the athlete's readiness, poor, ok or good, asked before the card; the readiness "
            "trigger reads it, and with none given it does not hold",
        ),
    ),
    output={
        "type": "object",
        "properties": {
            "pull": PULL_SCHEMA,
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
    run=InInstance(run),
    examples=(
        Example(("checkin", "open"), "Open today's check-in card."),
        Example(
            ("checkin", "open", "--date", "2026-11-01", "--tier", "deep"),
            "Open the card for 1 Nov 2026 at the deep tier.",
        ),
    ),
)
