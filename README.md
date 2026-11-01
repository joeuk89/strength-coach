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

Install the engine from GitHub; you don't need a copy of the repo:

```
uv tool install git+https://github.com/joeuk89/strength-coach
```

This puts two commands on your PATH: `coach`, the CLI, and `coach-hook`, which the plugin's hooks
call. `uv tool upgrade coach` updates it later. Then, in Claude Code:

```
/plugin marketplace add joeuk89/strength-coach
/plugin install coach@strength-coach
```

The plugin gives Claude the coaching skills and the guard rails described below.

## Create your instance

Your instance is a folder that holds your own training data: your settings, your profile, your
history and the pages the coach writes for you. Create one in an empty folder. This is the only
command you run yourself:

```
mkdir ~/training && cd ~/training
coach init
```

`init` asks a few questions: kg or lb, the day your week starts, your timezone, the days you can
train, how long a usual session is, how often you want to check in, and whether you use Hevy. If
you do, have your Hevy API key ready; it's saved in a file git ignores.

The folder is a git repository. Push it to a private remote if you want a backup.

## Get started

Open Claude Code in your instance folder and say hello. The coach notices what's missing and walks
you through setup, one conversation at a time:

1. **Your kit.** Where you train and what equipment you have: a gym, a home plate set, or both.
2. **About you.** Your training history, what you want to achieve, and anything to work around.
3. **Your program.** The coach designs one around your days, kit and goal, and talks you through
   it.
4. **Your first week.** The coach plans the sessions and, once you approve, sends them to Hevy as
   routines.

If you already log workouts in Hevy, the coach reads your history first, so your program starts
from what you can actually lift.

## Train with your coach

Each week runs the same way:

1. **Train.** Open Hevy, start the coach's routine for the day and log your sets as usual.
2. **Check in.** At the end of the week, tell the coach. It pulls your workouts from Hevy, shows
   what it already knows and asks only what it can't: how you feel, how you slept, any aches.
3. **Plan the next week.** The coach adjusts each load from what you did, explains every change and
   sends the new routines to Hevy once you approve.

You can talk to the coach in plain words, or start a step with a slash command:

| Command | Use it to |
| --- | --- |
| `/check-in` | Review your week |
| `/plan-week` | Plan next week, or change this one: move, drop or swap a session |
| `/program` | Rework your program, for example at the end of a training block |
| `/kit` | Add a place to train, or record equipment you bought or lost |
| `/onboard` | Start over on who you are and what you train for |

Some things you might say:

- "Time for my check-in."
- "Plan my week."
- "I'm away Thursday, can we move lower body to Saturday?"
- "My shoulder's sore, can we swap overhead press this week?"
- "How's my bench going?"
- "I bought a pair of 30 kg dumbbells."

### You stay in charge

- The coach records nothing until you say yes.
- Before anything goes to Hevy, you see exactly what will change and approve it.
- Every coaching decision is saved with its reason, so you can always ask why.
- The coach writes readable pages into your instance: this week's plan under `pages/week.md`, each
  routine, your progress and every check-in.

## Development

To work on the engine, clone the repo and install it in editable mode, so `coach` runs your
working copy. Point the plugin at the checkout to try changes to the skills and hooks:

```
git clone https://github.com/joeuk89/strength-coach
cd strength-coach
uv tool install --editable .
```

```
/plugin marketplace add <path to your strength-coach checkout>
/plugin install coach@strength-coach
```

Claude runs the `coach` CLI on your behalf. To see it directly, `coach --help` lists its verbs,
and `coach schema <verb>` gives one verb's arguments and output. `tests/fixtures/instance/` is a
complete example instance.

The checks:

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
