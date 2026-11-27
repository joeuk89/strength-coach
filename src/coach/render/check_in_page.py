"""A check-in record: the read verbatim beside generated sections of typed facts
(docs/spec/check-in.md, "The prose rule")."""

from collections.abc import Mapping, Sequence
from typing import cast

from coach.core.check_in_card import CardField
from coach.core.pages import CheckInRecord, PageNames
from coach.core.registries.program import MUSCLES
from coach.core.registries.registry import title_of
from coach.render.facts import Shown, facts_text
from coach.render.markdown import MANUAL_CLIMB, page, section, table

TITLES = {
    "sessions": "Sessions",
    "week_kind": "Week kind",
    "block": "Block",
    "adherence": "Adherence",
    "dose": "Dose",
    "lifts": "Lifts",
    "ladders": "Ladders",
    "sleep": "Sleep",
    "weight_phase": "Weight and Phase",
    "activities": "Activities",
    "niggles": "Niggles",
    "follow_ups": "Follow-ups",
    "notes": "Notes",
    "deep_tier": "Deep tier",
}

PLANNED_SESSION = "planned_session:"


def check_in_path(record: CheckInRecord) -> str:
    return f"pages/check-ins/{record.date.isoformat()}.md"


def check_in_page(record: CheckInRecord, *, names: PageNames) -> str:
    window = record.window
    intro = (
        f"{record.tier.capitalize()} check-in over {window.start.isoformat()} to "
        f"{window.end.isoformat()}{', a catch-up' if window.catch_up else ''}. "
        f"Readiness: {record.readiness or 'not given'}."
    )
    generated = [
        section(TITLES[f.name], _field_text(f, names))
        for f in record.card.fields
        if f.name in TITLES
    ]
    decisions = table(
        ["decision", "kind", "because", "text"],
        [[d.id, d.kind, d.because, d.text] for d in record.decisions],
    )
    return page(
        f"Check-in {record.date.isoformat()}",
        intro,
        section("Read", record.read),
        *generated,
        section("Decisions", decisions),
    )


def _field_text(field: CardField, names: PageNames) -> str:
    if field.name == "ladders":
        return _ladders(cast(Sequence[Mapping[str, object]], field.facts["rows"]), names)
    facts = field.facts
    if field.name == "block":
        facts = {key: value for key, value in facts.items() if key != "block"}
    return facts_text(facts, _shown(names))


def _shown(names: PageNames) -> Shown:
    def shown(key: str, value: object) -> object:
        if not isinstance(value, str):
            return value
        if key in ("exercise", "lift"):
            return names.exercise(value)
        if key == "muscle":
            return title_of(MUSCLES, value)
        if key == "session" and value.startswith(PLANNED_SESSION):
            day, session_id = value.removeprefix(PLANNED_SESSION).split("/", 1)
            return f"{names.session(session_id)} on {day}"
        return value

    return shown


def _ladders(rows: Sequence[Mapping[str, object]], names: PageNames) -> str:
    return table(
        ["line", "standing rung", "exposures toward the criterion", "met", "held", "next rung"],
        [
            [
                f"{names.session(str(r['session']))}: {names.exercise(str(r['line']))}",
                r["label"],
                MANUAL_CLIMB if r["needed"] is None else f"{r['exposures']} of {r['needed']}",
                r["met"],
                r["held"],
                r["next_label"],
            ]
            for r in rows
        ],
    )
