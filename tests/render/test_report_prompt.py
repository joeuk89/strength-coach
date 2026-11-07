from coach.core.report import IssueDraft
from coach.render.report_prompt import report_prompt


def test_the_prompt_is_the_repo_the_title_the_labels_and_the_body() -> None:
    issue = IssueDraft("No swims", "Swims are not logged.\n", ("needs-triage", "enhancement"))

    assert report_prompt("joeuk89/strength-coach", issue) == (
        "Report to joeuk89/strength-coach\n"
        "Title: No swims\n"
        "Labels: needs-triage, enhancement\n"
        "\n"
        "Swims are not logged.\n"
    )


def test_a_body_far_past_forty_lines_is_never_cut() -> None:
    body = "".join(f"line {n}\n" for n in range(500))

    prompt = report_prompt("joeuk89/strength-coach", IssueDraft("t", body, ("bug",)))

    assert prompt.endswith(body)
    assert len(prompt.splitlines()) == 504
