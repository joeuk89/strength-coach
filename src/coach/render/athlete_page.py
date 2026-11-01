"""The athlete page: the profile verbatim with sections generated from config and the store
(ADR 0009)."""

from coach.core.config import GridLocation, Location
from coach.core.pages import AthletePage
from coach.render.markdown import bullets, cell, page, section, table


def athlete_page(athlete: AthletePage) -> str:
    facts = athlete.athlete
    return page(
        "Athlete",
        section("Profile", athlete.profile or "No profile yet."),
        section(
            "Facts",
            bullets(
                [
                    f"units: {facts.units}",
                    f"bodyweight units: {facts.bodyweight_units}",
                    f"week starts: {facts.week_starts}",
                    f"timezone: {facts.timezone}",
                    f"available days: {', '.join(facts.available_days)}",
                    f"session minutes: {facts.session_minutes}",
                    f"check-in cadence days: {facts.checkin_cadence_days}",
                ]
            ),
        ),
        section("Equipment by location", bullets([_location(loc) for loc in athlete.locations])),
        section(
            "Open niggles",
            table(
                ["niggle", "site", "status", "opened", "constraints"],
                [
                    [n.id, n.site, n.status, n.opened, [cell(c) for c in n.constraints]]
                    for n in athlete.niggles
                ],
            ),
        ),
        section(
            "Open follow-ups",
            table(
                ["follow-up", "due", "text"], [[f.id, f.due, f.text] for f in athlete.follow_ups]
            ),
        ),
        section("Observations", bullets(list(athlete.observations))),
        section(
            "Override Decisions",
            table(
                ["decision", "session", "exercise", "until", "because", "text"],
                [
                    [d.id, d.session_id, d.exercise_id, d.until, d.because, d.text]
                    for d in athlete.decisions
                ],
            ),
        ),
        section(
            "Recent reads",
            "\n\n".join(f"**{day.isoformat()}**\n\n{read}" for day, read in athlete.reads),
        ),
    )


def _location(location: Location) -> str:
    implements = ", ".join(f"{kind} → {name}" for kind, name in location.implements.items())
    if isinstance(location, GridLocation):
        return f"{location.name} (grid): {implements or 'no implements'}"
    return f"{location.name} (plate-pool, kit {location.kit}): {implements or 'no implements'}"
