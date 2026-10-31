# Check-in

A check-in is deterministic output with the coach's prose as voice only. The athlete's answers
become records in the tables that already own those facts; the Check-in row is a small event; the
card, the rendered record, deep-tier due and week closure are views of the store at a date.

Decided on wayfinder ticket [Check-in as data](https://github.com/joeuk89/strength-coach/issues/21),
2026-10-27. The prose rule follows ADR 0005; the Observation lifecycle follows ADR 0009; the
closed week, Match, adherence, the fatigue triggers and the due rules are `week.md`'s
([The closed week](https://github.com/joeuk89/strength-coach/issues/38), 2026-10-31).

## The row

| Field | Meaning |
| --- | --- |
| `date` | The day the check-in was recorded |
| `tier` | `light` or `deep` |
| `window_start`, `window_end` | The span it reviews: the day after the previous `current` check-in's `window_end` to `date`. Derived once by the engine at `checkin record` and then stored, because it is a fact of the event. The first row has no previous one: its `window_start` is the first approved WeekPlan's Monday, or `date` with no plan, and the record file may set it on the first row only (`week.md`, `cutover.md`) |
| `readiness` | The athlete's reported readiness, `poor`, `ok` or `good`, asked on every card. The one typed input the fatigue triggers need (`week.md`); null when the athlete gave none |
| `read` | The coach's read, free text, inserted verbatim wherever it is shown |
| `status` | `current` or `superseded` (see Correcting) |

Nothing else. Adherence, week kind, block count, e1RMs, triggers and the hard-week count are
views (`week.md`). A declined ceiling or a deferred deep review decided at the check-in is a
Decision row carrying the check-in reference; a light week taken is the `light_week` override on
the next WeekPlan, and the Block closes by the derived week kind (`week.md`).

Catch-up is not stored: a check-in whose window is longer than 10 days is a catch-up by
definition, and the deep tier is deferred to the next check-in by the same test (`week.md`).

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

Match is `week.md`'s rule for every session kind: an imported Hevy workout inside the planned
session's window, routine id as a tiebreaker, corrected by an Annotation of kind `match`, never
stored. For a coach-led session the matched workout fulfils it; minutes come from the workout's
start and end and session RPE is the mean working-set RPE. The card prefills "logged in Hevy,
60 min" and asks for the RPE only when the sets carry none.

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

- **The card**: the fields below in this order, inapplicable fields dropped; prefill states what
  the store knows and asks only what it cannot. The `check-in` skill carries none of it.

  | # | Field | Prefill and ask |
  | --- | --- | --- |
  | 1 | Header | window, derived tier, catch-up or not, plan in force |
  | 2 | Sessions | every planned core session in the window: matched (workout, minutes, session RPE), trained-unlogged, cancelled or missed; asks a miss tag per miss and session RPE only where the sets carry none; the against-the-prescription read per session; optional sessions as a done streak |
  | 3 | Week kind | the closed week's kind, trained fraction, gate passes (`week.md`) |
  | 4 | Block | hard weeks against the ceiling, triggers fired with evidence refs, the proposal: `deload`, `light`, `none` or `skipped (<n> hard weeks)` |
  | 5 | Adherence | figure, weeks counted, state (`ok`, `watch`, `low`, `insufficient`) |
  | 6 | Dose | per muscle, delivered against the version's target, trailing four-ordinary-week mean |
  | 7 | Lifts | per the version's emphasis and priority lifts (`goals.md`, the check-in row of its per-emphasis table, ADR 0020): with priority lifts it leads with them, the top set's load and reps stated and how it moved and felt asked; on a `hypertrophy` version reps and RIR on the lines that moved, pump and soreness as a dose read; on `maintenance` whether the kept lifts held; e1RM rows compounds first |
  | 8 | Readiness | asked: `poor`, `ok`, `good` |
  | 9 | Sleep | nights in the window, short nights, Short-sleep week or not; asks for nights only where none are stored |
  | 10 | Weight and Phase | weigh-ins in the window, the 14-day average; asks when none stored. With an open Phase, the Phase line: kind, target rate, the 14-day trend against it and the `until` condition; `phase_trend_off` and `phase_condition_met` are raised here, not at the block boundary (`goals.md`, **What the Phase changes**) |
  | 11 | Activities | runs and conditioning in the window, quality count against the cap, any run spike |
  | 12 | Niggles | each open one with status and constraints; asks a status |
  | 13 | Follow-ups | those due; the deep tier lists every open one and asks a disposition each |
  | 14 | Notes | athlete notes in the window, verbatim |
  | 15 | Deep tier | misses by tag since the last deep row; open Observations to confirm or retire |

  The outside-plan codes `checkin open` reports are `week.md`'s list.
- **Week closure**, **due** (light and deep), **catch-up**: `week.md`. No stored flag, no title.
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
