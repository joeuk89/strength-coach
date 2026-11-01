import datetime
from contextlib import closing

from coach.cli.declaration import Argument, Call, Declaration, Example, Json, Outcome
from coach.cli.instance import open_instance_store
from coach.core.errors import Invalid
from coach.core.registries.agent import VIEWS
from coach.services.query import QueryResult, exposures, ledger, readings


def run(call: Call) -> Outcome:
    assert call.instance is not None and call.clock is not None
    view = str(call.args["view"])
    if view not in VIEWS:
        raise Invalid("invalid_argument", f"no view {view!r}; one of {', '.join(VIEWS.names())}")
    last = None if call.full else call.last
    kind = _text(call, "kind")
    with closing(open_instance_store(call.instance)) as conn:
        if view == "exposures":
            result = exposures(
                conn,
                exercises=_texts(call, "exercise"),
                since=_date(call, "since"),
                last=last,
                units=call.instance.config.athlete.units,
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
        else:
            raise Invalid("invalid_argument", f"query {view} is not in this engine build yet")
    return Outcome(_rows(result))


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
    "annotations applied and its e1RM), readings (Weigh-ins, Sleep nights, Activities) or "
    "ledger (one record kind with its withdrawals or event history, or one record by id).",
    writes="none",
    needs_instance=True,
    arguments=(
        Argument("view", f"one of {', '.join(VIEWS.names())}", required=True),
        Argument("--exercise", "exposures: one exercise id; repeat for more", repeatable=True),
        Argument("--since", "exposures: on or after this date, YYYY-MM-DD"),
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
            ("query", "exposures", "--exercise", "bb_bench_press", "--last", "5"),
            "The last 5 bench press exposures.",
        ),
        Example(
            ("query", "readings", "--kind", "weigh_in", "--last", "3"), "The last 3 Weigh-ins."
        ),
        Example(("query", "ledger", "--kind", "status_span", "--open"), "Status spans in force."),
        Example(("query", "ledger", "--kind", "niggle", "--open"), "Open niggles."),
    ),
)
