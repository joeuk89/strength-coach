---
status: accepted
date: 2026-10-31
---

# A WeekPlan carries twelve override kinds, a Decision's kind is its outcome, an override Decision applies itself, and promotion is a warning the agent acts on

The departures the agent may make from the program version's rule are a closed catalogue of
typed kinds (`docs/spec/overrides.md`): twelve on the WeekPlan for one span, and ten Decision
kinds for anything longer or any agreement with the athlete. A Decision has no outcome field:
it is written only when made, and its kind says what was decided (`decline_ceiling`,
`defer_deep_review`); a taken proposal is an override on the plan, an untaken one is nothing.
An override Decision wraps one line-scope kind with an until date of at most eight weeks and
applies itself to every WeekPlan in its span. A line override recurring on three consecutive
plans raises a warning; the agent promotes it to an amended version, extends it as a Decision,
or leaves it, and nothing promotes on its own.

## Context

ADR 0005 fixed the override shape (scopes, the reason triple, a load only as a typed field) and
left the kinds to this catalogue. The old instance carried overrides as per-line `proposed_sets`
in an overlay, standing overrides as decisions with `standing: true` and a four-to-eight week
until, a decisions ledger with `adopted | declined | deferred` outcomes, caps in config, and a
light-week state machine over `decisions.json`. Niggle constraints already lived on the niggle.

## Considered options

- **A closed catalogue, Decision kind as outcome, self-applying override Decisions, promotion
  by warning (chosen).** Every departure is countable and typed; the ledger holds what happened,
  not what was proposed; a temporary swap during a niggle or a hold through a deficit need not
  become a version; the coach decides when a pattern is the program.
- **Outcomes on Decisions, as the old ledger had.** Records proposals the athlete never acted
  on and needs a status machine (the old `block decide`) to keep them consistent. The proposal
  lives in the check-in card and the dry run; only the choice is a record.
- **No override Decisions: a persisting override is always a new version.** Fills the version
  history with temporary states and makes a four-week hold an `amend` with a reversal later.
- **Automatic promotion after N weeks.** The engine would author a program version; versions
  are the one record the athlete authors (ADR 0001, 0015).
- **A light week and a block reset as Decisions.** A light week is one span, so it is a plan
  override approved with the plan; a reset is derived from the week kind or a `redesign`
  version, so a record that says "reset" would be a second source of truth.
- **Niggle caps as Decisions.** The cap's lifetime is the niggle's status; a second record
  would drift from it. A limit that outlives the niggle is a Safety ceiling.

## Consequences

- `prescribe` reads the version, the exposures, the plan's overrides and the Decisions in
  force; the signature stays closed to any WeekPlan (ADR 0005).
- The glossary's Decision entry loses "a light week" and "outcome"; `validation.md` gains seven
  codes and loses "a block reset Decision" as a clearer; the check-in and goals specs name the
  block boundary as the check-in whose week kind closes the block, not a Decision.
- The old `[caps]` and `[cardio]` run caps migrate as `safety_ceiling` and `activity_cap`
  Decisions; open standing overrides migrate as `override` Decisions.
- Regression tests: an override Decision in force changes a plan the Draft never mentions; a
  plan override on the same line wins for that week; the third consecutive swap raises
  `override_persisting` and the second does not; a `pin_load` above a niggle cap is
  `recovery_ceiling_exceeded`, not a lower cap; no `[[decision]]` row carries an outcome.
