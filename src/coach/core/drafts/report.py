from functools import cache

from coach.core.draft_schema import DraftKind
from coach.core.report import Footer, issue_draft

EXAMPLE = """kind = "gap"
title = "plan draft gives no rest day hint"
body = "What happened, what was expected, and the steps that show it."
"""

COVERAGE = (
    '''kind = "bug"
title = "plan apply drops a set"
body = """
The plan held three sets; Hevy showed two.
"""
verb = "plan apply"
code = "invalid_argument"
''',
)

# A Report's footer is the engine's own; reading the Draft's shape needs none of it.
_FOOTER = Footer("athlete", "0", "0", 0, "3", "platform")


@cache
def report_kind(verbs: tuple[str, ...]) -> DraftKind:
    """The report Draft, whose `verb` names one of `verbs`."""
    return DraftKind(
        "report",
        lambda data: issue_draft(data, verbs=verbs, footer=_FOOTER),
        EXAMPLE,
        COVERAGE,
    )
