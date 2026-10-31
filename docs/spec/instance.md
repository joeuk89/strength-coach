# Instance

One athlete's directory: config, profile, the store and its committed export, and nothing of the
engine (ADR 0007). Decided on wayfinder ticket
[Instance repo layout](https://github.com/joeuk89/strength-coach/issues/20), 2026-10-27.
Ownership tiers and where numbers live are ADR 0013; this page is the tables.

## The tree

```
<instance>/
├── coach.toml                 athlete-authored; [engine] section engine-owned
├── profile.md                 athlete prose, written by onboard on the athlete's yes (ADR 0009)
├── .env                       HEVY_API_KEY=…  gitignored
├── .gitignore                 written once by init; the athlete may extend it
├── CLAUDE.md                  generated, engine-owned
├── README.md                  written by publish (ADR 0012)
├── .claude/
│   ├── settings.json          generated, engine-owned (ADR 0007)
│   └── settings.local.json    the athlete's own Claude Code settings, gitignored
├── .coach/                    gitignored, the whole directory
│   ├── coach.db               the store (ADR 0001)
│   └── drafts/                Drafts: agent-written verb inputs
├── export/                    written by publish, read by import (ADR 0001)
│   ├── manifest.json          schema version, engine version, row counts (schema.md)
│   └── <table>.jsonl          one file per table, rows sorted by primary key (schema.md)
├── hevy/
│   └── writes.jsonl           append-only write audit (ADR 0011)
└── pages/                     written by publish (ADR 0012)
```

Nothing else. No `data/`, `check-ins/`, `routine/`, `reference/`, `research/`, `docs/` or
`.agent/`: check-in records are pages, the program is in the store, research notes live in the
engine (ADR 0004).

`.gitignore` as written by `init`:

```
.coach/
.env
.claude/settings.local.json
```

## Drafts

Every verb that takes a document (a plan, a check-in record, a program text form, a manual
workout) takes the path of a file the agent wrote first (ADR 0002). The file is a **Draft**: TOML,
by convention at `.coach/drafts/<date>-<kind>.toml`, gitignored, read by nothing after the verb
consumes it, never pruned. The verb accepts any path; the convention is only where the agent puts
them and is named once in the generated CLAUDE.md. TOML because `tomllib` is stdlib, multi-line
strings carry the coach's read, and it matches `coach.toml`. The athlete reviews the rendered dry
run, not the file (ADR 0006), so the directory need not be visible.

## Secrets and the Hevy switch

`.env` at the instance root holds exactly `HEVY_API_KEY`, gitignored, written by `init` when a
key is given; the environment variable overrides it (ADR 0011). Whether Hevy is used is the
presence of the `[hevy]` table in `coach.toml`, which is committed: a table with no key is a
violation on `import` and `plan apply`, so a second machine that clones without `.env` fails
loudly instead of planning without Hevy. No `enabled` flag, no `.env.example`.

## coach.toml

Four tables. Unknown tables and keys are a violation on every verb.

| Table | Owner | Holds |
| --- | --- | --- |
| `[engine]` | engine | `version`, the engine pin (ADR 0007) |
| `[athlete]` | athlete | the facts rules read (ADR 0009): `units`, `bodyweight_units`, `week_starts`, `timezone`, `birth_date`, `height_cm`, `available_days`, `session_minutes`, plus `checkin_cadence_days` |
| `[hevy]` | athlete | present when Hevy is used; empty in v1 |
| `[location.<name>]` | athlete | `kind = "plate-pool"` with `url`, or `kind = "grid"` with increments and bar weights (ADR 0008) |

No lifting goal (the Goal is a record and the emphasis is on the Program version, ADR 0014), no
`experience` (level is derived per lift), no caps, no thresholds, no feature toggles (ADR 0004).
A number that is a rule is an engine constant; one that is an agreement is a Decision (ADR 0013).

## coach init

Runs in a terminal, interactively. It asks for the `[athlete]` facts above with defaults where
one exists (timezone from the machine, cadence 7 days), whether Hevy is used and if so the key,
and the home location source (default the plate-pool URL). Every answer has a flag so personas,
fixtures and the migration run it non-interactively; `--defaults` takes every default. It
refuses if any engine-owned path already exists and otherwise writes beside whatever is there.
It writes the tree above with an empty store, `profile.md` absent (the `onboard` skill writes
it), and the grid-location table as a commented example. It runs `git init` if the directory is
not a repo and, after a final TTY confirmation listing the files, makes one commit,
`coach init vX.Y.Z`; it is an asked verb like `upgrade`. Creating the remote repository and
pushing are the human's job and are printed as the next step.

## Generated CLAUDE.md

Under about forty lines, no coaching content (`docs/spec/skills.md`): what this directory is and
the engine version; `coach --help` and `coach schema` as the way to learn verbs; the profile
named once; the drafts convention named once; the one procedural line (the athlete says yes
before any verb records); where the never-list's items live. Skills, hooks and permission rules
come from the plugin and `settings.json`, so it lists none of them.
