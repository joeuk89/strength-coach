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
| `readiness` | The athlete's reported readiness, `poor`, `ok` or `good`, asked before the card and passed to `checkin open --readiness`; `checkin record` stores it. The one typed input the fatigue triggers need (`week.md`); null when the athlete gave none |
| `read` | The coach's read, prose, inserted verbatim wherever it is shown |
| `status` | `current` or `superseded` (see Correcting) |

Nothing else. Adherence, week kind, block count, e1RMs, triggers and the hard-week count are
views (`week.md`). A declined ceiling or a deferred deep review decided at the check-in is a
Decision row carrying the check-in reference; a light week taken is the `light_week` override on
the next WeekPlan, and the Block closes by the derived week kind (`week.md`).

Catch-up is not stored: a check-in whose window is longer than 10 days is a catch-up by
definition, and the deep tier is deferred to the next check-in by the same test (`week.md`).
`checkin open --tier deep` is honoured on a catch-up all the same: the flag only ever raises the
tier, so a coach who wants the deep pass now gets it, and the row records `deep`.

## The sourced records

Every record entered during a check-in carries a `check_in` reference to the row. Where each
answer lands:

| Answer | Record |
| --- | --- |
| Missed core session, with its reason tag | Annotation of kind `miss_tag` on the planned session; the tag is its `because`, one of the seven reasons (`schema.md`). Miss stays derived; only the tag is stored |
| Planned session called off on purpose, not a miss (a rest day agreed, a session the plan should not have held) | Annotation of kind `cancelled` on the planned session; it leaves both of `week.md`'s denominators |
| Coach-led session done | Normally nothing: the Hevy workout already fulfils it (see Matching). A hand-entered Workout with no sets, with minutes and session RPE, only when Hevy has nothing for that day |
| Trained but not logged | Annotation of kind `trained_unlogged` on the planned session |
| Sleep | Sleep night rows, source `check_in`. A period mean is not a night and is stored nowhere; the read may quote it |
| Weight | Weigh-in, source `check_in` |
| Niggle reported, aggravated, easing, resolved | Niggle status event |
| Follow-up disposition | Follow-up event: `kept` (the due date stands, or is set for the first time: the raising event is a `kept`), `deferred` (the due date moves later), `resolved` or `dropped`. A deep check-in gives every open one a disposition |
| Free note from the athlete | Athlete note: date, text verbatim, optional `about` reference (planned session, exercise, niggle, follow-up). Never classified by code |
| A pattern the coach has noticed, or one that stopped holding | Observation raised or retired (ADR 0009) |
| Phase opened, or the open one closed | Phase row (`goals.md`): the file's `[phase]` table, `kind`, `rate_pct_bw_per_week`, `until` and the reason, or `[phase] close = true` with the reason; the Check-in row is the `opened` or `closed` reference |
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
2. The next plan Draft carries every note since the last approved WeekPlan in its `[[note]]`
   array, verbatim with `about`, and `plan draft`'s summary repeats them as `notes[]`
   (`verbs.md`, `overrides.md`); a note with an `about` reference is also placed beside that
   line, session or niggle in the Draft.
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
(`status = superseded`, the supersede write of `schema.md`). Records sourced from the superseded
row stay unless the new file withdraws them: annotations by a withdrawing annotation, niggle and
follow-up events by a later event, a weigh-in, sleep night or status span by a row that
`withdraws` it. A mistyped reading is corrected by withdrawing it and entering the right one in
the same file; a second live reading for one date and source is the violation
`reading_duplicate`. No edit in place, no delete.

## Views

All of these are pure functions of the store at a date and are never stored:

- **The card**: the fields below in this order, inapplicable fields dropped; prefill states what
  the store knows and asks only what it cannot. The `check-in` skill carries none of it.

  | # | Field | Prefill and ask |
  | --- | --- | --- |
  | 1 | Header | window, derived tier, catch-up or not, plan in force |
  | 2 | Sessions | every planned core session in the window: matched (workout, minutes, session RPE), trained-unlogged, cancelled or missed; asks a miss tag per miss and session RPE only where the sets carry none; the against-the-prescription read per session; optional sessions as a done streak |
  | 3 | Week kind | the closed week's kind, trained fraction, gate passes (`week.md`) |
  | 4 | Block | hard weeks against the ceiling, triggers fired with evidence refs, the proposal: a light week with the proposed shape (`week.md`), `none` or `skipped (<n> hard weeks)` |
  | 5 | Adherence | figure, weeks counted, state (`ok`, `watch`, `low`, `insufficient`) |
  | 6 | Dose | per muscle and per priority lift (its counted variants included, `week.md`), delivered against the version's target, trailing four-ordinary-week mean |
  | 7 | Lifts | per the version's emphasis and priority lifts (`goals.md`, the check-in row of its per-emphasis table, ADR 0020): with priority lifts it leads with them, the top set's load and reps stated and how it moved and felt asked; on a `hypertrophy` version reps and RIR on the lines that moved, pump and soreness as a dose read; on `maintenance` whether the kept lifts held; e1RM rows compounds first |
  | 7b | Ladders | every `exercise_ladder` line (ADR 0023): its session, the standing rung (index and exercise), the run of exposures toward the rung's criterion since the rung's start out of those it needs, `met` where `rung_met` or `ladder_top` stands, `held` where that flag is left as the approval prompt leaves it (an acknowledgement on the newest WeekPlan up to this week, or a `leave_warning` Decision in force), the next rung's exercise, and the labels of the standing and next rungs (`rung <n> · [<exercise name> · ]<dose>[ · <load>][ · <cues>]`, ADR 0025; the name only when the rung's exercise differs from the standing rung's); asks only on a `manual` rung with a rung above it, "ready for the next rung?". A yes is a `ladder_rung` Decision in the check-in's record file |
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
