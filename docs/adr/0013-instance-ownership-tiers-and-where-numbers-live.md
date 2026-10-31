---
status: accepted
date: 2026-10-27
---

# An instance has three ownership tiers, and a number lives where its kind says: fact in config, rule in code, agreement as a Decision

Every path in an instance belongs to one of three tiers. **Athlete-authored**: `coach.toml`
outside `[engine]`, `profile.md`, `.env`, `.claude/settings.local.json` and additions to
`.gitignore`. **Engine-owned**: CLAUDE.md, `.claude/settings.json`, `README.md`, `pages/`,
`export/` and `[engine]` in `coach.toml`, regenerated wholesale by `upgrade` or `publish`, never
merged. **Append-only**: `hevy/writes.jsonl`. A hand edit to an engine-owned file is overwritten
at the next regeneration with no merge and no prompt beyond the verb's own ask; `status` has
already warned on the drift and the git diff of the regenerating commit shows what was lost.

A number has one of three homes, by what it is. A **fact** about the athlete, their kit or their
preferences lives in `coach.toml` (units, available days, session minutes, check-in cadence,
grid-kit increments; birth date and height are profile prose since no rule reads them, amended
2026-10-31). A **rule** the coach would apply to anyone is an engine constant
with its `rn:` citation beside it in code (return bands, the hard-week fractions, adherence floors
and lookback, light-week RPE ceiling, short-sleep hours, run-spike ratio, quality RPE;
`docs/spec/week.md`). An **agreement** between the
coach and this athlete (a weekly run cap, a Safety ceiling, "box squats only at the gym") is a
Decision in the store with its reason, never config. In v1 an instance cannot override an engine
constant: there is no `[thresholds]` table.

## Context

The old `config.toml` held about sixty keys. Twenty were coaching thresholds with `rn:` comments
(`spike_ratio`, `sleep_short_hours`, `quality_rpe_min`), beside athlete facts and per-athlete
caps on running and loads. Each threshold therefore lived in two places, the research note and
the config, and a rule that read config could be tuned without a reason being recorded anywhere.
The review's seventh principle is that each rule lives in one place with its citation. The old
instance also carried engine files that drifted when hand-edited (root problem 7), and its
generated files had no stated owner.

## Considered options

- **Three homes by kind, no instance override (chosen).** Each number has one owner. Changing a
  rule is an engine release, which the athlete can make because they are also the author; other
  athletes are not a v1 acceptance test (ADR 0007). An agreement carries its reason because a
  Decision requires one.
- **A `[thresholds]` table overriding any engine constant, with a `because` string.** Keeps
  per-athlete tuning without a release, but every rule then reads config first and the citation
  no longer sits with the value in force. Can be added later without moving anything; removing
  it later would mean rehoming every tuned value.
- **A curated subset of tunables in config, as the old instance had.** The line between tunable
  and constant has to be drawn and defended per threshold; the old set grew to twenty.
- **Merging hand edits to generated files on upgrade.** Three-way merge logic for files nobody
  should edit. The athlete's own Claude settings already have a home Claude Code merges for them,
  `settings.local.json`, and anything the athlete wants to tell the coach goes in the profile.

## Consequences

- `coach.toml` shrinks to four tables: `[engine]`, `[athlete]`, `[hevy]`, `[location.<name>]`
  (`docs/spec/instance.md`). The old `[cardio]` and `[caps]` tables split into engine constants
  and Decisions; the Override catalogue defines the Decision kinds that carry run caps and load
  ceilings.
- `status` warns on drift between an engine-owned file and what the engine would generate, for
  CLAUDE.md and `.claude/settings.json`. `pages/`, `README.md` and `export/` are rewritten at
  every publish, so drift there lasts one publish and is not checked (ADR 0012).
- No "local additions" block in the generated CLAUDE.md. The athlete speaks through the profile
  and `settings.local.json`.
- A threshold found in config, prose or a skill is a defect; the home for it is a constant with
  its citation, and the test is on the behaviour at the boundary, never the sentence
  (`docs/spec/skills.md`).
