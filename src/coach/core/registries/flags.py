from dataclasses import dataclass
from typing import Literal

from coach.core.registries.registry import Registry, Row

type Severity = Literal["violation", "warning"]
type ScopeKind = Literal[
    "week", "session", "line", "exposure", "routine", "workout", "instance", "version", "exercise"
]
type Refs = tuple[str, ...]


@dataclass(frozen=True)
class ByCase:
    """A code whose citation depends on one of its params, as `recovery_ceiling_exceeded`'s on
    its ceiling kind."""

    param: str
    cases: tuple[tuple[str, Refs], ...]

    def refs_for(self, value: object) -> Refs:
        return next((refs for case, refs in self.cases if case == value), ())


type Citation = Refs | ByCase


@dataclass(frozen=True)
class FlagCode:
    name: str
    severity: Severity
    acknowledgeable: bool
    scopes: tuple[ScopeKind, ...]
    params: tuple[str, ...]
    rn: Citation = ()
    cleared_by: tuple[str, ...] = ()

    def refs_for(self, params: dict[str, object]) -> Refs:
        if isinstance(self.rn, ByCase):
            return self.rn.refs_for(params.get(self.rn.param))
        return self.rn

    def describe(self) -> Row:
        row: Row = {
            "code": self.name,
            "severity": self.severity,
            "acknowledgeable": self.acknowledgeable,
            "scope": list(self.scopes),
            "params": list(self.params),
            "rn": _citation(self.rn),
        }
        if self.cleared_by:
            row["cleared_by"] = list(self.cleared_by)
        return row


def _citation(rn: Citation) -> object:
    if isinstance(rn, ByCase):
        return {"by": rn.param, "cases": {case: _refs(refs) for case, refs in rn.cases}}
    return _refs(rn)


def _refs(refs: Refs) -> object:
    if not refs:
        return None
    return refs[0] if len(refs) == 1 else list(refs)


def violation(
    name: str,
    scopes: tuple[ScopeKind, ...],
    params: tuple[str, ...],
    cleared_by: tuple[str, ...],
    rn: Citation = (),
) -> FlagCode:
    return FlagCode(name, "violation", False, scopes, params, rn, cleared_by)


def acknowledgeable_warning(
    name: str, scopes: tuple[ScopeKind, ...], params: tuple[str, ...], rn: Citation = ()
) -> FlagCode:
    return FlagCode(name, "warning", True, scopes, params, rn)


def outside_warning(
    name: str, scopes: tuple[ScopeKind, ...], params: tuple[str, ...], rn: Citation = ()
) -> FlagCode:
    return FlagCode(name, "warning", False, scopes, params, rn)


# docs/spec/validation.md, "Code registry": one row per code, in the spec's order.
VIOLATIONS = (
    violation(
        "load_off_grid",
        ("line",),
        ("load", "implement", "location", "nearest_grid_loads"),
        ("plan apply",),
    ),
    violation(
        "recovery_ceiling_exceeded",
        ("line",),
        ("ceiling_kind", "ceiling", "prescribed", "ref"),
        ("[[niggle]]", "[[annotation]]", "[[workout]]", "plan apply"),
        ByCase(
            "ceiling_kind",
            (
                ("return_band", ("rn:detraining-return.3",)),
                ("illness", ("rn:detraining-return.4",)),
                ("light_week", ("rn:deloads.10",)),
                ("niggle", ()),
            ),
        ),
    ),
    violation(
        "return_band_disagrees",
        ("line",),
        ("days_off", "band", "load", "set_delta", "rpe_cap"),
        ("plan apply",),
        ("rn:detraining-return.3",),
    ),
    violation(
        "block_ceiling_exceeded",
        ("week",),
        ("hard_weeks", "ceiling", "block_id"),
        ("[[decision]]", "plan apply", "program adopt"),
        ("rn:deloads.3",),
    ),
    violation(
        "hevy_template_missing",
        ("line",),
        ("exercise_id", "missing_columns"),
        ("[[exercise]]", "program adopt"),
    ),
    violation(
        "load_mode_mismatch",
        ("line",),
        ("exercise_load_mode", "line_load_mode"),
        ("[[exercise]]", "plan apply"),
    ),
    violation("rotation_unconfirmed", ("week",), ("inferred_position", "source"), ("plan apply",)),
    violation("goal_missing", ("version",), (), ("goal adopt",)),
    violation(
        "priority_lifts_required", ("version",), ("emphasis",), ("goal adopt", "program adopt")
    ),
    violation("unknown_key", ("version",), ("key_path",), ("program adopt",)),
    violation("unknown_exercise", ("line",), ("exercise_id",), ("program adopt",)),
    violation("unknown_scheme", ("line", "session"), ("scheme", "param"), ("program adopt",)),
    violation("unknown_load_mode", ("line",), ("load_mode",), ("program adopt",)),
    violation("duplicate_id", ("version",), ("session_id", "exercise_id"), ("program adopt",)),
    violation(
        "schedule_session_missing",
        ("version",),
        ("week", "weekday", "session_id"),
        ("program adopt",),
    ),
    violation("session_unscheduled", ("session",), ("session_id",), ("program adopt",)),
    violation("cadence_on_scheduled", ("session",), ("session_id", "cadence"), ("program adopt",)),
    violation("location_unknown", ("version", "session"), ("location",), ("program adopt",)),
    violation(
        "equipment_unsupplied", ("line",), ("equipment_kind", "location"), ("program adopt",)
    ),
    violation("rehab_in_version", ("session",), ("session_id",), ("program adopt",)),
    violation("practice_not_optional", ("session",), ("session_id",), ("program adopt",)),
    violation("coach_led_has_lines", ("session",), ("session_id",), ("program adopt",)),
    violation("start_load_missing", ("line",), ("exercise_id",), ("program adopt", "plan apply")),
    violation(
        "start_load_off_rack",
        ("line",),
        ("start_load", "location", "nearest_rows"),
        ("program adopt",),
    ),
    violation("no_working_sets", ("line",), ("scheme",), ("program adopt",)),
    violation("set_type_not_allowed", ("line",), ("set_type", "scheme"), ("program adopt",)),
    violation("set_groups_off_scheme", ("line",), ("scheme", "expected_shape"), ("program adopt",)),
    violation("rpe_missing", ("line",), ("scheme", "group_index"), ("program adopt",)),
    violation("acknowledgement_unmatched", ("version",), ("flag_key",), ("program adopt",)),
    violation(
        "record_kind_not_allowed",
        ("instance",),
        ("record_kind", "verb"),
        ("record", "checkin record"),
    ),
    violation("override_conflict", ("week", "session", "line"), ("kinds",), ("plan apply",)),
    violation(
        "reading_duplicate",
        ("instance",),
        ("reading_kind", "date", "source", "live_id"),
        ("record", "checkin record"),
    ),
    violation(
        "draft_ref_unresolved",
        ("instance",),
        ("ref", "file"),
        ("record", "checkin record", "goal adopt"),
    ),
    violation("niggle_constraint_on_resolved", ("instance",), ("niggle_id",), ("[[niggle]]",)),
)

PLAN_WARNINGS = (
    acknowledgeable_warning(
        "top_set_above_e1rm",
        ("line",),
        ("e1rm", "model", "load", "rpe_target"),
        ("rn:autoregulation.6",),
    ),
    acknowledgeable_warning(
        "no_e1rm", ("line",), ("exercise_id", "scheme"), ("rn:autoregulation.5",)
    ),
    acknowledgeable_warning(
        "increment_over_step", ("line",), ("increment", "scheme_step", "from_exposure")
    ),
    acknowledgeable_warning(
        "offgrid_anchor_ignored", ("line",), ("exposure", "logged_load", "anchor_used")
    ),
    acknowledgeable_warning(
        "over_rep_cap", ("exposure",), ("reps", "cap"), ("rn:autoregulation.5",)
    ),
    acknowledgeable_warning(
        "short_sleep_week",
        ("week",),
        ("short_nights", "threshold", "window"),
        ("rn:sleep-dieting.1",),
    ),
    acknowledgeable_warning(
        "stall_streak", ("line",), ("streak", "exposures"), ("rn:progression-methods §4",)
    ),
    acknowledgeable_warning(
        "rep_range_missed",
        ("line",),
        ("set_index", "reps", "range", "logged_rpe", "authored_rpe"),
    ),
    acknowledgeable_warning(
        "training_max_due",
        ("line",),
        ("training_max", "source", "rep_outs"),
        ("rn:progression-training-age.9",),
    ),
    acknowledgeable_warning(
        "rpe_ceiling_unchecked",
        ("line",),
        ("cap", "clipped_load", "anchor_exposure"),
        ("rn:autoregulation.6",),
    ),
    acknowledgeable_warning(
        "unexplained_drift", ("line",), ("last_prescription", "this_prescription", "delta")
    ),
    acknowledgeable_warning(
        "session_drop_suggested",
        ("session",),
        ("reason", "evidence"),
        ByCase(
            "reason",
            (
                ("quality_stack", ("rn:concurrent-training.4", "rn:concurrent-training.5")),
                ("status_span", ()),
            ),
        ),
    ),
    acknowledgeable_warning(
        "dose_under_target",
        ("week",),
        ("muscle", "target", "weekly_figures"),
        ("rn:volume-frequency.1",),
    ),
    acknowledgeable_warning(
        "session_dose_high", ("session",), ("planned_sets", "ceiling"), ("rn:volume-frequency.3",)
    ),
    acknowledgeable_warning("override_persisting", ("line",), ("kind", "weeks", "plan_ids")),
    acknowledgeable_warning(
        "light_week_shape_off_trigger",
        ("week",),
        ("proposed_shape", "plan_shape", "triggers"),
        ("rn:deloads.5", "rn:deloads.8", "rn:deloads.9", "rn:deloads.10"),
    ),
    acknowledgeable_warning(
        "light_week_unprompted",
        ("week",),
        ("hard_weeks", "ceiling"),
        ("rn:deloads.3", "rn:deloads.4"),
    ),
    acknowledgeable_warning(
        "minimum_week_floor",
        ("week",),
        ("priority_lift", "kept_sessions"),
        ("rn:minimum-effective-dose.4",),
    ),
)

ADOPT_WARNINGS = (
    acknowledgeable_warning("emphasis_off_goal", ("version",), ("goal_kind", "emphasis")),
    acknowledgeable_warning(
        "scheme_off_emphasis",
        ("line",),
        ("scheme", "emphasis", "expected_band"),
        ("rn:goal-programming §4",),
    ),
    acknowledgeable_warning("priority_lift_absent", ("version",), ("exercise_id",)),
    acknowledgeable_warning(
        "priority_lift_not_first",
        ("session",),
        ("exercise_id", "position"),
        ("rn:goal-programming §7",),
    ),
    acknowledgeable_warning(
        "dose_off_band",
        ("version",),
        ("target_of", "target", "band", "phase"),
        ("rn:goal-programming §3",),
    ),
    acknowledgeable_warning(
        "deload_off_emphasis",
        ("version",),
        ("deload_policy", "expected_shape"),
        ("rn:goal-programming §6",),
    ),
    acknowledgeable_warning(
        "muscle_no_hard_sets",
        ("version",),
        ("muscle", "sessions_searched"),
        ("rn:volume-frequency.1",),
    ),
    acknowledgeable_warning("session_over_minutes", ("session",), ("estimate", "minutes")),
    acknowledgeable_warning(
        "session_on_unavailable_day", ("session",), ("session_id", "weekday", "available_days")
    ),
    acknowledgeable_warning("block_open_at_redesign", ("version",), ("block_id", "hard_weeks")),
    acknowledgeable_warning(
        "start_load_ignored", ("line",), ("start_load", "last_exposure_load", "exposure")
    ),
    acknowledgeable_warning("superset_rest_differs", ("session",), ("superset", "rest_values")),
    acknowledgeable_warning("session_retired", ("version",), ("session_id", "routine_id")),
    acknowledgeable_warning(
        "scheme_change_off_signal",
        ("line",),
        ("previous_scheme", "new_scheme", "signal_key", "may_schemes"),
        ("rn:progression-methods §4",),
    ),
    acknowledgeable_warning(
        "core_session_added_low_adherence",
        ("session",),
        ("session_id", "adherence", "weeks"),
        ("rn:deloads.7",),
    ),
)

OUTSIDE_WARNINGS = (
    outside_warning("routine_drift", ("routine",), ("drift_class", "plan_in_force", "diff")),
    outside_warning("workout_reappeared", ("workout",), ("noticed_at", "updated_at")),
    outside_warning("followup_due", ("instance",), ("follow_up_id", "due")),
    outside_warning("niggle_unconstrained", ("instance",), ("niggle_id", "opened")),
    outside_warning("engine_pin_dev", ("instance",), ("pinned_version", "running_version")),
    outside_warning("generated_file_drift", ("instance",), ("file", "engine_version")),
    outside_warning(
        "frozen_load_off_rack", ("session",), ("week", "line", "frozen_load", "location")
    ),
    outside_warning("snapshot_stale", ("instance",), ("last_import", "age_limit_days")),
    outside_warning(
        "cadence_slow",
        ("exercise",),
        ("scheme", "metric", "blocks", "may_schemes", "may", "never"),
        ("rn:training-level §2",),
    ),
    outside_warning(
        "cadence_fast",
        ("exercise",),
        ("scheme", "metric", "may_schemes", "may", "never"),
        ("rn:training-level §2",),
    ),
    outside_warning("phase_condition_met", ("instance",), ("phase_id", "condition", "value")),
    outside_warning(
        "phase_trend_off",
        ("instance",),
        ("phase_id", "target_rate", "observed_rate", "window"),
        ("rn:training-level §4",),
    ),
    outside_warning(
        "activity_cap_exceeded",
        ("week",),
        ("cap", "observed", "activities"),
        ("rn:running-load.5", "rn:running-load.6"),
    ),
    # validation.md scopes run_spike on "workout or activity"; activity is no scope kind.
    outside_warning(
        "run_spike",
        ("workout",),
        ("distance", "longest_30_days", "ratio"),
        ("rn:running-load.1", "rn:running-load.4"),
    ),
    outside_warning("training_max_unused", ("exercise",), ("scheme", "decision_id")),
    outside_warning("exercise_unmapped", ("workout",), ("hevy_template_id", "title")),
)

FLAGS = Registry("flags", VIOLATIONS + PLAN_WARNINGS + ADOPT_WARNINGS + OUTSIDE_WARNINGS)
