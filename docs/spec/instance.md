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
├── export/                    written by publish, read only to rebuild a missing store (ADR 0001, schema.md)
│   ├── manifest.json          schema version, engine version, row counts (schema.md)
│   └── <table>.jsonl          one file per table, rows sorted by primary key (schema.md)
├── hevy/
│   └── writes.jsonl           append-only write audit (ADR 0011)
├── kit/                       athlete-authored, one pair of files per plate-pool location (ADR 0021)
│   ├── <name>.json            the inventory, in plate-pool's inventory.schema.json
│   └── <name>.achievable.json the tables `npx plate-pool achievable` emits from it, with its header
└── pages/                     written by publish (ADR 0012)
```

Nothing else. No `data/`, `check-ins/`, `routine/`, `reference/`, `research/`, `docs/` or
`.agent/`: check-in records are pages, the program is in the store, research notes live in the
engine repo and are read by no running agent (ADR 0004, ADR 0020).

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
presence of the `[hevy]` table in `coach.toml`, which is committed: a table with no key stops
`import`, `plan apply` and every verb that pulls first with exit 5, `error.code = hevy_key_missing` (`verbs.md`), so a second
machine that clones without `.env` fails loudly instead of planning without Hevy. No `enabled`
flag, no `.env.example`. Without the table, `hevy_template_missing` is never raised and a
`[[workout]]` record is the only way a workout enters the store (ADR 0006).

## coach.toml

Four tables. An unknown table or key, or an `implements` value naming no implement of its
location, stops every verb with exit 5, `error.code = config_unknown_key`, naming the key
(`verbs.md`): a setup refusal, not a flag.

| Table | Owner | Holds |
| --- | --- | --- |
| `[engine]` | engine | `version`, the engine pin (ADR 0007) |
| `[athlete]` | athlete | the facts rules read (ADR 0009): `units`, `bodyweight_units`, `week_starts`, `timezone`, `available_days`, `session_minutes`, `checkin_cadence_days`; each has a reader, below |
| `[hevy]` | athlete | present when Hevy is used; empty in v1 |
| `[location.<name>]` | athlete | `kind = "plate-pool"` with `kit = "<name>"` (naming `kit/<name>.json` and `kit/<name>.achievable.json`) and one `[location.<name>.implement.<id>]` table per inventory implement id `implements` names, its `hardware` (a hardware id or `none`) and, on a handle, `single` (default false, a pair) choosing which tables apply ("Kit"), or `kind = "grid"` with one `[location.<name>.implement.<implement>]` table per implement; either kind carries `implements`, the map from equipment kind to implement ("Locations", ADR 0008, ADR 0021). No URL: the engine fetches nothing |

No lifting goal (the Goal is a record and the emphasis is on the Program version, ADR 0014), no
`experience` (level is derived per lift), no caps, no thresholds, no feature toggles (ADR 0004).
A number that is a rule is an engine constant; one that is an agreement is a Decision (ADR 0013).

Every `[athlete]` fact has a rule that reads it; a fact with no reader is profile prose, not
config. Birth date and height are prose for that reason: the `onboard` skill writes them in the
profile's facts section and the coach reads them there; the phase judgement reads them with no
formula, so no code rule needs either (`skills.md`, the `onboard` worked example).

| Fact | Shape | Reader |
| --- | --- | --- |
| `units`, `bodyweight_units` | `kg` or `lb` | every load and weigh-in |
| `week_starts`, `timezone` | weekday (`monday` or `mon`, any case; the full name is stored); IANA name | the week, the closed week and every date; `cli` builds the Clock every service and the Hevy client receive from `timezone` (ADR 0019) |
| `available_days` | list of weekdays, each as `week_starts` takes it; the full names are stored | `adopt`: a scheduled weekday outside the list is `session_on_unavailable_day` (`program.md`); the `program` skill designs the split around it |
| `session_minutes` | integer | `adopt` fills it into a lifting session that states no `minutes`, so `session_over_minutes` reads it (`program.md`) |
| `checkin_cadence_days` | integer, default 7 | the light-tier due rule (`week.md`) |

## coach init

Runs in a terminal, interactively. It asks for the `[athlete]` facts above with defaults where
one exists (timezone from the machine, cadence 7 days), whether Hevy is used and if so the key,
and nothing about kit (the `kit` skill writes every location, ADR 0021). Every answer has a flag so personas,
fixtures and the migration run it non-interactively; `--defaults` takes every default. It
refuses if any engine-owned path already exists and otherwise writes beside whatever is there.
It writes the tree above with an empty store, `profile.md` absent (the `onboard` skill writes
it), `kit/` empty, and a `[location.<name>]` example of each kind, commented. It runs `git init` if the directory is
not a repo and, after a final TTY confirmation listing the files, makes one commit,
`coach init vX.Y.Z`; it is a Writing verb (git) like `upgrade`, with `--dry-run` printing the
tree it would write. On a `.dev` build it refuses without `--pin X.Y.Z`, the release the
instance will run, so `[engine]` never holds a `.dev` version (ADR 0007, `verbs.md`). Creating
the remote repository and pushing are the human's job and are printed as the next step.
With Hevy on and a key set, `init` then runs the full pull into the store (`verbs.md`, "The
pull"); Hevy unreachable exits 4 with the tree written and committed, and with no key yet the
next pulling verb runs it.

## Locations

Every location carries `implements`, an inline table from equipment kind (`coach schema
--registry equipment-kinds`) to the name of one implement the location has. Adopt reads it for
every line whose load mode is `total`, `per_hand_x2` or `single_implement`: a kind the session's
location does not map is `equipment_unsupplied` on the line, and mapping it here is the clearing
path (`program.md`, `validation.md`). Lines under `bodyweight`, `assisted`, `band`, `duration` or
`distance` carry no rack load and read no implement. An `implements` key outside the registry,
or a value naming no implement of the location, is the setup refusal `config_unknown_key` on
every verb: config is parsed whole before any verb runs.

At a plate-pool location a value names an implement of the kit tables, so the load step is that
implement's table. At a grid location a value names one of the location's own implement tables,
each either an increment rule or a listed rack (ADR 0008):

```toml
[location.gym]
kind = "grid"
implements = { barbell = "bar", dumbbell = "rack", machine = "stack", cable = "stack", bodyweight = "dip_belt" }

[location.gym.implement.bar]
increment = 2.5     # athlete units
base = 20           # the bare implement; optional, default 0
max = 180           # optional

[location.gym.implement.rack]
rack = [4, 6, 8, 10, 12.5, 15, 17.5, 20, 22.5, 25, 30, 35, 40]

[location.gym.implement.stack]
increment = 5

[location.gym.implement.dip_belt]
increment = 2.5
```

A grid implement has exactly one of `increment` (with optional `base` and `max`) or `rack`; the
rack of an `increment` implement is every multiple from `base` to `max`, or unbounded above when
`max` is absent. The `kit` skill writes this table for the athlete (`skills.md`).

## Kit

A plate-pool location's kit is two athlete-authored files (ADR 0021). `kit/<name>.json` is the
inventory in plate-pool's `inventory.schema.json` format 1, the contract between the repos. `kit/<name>.achievable.json`
is what `npx plate-pool achievable --inventory kit/<name>.json` emits: a header, `format` (the
document format the engine states it parses), `plate_pool` (the version that wrote it),
`inventory_sha256` and `name`, then the tables. The engine reads only the tables file, through `core/kit.py`
(ADR 0019); it never parses the inventory, runs Node or fetches. A verb that rounds hashes the
inventory first and stops with exit 5, `kit_tables_stale`, when the header disagrees (`verbs.md`).

```toml
[location.home]
kind = "plate-pool"
kit = "home"
implements = { barbell = "barbell", dumbbell = "dumbbell" }

[location.home.implement.barbell]
hardware = "collar-clamp"

[location.home.implement.dumbbell]
hardware = "screw-standard"
single = false
```

Each table names an `implement` (an inventory implement id), and carries `hardware` when the
implement has hardware options and `pair` on a handle. For each implement `implements` names, the
engine reads the one table whose `hardware` equals the location's choice and whose `pair` equals
`not single`. Hardware is required and never defaulted; plate-pool's `default` flag is not read.
A missing hardware choice where the tables carry `hardware`, a hardware id no table of that
implement has, a hardware choice where they carry none, and `single` where they carry no `pair`
each stop with `kit_tables_stale`, naming the implement and the ids on offer. Implements
`implements` does not name are ignored. A row's rack load is `total.<units>` and its loading
`loading.positions[].name` and `.plates`; nothing reads `uneven`, `smallest` or `ids`.

A routine page at a plate-pool location carries one set-up link,
`https://joeuk89.github.io/plate-pool/#inventory=<payload>`, where the payload is the inventory's
bytes compressed as raw deflate (no zlib header or trailer), base64url with `=` padding
stripped, in the fragment, never the query. Each loaded line carries a per-line link,
`https://joeuk89.github.io/plate-pool/?<id>=<load><unit>&<id>.hardware=<hardware id|none>&kit=<first 8 hex of inventory_sha256>`:
`<id>.single=` in place of `<id>=` for a handle rounded single, and `<id>.hardware=` only when
the location names a hardware choice for that implement.
The `kit` skill edits these files and runs the generator for the athlete (`skills.md`). A grid
location has no files: its kit is the `[location.<name>]` table and its implement tables alone.

## Generated CLAUDE.md

Under about forty lines, no coaching content (`docs/spec/skills.md`): what this directory is and
the engine version; `coach --help` and `coach schema` as the way to learn verbs; the profile
named once; the drafts convention named once; the one procedural line (the athlete says yes
before any verb records); one line for the ad-hoc moment (a question outside the skills is
read-only: `coach status`, `coach progress`, `coach query`; `docs/spec/skills.md`); where the
never-list's items live. Skills, hooks and permission rules
come from the plugin and `settings.json`, so it lists none of them.
