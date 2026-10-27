---
status: accepted
date: 2026-10-27
---

# Sessions outside the rotation are Sessions by kind and cadence; rehab is carried by the niggle

Conditioning on top of the lifting week, a daily practice such as dead hangs, and a short rehab
routine tied to a niggle are all Sessions. Kind (conditioning, practice) and the slot's cadence
(standing, daily) say what they are and how often they are expected; tier says whether a week is
judged on them. There is no add-on or practice noun. A rehab session is the one Session that lives
outside a program version: the niggle carries it, plans it while open and retires it on resolve.
A session's on or off state never lives on the immutable program version: a one-week drop is a
WeekPlan override, a longer park or resume is a Decision.

## Considered options

- **Sessions by kind and cadence, rehab on the niggle (chosen).** One noun, one planning,
  matching and Hevy path. The rehab lifecycle is exactly the niggle's, which already owns the load
  constraints that go with it.
- **A separate add-on or practice noun.** Its own planning, matching and projection code for
  behaviour the Session already has.
- **Rehab authored into the program version, parked and resumed by Decisions.** Every later
  version carries dead rehab work and a swap needs a new version mid-block.
- **Rehab as an override Decision carrying a session body.** Hides a template inside a ledger
  record.
- **Status on the session, as the old program had.** Parking would need a new version, so in
  practice the version would be edited in place.

## What each kind's workout yields

- A workout matched to a lifting or rehab session yields Exposures: progression, e1RM and hard
  sets by the one rule (a working set above RPE 5). Rehab sets count only when logged above it.
- A conditioning workout yields an Activity (kind conditioning, quality, RPE from the log or 7)
  and no Exposures, so it enters concurrent-training spacing and never the muscle balance.
- A practice workout yields a match and nothing else. A daily dead hang never feeds the dead-hang
  line's progression or the balance, even when the same exercise sits in a lifting session.

## Counting

- The hard-week gate reads lifting sessions only. Conditioning, practice and rehab never make a
  week hard and never fail it.
- Adherence counts core-tier planned sessions of any kind. A practice is always optional; a rehab
  session defaults to optional. Their done-counts show in the check-in as a streak the coach
  reads.
- A light week's RPE ceiling applies to lifting and rehab lines. Each conditioning planned session
  in a light week is warned; a practice carries no RPE and is untouched.

## Prescription and the drop rule

- `prescribe` covers every kind. A conditioning session carries its scheme at session level
  (density minutes or rounds with step, cap and decay) and derives this week's dose from its last
  matched Activity. Practice and rehab carry a hold scheme: the authored numbers stand until a
  line override or the physio's new numbers. All freeze into the WeekPlan at approval (ADR 0003).
- The old drop rule (an optional conditioning session removed on sleep debt, a status day or a
  quality stack) becomes warnings on the planned session. The agent drops it with a WeekPlan
  override, drop planned session, because fatigue or schedule. Core and optional get the same
  warning; tier decides only whether the drop is a miss.

## Lifecycle

- A one-week drop: WeekPlan override. A park or resume for longer: an override Decision with no
  until date; the sessions in force on a date are the version's sessions minus those parked.
- Promotion of a conditioning session to core is a tier change, so a new program version through
  `adopt`.
- A rehab session is raised on the niggle and retires when the niggle resolves; a chronic niggle
  keeps it. By default it sits beside the rotation; to replace a rotation session, park that
  session with a Decision.
- None of these is a new gated write. They are store writes on the athlete's yes, recorded as the
  Decision or niggle event; their Hevy effect lands on the next `plan apply`, whose dry run shows
  the routine create or retire (ADR 0006).

## Hevy

- Every session with a Hevy template gets a routine. Rotation sessions project into the program's
  folder; standing, daily and rehab sessions into a second fixed folder, so the app's home shows
  the week's lifting first.
- Routines are created only on `plan apply`. A parked or retired session's routine is retired on
  the next push (Hevy's API has no DELETE; see ADR 0011): routines are projections and only
  workout history is protected.
- Practice workouts match the practice session by routine id and import as ordinary append-only
  Workouts.

## Consequences

- The schema has no session status column and no add-on table; the niggle row links to its rehab
  session.
- The override catalogue (wayfinder #19) carries drop planned session on the WeekPlan and park
  and resume session as Decision kinds.
- The Hevy integration (wayfinder #17) carries the second folder and routine retire (ADR 0011).
- Program authoring (wayfinder #22) carries session-level conditioning schemes and the hold scheme.
- Regression tests: a conditioning workout produces no Exposure; a practice workout produces no
  Exposure for an exercise that also sits in a lifting session; a parked session is absent from
  the plan without a new program version; a rehab session leaves the plan when its niggle resolves.
