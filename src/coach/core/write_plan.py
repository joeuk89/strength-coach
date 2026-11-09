"""The Write plan hash (ADR 0006, "The Write plan"): the WeekPlan row that would be frozen, the
Hevy writes, and the stored version of each routine they touch. The Draft's notes are not in it."""

import datetime
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import cast

from coach.core.config import Units
from coach.core.flag import Acknowledgement
from coach.core.frozen_prescription import frozen_groups
from coach.core.hevy_actions import HevyActions
from coach.core.instant import parse_instant
from coach.core.plan_draft import PlanDraft
from coach.core.prescription import PlanOverride
from coach.core.program.form import SetGroup, group_document

type Json = dict[str, object]


def write_plan_hash(
    draft: PlanDraft,
    *,
    acknowledgements: Sequence[Acknowledgement],
    actions: HevyActions,
    routine_versions: Mapping[str, str | None],
    units: Units,
) -> str:
    document: Json = {
        "week": draft.week.isoformat(),
        "position": draft.position.week,
        "overrides": [_override(o) for o in draft.overrides],
        "acknowledgements": [_acknowledgement(a) for a in acknowledgements],
        "prescriptions": [
            {
                "session": prescribed.session.session_id,
                "date": prescribed.session.date.isoformat(),
                "location": prescribed.session.location,
                "exercise": line.exercise_id,
                "derived_from": line.derived_from,
                "set_groups": frozen_groups(line.groups, units),
                **({} if line.rung is None else {"rung": line.rung}),
            }
            for prescribed in draft.sessions
            for line in prescribed.lines
        ],
        "hevy": actions.to_json(),
        "routines": {
            routine: routine_versions.get(routine) for routine in actions.touched_routines
        },
    }
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def moved_routines(
    touched: Sequence[str],
    *,
    approved_at: str,
    imports: Mapping[str, str],
    own_writes: Mapping[str, str],
) -> tuple[str, ...]:
    """The touched routines the mirror took in after approval and after the push last wrote or
    checked them. The push's own read-back stamps `imported_at` and `written_at` alike."""
    approved = parse_instant(approved_at)
    return tuple(
        routine
        for routine in touched
        if routine in imports
        and parse_instant(imports[routine]) > _last_seen(approved, own_writes.get(routine))
    )


def _last_seen(approved: datetime.datetime, written_at: str | None) -> datetime.datetime:
    return approved if written_at is None else max(approved, parse_instant(written_at))


def resumed_write_plan_hash(approved: str, moved_versions: Mapping[str, str | None]) -> str:
    """The approved hash while no touched routine moved; else one covering the moved versions."""
    if not moved_versions:
        return approved
    canonical = json.dumps(
        {"approved": approved, "moved": dict(moved_versions)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _override(override: PlanOverride) -> Json:
    return {
        "kind": override.kind,
        "session": override.session_id,
        "exercise": override.exercise_id,
        "date": None if override.date is None else override.date.isoformat(),
        "params": override_params(override),
        "because": override.because,
        "text": override.text,
        "evidence": list(override.evidence),
    }


def override_params(override: PlanOverride) -> Json:
    """The kind's params as JSON values the Draft parser reads back."""
    return {name: _param(value) for name, value in override.params.items()}


def _param(value: object) -> object:
    if isinstance(value, tuple):
        return [
            group_document(item) if isinstance(item, SetGroup) else item
            for item in cast(tuple[object, ...], value)
        ]
    if isinstance(value, datetime.date):
        return value.isoformat()
    return value


def _acknowledgement(acknowledgement: Acknowledgement) -> Json:
    return {
        "key": str(acknowledgement.key),
        "params_hash": acknowledgement.params_hash,
        "because": acknowledgement.because,
        "text": acknowledgement.text,
        "evidence": list(acknowledgement.evidence),
    }
