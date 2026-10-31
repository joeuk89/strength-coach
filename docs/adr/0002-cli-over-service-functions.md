---
status: accepted
date: 2026-10-26
amended: 2026-10-31 by wayfinder #43 (the declaration's `writes` field names four kinds; four asked verbs, each with a dry run; permission mode is the hook's concern, not the verb's); 2026-10-31 by wayfinder #44 (`main` takes a client factory and a clock; the suite target is ADR 0019's ten seconds)
---

# The agent drives the engine through a CLI over plain service functions

The agent interface is a command-line program, `coach <verb>`, that prints one JSON envelope per
call and returns the result class as its exit code. Each verb is a thin adapter over a service
function that takes a typed request and returns a typed result. No MCP server is built in v1 and no
seam is added for one: a later MCP server would be a second thin adapter over the same service
functions, written when something needs it. Chosen because the engine is stdlib-only (an MCP
server would be a hand-written JSON-RPC loop), Claude Code's Bash permission rules and hooks
already gate a CLI, and a `schema` verb gives the self-description MCP tool schemas would have
given for free.

## Considered options

Weighted by the athlete: approval safety 25, works anywhere 20, self-description 15, build and
maintenance cost 15, testability 15, context cost per pass 10.

- **CLI over plain service functions (chosen).** Wins on works anywhere, cost and testability;
  matches MCP on approval safety once the dry-run hook is kept; loses only on typed arguments
  checked before the call, which `schema` plus validation at the edge recovers.
- **MCP server with typed tools.** Arguments typed and tool schemas loaded by the host, no shell
  quoting of JSON. Loses on stdlib cost, on serving cron, hooks and a human terminal, and on
  per-tool permission rules that cannot show a dry run of the write without a hook anyway.
- **CLI now over an explicit interface-agnostic service seam.** Rejected as speculative: one
  adapter is a hypothetical seam. Plain functions with typed request and result objects are
  already interface-agnostic without an abstraction to maintain.

## Consequences

- **Hosts.** v1 serves Claude Code, its SessionStart and PreToolUse hooks, and a human in a
  terminal for debugging. No other agent is served, and nothing may assume Claude Code is the only
  host.
- **One declaration per verb** (name, arguments, input and output schema, examples, and
  `writes: none | store | hevy | git`, the one field that separates a read, a store write the
  permission rules allow, and a Writing verb they ask on; `docs/spec/verbs.md`) generates `coach --help`, `coach <verb> --help`, `coach schema [verb]` as JSON Schema,
  and the contract tests that check each skill names only verbs that exist. No verb list is
  written by hand anywhere, CLAUDE.md included.
- **Envelope:** `schema_version`, `ok`, `verb`, `result` or `error {code, message}`, `warnings[]`.
  Pretty-printed when stdout is a TTY, one line when piped. No table or prose mode: the human sees
  what the agent sees.
- **Output budget.** Every read verb returns a compact summary by default, capped at 3 KB by a
  test per verb, with `--full` for the whole record and `--fields a,b,c` for a projection. An
  inline `python3 -c` filter in a transcript marks a missing `query` view.
- **Inputs.** Scalars travel as flags. Anything authored or longer than a line (a plan, check-in
  answers, a program patch, a manual workout) travels as the path of a file the agent wrote
  first, never as JSON on argv or stdin. The envelope echoes the file's hash so the record names
  exactly what was applied.
- **Exit codes** keep the old five classes: 0 ok, 1 data or check failed, 3 a guard refused a
  write, 4 Hevy unreachable, 5 setup stops it. `error.code` carries the specific reason. Services
  raise typed exceptions (`Refused`, `Invalid`, `Unreachable`, `Setup`) and the CLI maps them to
  codes in one place.
- **Approval attaches in two layers:** permission rules allow every verb declared `writes: none`
  or `store` and ask on every verb declared `hevy` or `git` (four in v1: `plan apply`,
  `publish`, `upgrade`, `init`), and a PreToolUse hook runs that verb's `--dry-run`, which every
  asked verb declares, so the prompt shows what Hevy, git or the tree will receive. The hook,
  not the verb, denies in bypass-permissions mode, because nobody would see the prompt; a verb
  never knows the permission mode. The human side of approval is the Approval UX decision, not
  this one.
- **Hooks are thin wrappers over verbs.** SessionStart wraps `coach status`; PreToolUse wraps the
  asked verb's dry run into ask or deny. Their only logic of their own is the
  shell-command parser that finds a coach write or a raw Hevy call, ported trimmed from the old
  `gate.py`.
- **Testability.** The entry point stays `main(argv, env, stdout, stderr) -> int`, in-process,
  with two keyword-only arguments, `make_client` and `clock`, that default to the real ones
  (ADR 0019). Services take a store connection, a Hevy client and a clock, never a repo root, so
  core and service tests run on an in-memory SQLite with no files. Only the command layer touches
  the filesystem, Hevy and git. Target: the whole suite in under ten seconds (ADR 0019; this
  line said "well under a minute").
- Whether the program is invoked as `coach` or `python3 -m coach` is the distribution decision;
  both must work.
