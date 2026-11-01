# strength-coach

A strength coach that runs inside Claude Code. You talk to Claude about your training; Claude plans
your week, reviews it with you at each check-in and pushes the sessions to Hevy, the workout app.
Underneath sits the `coach` engine. It owns everything that must be exact: arithmetic, units,
rounding loads to the plates and dumbbells you own, safety bounds, data integrity and the shape of
what goes to Hevy. Claude owns the coaching judgement and records a reason for every decision.

**The engine never changes or deletes your existing Hevy workout history.** It reads workouts and
weigh-ins, and its only writes are creating and updating routines, creating routine folders and
creating custom exercise templates (ADR 0011, `ALLOWED_WRITES` in `src/coach/hevy/client.py`).

## Requirements

- Python 3.12 or later and [`uv`](https://docs.astral.sh/uv/)
- git, with a committer name and email set
- [Claude Code](https://claude.com/claude-code)
- Optional: a Hevy Pro account and its API key, if you log workouts in Hevy
- Optional: Node, if you train at home with a plate set (the `kit` skill runs
  `npx plate-pool` to work out which loads your plates can make)

## Install the engine and plugin

```
git clone https://github.com/joeuk89/strength-coach
cd strength-coach
uv tool install --editable .
```

This puts two commands on your PATH: `coach`, the CLI, and `coach-hook`, which the plugin's hooks
call. Then, in Claude Code:

```
/plugin marketplace add <path to your strength-coach checkout>
/plugin install coach@strength-coach
```

The plugin adds five skills and two hooks. The session-start hook runs `coach status` so every
conversation opens knowing where you stand. The pre-tool-use hook asks for your approval before
any verb that writes to Hevy or commits to git, and blocks any direct call to Hevy's workout
history.

## Create your instance

An instance is your own directory of training data: config, profile, the store and the pages it
renders. It holds no engine code, so one engine install serves any number of instances. Create one
in an empty directory:

```
mkdir ~/training && cd ~/training
coach init --pin 0.1.0
```

`init` asks your units, the day your week starts, your timezone, the days you can train, your
usual session length, how often you check in, and whether you use Hevy. Every question also has a
flag; `--defaults` takes the default for each one you leave out, and `--dry-run` lists what `init`
would write without writing it. To connect Hevy, pass `--hevy-key <key>`: `init` writes it to a
gitignored `.env`. `--pin` is needed while the engine is a development build (`0.1.0.dev0`); it
names the release your instance will run.

`init` makes one git commit. Push the directory to a private remote if you want a backup.

As you train, the instance fills out like this:

```
~/training/
├── coach.toml       your settings and training locations
├── profile.md       who you are and what you train for, in prose
├── CLAUDE.md        how Claude works in this instance (generated)
├── README.md        index of the pages (generated)
├── kit/             your plate and dumbbell inventory per location
├── pages/           this week's plan, each routine, progress, every check-in
├── export/          the store as JSON lines, committed so you can rebuild it
├── hevy/            an append-only log of every write sent to Hevy
└── .coach/          the store (coach.db) and Drafts; gitignored
```

`tests/fixtures/instance/` is a complete example, with rendered pages under `pages/`.

The generated `CLAUDE.md` tells Claude how to work in an instance: open with `coach status`,
write each verb's input as a Draft under `.coach/drafts/`, and record nothing until you say yes.
`coach upgrade` rewrites it when the engine moves on, so don't edit it by hand.

## First conversation

Open Claude Code in your instance directory and say hello. The skills take it from there, in this
order:

1. **`kit`**: where you train and with what. Claude writes each location into `coach.toml` and,
   for a home plate set, its inventory under `kit/`.
2. **`onboard`**: who you are and what you train for. Claude writes `profile.md`, your Goal and
   your Phase.
3. **`program`**: your first Program version, designed around your days, kit and Goal.
4. **`plan-week`**: the first week's sessions, pushed to Hevy as routines once you approve.

If you already log in Hevy, run `coach import` straight after `init` so the coach starts from
your history. `docs/spec/cutover.md` covers moving over from an older setup.

## The weekly loop

1. **Train.** Log your sessions in Hevy from the routines the coach pushed.
2. **Import.** `coach import` pulls new workouts and weigh-ins into the store. It only reads.
3. **Check in.** Claude opens a check-in card filled from the store and asks only what it can't
   know: readiness, sleep, niggles and how the week felt. It records the check-in once you agree.
4. **Plan the week.** Claude drafts next week's sessions, explains every change and pushes them
   to Hevy once you approve.

Each skill also runs as a slash command: `/check-in`, `/plan-week`, `/program`, `/kit`,
`/onboard`.

### Examples

Talk to Claude in plain words:

- "Time for my check-in." Claude asks your readiness first, then sends the card.
- "Plan my week." Claude drafts the week, shows each changed load and why, and asks before
  pushing to Hevy.
- "My shoulder's sore, can we swap overhead press this week?" Claude records the niggle and
  replans the affected sessions.
- "How's my bench going?" Claude answers from your history and records nothing.

The same steps from the terminal:

```
coach status                                          # where things stand
coach query exposures --exercise bb_bench_press --last 5
coach plan draft                                      # write next week's plan Draft
coach plan apply .coach/drafts/2026-11-01-plan.toml --dry-run
coach plan apply .coach/drafts/2026-11-01-plan.toml --expect sha256:…
coach publish                                         # render pages/ and commit
```

`plan apply --dry-run` validates the plan, lists every Hevy action and prints a hash. Passing that
hash back with `--expect` is the approval: if the plan changed since the dry run, the hash no
longer matches and nothing is sent.

## Commands

Every verb prints one JSON envelope. `coach --help` lists them; `coach <verb> --help` or
`coach schema <verb>` gives one verb's arguments, examples and output shape.

| Verb | Writes | What it does |
| --- | --- | --- |
| `init` | git | Create an instance in this directory |
| `status` | nothing | Where things stand: Hevy, kit, plan, program, Goal, check-in due, niggles |
| `import` | store | Pull Hevy workouts, weigh-ins and routines, append-only |
| `record <draft>` | store | Record a ledger Draft outside a check-in, such as a niggle or a manual workout |
| `query <view>` | nothing | Read one view: `exposures`, `readings`, `flags`, `lines`, `routines` or `ledger` |
| `progress` | nothing | The block-boundary report: e1RM per priority lift, stalls, hard sets |
| `goal adopt <draft>` | store | Record a new Goal and open or close the Phase |
| `program show` | nothing | The Program version in force; `--draft` writes it out to edit |
| `program adopt <draft>` | store | Adopt a program Draft as the next Program version |
| `plan draft` | nothing | Derive next week's sessions and write the plan Draft |
| `plan apply <draft>` | Hevy | Validate with `--dry-run`, push with `--expect <hash>` |
| `checkin open` | nothing | The check-in card, prefilled from the store |
| `checkin record <draft>` | store | Record a check-in file |
| `publish` | git | Write `export/`, `pages/` and `README.md`, then commit |
| `schema [<verb>]` | nothing | Verb declarations as JSON Schema |
| `upgrade` | git | Bring the instance up to the installed engine |

## Development

```
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

CI runs these five on every push and pull request (`.github/workflows/ci.yml`). Tests make no
network calls and no live Hevy calls.

## Learn more

- `GLOSSARY.md`: the domain terms (Instance, Program version, WeekPlan, Draft, check-in and more).
- `docs/spec/`: how each part behaves; `verbs.md`, `skills.md` and `instance.md` are good starts.
- `docs/adr/`: the architecture decisions and why they were made.
