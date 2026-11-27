---
status: accepted
date: 2026-11-27
---

# A loaded timed line gets its own scheme, `timed_load`, and `hold` stays as it is

A loaded carry held for time had no scheme that could move its load. It sat on `hold`, which
reads the anchor's top load and nothing else, and its Hevy template stored weight and distance,
so each exposure arrived as load only. Issue #328. We add a line scheme, `timed_load`: an
authored `duration_s`, set count and RPE target; every set held for the seconds at an effort
at or under the target moves the load one rack row up, and anything else holds. Hevy records
the seconds on a `weight_duration` template but takes no RPE there, so the engine asks the
effort at the check-in and stores the answer as a `repair` of each set's `rpe`. Adopt refuses
the scheme on any other template (`template_untimed`).

## Considered options

- **A new scheme (chosen).** `hold` keeps one meaning, "the authored sets stand until an
  override or a new version", which conditioning lines, strict singles and unloaded holds all
  rely on. The new scheme carries its own hit test, stall metric and set-group shape.
- **A progression option on `hold`.** Rejected: a param that turns `hold` into a progressing
  scheme gives one name two rules, and every reader of `hold` (the stall table, the cadence
  table, the check-in's `rpe_missing`, conditioning lines) would have to ask which one it is.
- **Read the effort from Hevy's set note.** Rejected: set notes stay unread by code
  (`docs/spec/check-in.md`), and a number typed into free text is not a typed field.

## Consequences

- An unloaded timed hold stays on an `exercise_ladder` with duration rungs (ADR 0025).
- A built-in carry records distance, so moving a carry onto `timed_load` means a new custom
  exercise with a `start_load`; its old history stays on the old exercise, untouched.
- A step down stays a coach decision: the scheme never cuts.
