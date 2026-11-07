from coach.core.report import IssueDraft


def report_prompt(repo: str, issue: IssueDraft) -> str:
    """What the athlete approves: the whole issue, never cut (docs/spec/voice.md, "The prompt")."""
    return "\n".join(
        [
            f"Report to {repo}",
            f"Title: {issue.title}",
            f"Labels: {', '.join(issue.labels)}",
            "",
            issue.body,
        ]
    )
