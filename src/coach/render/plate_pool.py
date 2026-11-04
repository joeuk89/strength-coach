"""Links into plate-pool's web app: one per loaded line, carrying the kit's short hash, and the
set-up link carrying the inventory inline (ADR 0021, "Routine pages")."""

import base64
import zlib

from coach.core.config import ImplementChoice, Units
from coach.core.pages import PageLine, PlatePoolKit
from coach.render.markdown import number

PLATE_POOL = "https://joeuk89.github.io/plate-pool/"


def line_link(line: PageLine, kit: PlatePoolKit, units: Units) -> str | None:
    """`?barbell=175lb&barbell.hardware=collar-clamp&kit=<hash>` from the line's heaviest working
    load and the hardware that builds it; none for a line with no load or an equipment kind the
    kit has no implement for."""
    implement = kit.implements.get(line.equipment_kind or "")
    loads = [
        float(str(g["load"]))
        for g in line.set_groups
        if g.get("type") != "warm_up" and g.get("load") is not None
    ]
    if implement is None or not loads:
        return None
    choice = kit.implement.get(implement, ImplementChoice())
    key = f"{implement}.single" if choice.single else implement
    parameters = [(key, f"{number(max(loads))}{units}")]
    hardware = kit.hardware_at(implement, max(loads))
    if hardware is not None:
        parameters.append((f"{implement}.hardware", hardware))
    parameters.append(("kit", kit.short_hash))
    return PLATE_POOL + "?" + "&".join(f"{name}={value}" for name, value in parameters)


def set_up_link(kit: PlatePoolKit) -> str | None:
    """The inventory as raw deflate (no zlib header), base64url without padding, in the fragment
    so it never reaches a server."""
    if kit.inventory is None:
        return None
    deflate = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = deflate.compress(kit.inventory) + deflate.flush()
    encoded = base64.urlsafe_b64encode(packed).rstrip(b"=").decode("ascii")
    return f"{PLATE_POOL}#inventory={encoded}"
