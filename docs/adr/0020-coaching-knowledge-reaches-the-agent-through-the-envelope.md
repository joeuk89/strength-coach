---
status: accepted
date: 2026-10-31
---

# Coaching knowledge reaches the agent through the envelope; a running agent reads no document but the profile

A running agent reads four things: the profile, the skill body, the envelopes (the card, flags,
dry runs, `progress`) and its own coaching knowledge. It never reads a research note, a spec
table or a reference file. Coaching knowledge the engine owns (thresholds, the permitted
responses to a signal, the citation behind a rule) reaches the agent only as typed fields on the
flag or verb result that needs it. The agent's own knowledge is expected and legitimate; where it
disagrees with an engine rule, the rule stands and the departure is recorded (an Acknowledgement,
an override `because`, an `against_research` Decision citing the flag's `rn`).

Decided on wayfinder ticket
[Where coaching knowledge lives at runtime](https://github.com/joeuk89/strength-coach/issues/35).
The spec had the `program` skill "citing" the switching table in `goals.md` and the four skills
citing its per-emphasis table, while `skills.md` forbids reference reads, the plugin ships only
skills and hooks and the instance ships no docs: the tables existed only where no running agent
could read them.

## Considered options

- **Typed fields in the envelope (chosen).** A coaching table the skills depend on becomes an
  engine table with its `rn:` citations, and the flag that prompts the moment carries the row
  (`cadence_slow` carries `may_schemes`, `may`, `never`). Judgement and voice stay in the skill.
  Costs tens of tokens per flag and keeps the 8k budget and the never-list intact.
- **Ship the notes and tables with the plugin and allow a cited reference read.** Rejected: the
  old system's measured 26.8k tokens of sub-file and reference reads per session is exactly this
  (`benchmark.md`), and a read the skill may make is a read it will make every time.
- **Spend skill budget on the tables and raise the budget.** Rejected: the switching table
  alone is a third of a skill, it would be copied into two skills, and a number in prose is the
  drift the guardrails name.

## Consequences

- The scheme-switching rule is a table in `core`, `(signal, scheme) → may_schemes, may, never`,
  specified in `goals.md` the way `schema.md` specifies `schema.sql`. The cadence flags carry
  their row in `params`. One adopt warning, `scheme_change_off_signal`, holds the rule that a
  scheme changes only when its cadence has run out.
- The per-emphasis table in `goals.md` is a design view: the "asks" row is the card builder's
  (the check-in card is emphasis-aware), the "judges" and "explains" rows are each skill's own
  Judge, in its own words, inside its budget. Nothing cites the table at runtime.
- The Flag shape gains an optional top-level `rn` (`rn:<note> §<n>`), outside `params` and the
  hash, filled from the constant that raised it; the flag registry carries the column and
  `coach schema --registry flags` shows it. Rendered pages link it to the note at the pinned
  engine tag on GitHub.
- Research notes live in the engine repo only: not package data, not in the plugin, not in the
  instance. One test in the repo resolves every `rn:` ref in code and the registry. ADR 0004's
  "parsed at runtime" is amended to this.
- The ad-hoc moment (a question outside the four skills, midweek) is not a skill: it is answered
  from the profile and the read verbs with nothing recorded, and the generated CLAUDE.md says so
  in one line. A change that follows it is `plan-week`'s or `check-in`'s own trigger.
- A new table a skill would want to "cite" is the same smell as a seventh skill section: it is
  argued on the map and lands as a flag field or a skill sentence, never as a read.
