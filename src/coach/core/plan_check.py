"""The one plan check: every flag of the plan Draft, each warning left or not
(docs/spec/validation.md, "Leaving a warning", "Violations")."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from coach.core.flag import Acknowledgement, Flag, Scope, leave, raise_flag
from coach.core.plan_draft import PlanDraft
from coach.core.planned_week import week_monday
from coach.core.program.checks import TEMPLATE_COLUMNS


@dataclass(frozen=True)
class TemplateFacts:
    """An Exercise's Hevy template id, or the four columns `plan apply` creates one from."""

    exercise_id: str
    hevy_template_id: str | None
    columns: Mapping[str, str | None]

    @property
    def missing(self) -> tuple[str, ...]:
        if self.hevy_template_id:
            return ()
        return tuple(c for c in TEMPLATE_COLUMNS if not self.columns.get(c))

    @property
    def to_create(self) -> bool:
        return not self.hevy_template_id and not self.missing


@dataclass(frozen=True)
class CheckedPlan:
    draft: PlanDraft
    flags: tuple[Flag, ...]

    @property
    def violations(self) -> tuple[Flag, ...]:
        return tuple(f for f in self.flags if f.severity == "violation")


def check_plan(
    draft: PlanDraft,
    *,
    acknowledgements: Sequence[Acknowledgement],
    templates: Mapping[str, TemplateFacts] | None,
) -> CheckedPlan:
    """`templates` is None without a `[hevy]` table: no template is needed then (ADR 0006)."""
    raised = (*draft.flags, *_missing_templates(draft, templates))
    # A daily session's line repeats on each day under one key; a key is one flag.
    unique: dict[str, Flag] = {}
    for flag in raised:
        unique.setdefault(flag.key, flag)
    left = [leave(flag, acknowledgements) for flag in unique.values()]
    ordered = sorted(left, key=lambda f: f.severity != "violation")
    return CheckedPlan(draft, tuple(ordered))


def _missing_templates(
    draft: PlanDraft, templates: Mapping[str, TemplateFacts] | None
) -> tuple[Flag, ...]:
    if templates is None:
        return ()
    found: list[Flag] = []
    for prescribed in draft.sessions:
        planned = prescribed.session
        for line in prescribed.lines:
            facts = templates.get(line.exercise_id)
            if facts is None or not facts.missing:
                continue
            scope = Scope(
                "line",
                week_monday(planned.date),
                session_id=planned.session_id,
                exercise_id=line.exercise_id,
            )
            found.append(
                raise_flag(
                    "hevy_template_missing",
                    scope,
                    {"exercise_id": line.exercise_id, "missing_columns": list(facts.missing)},
                    f"{line.exercise_id} has no Hevy template and lacks {', '.join(facts.missing)}",
                )
            )
    return tuple(found)
