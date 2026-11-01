import datetime
import json
import time
import urllib.error
import urllib.request
from http.client import IncompleteRead
from pathlib import Path
from typing import Any

import pytest
from support.clock import FixedClock
from support.hevy_fixtures import hevy_fixture
from support.recording_opener import RecordingOpener, RecordingSleeper, Reply, ScriptedResponse

from coach.cli import envelope
from coach.core.errors import Refused, Unreachable
from coach.core.message import Message
from coach.core.mirror import Folder
from coach.hevy.client import EndpointNotAllowed, HevyApiClient
from coach.hevy.protocol import WriteContext

KEY = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
CONTEXT = WriteContext(week_plan_id="wp-2026-w44", write_plan_hash="h-abc", routine_id=None)


def a_client(
    tmp_path: Path, opener: RecordingOpener, sleeper: RecordingSleeper | None = None
) -> HevyApiClient:
    return HevyApiClient(
        KEY,
        tmp_path / "hevy" / "writes.jsonl",
        FixedClock(),
        opener=opener,
        sleeper=sleeper or RecordingSleeper(),
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("DELETE", "/v1/routines/r-1"),
        ("POST", "/v1/workouts"),
        ("PUT", "/v1/workouts/w-1"),
        ("PUT", "/v1/routine_folders/1"),
        ("POST", "/v1/routines/r-1"),
        ("PUT", "/v1/routines"),
        ("PUT", "/v1/routines/r-1/extra"),
        ("PATCH", "/v1/routines/r-1"),
        ("POST", "/v1/exercise_templates/x"),
        ("GET", "https://example.com/v1/routines"),
    ],
)
def test_a_request_off_the_allow_list_raises_before_the_opener_is_called(
    tmp_path: Path, method: str, path: str
) -> None:
    opener = RecordingOpener()
    client = a_client(tmp_path, opener)

    with pytest.raises(EndpointNotAllowed):
        client.request(method, path, body={}, context=CONTEXT)

    assert opener.sent == []
    assert not (tmp_path / "hevy" / "writes.jsonl").exists()


def audit_lines(tmp_path: Path) -> list[dict[str, Any]]:
    text = (tmp_path / "hevy" / "writes.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


ROUTINE_BODY: dict[str, object] = {
    "routine": {"title": "Session A", "folder_id": 1, "notes": "week 3", "exercises": []}
}


def test_a_write_appends_one_request_line_before_the_send_and_one_response_line_after(
    tmp_path: Path,
) -> None:
    routine = hevy_fixture("routine")["routine"]
    recording = RecordingOpener([Reply(200, {"routine": [routine]})])
    lines_at_send: list[list[dict[str, Any]]] = []

    def opener(request: urllib.request.Request, timeout: float) -> ScriptedResponse:
        lines_at_send.append(audit_lines(tmp_path))
        return recording(request, timeout)

    client = HevyApiClient(KEY, tmp_path / "hevy" / "writes.jsonl", FixedClock(), opener=opener)
    context = WriteContext("wp-2026-w44", "h-abc", "00000000-0000-4000-8000-000000000001")

    created = client.update_routine("00000000-0000-4000-8000-000000000001", ROUTINE_BODY, context)

    assert created.id == "00000000-0000-4000-8000-000000000001"
    [before] = lines_at_send
    request_line, response_line = audit_lines(tmp_path)
    assert before == [request_line]
    assert request_line == {
        "kind": "request",
        "at": "2026-10-30T12:00:00+00:00",
        "method": "PUT",
        "path": "/v1/routines/00000000-0000-4000-8000-000000000001",
        "routine_id": "00000000-0000-4000-8000-000000000001",
        "week_plan_id": "wp-2026-w44",
        "write_plan_hash": "h-abc",
        "body": ROUTINE_BODY,
        "body_sha256": request_line["body_sha256"],
    }
    assert len(request_line["body_sha256"]) == 64
    assert response_line == {
        "kind": "response",
        "at": "2026-10-30T12:00:00+00:00",
        "method": "PUT",
        "path": "/v1/routines/00000000-0000-4000-8000-000000000001",
        "body_sha256": request_line["body_sha256"],
        "status": 200,
        "attempts": 1,
    }


def test_the_response_line_carries_the_status_hevy_answered(tmp_path: Path) -> None:
    folder = {"id": 7, "index": 0, "title": "Program"}
    client = a_client(tmp_path, RecordingOpener([Reply(201, {"routine_folder": folder})]))

    client.create_folder(FOLDER_BODY, CONTEXT)

    _, response_line = audit_lines(tmp_path)
    assert response_line["status"] == 201


def test_the_body_digest_names_the_body_not_its_key_order(tmp_path: Path) -> None:
    folder = {"id": 7, "index": 0, "title": "Program"}
    opener = RecordingOpener([Reply(200, {"routine_folder": folder})] * 2)
    client = a_client(tmp_path, opener)

    client.create_folder({"routine_folder": {"title": "Program", "index": 0}}, CONTEXT)
    client.create_folder({"routine_folder": {"index": 0, "title": "Program"}}, CONTEXT)
    first, _, second, _ = audit_lines(tmp_path)

    assert first["body_sha256"] == second["body_sha256"]


def test_each_write_sends_its_body_to_its_allow_listed_path(tmp_path: Path) -> None:
    routine = hevy_fixture("routine")["routine"]
    opener = RecordingOpener(
        [
            Reply(200, {"routine": [routine]}),
            Reply(200, {"routine_folder": {"id": 7, "index": 2, "title": "Retired"}}),
            Reply(200, {"id": "C0FFEE01"}),
        ]
    )
    client = a_client(tmp_path, opener)

    routine_value = client.create_routine(ROUTINE_BODY, CONTEXT)
    folder = client.create_folder({"routine_folder": {"title": "Retired"}}, CONTEXT)
    template_id = client.create_exercise_template({"exercise": {"title": "Sled Push"}}, CONTEXT)

    assert routine_value.title == "Session A"
    assert folder == Folder(id="7", title="Retired", index=2, updated_at=None)
    assert template_id == "C0FFEE01"
    assert [(s.method, s.url) for s in opener.sent] == [
        ("POST", "https://api.hevyapp.com/v1/routines"),
        ("POST", "https://api.hevyapp.com/v1/routine_folders"),
        ("POST", "https://api.hevyapp.com/v1/exercise_templates"),
    ]
    assert opener.sent[0].body == ROUTINE_BODY
    assert opener.sent[0].headers["api-key"] == KEY
    assert [line["kind"] for line in audit_lines(tmp_path)] == ["request", "response"] * 3


def test_a_bare_id_answer_to_an_exercise_template_post_is_the_template_id(
    tmp_path: Path,
) -> None:
    opener = RecordingOpener([Reply(200, "C0FFEE02")])
    client = a_client(tmp_path, opener)

    assert client.create_exercise_template({"exercise": {"title": "Sled"}}, CONTEXT) == "C0FFEE02"


def test_a_read_sends_no_audit_line(tmp_path: Path) -> None:
    opener = RecordingOpener([Reply(200, hevy_fixture("routine"))])
    client = a_client(tmp_path, opener)

    routine = client.routine("00000000-0000-4000-8000-000000000001")

    assert routine.title == "Session A"
    assert opener.sent[0].method == "GET"
    assert opener.sent[0].body is None
    assert not (tmp_path / "hevy" / "writes.jsonl").exists()


FOLDER_ANSWER = Reply(200, {"routine_folder": {"id": 7, "index": 0, "title": "Program"}})
FOLDER_BODY: dict[str, object] = {"routine_folder": {"title": "Program"}}


def test_a_429_is_retried_after_30_s_up_to_three_attempts(tmp_path: Path) -> None:
    opener = RecordingOpener([Reply(429), Reply(429), FOLDER_ANSWER])
    sleeper = RecordingSleeper()
    client = a_client(tmp_path, opener, sleeper)
    started = time.perf_counter()

    folder = client.create_folder(FOLDER_BODY, CONTEXT)

    assert folder.id == "7"
    assert sleeper.slept == [30, 30]
    assert len(opener.sent) == 3
    request_line, response_line = audit_lines(tmp_path)
    assert request_line["kind"] == "request"
    assert response_line["status"] == 200
    assert response_line["attempts"] == 3
    assert time.perf_counter() - started < 0.5


def test_a_third_429_gives_up_as_hevy_unreachable_and_audits_the_error(tmp_path: Path) -> None:
    opener = RecordingOpener([Reply(429), Reply(429), Reply(429)])
    sleeper = RecordingSleeper()
    client = a_client(tmp_path, opener, sleeper)

    with pytest.raises(Unreachable) as raised:
        client.create_folder(FOLDER_BODY, CONTEXT)

    assert raised.value.code == "hevy_unreachable"
    assert sleeper.slept == [30, 30]
    _, response_line = audit_lines(tmp_path)
    assert response_line["attempts"] == 3
    assert "429" in response_line["error"]
    assert "status" not in response_line


def test_a_read_is_retried_on_429_too(tmp_path: Path) -> None:
    opener = RecordingOpener([Reply(429), Reply(200, hevy_fixture("routine"))])
    sleeper = RecordingSleeper()
    client = a_client(tmp_path, opener, sleeper)

    client.routine("00000000-0000-4000-8000-000000000001")

    assert sleeper.slept == [30]


@pytest.mark.parametrize(
    "failure",
    [
        Reply(500, {"error": "boom"}),
        Reply(404, {"error": "Routine not found"}),
        urllib.error.URLError("connection refused"),
        TimeoutError("timed out"),
        Reply(200, read_error=TimeoutError("read timed out")),
        Reply(200, read_error=ConnectionResetError("connection reset by peer")),
        Reply(200, read_error=IncompleteRead(b"{", 10)),
    ],
)
def test_a_failed_write_is_hevy_unreachable_with_a_response_line(
    tmp_path: Path, failure: Reply | Exception
) -> None:
    client = a_client(tmp_path, RecordingOpener([failure]))

    with pytest.raises(Unreachable):
        client.create_folder(FOLDER_BODY, CONTEXT)

    request_line, response_line = audit_lines(tmp_path)
    assert (request_line["kind"], response_line["kind"]) == ("request", "response")
    assert response_line["attempts"] == 1
    assert response_line["error"]


def test_a_rejected_key_names_the_variable_to_check(tmp_path: Path) -> None:
    client = a_client(tmp_path, RecordingOpener([Reply(401, {"error": "Unauthorized"})]))

    with pytest.raises(Unreachable) as raised:
        client.routines()

    assert "401" in raised.value.message
    assert "HEVY_API_KEY" in raised.value.message


@pytest.mark.parametrize(
    "failure",
    [
        Reply(401, {"error": f"invalid api-key {KEY}"}),
        Reply(400, f"bad request for key {KEY}"),
        urllib.error.URLError(f"proxy refused {KEY}"),
    ],
)
def test_the_key_appears_in_no_error_envelope_or_audit_line(
    tmp_path: Path, failure: Reply | Exception
) -> None:
    opener = RecordingOpener([failure])
    client = a_client(tmp_path, opener)

    with pytest.raises(Unreachable) as raised:
        client.create_folder({"routine_folder": {"title": f"echo {KEY}"}}, CONTEXT)

    failed = envelope.failure(1, "plan apply", Message(raised.value.code, raised.value.message), [])
    assert KEY not in str(raised.value)
    assert KEY not in envelope.render(failed, pretty=False)
    assert KEY not in (tmp_path / "hevy" / "writes.jsonl").read_text(encoding="utf-8")
    assert opener.sent[0].headers["api-key"] == KEY
    assert KEY not in opener.sent[0].url


def test_writes_are_spaced_by_a_token_bucket_and_reads_are_not(tmp_path: Path) -> None:
    opener = RecordingOpener([FOLDER_ANSWER] * 4 + [Reply(200, hevy_fixture("routine"))] * 3)
    sleeper = RecordingSleeper()
    client = a_client(tmp_path, opener, sleeper)

    for _ in range(3):
        client.create_folder(FOLDER_BODY, CONTEXT)
    assert sleeper.slept == []
    client.create_folder(FOLDER_BODY, CONTEXT)
    assert sleeper.slept == [3.0]
    for _ in range(3):
        client.routine("00000000-0000-4000-8000-000000000001")
    assert sleeper.slept == [3.0]


def test_a_listing_follows_every_page(tmp_path: Path) -> None:
    folder_page = hevy_fixture("routine_folder_page")
    second = {
        **folder_page,
        "page": 2,
        "page_count": 2,
        "routine_folders": [{"id": 2, "index": 1, "title": "Standing"}],
    }
    opener = RecordingOpener([Reply(200, {**folder_page, "page_count": 2}), Reply(200, second)])
    client = a_client(tmp_path, opener)

    folders = client.folders()

    assert [f.title for f in folders] == ["Program", "Standing"]
    assert [s.url for s in opener.sent] == [
        "https://api.hevyapp.com/v1/routine_folders?page=1&pageSize=10",
        "https://api.hevyapp.com/v1/routine_folders?page=2&pageSize=10",
    ]


def test_an_empty_listing_stops_at_page_count_zero(tmp_path: Path) -> None:
    opener = RecordingOpener([Reply(200, {"page": 1, "page_count": 0, "routines": []})])

    assert a_client(tmp_path, opener).routines() == ()


def test_every_get_reads_its_endpoint(tmp_path: Path) -> None:
    opener = RecordingOpener(
        [
            Reply(200, hevy_fixture("workout_page")),
            Reply(200, hevy_fixture("workout_events_page")),
            Reply(200, hevy_fixture("exercise_template_page")),
            Reply(200, hevy_fixture("body_measurement_page")),
        ]
    )
    client = a_client(tmp_path, opener)
    since = datetime.datetime(2026, 10, 1, 9, 50, tzinfo=datetime.UTC)

    assert len(client.workouts()) == 1
    assert [e.kind for e in client.workout_events(since)] == ["updated", "deleted"]
    assert client.exercise_templates()[0].id == "F0000001"
    assert client.body_measurements()[0].weight_kg == 80.4
    assert [s.url for s in opener.sent] == [
        "https://api.hevyapp.com/v1/workouts?page=1&pageSize=10",
        "https://api.hevyapp.com/v1/workouts/events?since=2026-10-01T09%3A50%3A00%2B00%3A00"
        "&page=1&pageSize=10",
        "https://api.hevyapp.com/v1/exercise_templates?page=1&pageSize=100",
        "https://api.hevyapp.com/v1/body_measurements?page=1&pageSize=10",
    ]


def test_a_read_back_appends_a_verify_line_with_the_diff(tmp_path: Path) -> None:
    opener = RecordingOpener([Reply(200, hevy_fixture("routine"))] * 2)
    client = a_client(tmp_path, opener)
    context = WriteContext("wp-2026-w44", "h-abc", "00000000-0000-4000-8000-000000000001")

    matched = client.read_back("00000000-0000-4000-8000-000000000001", context, lambda r: ())
    differed = client.read_back(
        "00000000-0000-4000-8000-000000000001", context, lambda r: (f"title {r.title}",)
    )

    assert matched.verified
    assert not differed.verified
    assert differed.diff == ("title Session A",)
    first, second = audit_lines(tmp_path)
    assert first == {
        "kind": "verify",
        "at": "2026-10-30T12:00:00+00:00",
        "routine_id": "00000000-0000-4000-8000-000000000001",
        "week_plan_id": "wp-2026-w44",
        "write_plan_hash": "h-abc",
        "verified": True,
        "diff": [],
    }
    assert (second["verified"], second["diff"]) == (False, ["title Session A"])


def test_open_audit_creates_the_file_for_append(tmp_path: Path) -> None:
    client = a_client(tmp_path, RecordingOpener())

    client.open_audit()

    assert (tmp_path / "hevy" / "writes.jsonl").read_text(encoding="utf-8") == ""


def test_an_audit_that_cannot_be_opened_refuses_before_any_request(tmp_path: Path) -> None:
    (tmp_path / "hevy").write_text("a file where the directory should be", encoding="utf-8")
    opener = RecordingOpener()
    client = a_client(tmp_path, opener)

    with pytest.raises(Refused) as opening:
        client.open_audit()
    with pytest.raises(Refused) as writing:
        client.create_folder(FOLDER_BODY, CONTEXT)

    assert opening.value.code == "audit_unwritable"
    assert writing.value.code == "audit_unwritable"
    assert opener.sent == []
