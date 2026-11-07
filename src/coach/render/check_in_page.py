"""A check-in record: the read verbatim beside generated sections of typed facts
(docs/spec/check-in.md, "The prose rule")."""

from coach.core.pages import CheckInRecord
from coach.render.facts import facts_text
from coach.render.markdown import page, section, table

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


def check_in_path(record: CheckInRecord) -> str:
    return f"pages/check-ins/{record.date.isoformat()}.md"


def check_in_page(record: CheckInRecord) -> str:
    window = record.window
    intro = (
        f"{record.tier.capitalize()} check-in over {window.start.isoformat()} to "
        f"{window.end.isoformat()}{', a catch-up' if window.catch_up else ''}. "
        f"Readiness: {record.readiness or 'not given'}."
    )
    generated = [
        section(TITLES[f.name], facts_text(f.facts)) for f in record.card.fields if f.name in TITLES
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
