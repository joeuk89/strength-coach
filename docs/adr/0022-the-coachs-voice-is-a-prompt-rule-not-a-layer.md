---
status: accepted
date: 2026-11-07
---

# The Coach's voice is a prompt rule, not a layer between the athlete and the system

Nothing structural sits between the athlete and the engine's output. The rule that nothing of
the system reaches the athlete is one section of the generated athlete `CLAUDE.md` plus the skill
template's closing line (`docs/spec/voice.md`), and the transcript benchmark counts what gets
through. Decided on wayfinder ticket
[Prompt rule alone or a system-talk layer](https://github.com/joeuk89/strength-coach/issues/228).

Three real sessions held 18 messages that leaked verb names, flag codes, store ids, paths and a
commit hash; the athlete twice asked what a term meant. The prototype
(`prototype/228-voice-layer`) replayed each leaking moment headlessly on the sessions' own model
under each mechanism and scored the reply with the lexicon:

| Mechanism | Leaking / 18 | Median s | Calls per reply |
| --- | --- | --- | --- |
| Today's `CLAUDE.md`, no rule | 17 | 17 | 1.0 |
| Voice section in `CLAUDE.md` | 9 | 17 | 1.0 |
| Voice section plus skill closing line (chosen) | 6 | 19 | 1.0 |
| Above plus a Stop-hook rewrite on a hit | 0 | 22 | 1.3 |
| Above plus a runner subagent brief | 1 | 91 | 2.0 |

## Considered options

- **The prompt rule alone (chosen).** Removes every registry and pattern class; the six
  leftovers are one stray fixed-list word each, and one is a false positive on a link the
  athlete asked for. No latency, no second call, nothing between the agent and the envelopes
  (ADR 0020).
- **A Stop hook that checks the reply against the lexicon and makes the coach rewrite on a
  hit.** Clean in 18 of 18, but a Stop hook fires after the message has streamed: the athlete
  reads the leak and then the correction. It corrects in view, it does not filter. Kept as the
  fallback.
- **A runner subagent that makes every verb call and returns a coaching brief.** Clean in 17 of
  18 at 91 s median against 19 and two calls per reply; the brief itself leaked, so the
  "quote, never retype" rule moves to the runner rather than going away. Bends ADR 0020 for no
  gain the rule does not give.
- **A plugin agent definition as the coach persona.** Not run: a subagent cannot address the
  athlete, so the main thread is the voice whatever it is called; the runner split inverted.
- **An engine `say` field on every envelope.** Not run: the leftovers are stray words, not
  envelope content, and the ad-hoc session's leaks had no verb involved. Athlete prose for every
  result puts coaching copy in code, against ADR 0020's "voice stays in the skill".

## Consequences

- The ceiling in `docs/spec/benchmark.md` is set with the leftovers in mind: zero hits in any
  registry or pattern class, fixed-list leaks in at most one athlete message in ten.
- **The fallback.** If two consecutive milestone re-runs on real athlete sessions miss the
  ceiling, the Stop-hook lexicon check is built as a fresh effort, with the lexicon as an engine
  registry that the hook and the benchmark script both read. Until then no hook reads prose.
- No test reads a sentence for tone (`docs/spec/skills.md`, "Contract tests"); the benchmark
  count is the only measure.
