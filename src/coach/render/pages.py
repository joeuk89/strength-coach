"""Every page `publish` writes, as text by path from the instance root (ADR 0012)."""

from coach.core.pages import Pages
from coach.render.athlete_page import athlete_page
from coach.render.check_in_page import check_in_page, check_in_path
from coach.render.progress_page import progress_page
from coach.render.readme import readme, routine_path
from coach.render.routine_page import routine_page
from coach.render.week_page import week_page

PAGES_DIR = "pages"
README = "README.md"


def render_pages(pages: Pages) -> dict[str, str]:
    rendered = {
        README: readme(pages),
        f"{PAGES_DIR}/week.md": week_page(pages.week, units=pages.units, pin=pages.pin),
        f"{PAGES_DIR}/athlete.md": athlete_page(pages.athlete),
        f"{PAGES_DIR}/progress.md": progress_page(
            pages.progress,
            units=pages.units,
            bodyweight_units=pages.bodyweight_units,
            pin=pages.pin,
        ),
    }
    rendered |= {
        routine_path(r.session_id): routine_page(r, units=pages.units) for r in pages.routines
    }
    rendered |= {check_in_path(c): check_in_page(c) for c in pages.check_ins}
    return rendered
