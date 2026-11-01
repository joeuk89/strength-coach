import datetime

from coach.cli.declaration import (
    Argument,
    Call,
    Declaration,
    Example,
    InInstance,
    InstanceCall,
    Json,
    Outcome,
)
from coach.cli.drafts import read_draft
from coach.cli.instance import open_instance_store
from coach.cli.kit import read_kit_files
from coach.core.errors import Invalid
from coach.core.plan_check import CheckedPlan
from coach.core.registries.agent import VIEWS
from coach.services.plan_apply import validate
from coach.services.query import (
    QueryResult,
    exposures,
    flags,
    ledger,
    lines,
    readings,
    routines,
)
from coach.store.connection import Connection


def run(call: InstanceCall) -> Outcome:
    view = str(call.args["view"])
    if view not in VIEWS:
        raise Invalid("invalid_argument", f"no view {view!r}; one of {', '.join(VIEWS.names())}")
    last = None if call.full else call.last
    kind = _text(call, "kind")
    with open_instance_store(call.instance) as conn:
        if view == "exposures":
            result = exposures(
                conn,
                exercises=_texts(call, "exercise"),
                since=_date(call, "since"),
                last=last,
                units=call.instance.units,
            )
        elif view == "readings":
            result = readings(conn, kind=kind, last=last)
        elif view == "ledger":
            result = ledger(
                conn,
                kind=kind,
                id_=_text(call, "id"),
                open_=call.args.get("open") is True,
                today=call.clock.today(),
                last=last,
            )
        elif view == "flags":
            result = flags(
                conn,
                draft=_draft(call, conn),
                today=call.clock.today(),
                code=_text(call, "code"),
                severity=_text(call, "severity"),
                scope=_text(call, "scope"),
                summary=call.args.get("summary") is True,
                last=last,
            )
        elif view == "lines":
            result = lines(
                conn,
                draft=_draft(call, conn),
                today=call.clock.today(),
                units=call.instance.units,
                exercises=_texts(call, "exercise"),
                session=_text(call, "session"),
                date=_date(call, "date"),
                changed=call.args.get("changed") is True,
                last=last,
            )
        else:
            result = routines(conn, last=last)
    return Outcome(_rows(result))


def _draft(call: InstanceCall, conn: Connection) -> CheckedPlan | None:
    """The named plan Draft validated now, read-only: the check `plan apply --dry-run` runs."""
    path = _text(call, "draft")
    if path is None:
        return None
    return validate(
        conn,
        read_draft(path),
        file=path,
        config=call.instance.config,
        kits=read_kit_files(call.instance),
        clock=call.clock,
    ).checked


def _text(call: Call, name: str) -> str | None:
    value = call.args.get(name)
    return value if isinstance(value, str) else None


def _texts(call: Call, name: str) -> tuple[str, ...]:
    value = call.args.get(name, ())
    return value if isinstance(value, tuple) else ()


def _date(call: Call, name: str) -> datetime.date | None:
    text = _text(call, name)
    if text is None:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        raise Invalid(
            "invalid_argument", f"--{name} takes a date, YYYY-MM-DD, not {text!r}"
        ) from None


def _rows(result: QueryResult) -> Json:
    return {"rows": result.rows, "count": result.count, "truncated": result.truncated}


DECLARATION = Declaration(
    name="query",
    summary="One read view as a row list: exposures (each exercise in a workout with its "
    "annotations applied and its e1RM), readings (Weigh-ins, Sleep nights, Activities), "
    "flags and lines (of the plan in force, or of a plan Draft validated now with --draft), "
    "routines (the Routine map with each routine's folder, status and last verify) or "
    "ledger (one record kind with its withdrawals or event history, or one record by id).",
    writes="none",
    arguments=(
        Argument("view", f"one of {', '.join(VIEWS.names())}", required=True),
        Argument(
            "--exercise", "exposures, lines: one exercise id; repeat for more", repeatable=True
        ),
        Argument("--since", "exposures: on or after this date, YYYY-MM-DD"),
        Argument(
            "--draft", "flags, lines: a plan Draft to validate now instead of the plan in force"
        ),
        Argument("--code", "flags: one flag code"),
        Argument("--severity", "flags: violation or warning"),
        Argument("--scope", "flags: one scope kind, such as line or week"),
        Argument("--summary", "flags: counts by code and severity", takes_value=False),
        Argument("--session", "lines: one session id"),
        Argument("--date", "lines: one date, YYYY-MM-DD"),
        Argument("--changed", "lines: only lines whose prescription moved", takes_value=False),
        Argument("--kind", "readings: weigh_in, sleep_night or activity; ledger: a record kind"),
        Argument("--id", "ledger: one record by id"),
        Argument("--open", "ledger: live rows only", takes_value=False),
    ),
    output={
        "type": "object",
        "properties": {
            "rows": {"type": "array", "items": {"type": "object"}},
            "count": {"type": "integer"},
            "truncated": {"type": "boolean"},
        },
        "required": ["rows", "count", "truncated"],
    },
    run=InInstance(run),
    examples=(
        Example(
            ("query", "exposures", "--exercise", "bb_bench_press", "--last", "5"),
            "The last 5 bench press exposures.",
        ),
        Example(
            ("query", "readings", "--kind", "weigh_in", "--last", "3"), "The last 3 Weigh-ins."
        ),
        Example(("query", "ledger", "--kind", "status_span", "--open"), "Status spans in force."),
        Example(("query", "ledger", "--kind", "niggle", "--open"), "Open niggles."),
        Example(("query", "flags", "--summary"), "Counts of the plan in force's flags by code."),
        Example(("query", "lines", "--changed"), "The plan in force's lines that moved."),
    ),
)
