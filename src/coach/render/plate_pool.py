"""Links into plate-pool's web app: one per loaded line, carrying the kit's short hash, and the
set-up link carrying the inventory inline (ADR 0021, "Routine pages")."""

import base64
import zlib

from coach.core.config import Units
from coach.core.pages import PageLine, PlatePoolKit
from coach.render.markdown import number

PLATE_POOL = "https://joeuk89.github.io/plate-pool/"


def line_link(line: PageLine, kit: PlatePoolKit, units: Units) -> str | None:
    """`?barbell=175lb&collars=clamp&kit=<hash>` from the line's heaviest working load; none
    for a line with no load or an equipment kind the kit has no implement for."""
    implement = kit.implements.get(line.equipment_kind or "")
    loads = [
        float(str(g["load"]))
        for g in line.set_groups
        if g.get("type") != "warm_up" and g.get("load") is not None
    ]
    if implement is None or not loads:
        return None
    parameters = [(_parameter(implement, kit), f"{number(max(loads))}{units}")]
    if implement == "barbell":
        parameters.append(("collars", kit.collars))
    parameters.append(("kit", kit.short_hash))
    return PLATE_POOL + "?" + "&".join(f"{name}={value}" for name, value in parameters)


def set_up_link(kit: PlatePoolKit) -> str | None:
    if kit.inventory is None:
        return None
    packed = base64.urlsafe_b64encode(zlib.compress(kit.inventory, 9)).rstrip(b"=")
    return f"{PLATE_POOL}?kit={packed.decode('ascii')}"


def _parameter(implement: str, kit: PlatePoolKit) -> str:
    if implement == "dumbbell":
        return "dumbbells" if kit.dumbbells == "pair" else "dumbbell"
    return implement
