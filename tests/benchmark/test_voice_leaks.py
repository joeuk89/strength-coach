import importlib.util
import json
import re
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.fixture_instances import serving

BENCHMARK = Path(__file__).resolve().parents[2] / "scripts" / "benchmark"
TRANSCRIPTS = BENCHMARK / "transcripts"


def load_measure() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure", BENCHMARK / "measure.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


measure = load_measure()


def run_engine(argv: list[str]) -> Any:
    return run_coach(*argv, make_client=serving(FakeHevy(FixedClock()))).envelope


@pytest.fixture(scope="module")
def lexicon(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(tmp_path_factory.mktemp("outside-an-instance"))
        yield measure.build_lexicon(run_engine)


def hand_marked(transcript: str) -> set[str]:
    readme = (TRANSCRIPTS / "README.md").read_text(encoding="utf-8")
    section = readme.split(f"### {transcript} ", 1)[1].split("\n### ", 1)[0].split("\n## ", 1)[0]
    return set(re.findall(r"^\| \d+ \| ([0-9a-f-]{36}) \|", section, re.MULTILINE))


def leaking_short_uuids(row: Any) -> set[str]:
    return {uuid[:8] for uuid in row["leaking_uuids"]}


# Counted by decision though the README leaves them out: the owner asking as a developer.
PULL_UP_DOSE_DEVELOPER_REGISTER = {"c843cdd5", "8c27e67d", "b2b5f0e4", "e60b0a52", "9151e507"}
# Marked by hand but in plain English ("a small program amend"), which the count cannot see.
INCLINE_CURL_PURE_ENGLISH = {"8553a369"}


@pytest.mark.parametrize(
    ("transcript", "added", "unseen", "leaking", "messages"),
    [
        ("2026-11-04-plate-pool-link", set[str](), set[str](), 3, 4),
        ("2026-11-04-incline-curl", set[str](), INCLINE_CURL_PURE_ENGLISH, 8, 15),
        ("2026-11-02-pull-up-dose", PULL_UP_DOSE_DEVELOPER_REGISTER, set[str](), 11, 13),
    ],
)
def test_the_count_marks_the_messages_the_readme_marks_by_hand(
    lexicon: Any, transcript: str, added: set[str], unseen: set[str], leaking: int, messages: int
) -> None:
    row = measure.measure(str(TRANSCRIPTS / f"{transcript}.jsonl"), None, lexicon)

    expected = ({uuid[:8] for uuid in hand_marked(transcript)} | added) - unseen
    assert leaking_short_uuids(row) == expected
    assert (row["leaking_messages"], row["athlete_messages"]) == (leaking, messages)


def transcript(tmp_path: Path, *records: dict[str, Any]) -> str:
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return str(path)


def said(uuid: str, text: str, *, sidechain: bool = False) -> dict[str, Any]:
    return {
        "type": "assistant",
        "uuid": uuid,
        "isSidechain": sidechain,
        "message": {"content": [{"type": "text", "text": text}]},
    }


def test_a_link_the_athlete_uses_is_not_a_leak(lexicon: Any, tmp_path: Path) -> None:
    link = "https://joeuk89.github.io/plate-pool/?barbell=140.5lb&kit=d33b57cc"
    path = transcript(
        tmp_path, said("u1", f"Open this on your phone:\n\n```\n{link}\n```\n\nor tap {link}.")
    )

    row = measure.measure(path, None, lexicon)

    assert (row["leaking_messages"], row["athlete_messages"]) == (0, 1)


def test_each_class_reports_its_terms_and_the_messages_it_hit(lexicon: Any, tmp_path: Path) -> None:
    path = transcript(
        tmp_path,
        said("u1", "The [[weigh_in]] table gave wi-0003, and plan apply stopped at exit 4."),
        said("u2", "The engine raised state_conflict."),
        said("u3", "Your squat moves to 100 kg on Friday."),
    )

    row = measure.measure(path, None, lexicon)

    assert row["leaking_uuids"] == ["u1", "u2"]
    hits = row["leak_hits"]
    assert hits["record"] == ["weigh_in"]
    assert hits["store-id"] == ["wi-0003"]
    assert hits["verb"] == ["plan apply"]
    assert hits["error"] == ["exit code", "state_conflict"]
    assert hits["fixed"] == ["the engine"]
    assert hits["hash"] == []
    by_class = row["leaking_messages_by_class"]
    assert (by_class["error"], by_class["verb"], by_class["fixed"], by_class["code"]) == (
        2,
        1,
        1,
        0,
    )


def test_a_subagent_message_and_a_tool_call_are_not_athlete_facing(
    lexicon: Any, tmp_path: Path
) -> None:
    tool_call = {
        "type": "assistant",
        "uuid": "u2",
        "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "x"}}]},
    }
    path = transcript(tmp_path, said("u1", "The engine said no.", sidechain=True), tool_call)

    row = measure.measure(path, None, lexicon)

    assert (row["leaking_messages"], row["athlete_messages"]) == (0, 0)


def test_the_markdown_table_shows_voice_leaks_as_leaking_over_messages(
    lexicon: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lexicon_file = tmp_path / "lexicon.json"
    lexicon_file.write_text(json.dumps(lexicon), encoding="utf-8")
    session = str(TRANSCRIPTS / "2026-11-04-incline-curl.jsonl")

    measure.main(["--lexicon", str(lexicon_file), "--md", session])

    header, _, row = capsys.readouterr().out.splitlines()
    assert header.rstrip(" |").endswith("Voice leaks")
    assert row.rstrip(" |").endswith("8/15")
