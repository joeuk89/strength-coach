from typing import cast

from coach.core.config import Units
from coach.core.flag import Flag
from coach.core.plan_draft import AthleteNote, PlanDraft
from coach.core.prescription import (
    LinePrescription,
    PlanOverride,
    PrescribedGroup,
    SessionPrescription,
)
from coach.core.program.form import SetGroup, group_document
from coach.render.toml import TomlValue, dumps

type Table = dict[str, object]


def plan_draft(draft: PlanDraft, *, units: Units) -> str:
    """The Draft the agent edits, carrying the overrides it was derived with; `acknowledge`
    starts empty and `plan apply` ignores the notes (docs/spec/overrides.md, "Draft shape")."""
    document: Table = {"week": draft.week}
    if draft.supersedes is not None:
        document["supersedes"] = draft.supersedes
    document |= {
        "override": [_override(override) for override in draft.overrides],
        "acknowledge": [],
        "position": {
            "week": draft.position.week,
            "source": draft.position.source,
            "confirmed": draft.confirmed,
        },
        "flag": [_flag(flag) for flag in (*draft.week_flags, *draft.conflicts, *draft.week_checks)],
        "session": [_session(session, draft.notes, units) for session in draft.sessions],
        "note": [_note(note) for note in draft.notes],
    }
    return dumps(cast(dict[str, TomlValue], document))


def _session(
    prescribed: SessionPrescription, notes: tuple[AthleteNote, ...], units: Units
) -> Table:
    session = prescribed.session
    table: Table = {
        "id": session.session_id,
        "date": session.date,
        "location": session.location,
        "kind": session.kind,
        "cadence": session.cadence,
    }
    about = f"planned_session:{session.date.isoformat()}/{session.session_id}"
    table |= _notes_about(notes, about)
    table["line"] = [_line(line, notes, units) for line in prescribed.lines]
    return table


def _line(line: LinePrescription, notes: tuple[AthleteNote, ...], units: Units) -> Table:
    table: Table = {"exercise": line.exercise_id, "scheme": line.scheme}
    if line.derived_from is not None:
        table["derived_from"] = line.derived_from
    table["change"] = line.change
    table |= _notes_about(notes, f"exercise:{line.exercise_id}")
    table["sets"] = [_group(group, units) for group in line.groups]
    table["step"] = [
        {key: value for key, value in step.to_json().items() if value is not None}
        for step in line.steps
    ]
    table["flag"] = [_flag(flag) for flag in line.flags]
    return table


def _group(group: PrescribedGroup, units: Units) -> Table:
    table: Table = {"type": group.type, "count": group.count}
    if group.load is not None:
        table |= {"load": float(group.load.amount), "load_kg": group.load.hevy_kg(units)}
    reps = list(group.reps) if isinstance(group.reps, tuple) else group.reps
    optional = {
        "reps": reps,
        "duration_s": group.duration_s,
        "rpe": group.rpe,
        "rpe_cap": group.rpe_cap,
    }
    return table | {key: value for key, value in optional.items() if value is not None}


def _override(override: PlanOverride) -> Table:
    table: Table = {"kind": override.kind}
    refs = {"session": override.session_id, "exercise": override.exercise_id}
    table |= {key: value for key, value in refs.items() if value is not None}
    if override.date is not None:
        table["date"] = override.date
    for name, value in override.params.items():
        table[name] = _param(value)
    table |= {"because": override.because, "text": override.text}
    if override.evidence:
        table["evidence"] = list(override.evidence)
    return table


def _param(value: object) -> object:
    if isinstance(value, tuple):
        return [
            group_document(item) if isinstance(item, SetGroup) else item
            for item in cast(tuple[object, ...], value)
        ]
    return value


def _flag(flag: Flag) -> Table:
    return {"key": flag.key, "code": flag.code, "severity": flag.severity, "message": flag.message}


def _note(note: AthleteNote) -> Table:
    table: Table = {"date": note.date, "text": note.text}
    return table if note.about is None else table | {"about": note.about}


def _notes_about(notes: tuple[AthleteNote, ...], about: str) -> Table:
    beside = [note.text for note in notes if note.about == about]
    return {"notes": beside} if beside else {}
