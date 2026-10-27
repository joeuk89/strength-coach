---
status: accepted
date: 2026-10-26
amended: 2026-10-27 by ADR 0014 (the version field is `emphasis`, `experience` leaves `[athlete]`, milestones are typed on the Goal)
---

# The profile is prose a coach reads; what code or a check-in needs is a record

`profile.md` in the instance is the one authored document: who the athlete is, the goal and
phase in words, why the week has its shape, body and limits in words, coaching preferences, and
history before this system. Code never opens it. Everything the old file accreted on top of that
moves to where its owner already is: facts a rule reads go to `[athlete]` in `coach.toml`; the
coach's notes split into Observations (patterns, a ledger record) and coaching preferences
(prose); agreements that constrain a line or a load are override Decisions; the lifting goal is a
field of the Program version; recovery history is the Check-in's coach's read; equipment, niggles
and follow-ups are already records.

## Considered options

- **Prose plus records, split by who reads it (chosen).** A stranger coach reads the prose once.
  A rule reads typed config. A check-in cites and retires an Observation by id. Nothing is stated
  twice.
- **Keep `profile.md` as the agent-maintained status document.** This is the old shape: 265
  lines, a hand-kept "last reviewed" log, a recovery history that duplicated the check-ins, a food
  section parsed as data, and a schedule that disagreed with the program. Rejected.
- **Parse structured sections out of the prose.** Rejected: documents are output, never input,
  and prose-as-data was the single largest source of drift checks in the old system.
- **Coach observations as a Decision kind.** Rejected: a Decision is a choice with a reason and an
  outcome; an observation is a pattern with evidence and a lifecycle. Forcing one into the other
  loses the retire step.
- **Lifting goal in `[athlete]`.** Rejected: on the athlete it is a label. In the old instance
  `dose_intent` was null and the goal never reached the loop. On the Program version it is a
  contract the week is checked against, and it changes exactly when the program does.

## Consequences

- `coach.toml` `[athlete]` holds the facts rules read: units, birth date, height, session
  length caps, available days, week start, timezone. No lifting goal, and no `experience`
  (ADR 0014: level is a derived per-lift signal, never a stored fact).
- Program version carries `emphasis` (`hypertrophy`, `strength`, `maintenance`; named `goal`
  until ADR 0014 moved the athlete's Goal to its own record) and optional explicit
  per-muscle weekly dose targets. The emphasis sets the default dose target when none is given
  (hypertrophy: 10 hard sets per primary muscle of core lifts, rising toward 20 with experience,
  rn:minimum-effective-dose; maintenance: about a third; strength: no default, targets must be
  agreed) and the dose rule warns on a week under or over it. Powerbuilding is `hypertrophy` plus
  strength schemes on the chosen lifts, stated line by line; ADR 0014 makes those lifts the
  Goal's priority lifts and has adopt fill the strength scheme on them. How goals reach the
  agent's judgement and the other formulas is ADR 0014 and `docs/spec/goals.md`.
- Observation is a ledger record: text, evidence refs, the Check-in that raised it, the Check-in
  and reason that retired it. Observations are raised and retired only inside a `checkin record`
  file; the athlete's yes to the record is the confirmation. No `observation` verb.
- The old Coach's notes split: patterns (drift adds intensity, PT sessions go under-logged) become
  Observations; agreements that constrain a line or a load (dumbbell curls not barbell, box squats
  on the PT day only) become override Decisions with no until date, defined by the Override
  catalogue; agreements about how to coach (a bad night moves the session, waist is a monthly ask)
  are coaching preferences in the prose.
- `profile.md` carries no schedule, no recovery history, no status log, no front matter, no
  rendered regions. The agent changes it only on the athlete's yes in conversation; `publish`
  commits it. It is read once per session that makes a coaching judgement, by the check-in and
  plan-draft skills, and named in the generated CLAUDE.md; `coach status` never includes it.
- One rendered athlete page composes the prose verbatim with sections generated from the store:
  athlete facts, equipment by location, open niggles with constraints, open follow-ups, active
  observations, standing override Decisions, the last three check-in reads. It lives at
  `pages/athlete.md` (ADR 0012).
- A dated strength milestone is a Follow-up. An undated one was prose here; ADR 0014 makes it a
  typed Milestone on the Goal so distance and date reached can be derived.
