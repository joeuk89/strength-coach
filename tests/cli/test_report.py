import hashlib
import platform
from pathlib import Path

import pytest
from support.cli import Run, run_coach
from support.fake_github import FakeGitHub, an_open_issue
from support.instances import an_instance

from coach.cli import app

ENGINE = "0.6.0"
TOKEN = "github_pat_11fixture0token0value"
DRAFT = ".coach/drafts/report.toml"
REPORT = (
    'kind = "bug"\n'
    'title = "Plan apply drops the last set"\n'
    'body = "Week 3 sent two sets of squats; the plan has three."\n'
    'verb = "plan apply"\n'
)


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = an_instance(tmp_path / "sam", pin=ENGINE)
    monkeypatch.chdir(root)
    assert run_coach("status").code == 0
    (root / ".coach" / "drafts").mkdir(parents=True, exist_ok=True)
    (root / DRAFT).write_text(REPORT, encoding="utf-8")
    return root


def report(github: FakeGitHub, *args: str, env: dict[str, str] | None = None) -> Run:
    return run_coach("report", DRAFT, *args, env=env or {}, make_github=github.factory())


def hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_the_dry_run_shows_the_issue_as_it_will_be_sent_and_files_nothing(instance: Path) -> None:
    github = FakeGitHub()
    before = hashes(instance)

    run = report(github, "--dry-run")

    assert run.code == 0, run.stdout
    result = run.envelope["result"]
    assert result["dry_run"] is True
    assert result["repo"] == "joeuk89/strength-coach"
    assert result["title"] == "Plan apply drops the last set"
    assert result["labels"] == ["needs-triage", "bug"]
    assert result["body"].startswith("Week 3 sent two sets of squats; the plan has three.\n\n---\n")
    assert "- Athlete: sam\n" in result["body"]
    assert f"- Engine: {ENGINE}, pin {ENGINE}, schema " in result["body"]
    assert f"- Python: {platform.python_version()} on " in result["body"]
    assert result["body"].endswith("- Verb: `plan apply`\n")
    assert github.filed == []
    assert hashes(instance) == before


def test_the_dry_run_needs_no_token(instance: Path) -> None:
    github = FakeGitHub()

    run = report(github, "--dry-run")

    assert run.code == 0
    assert github.tokens == [None]


def test_the_athlete_name_is_the_profile_heading(instance: Path) -> None:
    (instance / "profile.md").write_text("# Sam Jones\n\nTrains at home.\n", encoding="utf-8")

    body = report(FakeGitHub(), "--dry-run").envelope["result"]["body"]

    assert "- Athlete: Sam Jones\n" in body


def test_the_dry_run_prompt_shows_repo_title_labels_and_the_whole_body(instance: Path) -> None:
    long_body = "\n".join(f"line {n} of what went wrong" for n in range(200))
    (instance / DRAFT).write_text(
        f'kind = "gap"\ntitle = "No swims"\nbody = """\n{long_body}"""\n', encoding="utf-8"
    )

    result = report(FakeGitHub(), "--dry-run").envelope["result"]

    prompt = result["prompt"]
    assert "joeuk89/strength-coach" in prompt
    assert "No swims" in prompt
    assert "needs-triage, enhancement" in prompt
    assert result["body"] in prompt
    assert "line 199 of what went wrong" in prompt


def test_the_dry_run_lists_similar_open_issues(instance: Path) -> None:
    github = FakeGitHub(
        [
            an_open_issue(7, "Plan apply drops a set on Fridays", "bug"),
            an_open_issue(8, "Status is slow", "bug"),
            an_open_issue(9, "Plan apply drops a set", "question"),
        ]
    )

    similar = report(github, "--dry-run").envelope["result"]["similar"]

    assert similar == [
        {
            "number": 7,
            "title": "Plan apply drops a set on Fridays",
            "url": "https://github.com/joeuk89/strength-coach/issues/7",
        }
    ]


def test_similar_is_null_with_a_warning_when_github_cannot_be_read(instance: Path) -> None:
    run = report(FakeGitHub(reads_fail=True), "--dry-run")

    assert run.code == 0
    assert run.envelope["result"]["similar"] is None
    assert [w["code"] for w in run.envelope["warnings"]] == ["github_unreachable"]


def test_the_real_run_files_the_issue_with_the_token_and_returns_number_url_and_labels(
    instance: Path,
) -> None:
    github = FakeGitHub(next_number=251)
    before = hashes(instance)

    run = report(github, env={"COACH_GITHUB_TOKEN": TOKEN})

    assert run.code == 0, run.stdout
    assert run.envelope["result"] == {
        "number": 251,
        "url": "https://github.com/joeuk89/strength-coach/issues/251",
        "labels": ["needs-triage", "bug"],
    }
    assert github.tokens == [TOKEN]
    assert github.bodies[0].endswith("- Verb: `plan apply`\n")
    assert TOKEN not in run.stdout + run.stderr
    assert hashes(instance) == before


def test_the_real_run_reads_the_token_from_dotenv(instance: Path) -> None:
    (instance / ".env").write_text(f"COACH_GITHUB_TOKEN={TOKEN}\n", encoding="utf-8")
    github = FakeGitHub()

    run = report(github)

    assert run.code == 0, run.stdout
    assert github.tokens == [TOKEN]


def test_the_real_run_does_not_check_for_similar_issues(instance: Path) -> None:
    github = FakeGitHub(reads_fail=True)

    run = report(github, env={"COACH_GITHUB_TOKEN": TOKEN})

    assert run.code == 0, run.stdout
    assert run.envelope["warnings"] == []


def test_no_token_is_github_token_missing_and_files_nothing(instance: Path) -> None:
    github = FakeGitHub()

    run = report(github, env={"HEVY_API_KEY": "a-hevy-key"})

    assert (run.code, run.envelope["error"]["code"]) == (5, "github_token_missing")
    assert github.filed == []
    assert (instance / DRAFT).read_text(encoding="utf-8") == REPORT


def test_github_unreachable_exits_4_and_keeps_the_draft(instance: Path) -> None:
    run = report(FakeGitHub(writes_fail=True), env={"COACH_GITHUB_TOKEN": TOKEN})

    assert (run.code, run.envelope["error"]["code"]) == (4, "github_unreachable")
    assert (instance / DRAFT).read_text(encoding="utf-8") == REPORT


@pytest.mark.parametrize(
    "draft",
    [
        'kind = "bug"\ntitle = "t"\nbody = "b"\nverb = "explain"\n',
        'kind = "bug"\ntitle = "t"\nbody = "b"\ncode = "made_up"\n',
        'kind = "complaint"\ntitle = "t"\nbody = "b"\n',
    ],
)
def test_an_unknown_value_is_invalid_argument_before_the_token_is_asked_for(
    instance: Path, draft: str
) -> None:
    (instance / DRAFT).write_text(draft, encoding="utf-8")

    run = report(FakeGitHub())

    assert (run.code, run.envelope["error"]["code"]) == (1, "invalid_argument")


def test_a_known_error_code_is_accepted(instance: Path) -> None:
    (instance / DRAFT).write_text(
        'kind = "bug"\ntitle = "t"\nbody = "b"\ncode = "hevy_unreachable"\n', encoding="utf-8"
    )

    run = report(FakeGitHub(), "--dry-run")

    assert run.code == 0, run.stdout
    assert run.envelope["result"]["body"].endswith("- Code: `hevy_unreachable`\n")
