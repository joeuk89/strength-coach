import pytest

from coach.core.errors import Invalid
from coach.core.report import (
    BODY_LIMIT,
    Footer,
    Issue,
    IssueDraft,
    athlete_name,
    issue_draft,
    similar,
)

VERBS = ("plan apply", "status")
FOOTER = Footer(
    athlete="Sam",
    engine_version="0.6.0",
    pin="0.5.0",
    schema_version=12,
    python="3.12.7",
    platform="macOS-15.1-arm64",
)
FOOTER_LINES = (
    "---\n"
    "- Athlete: Sam\n"
    "- Engine: 0.6.0, pin 0.5.0, schema 12\n"
    "- Python: 3.12.7 on macOS-15.1-arm64\n"
)


def draft(text: str) -> IssueDraft:
    return issue_draft(text.encode(), verbs=VERBS, footer=FOOTER)


def test_a_bug_draft_becomes_its_title_its_body_with_the_footer_and_the_bug_labels() -> None:
    made = draft('kind = "bug"\ntitle = "Plan apply drops a set"\nbody = "Week 3 lost a set."\n')

    assert made == IssueDraft(
        title="Plan apply drops a set",
        body="Week 3 lost a set.\n\n" + FOOTER_LINES,
        labels=("needs-triage", "bug"),
    )


def test_a_gap_is_labelled_enhancement() -> None:
    made = draft('kind = "gap"\ntitle = "No way to log a swim"\nbody = "Swims."\n')

    assert made.labels == ("needs-triage", "enhancement")


def test_the_verb_and_code_join_the_footer_when_given() -> None:
    made = draft(
        'kind = "bug"\ntitle = "t"\nbody = "b"\nverb = "plan apply"\ncode = "hevy_unreachable"\n'
    )

    assert made.body == (
        "b\n\n" + FOOTER_LINES + "- Verb: `plan apply`\n- Code: `hevy_unreachable`\n"
    )


@pytest.mark.parametrize(
    "text",
    [
        'kind = "complaint"\ntitle = "t"\nbody = "b"\n',
        'kind = "bug"\ntitle = "t"\nbody = "b"\nverb = "explain"\n',
        'kind = "bug"\ntitle = "t"\nbody = "b"\ncode = "made_up"\n',
        'kind = "bug"\nbody = "b"\n',
        'kind = "bug"\ntitle = ""\nbody = "b"\n',
        'kind = "bug"\ntitle = "t"\n',
        'kind = "bug"\ntitle = "t"\nbody = 3\n',
        'kind = "bug"\ntitle = "t\nbody = "b"\n',
    ],
)
def test_an_unknown_or_missing_value_is_invalid_argument(text: str) -> None:
    with pytest.raises(Invalid) as raised:
        draft(text)

    assert raised.value.code == "invalid_argument"


def test_an_unknown_key_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        draft('kind = "bug"\ntitle = "t"\nbody = "b"\nlabels = ["urgent"]\n')

    assert raised.value.code == "unknown_key"


def body_of_length(total: int) -> str:
    """A Draft body whose issue body, footer included, is `total` characters."""
    footer = len("\n\n" + FOOTER_LINES)
    return "x" * (total - footer)


def test_the_body_limit_is_65536_characters() -> None:
    assert BODY_LIMIT == 65_536


def test_an_issue_body_of_exactly_the_limit_is_accepted() -> None:
    made = draft(f'kind = "bug"\ntitle = "t"\nbody = "{body_of_length(65_536)}"\n')

    assert len(made.body) == 65_536


def test_an_issue_body_one_character_over_the_limit_is_invalid_argument() -> None:
    with pytest.raises(Invalid) as raised:
        draft(f'kind = "bug"\ntitle = "t"\nbody = "{body_of_length(65_537)}"\n')

    assert raised.value.code == "invalid_argument"
    assert "65536" in raised.value.message


def an_issue(number: int, title: str, *labels: str) -> Issue:
    url = f"https://github.com/joeuk89/strength-coach/issues/{number}"
    return Issue(number, title, url, labels)


def test_similar_issues_share_two_or_more_non_stopwords_with_the_title() -> None:
    issues = (
        an_issue(1, "Plan apply drops the last set", "bug"),
        an_issue(2, "The plan is late", "bug"),
        an_issue(3, "Apply a set of plans", "enhancement"),
        an_issue(4, "Status shows the wrong week", "bug"),
    )

    found = similar("Plan apply drops a set", issues)

    assert [i.number for i in found] == [1, 3]


def test_similar_reads_only_issues_labelled_bug_or_enhancement() -> None:
    issues = (
        an_issue(1, "Plan apply drops a set", "question"),
        an_issue(2, "Plan apply drops a set", "needs-triage", "bug"),
        an_issue(3, "Plan apply drops a set"),
    )

    assert [i.number for i in similar("Plan apply drops a set", issues)] == [2]


def test_stopwords_and_case_and_punctuation_do_not_count_as_shared_words() -> None:
    issues = (an_issue(1, "The: of, AND a an", "bug"), an_issue(2, "PLAN-apply!", "bug"))

    assert [i.number for i in similar("the of and a plan apply", issues)] == [2]


def test_the_athlete_name_is_the_profile_heading_or_the_instance_folder() -> None:
    assert athlete_name("# Sam Jones\n\nTrains at home.\n", "sam") == "Sam Jones"
    assert athlete_name("Trains at home.\n", "sam") == "sam"
    assert athlete_name(None, "sam") == "sam"
