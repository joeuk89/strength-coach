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
| `check-in` | The weekly review | A check-in is due, the athlete reports on the week, or the newest check-in is older than a week |
| `plan-week` | The week's prescription | A check-in has closed a week, a light or constrained week is agreed, a midweek change is needed |
| `program` | Authoring or revising a program version | A new program, a block boundary swap, a sustained stall, a parked session promoted (detail: Program authoring). Its Judge keys `cadence_slow` and `cadence_fast` to **Response to a cadence signal** in `goals.md` and carries no switching rule of its own |
| `onboard` | The first conversation | After `coach init`, or when no profile exists. Writes the profile (ADR 0009 sections) on the athlete's yes and nothing else |

Dropped: `hevy-sync` (drift is a warning on the plan draft, resolved by override or overwrite, ADR
0011), `goals` (the Goal is a record written by `goal adopt` inside `onboard` and `program`, its
why in the profile prose, ADR 0014; what each skill asks, judges and explains per emphasis is one
table in `goals.md` that the skills cite), `setup`
(config and the Hevy key are `coach init`), `framework-sync` (`coach upgrade`), nutrition, recipes
and meal plans (ADR 0004).

Every skill is model-invoked from its description and also runs as `/<name>`. No skill names
another skill: each When covers its own trigger, including the one that follows a check-in, so the
core loop in one session is two skill loads, never one skill driving another.

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
| A glossary term's avoid-list word | The glossary term |

The generated CLAUDE.md carries no coaching content either: what the instance is, where the
profile is, that `coach status` opens a session and `coach --help` is the manual.

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

The reference for register and length. Under budget (about 2.2k characters). The card and its
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
- **Readiness.** The athlete's own words and their Hevy set notes are the signal; RPE drift
  (`rpe_drift`) matters on the compound lifts, elsewhere it is a note.
- **Misses.** A tag per missed core session. Pattern over blame: three weeks of `time` misses is a
  schedule problem for the plan, not a willpower problem.
- **Sleep and weight.** Read the trend, not the week. A short-sleep week (`short_sleep_week`)
  shapes next week's dose; one bad night does not.
- **Niggles.** Reported, aggravated, easing, resolved. Escalate to a professional when pain
  changes gait, sleep or daily tasks; never diagnose.
- **Block and tier.** When the card raises `block_ceiling` or `deep_due`, propose and let the
  athlete adopt, decline with a reason or defer. The rotation position is confirmed, not asked.
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
