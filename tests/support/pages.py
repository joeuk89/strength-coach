"""Every page `publish` would write from a store, rendered through the service and `render`."""

import datetime
from collections.abc import Sequence

from coach.core.kit import KitFiles
from coach.render.pages import render_pages
from coach.services.pages import page_facts
from coach.store.connection import Connection
from support.programs import a_config


def the_pages(
    conn: Connection, *, kits: Sequence[KitFiles] = (), profile: str | None = None
) -> dict[str, str]:
    """Lift loads in lb and bodyweight in kg, as `a_config` sets them."""
    return render_pages(
        page_facts(conn, config=a_config(), kits=kits, profile=profile, zone=datetime.UTC)
    )
