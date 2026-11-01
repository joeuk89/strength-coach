"""Program versions as rows: the version, its sessions and its lines (schema.md, "Program")."""

import json
from dataclasses import dataclass

from coach.core.program.form import (
    AcknowledgeEntry,
    ProgramForm,
    line_document,
    scheme_document,
)
from coach.core.program.parse import parse_form
from coach.store.connection import Connection
from coach.store.ids import next_ids

VERSION_COLUMNS = (
    "id",
    "sequence",
    "name",
    "kind",
    "because",
    "emphasis",
    "location",
    "position",
    "adopted",
    "form",
    "schedule",
    "dose",
    "deload",
    "draft_hash",
    "recorded_at",
)
READ = "SELECT id, sequence, position, adopted, form, draft_hash, recorded_at FROM program_version"


@dataclass(frozen=True)
class VersionRow:
    id: str
    sequence: int
    position: str
    adopted: str
    form: ProgramForm
    draft_hash: str
    recorded_at: str


def insert_version(conn: Connection, row: VersionRow) -> None:
    """The version row, a `session` row for each id it names first, and its sessions and lines."""
    document = row.form.to_document()
    values = {
        "id": row.id,
        "sequence": row.sequence,
        "name": row.form.name,
        "kind": row.form.kind,
        "because": row.form.because,
        "emphasis": row.form.emphasis,
        "location": row.form.location,
        "position": row.position,
        "adopted": row.adopted,
        "form": _json(document),
        "schedule": _json(document["schedule"]),
        "dose": _json(document.get("dose")),
        "deload": _json(document.get("deload")),
        "draft_hash": row.draft_hash,
        "recorded_at": row.recorded_at,
    }
    conn.execute(
        f"INSERT INTO program_version VALUES ({', '.join('?' * len(VERSION_COLUMNS))})",
        [values[name] for name in VERSION_COLUMNS],
    )
    for session in row.form.sessions:
        conn.execute("INSERT OR IGNORE INTO session VALUES (?, ?)", (session.id, row.id))
        conn.execute(
            "INSERT INTO program_session VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row.id,
                session.id,
                session.title,
                session.kind,
                session.tier,
                session.cadence or "weekly",
                session.location,
                session.minutes,
                _json(scheme_document(session.scheme)) if session.scheme else None,
                _json(dict(session.estimated_sets)) if session.estimated_sets else None,
            ),
        )
        for position, line in enumerate(session.lines, start=1):
            written = line_document(line)
            conn.execute(
                "INSERT INTO program_line VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.id,
                    session.id,
                    line.exercise,
                    position,
                    line.load_mode,
                    _json(written["sets"]),
                    line.rest_s,
                    line.cues,
                    _json(written["scheme"]),
                    line.start_load,
                    line.superset,
                ),
            )


def freeze_acknowledgements(
    conn: Connection, version_id: str, entries: tuple[AcknowledgeEntry, ...]
) -> None:
    ids = next_ids(conn, "acknowledgement", "ak-", len(entries))
    conn.executemany(
        "INSERT INTO acknowledgement (id, version_id, key, params_hash, because, text) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (id_, version_id, entry.flag, entry.params_hash, entry.because, entry.text)
            for id_, entry in zip(ids, entries, strict=True)
        ],
    )


def acknowledgements(conn: Connection, version_id: str) -> tuple[AcknowledgeEntry, ...]:
    return tuple(
        AcknowledgeEntry(key, because, text, params_hash)
        for key, params_hash, because, text in conn.execute(
            "SELECT key, params_hash, because, text FROM acknowledgement "
            "WHERE version_id = ? ORDER BY id",
            (version_id,),
        )
    )


def latest(conn: Connection) -> VersionRow | None:
    return _one(conn, f"{READ} ORDER BY sequence DESC LIMIT 1", ())


def in_force_at(conn: Connection, instant: str) -> VersionRow | None:
    """The latest version recorded by `instant`; one recorded in the same second counts."""
    return _one(
        conn,
        f"{READ} WHERE substr(recorded_at, 1, 19) <= substr(?, 1, 19) "
        "ORDER BY sequence DESC LIMIT 1",
        (instant,),
    )


def line_counts(conn: Connection, version_id: str) -> list[tuple[str, int]]:
    """Each session of the version with its line count, in the version's order."""
    return [
        (session_id, count)
        for session_id, count in conn.execute(
            "SELECT s.session_id, count(l.exercise_id) FROM program_session s "
            "LEFT JOIN program_line l "
            "ON l.version_id = s.version_id AND l.session_id = s.session_id "
            "WHERE s.version_id = ? GROUP BY s.session_id ORDER BY min(s.rowid)",
            (version_id,),
        )
    ]


def block_opened(conn: Connection) -> str | None:
    """The adopted date of the latest redesign: the open Block's id is `b-<that date>`."""
    found = conn.execute(
        "SELECT adopted FROM program_version WHERE kind = 'redesign' ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    return found[0] if found else None


def _one(conn: Connection, sql: str, params: tuple[object, ...]) -> VersionRow | None:
    found = conn.execute(sql, params).fetchone()
    if found is None:
        return None
    id_, sequence, position, adopted, form, draft_hash, recorded_at = found
    parsed, _ = parse_form(json.loads(form), file=f"program_version {id_}")
    return VersionRow(id_, sequence, position, adopted, parsed, draft_hash, recorded_at)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
