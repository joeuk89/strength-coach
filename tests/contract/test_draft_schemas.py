"""`coach schema <verb>` carries the JSON Schema of the Draft a verb reads, recorded from the
verb's own parser over its example and coverage Drafts, so the schema cannot drift from it."""

import copy
import json
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from support.cli import run_coach
from support.json_schema import problems

from coach.cli.registry import declarations, find
from coach.core.draft_schema import DraftKind, record
from coach.core.errors import Invalid
from coach.core.program.parse import parse_program_draft
from coach.core.registries.agent import RECORD_KINDS
from coach.core.registries.ledger import DECISION_KINDS, FOLLOW_UP_EVENTS
from coach.core.registries.log import ANNOTATION_KINDS
from coach.core.registries.schemes import CRITERION_KEYS, SCHEMES
from coach.core.registries.week import OVERRIDE_KINDS
from coach.render.toml import dumps

type Json = dict[str, Any]

KINDS = {
    "program adopt": "program",
    "plan apply": "plan",
    "record": "ledger",
    "checkin record": "check-in",
    "goal adopt": "goal",
    "report": "report",
}
UNLISTED = "unlisted_key"


@pytest.fixture(autouse=True)
def outside_an_instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def draft_of(verb: str) -> Json:
    run = run_coach("schema", verb)
    assert run.code == 0, run.stdout
    return run.envelope["result"]["draft"]


def kind_of(verb: str) -> DraftKind:
    declaration = find(verb)
    assert declaration is not None and declaration.draft is not None
    return declaration.draft()


def unknown_keys(verb: str, text: str) -> tuple[str, ...]:
    """The keys the verb's parser reports as unknown; any other refusal fails the test."""
    data = text.encode()
    if verb == "program adopt":
        return parse_program_draft(data, file="draft.toml").unknown_keys
    try:
        kind_of(verb).read(data)
    except Invalid as error:
        if error.code == "unknown_key":
            return (error.message,)
        raise
    return ()


@pytest.mark.parametrize("verb", KINDS)
def test_a_draft_verb_carries_its_drafts_kind_schema_and_example(verb: str) -> None:
    draft = draft_of(verb)

    assert draft["kind"] == KINDS[verb]
    assert draft["schema"]["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert draft["schema"]["type"] == "object"
    assert draft["example"].strip()
    json.dumps(draft, allow_nan=False)


def test_a_verb_that_reads_no_draft_carries_no_draft() -> None:
    assert "draft" not in run_coach("schema", "status").envelope["result"]


def test_exactly_the_draft_verbs_name_a_draft() -> None:
    assert {d.name for d in declarations() if d.draft is not None} == set(KINDS)


def test_the_verb_less_listing_leaves_the_drafts_out() -> None:
    rows = run_coach("schema").envelope["result"]["rows"]

    assert all("draft" not in row for row in rows)


@pytest.mark.parametrize("verb", KINDS)
def test_the_example_parses_with_the_verbs_own_parser_and_no_unknown_key(verb: str) -> None:
    assert unknown_keys(verb, draft_of(verb)["example"]) == ()


@pytest.mark.parametrize("verb", KINDS)
def test_the_example_and_every_coverage_draft_conform_to_the_schema(verb: str) -> None:
    schema = draft_of(verb)["schema"]
    kind = kind_of(verb)

    for text in (kind.example, *kind.coverage):
        assert problems(tomllib.loads(text), schema) == [], text


@pytest.mark.parametrize("verb", KINDS)
def test_every_key_path_the_parser_reads_from_the_example_is_in_the_schema(verb: str) -> None:
    kind = kind_of(verb)
    read = record(kind.read, [kind.example]).paths()

    assert read <= set(key_paths(draft_of(verb)["schema"]))
    assert read


@pytest.mark.parametrize("verb", KINDS)
def test_a_key_the_schema_does_not_list_is_unknown_to_the_parser(verb: str) -> None:
    kind = kind_of(verb)
    document = tomllib.loads(kind.example)
    closed = list(closed_tables(document, draft_of(verb)["schema"], ()))

    for at in closed:
        widened = copy.deepcopy(document)
        table_at(widened, at)[UNLISTED] = "x"
        assert unknown_keys(verb, toml_of(widened)), at
    assert closed


@pytest.mark.parametrize("verb", KINDS)
def test_the_coverage_drafts_enter_every_table_the_parser_reads(verb: str) -> None:
    assert kind_of(verb).recording().unreached() == []


def test_the_program_schema_offers_every_scheme_by_its_level() -> None:
    properties = draft_of("program adopt")["schema"]["properties"]
    session = properties["session"]["items"]["properties"]
    line = session["line"]["items"]["properties"]

    assert scheme_names(line["scheme"]) == {s.name for s in SCHEMES.entries if s.level == "line"}
    assert scheme_names(session["scheme"]) == {
        s.name for s in SCHEMES.entries if s.level == "session"
    }


def test_the_exercise_ladder_scheme_carries_its_rung_table_and_criterion_keys() -> None:
    line = draft_of("program adopt")["schema"]["properties"]["session"]["items"]["properties"]
    ladder = scheme_branch(line["line"]["items"]["properties"]["scheme"], "exercise_ladder")
    rung = ladder["properties"]["rungs"]["items"]

    assert set(rung["properties"]) == {"exercise", "sets", "cues", "advance", "start_load"}
    assert rung["required"] == ["sets"]
    assert tuple(rung["properties"]["advance"]["properties"]) == CRITERION_KEYS
    assert tuple(ladder["properties"]["advance"]["properties"]) == CRITERION_KEYS
    assert ladder["required"] == ["name", "rungs"]


def test_a_scheme_param_takes_its_type_from_the_schemes_registry() -> None:
    line = draft_of("program adopt")["schema"]["properties"]["session"]["items"]["properties"]
    top_backoff = scheme_branch(line["line"]["items"]["properties"]["scheme"], "top_backoff")

    assert top_backoff["properties"]["pct_of_top"] == {
        "type": "number",
        "exclusiveMinimum": 0,
        "maximum": 100,
    }
    assert top_backoff["required"] == ["name", "pct_of_top"]
    assert top_backoff["additionalProperties"] is False


def test_the_record_schema_holds_every_record_kind_but_the_check_in_only_ones() -> None:
    record_tables = set(draft_of("record")["schema"]["properties"])
    check_in_tables = set(draft_of("checkin record")["schema"]["properties"])
    kinds = {k.name for k in RECORD_KINDS.entries}
    check_in_only = {k.name for k in RECORD_KINDS.entries if k.check_in_only}

    assert record_tables == kinds - check_in_only
    assert check_in_only == {"observation"}
    assert kinds <= check_in_tables
    assert {"date", "tier", "read", "phase"} <= check_in_tables - kinds


def test_a_record_table_is_an_array_of_its_kinds_shape() -> None:
    weigh_in = draft_of("record")["schema"]["properties"]["weigh_in"]

    assert weigh_in["type"] == "array"
    assert set(weigh_in["items"]["properties"]) == {"date", "kg", "withdraws", "key"}


@pytest.mark.parametrize(
    ("verb", "at", "key", "values"),
    [
        ("record", ("decision", "[]"), "kind", DECISION_KINDS.names()),
        ("record", ("annotation", "[]"), "kind", ANNOTATION_KINDS.names()),
        ("record", ("follow_up", "[]"), "kind", FOLLOW_UP_EVENTS.names()),
        ("plan apply", ("override", "[]"), "kind", OVERRIDE_KINDS.names()),
    ],
)
def test_the_coverage_drafts_reach_every_kind_a_parser_branches_on(
    verb: str, at: tuple[str, ...], key: str, values: tuple[str, ...]
) -> None:
    assert kind_of(verb).recording().values(at, key) == set(values)


def scheme_names(schema: Json) -> set[str]:
    return {branch["properties"]["name"]["const"] for branch in schema["oneOf"]}


def scheme_branch(schema: Json, name: str) -> Json:
    return next(b for b in schema["oneOf"] if b["properties"]["name"]["const"] == name)


def key_paths(schema: Json, at: tuple[str, ...] = ()) -> Iterator[tuple[str, ...]]:
    for key, child in cast(dict[str, Json], schema.get("properties", {})).items():
        yield (*at, key)
        yield from key_paths(child, (*at, key))
    if isinstance(schema.get("additionalProperties"), dict):
        yield (*at, "*")
        yield from key_paths(schema["additionalProperties"], (*at, "*"))
    if isinstance(schema.get("items"), dict):
        yield from key_paths(schema["items"], (*at, "[]"))
    for branch in schema.get("anyOf", []) + schema.get("oneOf", []):
        yield from key_paths(branch, at)


def closed_tables(
    value: object, schema: Json, at: tuple[object, ...]
) -> Iterator[tuple[object, ...]]:
    """The paths of the example's tables whose schema allows no other key."""
    branches = schema.get("anyOf")
    if branches:
        schema = next(b for b in branches if not problems(value, b))
    if isinstance(value, dict) and "oneOf" not in schema:
        table = cast(dict[str, object], value)
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties")
        if extra is False:
            yield at
        for key, child in table.items():
            child_schema = properties.get(key, extra if isinstance(extra, dict) else None)
            if child_schema is not None:
                yield from closed_tables(child, child_schema, (*at, key))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(cast(list[object], value)):
            yield from closed_tables(item, schema["items"], (*at, index))


def table_at(document: object, at: tuple[object, ...]) -> dict[str, object]:
    for step in at:
        document = cast(Any, document)[step]
    return cast(dict[str, object], document)


def toml_of(document: dict[str, object]) -> str:
    return dumps(cast(Any, document))
