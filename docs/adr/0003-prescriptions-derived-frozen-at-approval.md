---
status: accepted
date: 2026-10-26
amended: 2026-10-31 by wayfinder #46 (no draft WeekPlan: the Draft is a file, the row is born approved, ADR 0006); 2026-10-31 by wayfinder #41 (`prescribe` takes one prescribe request, listed once in `docs/spec/prescription.md`; the request is never a WeekPlan, Goal, Phase, profile or Weigh-in, and is rebuilt on demand, never frozen)
---

# Prescriptions are derived from rule and history, and frozen only at approval

A prescription (this week's sets, load, reps and RPE for one line) is computed from the program
version, the exposures logged so far and the WeekPlan's typed overrides. It is never authored and
never stored as a weekly delta. The one exception is approval: when the athlete approves a
WeekPlan, the prescriptions it derived at that moment are frozen onto it, because approval must
bind to exact numbers and a later workout import must not change what was approved and pushed.
Likewise no progression state is stored: e1RM, double-progression stage and miss counts are
recomputed from exposures, and a training max is a recorded Decision.

## Considered options

- **Derived, frozen at approval (chosen).** Coaches move only the dose weekly, by rule from last
  week's log (wayfinder #14). Deriving reproduces that; freezing at approval keeps the audit
  exact. The frozen copy is a recorded fact (what was said yes to), not cached derived data.
- **Stored weekly prescriptions as the plan.** The old overlay model. A delta over a delta
  reintroduced the compounding return cut (template #257) and needed drift checks between the
  stored numbers and the history they came from.
- **Derived with no freeze.** Pure, but a late import or an annotation silently changes the
  approved numbers, so the Hevy push could not prove it sent what was approved.

## Consequences

- The plan Draft file carries overrides and reasons; the WeekPlan row is born approved with its
  prescriptions frozen, there is no draft WeekPlan (ADR 0006). Re-planning midweek supersedes it
  and freezes afresh.
- A return cut is measured once from the pre-layoff exposure, never from a frozen prescription
  that already carries the cut.
- Tests of progression assert `prescribe(request)` against values, the request being the one
  listed in `docs/spec/prescription.md` (**What prescribe is handed**: the version, exposures,
  plan overrides, Decisions in force, niggle constraints, status spans, racks, Block count,
  activities, date; never a WeekPlan, Goal, Phase, profile or Weigh-in); nothing reads a stored
  progression row. The request is not frozen: the prescriptions and their steps are.
- The schema has no `prescription` table outside the approved WeekPlan, and no
  `progression_state` table.
