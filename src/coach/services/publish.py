from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from coach.core.clock import Clock
from coach.core.config import Config
from coach.core.kit import KitFiles
from coach.render.pages import render_pages
from coach.services.pages import page_facts
from coach.store.connection import Connection
from coach.store.export import Export, export


@dataclass(frozen=True)
class Publication:
    """The export's files and every page, each page by its path from the instance root."""

    export: Export
    pages: Mapping[str, str]


def publish(
    conn: Connection,
    clock: Clock,
    *,
    engine_version: str,
    config: Config,
    kits: Sequence[KitFiles] = (),
    profile: str | None = None,
) -> Publication:
    """What `publish` writes from the store: the export (schema.md, "Export") and the pages
    (ADR 0012)."""
    facts = page_facts(conn, clock, config=config, kits=kits, profile=profile)
    return Publication(export(conn, engine_version), render_pages(facts))
