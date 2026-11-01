from contextlib import closing

from coach.cli.declaration import Argument, Call, Declaration, Example, Json, Outcome
from coach.cli.instance import open_instance_store
from coach.core.errors import Invalid
from coach.core.registries.agent import VIEWS
from coach.services.query import QueryResult, ledger, readings


def run(call: Call) -> Outcome:
    assert call.instance is not None and call.clock is not None
    view = str(call.args["view"])
    if view not in VIEWS:
        raise Invalid("invalid_argument", f"no view {view!r}; one of {', '.join(VIEWS.names())}")
    last = None if call.full else call.last
    kind = _text(call, "kind")
    with closing(open_instance_store(call.instance)) as conn:
        if view == "readings":
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
        else:
            raise Invalid("invalid_argument", f"query {view} is not in this engine build yet")
    return Outcome(_rows(result))


def _text(call: Call, name: str) -> str | None:
    value = call.args.get(name)
    return value if isinstance(value, str) else None


def _rows(result: QueryResult) -> Json:
    return {"rows": result.rows, "count": result.count, "truncated": result.truncated}


DECLARATION = Declaration(
    name="query",
    summary="One read view as a row list: readings (Weigh-ins, Sleep nights, Activities) or "
    "ledger (one record kind with its withdrawals or event history, or one record by id).",
    writes="none",
    needs_instance=True,
    arguments=(
        Argument("view", f"one of {', '.join(VIEWS.names())}", required=True),
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
    run=run,
    examples=(
        Example(
            ("query", "readings", "--kind", "weigh_in", "--last", "3"), "The last 3 Weigh-ins."
        ),
        Example(("query", "ledger", "--kind", "status_span", "--open"), "Status spans in force."),
        Example(("query", "ledger", "--kind", "niggle", "--open"), "Open niggles."),
    ),
)
