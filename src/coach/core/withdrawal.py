from collections.abc import Mapping

from coach.core.errors import Invalid


def withdrawable(
    kind: str, target: str, stored: Mapping[str, object] | None, withdrawn_by: str | None
) -> Mapping[str, object]:
    """The stored row `target` names, refused unless a new `kind` row may withdraw it."""
    if stored is None:
        raise Invalid("draft_ref_unresolved", f"[[{kind}]] withdraws {target}, which is not stored")
    if stored["withdraws"] is not None:
        raise Invalid("state_conflict", f"{target} is itself a withdrawal; it cannot be withdrawn")
    if withdrawn_by:
        raise Invalid("state_conflict", f"{target} is already withdrawn by {withdrawn_by}")
    return stored
