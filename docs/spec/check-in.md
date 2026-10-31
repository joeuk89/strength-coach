# Check-in

A check-in is deterministic output with the coach's prose as voice only. The athlete's answers
become records in the tables that already own those facts; the Check-in row is a small event; the
card, the rendered record, deep-tier due and week closure are views of the store at a date.

Decided on wayfinder ticket [Check-in as data](https://github.com/joeuk89/strength-coach/issues/21),
2026-10-27. The prose rule follows ADR 0005; the Observation lifecycle follows ADR 0009; timing
rules are in the parity checklist (`parity.md`, "Core loop: check-in, ledger and research
citations").

## The row

| Field | Meaning |
| --- | --- |
| `date` | The day the check-in was recorded |
| `tier` | `light` or `deep` |
| `window_start`, `window_end` | The span it reviews: the day after the previous check-in's `window_end` to `date`. Derived once by the engine at `checkin record` and then stored, because it is a fact of the event |
| `read` | The coach's read, free text, inserted verbatim wherever it is shown |
| `status` | `current` or `superseded` (see Correcting) |

Nothing else. Adherence, week kind, block count, e1RMs, triggers and the hard-week count are
views. A declined ceiling or a deferred deep review decided at the check-in is a Decision row
carrying the check-in reference; a light week taken is the `light_week` override on the next
WeekPlan, and the block closes by the derived week kind (`overrides.md`).

Catch-up is not stored: a check-in whose window is longer than the first return band (10 days) is a
catch-up by definition, and the deep tier is deferred to the next check-in by the same test.

## The sourced records

Every record entered during a check-in carries a `check_in` reference to the row. Where each
answer lands:

| Answer | Record |
| --- | --- |
| Missed core session, with its reason tag | Annotation of kind `miss tag` on the planned session. Miss stays derived; only the tag is stored |
| Coach-led session done | Normally nothing: the Hevy workout already fulfils it (see Matching). A hand-entered Workout with no sets, with minutes and session RPE, only when Hevy has nothing for that day |
| Trained but not logged | Annotation `trained-unlogged` |
| Sleep | Sleep night rows, source `check-in`. A period mean is not a night and is stored nowhere; the read may quote it |
| Weight | Weigh-in, source `check-in` |
| Niggle reported, aggravated, easing, resolved | Niggle status event |
| Follow-up disposition | Follow-up event: deferred, kept, resolved or dropped. A deep check-in gives every open one a disposition |
| Free note from the athlete | Athlete note: date, text verbatim, optional `about` reference (planned session, exercise, niggle, follow-up). Never classified by code |
| A pattern the coach has noticed, or one that stopped holding | Observation raised or retired (ADR 0009) |
| Declined ceiling, deferred deep review, an agreement or an override for longer than a week | Decision (`overrides.md`) |

### Matching a coach-led session

The Match for a coach-led planned session is derived: an imported Hevy workout on that date (or
inside the slot's window for a standing cadence) that is not matched to another planned session
fulfils it. Minutes come from the workout's start and end; session RPE is the mean working-set RPE.
The card prefills "logged in Hevy, 60 min" and asks for the RPE only when the sets carry none. When
the rule matches wrongly (two workouts on one day, a session logged on the wrong date) the fix is
an Annotation of kind `match` naming the planned session. Match is never a stored table.

### Athlete notes

A note is surfaced by rule in three places and nowhere else:

1. The next check-in card lists every note in its window, verbatim, under the athlete's answers.
2. The next plan draft's context lists every note since the last approved WeekPlan; a note with an
   `about` reference is also shown beside that line, session or niggle in the draft.
3. The rendered check-in page prints the window's notes verbatim.

A note has no lifecycle of its own. Once its window has closed it lives only on the rendered
record, unless its `about` reference is an open niggle or follow-up, in which case it rides with
that record until it closes. A note that turns out to be a niggle or a follow-up is cited as
evidence when the coach raises one; the note is never reclassified. Hevy's own set notes stay on
the workout and are surfaced from there.

## The record file

`checkin record` takes one file holding the tier, the read and the typed records above. The engine
derives the window, writes everything in one transaction and stamps each record with the check-in
reference. The athlete's yes is the conversational yes before the agent runs the verb (ADR 0009);
the verb touches neither Hevy nor git, so it is not a Writing verb and no permission prompt
attaches to it.

## Correcting

Rows are append-only. Re-running `checkin record` for the same date supersedes the earlier row
(`status = superseded`). Records sourced from the superseded row stay unless the new file withdraws
them: annotations by a withdrawing annotation, niggle and follow-up events by a later event. No
edit in place, no delete.

## Views

All of these are pure functions of the store at a date and are never stored:

- **The card**: fields in a fixed order, inapplicable fields dropped; prefill states what the store
  knows and asks only what it cannot; e1RM rows compounds first; athlete notes verbatim; the deep
  tier adds misses by tag since the last deep check-in; due follow-ups. The card reads the
  version's emphasis and priority lifts (`goals.md`, the check-in row of its per-emphasis
  table, ADR 0020): with priority lifts it leads with them, the top set's load and reps stated
  and how it moved and felt asked; on a `hypertrophy` version it asks reps and RIR on the lines
  that moved, pump and soreness as a dose read; on `maintenance` whether the kept lifts held.
  With an open Phase the card carries a Phase line: kind, target rate, the 14-day bodyweight
  trend against it and the `until` condition; `phase_trend_off` and `phase_condition_met` are
  raised here, not at the block boundary (`goals.md`, **What the Phase changes**).
  The `check-in` skill carries none of this.
- **Week closure**: a week is closed when a `current` check-in's window covers its Sunday.
- **Deep due**: 42 days since the newest `current` row with `tier = deep`, or a light week newly
  proposed, or a restructure, or the previous check-in was a catch-up; suppressed by a Decision of
  kind `defer_deep_review` until its date. No stored flag, no title.
- **The rendered record**: rendered on demand from the row, its sourced records and the store as it
  stands now, so later annotations and imports improve an old page rather than being hidden from
  it. The read is the only frozen text. The page is committed and regenerated at every publish
  (ADR 0012).

## The prose rule

The read is free voice. The renderer places every typed fact (adherence table, e1RM table, sleep,
weight, niggles, decisions) in generated sections beside it. Nothing parses or polices the read:
no regex, no word count, no check that it carries no number. A number in prose is voice; a number
in a typed field is data; only typed fields reach a rule or a page's tables (ADR 0005).

The test that replaces `bare_hevy_values`: every number in a rendered record's generated sections
equals a value derived from the store, and the read appears verbatim. Nothing asserts anything
about the read's wording.
