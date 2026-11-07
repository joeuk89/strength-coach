# Transcript benchmark

The measured cost of the old system's core loop, taken from Claude Code session transcripts.
Every rebuild milestone is measured the same way and compared with this table. Wayfinder
ticket #11; first version of the table in the 2026-10-26 system review (old instance repo,
`.agent/reviews/2026-10-26-system-review.md`, "Evidence").

## Baseline (measured 2026-10-26)

| Session | Flow | Wall time | coach calls | Distinct subcommands | Bash calls with inline Python | Peak context | Athlete replies | Instruction tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| d4f30a4f, 26 Oct | check-in → program-week → publish | 28 min | 82 | 47 | 27 | 186k | 3 | ~22k |
| d4a44e8b, 18 Oct | check-in → program-week → fix → publish ×2 | 35 min | 141 | 61 | 33 | 300k | 7 | ~37k |
| 08c4bfd8, 12–13 Oct | goals + deload (migration day: recipes, goals, program-week) | 41 min | 134 | 55 | 59 | 432k | 8 | ~22k |

Instruction tokens by source (characters ÷ 4):

| Session | Skill bodies (SKILL.md via the Skill tool) | CLAUDE.md files (system prompt) | Skill sub-files and `reference/` read through Bash |
| --- | --- | --- | --- |
| d4f30a4f | 2.9k | 8.0k | 11.5k |
| d4a44e8b | 2.8k | 7.7k | 26.8k (includes a second read of the project CLAUDE.md) |
| 08c4bfd8 | 4.6k | 7.3k | 9.6k |

## Targets

From the review, per check-in plus programming pass:

- **Under 10 `coach` calls.** Baseline: 82 and 141. A call is `coach` or `python3 -m coach` at
  the start of a command (the string start, or after `;`, `&&`, `|`, `(`, `{`, `do`, `then`
  or a newline), so
  `coach-hook`, `coach.toml`, a `coach` directory passed to grep and the word in a commit
  message are not calls.
- **Under 8k tokens of engine-owned instructions loaded.** Baseline: 22k and 37k. The count is
  the skills loaded, the project CLAUDE.md files and every instruction file read through Bash.
  The athlete's global CLAUDE.md (the `User` file in the session's `instructions` attachment)
  and the auto-memory index are outside it, because the engine cannot shorten them; the script
  reports them as a separate `outside_target_tokens` figure. The baseline rows were measured
  before the split and include the global file; re-measured on 2026-10-31 with the split, the
  three sessions hold 19.2k, 34.4k and 19.1k in the target and 3.2k, 2.9k and 2.5k outside it,
  so the project CLAUDE.md alone was 4.8k.
- **Zero Bash calls with inline Python.** Baseline: 27 and 33. Every one marks a verb whose
  output the agent could not use as printed.
- **Zero voice leaks in any registry or pattern class, and fixed-list leaks in at most one
  athlete message in ten.** A voice leak is a lexicon term in an athlete-facing message
  (`voice.md`); the classes are `verb`, `flag`, `record`, `view`, `error`, `path`, `store-id`,
  `hash` and `code`, then `fixed`. Baseline on the three transcripts, by hand: 3 of 4, 9 of 15 and
  6 of 13 messages leaking. A URL the athlete uses is stripped before matching and is never a
  leak. Measured on athlete sessions only; the script reports `leaking_messages` over
  `athlete_messages` and `leak_hits` by class.

## Method

Run from this repo's root:

```
python3 -I scripts/benchmark/measure.py --repo <instance repo> --md <session>.jsonl ...
```

Transcripts live under `~/.claude-personal/projects/<project-dir>/<session-id>.jsonl`, one JSON
record per line. Pass `--repo` as the instance repo the session ran in; the script never reads
the transcripts as instructions, only as data. Drop `--md` for the full JSON, which lists the
subcommands and the instruction files found.

How each column is computed:

- **Wall time.** Last `timestamp` minus first, over every record in the file, rounded to the
  minute. Idle time while the athlete was away is included, so this is a ceiling.
- **coach calls.** Occurrences of `coach` or `python3 -m coach` at the start of a command
  (`COACH_CALL` in the script) in the `command` input of every Bash tool call on assistant
  messages. A Bash call that chains three coach commands counts three.
- **Distinct subcommands.** Unique `<group> <command>` pairs after that prefix, where the
  command is the next bare word (not a flag). A group run with no command, such as `status` or
  `niggles --json`, counts as its own entry.
- **Bash calls with inline Python.** Bash calls whose command contains `python3 -c`, `python -c`
  or a `python3 - <<` / `python3 <<` heredoc. The JSON also reports raw occurrences
  (`inline_filters`), which run higher: 39, 49 and 77 for the three sessions.
- **Peak context.** The largest `input_tokens + cache_creation_input_tokens +
  cache_read_input_tokens` on any assistant message's `usage`. This is the real request size.
- **Athlete replies.** User records that are plain text (a string, or text blocks) and not a tool
  result, a skill load or a meta record. The opening slash command counts as one.
- **Instruction tokens.** Characters ÷ 4 of three sources, summed: skill bodies (user text blocks
  that start `Base directory for this skill:`), the `Project` CLAUDE.md files in the session's
  `instructions` attachment, and every path matching `.claude/skills/**/*.md`, `reference/*.md`
  or `CLAUDE.md` named in a Bash command, sized with `git show` at the instance repo's last commit
  before the session ended. A file missing at that commit counts zero and is listed as `null`.
  The attachment's `User` and `AutoMem` files (the global CLAUDE.md and the memory index) are
  summed separately as `outside_target` and never enter the figure.

Known limits:

- Characters ÷ 4 is an estimate. Prose runs closer to 4.2; the figure is good to about 10 %.
- Sidechain (subagent) records are skipped. None of the three baseline sessions used subagents.
- A file read twice is counted twice. That is deliberate: it was loaded twice.
- The review's "over 30k tokens" sized the complete check-in and program-week skill trees. The
  sessions loaded only the sub-files they reached, which is why the measured figures are lower.
- Each session's flow is read from the transcript by hand. The 12–13 Oct session was a migration
  day (recipes, goals, an opening-week program), not a check-in, so compare it with care.

## Re-running after a milestone

1. Run one real check-in plus programming pass in the new system.
2. Point the script at its transcript with `--repo` set to the new instance repo. `COACH_CALL`
   and `SUBCOMMAND` already count both `coach` and `python3 -m coach`.
3. Add a row above, dated, and keep the old rows.
