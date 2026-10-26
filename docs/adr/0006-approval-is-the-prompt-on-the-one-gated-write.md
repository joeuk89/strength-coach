---
status: accepted
date: 2026-10-26
---

# Approval is the human's yes to the one gated write, bound by a Write plan hash

Approval has no verb of its own. It is the athlete saying yes to `coach plan apply`, the one
verb that writes to Hevy: in Claude Code, at the permission prompt the PreToolUse hook fills
with the verb's dry run; in a terminal, at the verb's own `[y/N]` prompt on a TTY. Nothing on
argv or in the environment counts as approval, because the agent can produce any of it. The yes
is bound to exactly what gets pushed by a hash, the Write plan, that the dry run prints and the
real run must be handed back and recompute. The draft is the plan file; the WeekPlan row is born
approved inside the `plan apply` transaction.

## Considered options

- **The prompt on the gated write, no approve verb (chosen).** One ceremony, no path by which
  the agent stamps its own plan, and the prompt shows the engine's dry run rather than the
  agent's account of it.
- **A separate `plan approve` step the human types.** Under Claude Code the agent could type it,
  so it needs the same prompt anyway; a second ceremony for no extra safety. This was the old
  `overlay approve`, which sat on the auto-allow list and so was self-stamped.
- **Both.** The second step adds only the chance that the approved row and the pushed plan drift.

## The Write plan

- `plan apply <file> --dry-run` prints the summary and the hash. `plan apply <file>` refuses
  without `--expect <hash>` and refuses when the recomputed hash differs. The hash covers the
  WeekPlan row that would be frozen (overrides, derived prescriptions, rotation position), the
  list of Hevy writes, and the current version of each routine touched. A history import, an
  edited file or a routine changed in the Hevy app between dry run and apply all change it.
- The hook compares the flag to its own dry run and denies, rather than asks, when it is missing
  or stale.

## The hook

- PreToolUse on Bash. It finds coach verbs whose declaration says they write to Hevy (never a
  hard-coded name), runs their dry run, and answers ask with the summary, or deny with the
  reason when the dry run refuses. Permission "ask" rules are generated from the same
  declarations.
- It asks only in modes where a human sees the prompt: `default`, `acceptEdits`, `plan`,
  `auto` (a hook ask forces a real prompt there; the classifier cannot approve it). It denies in
  `bypassPermissions`, `dontAsk` and any mode it does not recognise. Headless `claude -p` needs
  nothing extra: the host denies an unanswered ask.
- A raw HTTP write to the Hevy API in a Bash command asks with a warning that it skips the
  verb's checks and audit, and is denied outright for any method on `/v1/workouts`. Permission
  config also denies `WebFetch` to the Hevy host.
- If the hook cannot read the command or the dry run throws, it asks with the reason in normal
  modes and denies where no prompt exists. It never answers allow.

## Consequences

- **The prompt** is a fixed layout budgeted to about 40 lines, held by a test: span and rotation
  position; per session, each line as exercise, sets × reps at load, with the delta against the
  last exposure; every override with its kind and reason; warnings; the Hevy actions (update,
  create, retire); then the hash. More is behind `--dry-run --full`.
- **The Approval record** holds the WeekPlan id, timestamp, Write plan hash and route (`prompt`
  or `terminal`, known by TTY). Not the summary text: it is reproducible from the frozen row.
  Nothing names the person; one athlete owns the instance.
- **WeekPlan status** is `approved | superseded`. There is no stored draft and no editing an
  approved plan: a changed file applied in the same span creates a new WeekPlan that supersedes
  the old, with its own approval and push, and its dry run shows the delta against the
  superseded plan. ADR 0005's "approval naming a WeekPlan that is not the current draft" is now
  the Write plan hash check.
- **Instance without Hevy:** same verb, same gate, same `--expect`. The dry run shows
  prescriptions with no Hevy actions. Approval is the athlete's commitment to the week's
  numbers, not only a Hevy safeguard.
- **Push fails after the yes** (Hevy unreachable): the WeekPlan and Approval rows persist.
  Re-running the same command resumes the push, prompts again, and refuses if the hash changed.
- **Saying no** leaves no record. The agent gets the reason as its tool result, edits the file,
  and returns with a new hash. There is no partial approval.
- **`publish`** (export plus one git commit) is its own verb with its own permission ask. It
  also follows block close, check-ins and imports, so it is not folded into `plan apply`.
- The shell-command parser ports trimmed from the old `gate.py`; it is the hook's only logic of
  its own (ADR 0002).
