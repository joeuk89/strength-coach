"""The instance's root README: the GitHub app's landing page, pointing at the pages."""

from coach.core.pages import Pages
from coach.render.check_in_page import check_in_path
from coach.render.markdown import bullets, page, section


def routine_path(session_id: str) -> str:
    return f"pages/routines/{session_id}.md"


def readme(pages: Pages) -> str:
    return page(
        "Training",
        bullets(
            [
                "[This week](pages/week.md)",
                "[Athlete](pages/athlete.md)",
                "[Progress](pages/progress.md)",
            ]
        ),
        section(
            "Routines",
            bullets([f"[{r.title}]({routine_path(r.session_id)})" for r in pages.routines]),
        ),
        section(
            "Check-ins",
            bullets(
                [
                    f"[{record.date.isoformat()}]({check_in_path(record)})"
                    for record in reversed(pages.check_ins)
                ]
            ),
        ),
    )
