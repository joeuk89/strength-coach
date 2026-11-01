from coach.core.ref import Ref
from coach.core.registries.agent import RECORD_KINDS
from coach.store.connection import Connection

# Ref kinds that are not record kinds, each naming a row of the table of its own name.
OWN_TABLE = ("goal", "milestone", "phase", "check_in", "routine")
KEY_OF = {"routine": "hevy_id"}


def exists(conn: Connection, ref: Ref) -> bool:
    """Whether a ref names a row of the live tables (schema.md, "Refs")."""
    if ref.kind == "planned_session":
        return _planned_session(conn, ref.id)
    if ref.kind in ("workout", "exposure"):
        workout_id, _, exercise_id = ref.id.partition("/")
        if ref.kind == "exposure" and not exercise_id:
            return False
        return _row(conn, "workout", workout_id) and (
            not exercise_id or _row(conn, "exercise", exercise_id)
        )
    table = _table_of(ref)
    return table is not None and _row(conn, table, ref.id)


def _table_of(ref: Ref) -> str | None:
    if ref.record_kind in RECORD_KINDS:
        return RECORD_KINDS.get(ref.record_kind).store_table
    return ref.kind if ref.kind in OWN_TABLE else None


def _row(conn: Connection, table: str, id_: str) -> bool:
    key = KEY_OF.get(table, "id")
    return conn.execute(f"SELECT 1 FROM {table} WHERE {key} = ?", (id_,)).fetchone() is not None


def _planned_session(conn: Connection, ref_id: str) -> bool:
    """`<date>/<session id>`, resolved against the plan in force on that date."""
    date, _, session_id = ref_id.partition("/")
    found = conn.execute(
        "SELECT 1 FROM plan_in_force p JOIN prescription r ON r.plan_id = p.id "
        "WHERE ? BETWEEN p.week AND p.week_end AND r.date = ? AND r.session_id = ?",
        (date, date, session_id),
    ).fetchone()
    return found is not None
