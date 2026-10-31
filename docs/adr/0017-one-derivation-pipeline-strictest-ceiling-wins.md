---
status: accepted
date: 2026-10-31
amended: 2026-10-31 by wayfinder #39 (the one week-level cut is one cut per line, the return band or the light cut, return winning; `minimum_week` and `one_off_week` choose sessions before the pipeline and cut nothing; illness is a ceiling; the light cut's shape is the version's `[deload]` table); 2026-10-31 by wayfinder #41 (the signature is one prescribe request, `docs/spec/prescription.md`)
---

# A prescription is derived by one fixed pipeline; exactly one week-level cut applies and ceilings bind by the strictest, never by compounding

Every line's prescription is derived by the same ordered steps: the scheme's move from the
anchor exposure, the plan's line override, the override Decision in force, one week-kind
transform, the niggle constraints, the RPE ceilings, the safety ceiling and rack rounding, then
the warm-up ladder. Each step runs once and records what it changed and why. At most one
week-level cut ever applies to a line (a return band, a deload cut, a light cut, or none),
chosen by the week kind's precedence (amended: the return band, the light cut, or none, in that order;
there is no separate deload cut and no cut from a minimum or one-off week). Every other limit (a
niggle's cap, an illness cap, a light week's RPE ceiling, a safety ceiling, a `pin_load`) is a
ceiling, and ceilings bind by `min`:
the strictest wins and none multiplies another. The spec is `docs/spec/prescription.md`.

## Context

ADR 0003 made the prescription a pure function and ADR 0005 put every departure in a typed
override, but neither said in what order the rule, the overrides and the recovery limits
apply, nor whether two limits on one line add up. The old engine ran a comparable order inside
`propose_line` but let the return decay and the week transform run in sequence, guarded by a
no-op in the return transform, and template #257 (a return cut taken twice) came from a cut
being measured from a number that already carried a cut.

## Considered options

- **One pipeline, one week-level cut, ceilings by `min` (chosen).** Every number is traceable
  to one step; a cut can never be applied twice because only one cut exists per line per week;
  a stricter limit is always safe to add because it can only lower a load. The explanation
  per line is the step list itself.
- **Compose cuts multiplicatively.** A return band in a deload week would cut 0.85 × 0.9. No
  coaching source stacks them, and a stacked cut is the #257 shape again.
- **Let each modifier decide its own order (the old transform plugins).** The order lived in
  code paths and a docstring; nothing stated which modifier won, and the agent read a prose
  rationale to find out.
- **Precedence as a parameter of the version or the instance.** A per-instance order makes
  the same history derive different numbers in two instances, and nothing in practice wants it.

## Consequences

- `prescribe` takes the one prescribe request `docs/spec/prescription.md` lists (**What
  prescribe is handed**), never a WeekPlan, Goal, Phase, profile or Weigh-in; the week kind is
  derived inside it from the plan's week override, the status spans and the days off.
- A line carries its derivation steps in every envelope; the dry run and the rendered week
  page show them, and no prose rationale is generated.
- A held line (`hold`) is still cut by the week transform and still bound by ceilings; `hold`
  replaces only the scheme's move.
- Regression tests: a 43+ day return line re-derived, rebuilt or re-planned midweek has the
  same load (ADR 0005's test, now by construction); a return band inside a light week applies
  the return band only, and a return line inside a minimum week keeps its band; a niggle cap below a safety ceiling binds and the ceiling is recorded
  as not binding; a `pin_load` above a niggle cap is `recovery_ceiling_exceeded`, not a cap.
