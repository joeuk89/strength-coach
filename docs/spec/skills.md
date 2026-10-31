# Skills

A skill is the coaching half of one moment in the loop. The code owns the procedure (ADR 0002:
each verb is one transaction, self-described by `--help` and `coach schema`); the skill says what
to ask the athlete, what to judge and how to explain, and names the verbs it uses in no order.

Decided on wayfinder ticket [Shape of the thin skills](https://github.com/joeuk89/strength-coach/issues/18),
2026-10-27. The budgets answer the benchmark's target of under 8k instruction tokens per check-in
plus programming pass (`benchmark.md`); the old check-in and program-week skills alone were about
101k characters across seventeen files.

## The set

Four skills, all in the plugin (ADR 0007), none in the instance:

| Skill | Moment | When |
| --- | --- | --- |
| `check-in` | The weekly review | `status` says a check-in is due (`week.md`), or the athlete reports on the week |
| `plan-week` | The week's prescription | A check-in has closed a week, a light or constrained week is agreed, a midweek change is needed |
| `program` | Authoring or revising a program version | A new program, a block boundary swap, a sustained stall, a parked session promoted (detail: Program authoring). Its Judge answers `cadence_slow` and `cadence_fast` only with a move the flag lists (`may_schemes`, `may`, `never`); the switching table is engine code specified in `goals.md`, and the skill carries none of it (ADR 0020) |
| `onboard` | The first conversation | After `coach init`, or when no profile exists. Writes the profile (ADR 0009 sections), the first Goal and the Phase (`goal adopt`) on the athlete's yes, and designs no program: `program`'s own When covers the first version (decided on ticket [Worked program and onboard skills](https://github.com/joeuk89/strength-coach/issues/36), 2026-10-31) |

Dropped: `hevy-sync` (drift is a warning on the plan draft, resolved by override or overwrite, ADR
0011), `goals` (the Goal is a record written by `goal adopt` inside `onboard` and `program`, its
why in the profile prose, ADR 0014; what the check-in asks per emphasis is the card's, what
each skill judges and explains per emphasis is that skill's own Judge, and `goals.md` shows the
four together as a design view, ADR 0020), `setup`
(config and the Hevy key are `coach init`), `framework-sync` (`coach upgrade`), nutrition, recipes
and meal plans (ADR 0004).

Every skill is model-invoked from its description and also runs as `/<name>`. No skill names
another skill: each When covers its own trigger, including the one that follows a check-in, so the
core loop in one session is two skill loads, never one skill driving another.

## What a running agent reads

Four things, and nothing else (ADR 0020): the profile, the skill body, the envelopes (the card,
flags, dry runs, `coach progress`) and its own coaching knowledge. No research note, spec table or
reference file. Knowledge the engine owns arrives as typed fields on the flag or result that needs
it: a cadence signal carries the moves the next version may make, every flag carries its `rn`
citation, `coach schema --registry flags` lists every code with its citation. The agent's own
knowledge is expected; where it disagrees with an engine rule, the rule stands and the departure
is recorded with a reason.

## The template

One `SKILL.md` per skill, nothing else: no step files, no `reference/` the agent reads, no
pointer at a CLAUDE.md section. Six sections, in this order. A seventh is a design smell to argue
on the map, not add.

```markdown
---
name: <skill>
description: <the When: the moments that call for this skill, in coaching terms>
---

## Read first
<the one or two inputs the judgement needs, by glossary name: "the profile", "the card from
`coach checkin open`">

## Ask
<what the athlete is asked and what is stated for confirmation, in coaching terms, never field
names. The manner: one message, follow-ups only for a gap that blocks the next step>

## Judge
<the coaching questions this moment holds, each naming the flag code or card field that prompts
it and answered with a recorded reason. Not every code gets an entry; the schema is the list>

## Explain
<what the athlete should come away knowing. Every figure is quoted from an envelope or the
rendered draft, never retyped. Ends with the fixed line below>

The athlete sees what will be recorded and says yes before any verb records it.

## Verbs
<the verbs this skill uses, as a plain list in no order: for the contract test and so a new agent
knows which `--help` to read>
```

The closing line of Explain is the one procedural sentence a skill carries, the same in every
skill. It exists because `checkin record` and the profile edit are not Writing verbs, so no
permission prompt attaches to them and the code cannot enforce a conversational yes. `plan apply`
has its own prompt (ADR 0006), so no skill quotes an approval sentence.

## Never in a skill

The review checklist for any skill edit. Each item has a home elsewhere, named here so the edit
goes there instead.

| Never | Where it lives |
| --- | --- |
| Command order, "run X then Y", re-run instructions | The verb's transaction (ADR 0002) |
| Exit codes and what to do on each | The envelope's `error.code`; the CLI maps classes once |
| Flags, argument shapes, JSON or file shapes | `coach <verb> --help`, `coach schema` |
| Thresholds and numbers | Code or config with the `rn:` citation; the skill names the flag code |
| File paths | The generated CLAUDE.md names `profile.md` once; skills say "the profile" |
| Formatting rules, word ceilings, table layouts | The renderer; the compact summary |
| The approval sentence | The `plan apply` prompt (ADR 0006) |
| A rule the code already enforces, explained | Nowhere: the violation or warning says it |
| Another skill's name | Nowhere: each skill's description is its own trigger |
| Coaching principles shared across skills | The profile prose (preferences, voice, ADR 0009); otherwise each skill's own Judge |
| A table the skill would "cite" (switching rule, per-emphasis defaults) | The flag's params (`may_schemes`, `may`, `never`) and the adopt diff; the skill's own Judge in its own words (ADR 0020) |
| A research note, its claim or a pointer to one | The flag's `rn` field and `coach schema --registry flags`; a running agent reads no note (ADR 0020) |
| A glossary term's avoid-list word | The glossary term |

The generated CLAUDE.md carries no coaching content either: what the instance is, where the
profile is, that `coach status` opens a session and `coach --help` is the manual.

## The ad-hoc moment

A question outside the four moments ("why is my bench flat?" on a Wednesday) is not a skill. It
is answered from the profile and the read verbs (`coach status`, `coach progress`, `coach query`)
with nothing recorded. If the conversation turns into a change, `plan-week`'s own description (a
midweek change is needed) or `check-in`'s triggers it; an Observation waits for the next
check-in. The generated CLAUDE.md carries this as one line, which is procedure, not coaching
(`instance.md`). A fifth skill would have no Ask and no verbs beyond the read set.

## Budgets

Measured as characters divided by four, frontmatter included, the way `benchmark.md` counts
instruction tokens.

| Budget | Limit | Held by |
| --- | --- | --- |
| One skill | 1,500 tokens (about 6k characters, roughly 80 lines of prose) | One test per skill |
| Check-in plus plan pass | Under 8k: CLAUDE.md plus `check-in` plus `plan-week` | The benchmark script, re-run at each milestone |

The old caps were line counts (120 per `SKILL.md`, 150 per step file) and every file filled them.
A token budget with no sub-files leaves nowhere to grow sideways.

## Contract tests

Two, and nothing on wording:

1. **Verbs exist.** Every `coach <word>` token in a skill file, and every entry in its Verbs list,
   is a declared verb (the declarations also generate `--help` and `schema`, ADR 0002).
2. **Size.** Each skill is within its budget.

No test reads a sentence, including no lint for digits in prose. A threshold that creeps back in
is caught at review against the never-list, not by a test. The old suite's 178 call sites that
asserted skill or CLAUDE.md wording have no successor.

## Worked example: `check-in`

The reference for register and length. Under budget (about 2.5k characters). The card and its
fields are the check-in spec (`check-in.md`); the verb names follow the Verb set ticket and the
contract test holds them to it.

```markdown
---
name: check-in
description: The weekly review. Use when a check-in is due, when the athlete reports on their
  week, or when the newest check-in is more than a week old. Also /check-in.
---

## Read first
The profile, once. The card from `coach checkin open`: it states what the store already knows
and asks only what it cannot. Never change its figures or the order of its fields.

## Ask
Send the card as one message in the coach's voice; the athlete answers by number. A fact the log
already answers is stated for confirmation, not asked. Follow up only for a gap that blocks the
read or next week's plan. On a deep tier, settle every open niggle and follow-up with the athlete
rather than carrying them.

## Judge
- **Readiness.** The athlete's own words and their Hevy set notes are the signal, and the card's
  Readiness field records it; the RPE drift trigger on the card matters on the compound lifts,
  elsewhere a rising RPE is a note.
- **Misses.** A tag per missed core session. Pattern over blame: three weeks of `time` misses is a
  schedule problem for the plan, not a willpower problem.
- **Sleep and weight.** Read the trend, not the week. A short-sleep week (`short_sleep_week`)
  shapes next week's dose; one bad night does not.
- **Phase.** When the card says the until condition is met or the trend is off, propose
  closing or keeping it with the athlete; a new Phase opens in the record.
- **Niggles.** Reported, aggravated, easing, resolved. Escalate to a professional when pain
  changes gait, sleep or daily tasks; never diagnose.
- **Block and tier.** When the card's Block line carries a proposal or the derived tier is deep,
  propose and let the athlete adopt, decline with a reason or defer. When adherence is `low`,
  present a smaller schedule with the same weekly hard sets per muscle. The rotation position is
  confirmed, not asked.
- **Patterns.** Raise an Observation when something has held for several weeks; retire one that
  stopped holding. Cite the exposures or notes it rests on.

## Explain
The read is one or two sentences on the week, then what the tables cannot say. Lead with a win
when there is one. Quote every number from the card or the rendered record; never retype a load.
Name each decision and its reason in plain words. Say what next week will feel like, not what
it will contain; the plan does that.

The athlete sees what will be recorded and says yes before any verb records it.

## Verbs
`coach status`, `coach checkin open`, `coach checkin record`
```

## Worked example: `program`

The heaviest judgement in the set, under budget (about 4.1k characters). Decided on wayfinder
ticket [Worked program and onboard skills](https://github.com/joeuk89/strength-coach/issues/36),
2026-10-31. It names no weekday, coach or gym: a fixed session is any session the athlete does
not control, and "the PT Tuesday" is profile prose. Design-level coverage (every pattern, each
muscle twice) is this Judge's and not a code check: `muscle_no_hard_sets` already catches what
a missing hinge or row looks like in muscle terms, and a carry has no muscle of its own. A
program that ships without a hinge while the muscle check stays quiet is the evidence to add
one. The phase judgement reads age and height from the profile and applies no formula, so
neither returns to `[athlete]` (`instance.md`).

```markdown
---
name: program
description: Authoring or revising a program version. Use for the first program once the
  profile and Goal exist, at a block boundary, after a cadence signal or a sustained stall,
  when a swap has persisted, when a parked session is promoted, or when the athlete's days,
  kit or fixed sessions change. Also /program.
---

## Read first
The profile, once. For a revision, the progress report from `coach progress` and the current
version from `coach program show --draft`. For a first program, the imported history and any
routines in the mirror, read as what the athlete has done, never as what they should do next.

## Ask
State for confirmation what is already known: the days and minutes, each location and its kit,
and every session the athlete does not control (coach-led, a sport, a class) with its day and
what it trains. Ask only what is missing: the lifts they want to feel first, exercises they
refuse or love, and for a revision what the last block taught them that the report cannot show.
One message; follow up only for a gap that blocks the design.

## Judge
- **The split.** Fit the week to the days the athlete has, never the reverse. Each muscle
  twice across a rotation week where the days allow, once with a reason where they do not. A
  fixed session covers what it covers, its estimated sets count, and the designed sessions fill
  around it: never the same muscles hard the day after. Fewer sessions done beats more sessions
  missed; under `low` adherence design the smaller week with the same hard sets per muscle.
- **Coverage.** Every pattern in the rotation. The hinge and a carry go in on purpose because
  they are dropped first; `muscle_no_hard_sets` sees a muscle, not a pattern.
- **Order and time.** Priority lifts first (`priority_lift_not_first`), the heaviest work while
  fresh, accessories last and the first cut when `session_over_minutes` fires. Superset small
  lifts to buy time, never the compounds.
- **Scheme, RPE and rest per line.** A top set and back-offs on a load-bearing priority lift,
  double progression elsewhere, a ladder while a lift is assisted. A coarse rack, a new lift or
  a technique lift stays on reps. `scheme_off_emphasis` marks each departure; acknowledge it
  with the reason or change the line.
- **Dose.** The filled targets open a block, they do not cap it. Raise a muscle the report shows
  behind and under target; leave what is growing alone. A deficit keeps the dose, a surplus can
  carry more; `dose_off_band` names the departure. An older athlete, or one who recovers slowly,
  earns the shorter block and the fuller deload, not a smaller dose.
- **Signals.** Answer `cadence_slow` and `cadence_fast` only with a move the flag lists, the
  Decision citing the flag. A stalled double-progression line wants sets, a swap or a new rep
  range, never a new scheme. RPE rising everywhere is fatigue for the deload policy; on one
  line it is technique or a niggle.
- **Emphasis and Phase.** The Goal's kind unless this block serves it better another way
  (`emphasis_off_goal`): maintenance when life asks for less, a strength block when a milestone
  is close. Re-read the Phase at every boundary against the trend the report shows and what the
  athlete says about their body; a new Phase travels in the Goal draft.
- **Kind.** A swap, a scheme change or a session changed inside the same split is an `amend`.
  A new split, emphasis or Phase is a `redesign`; one mid-block is acknowledged with why the
  block cannot finish (`block_open_at_redesign`).

## Explain
Walk the athlete through the week as they will live it, session by session, then the rules
that move it week to week. Say why each exercise is there and what would earn a swap. Quote
every load, set count and filled default from the adopt dry run; never retype one. For a
revision, lead with what the report says changed and what this version does about it.

The athlete sees what will be recorded and says yes before any verb records it.

## Verbs
`coach status`, `coach progress`, `coach program show`, `coach program adopt`,
`coach goal adopt`, `coach query`, `coach schema`
```

## Worked example: `onboard`

Under budget (about 3.3k characters). It writes the profile, the Goal and the Phase and stops;
the first program is `program`'s moment, so the first conversation is two skill loads like the
core loop. `cutover.md` step 3 splits the same way. A priority lift is unbounded in number and
the Judge says what each costs instead of capping them.

```markdown
---
name: onboard
description: The first conversation with an athlete. Use after `coach init`, when no profile
  exists, or when the athlete wants to start over on who they are and what they train for.
  Writes the profile, the Goal and the Phase; the program is the next moment. Also /onboard.
---

## Read first
`coach status`, for what init recorded and whether a history was imported. With a history, the
exposures and weigh-ins from `coach query`, as evidence of where the athlete is today.

## Ask
One conversation in the coach's voice, in this order because each answer shapes the next: who
they are and how they got here; what they want and why, in their words, until the kind of goal
is plain (bigger, stronger, or both with named lifts); which lifts matter most and any number
that would mean something to them; how their body is (age, height, injuries, limits, and weight
if they volunteer it); the week as it stands (the days and minutes already recorded, stated for
confirmation; the sessions they do not control; where they train and with what kit); and how
they want to be coached (voice, how much a week may change, what a bad night does to a
session). A fact the history answers, what they lift, how often, their bodyweight, is stated
for confirmation, never asked.

## Judge
- **Goal kind.** Strength when the athlete names numbers on lifts; hypertrophy when they
  describe a look; both is hypertrophy with priority lifts. Maintenance is never a goal.
- **Priority lifts.** Any number, each one the athlete can train most weeks on the kit they
  have. Say what each costs before they name it: a strength scheme, its own weekly dose, first
  place in its session, a test single every light week, the first question at every check-in. A
  lift possible only at a second location is a milestone, not a priority.
- **Milestones.** Each measurable on one lift with no date; a dated target waits for the first
  check-in as a follow-up. Set them from the history where there is one, from the athlete's
  words where not, and never from a formula.
- **Phase.** Deficit when the athlete wants to be leaner and the trend is flat or rising;
  surplus when they want to be bigger, are lean by their own account and the trend is flat;
  maintenance when unsure, in the first weeks of coaching, or when weight is not the point,
  until coach's call. The rate is the kind's default; a bodyweight condition only when the
  athlete has one. Calories are the athlete's own tool, never this conversation.
- **Prose or record.** A current pain or limit is a niggle with a constraint at the first
  check-in; a lift the athlete refuses is a coaching preference; a fixed session is part of why
  the week has its shape. Nothing goes in the profile that a record holds.
- **Done.** Onboarding ends when the profile, Goal and Phase are written. It designs no program.

## Explain
Read the profile back to the athlete, in their words and yours: who, the goal and why, the
week's shape and why it has it, limits, how they want to be coached, history. Then the Goal and
Phase as the draft states them. Say what changes each: the Goal when the aim changes, the
profile when they say so, the Phase at a check-in or a block boundary.

The athlete sees what will be recorded and says yes before any verb records it.

## Verbs
`coach status`, `coach query`, `coach goal adopt`
```
