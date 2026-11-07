# Prototype: prompt rule alone or a system-talk layer (wayfinder #228)

Throwaway. Replays the 18 hand-marked leaking moments of the three transcripts in
`scripts/benchmark/transcripts/` (branch `issue/224-leak-transcripts`, PR #231) under five
mechanisms and scores each reply with the #226 lexicon. Run `python3 run.py <mechanism>` from
this directory with the transcripts in place, then `python3 report.py`. Each run is a headless
`claude -p` call (model claude-fable-5-1, the sessions' own) with the mechanism's instructions as
the whole system prompt and the moment's history rendered as a transcript in the user turn.

## Result

| Mechanism | Leaking / messages | Hit classes | Median seconds | Calls per reply | Instruction tokens | Cost of 18 (USD) |
| --- | --- | --- | --- | --- | --- | --- |
| today's CLAUDE.md (no rule) | 17/18 | code 16, fixed 13, verb 12, store_id 12, flag 8, path 8, hash 5, view 1 | 17 | 1.0 | 1282 | 13.07 |
| voice section in CLAUDE.md | 9/18 | fixed 8, hash 1, code 1 | 17 | 1.0 | 1401 | 13.05 |
| voice section + skill closing line | 6/18 | fixed 5, hash 1, code 1 | 19 | 1.0 | 1418 | 12.73 |
| rule_skill + Stop-hook rewrite on a hit | 0/18 | none | 22 | 1.3 | 1418 | 5.55 |
| rule_skill + runner subagent brief | 1/18 | fixed 1 | 91 | 2.0 | 1418 | 17.41 |

Per message (terms that leaked):

| Session | # | base | rule | rule_skill | hook | split |
| --- | --- | --- | --- | --- | --- | --- |
| pull-up-dose | 3 | .coach/drafts/2026-11-02-program.toml; Draft; `.coach/drafts/2026-11-02-program. | clean | acknowledgement | clean | clean |
| pull-up-dose | 4 | .coach/drafts/2026-11-02-program.toml; `.coach/drafts/2026-11-02-program.toml`;  | acknowledgement; the engine | Draft; dry run; flags | clean | clean |
| pull-up-dose | 5 | `dose_off_band`; `lift_dose_under_target`; acknowledgement; dose_off_band; dry r | dry run; flag | the engine | clean | clean |
| pull-up-dose | 6 | .coach/drafts/2026-11-02-program.toml; `amend`; `b-2026-11-01`; `coach program a | acknowledgement; dry run | clean | clean | clean |
| pull-up-dose | 7 | `lift_dose_under_target`; `plan draft`; acknowledgement; lift_dose_under_target; | flags | clean | clean | clean |
| pull-up-dose | 8 | `["mon-ohp", "cond-swings"]`; `coach progress`; `coach status`; `dose_off_band`; | acknowledgement; the store | clean | clean | flag |
| incline-curl | 3 | `~/personal/workout/routine/`; pv-3 | clean | clean | clean | clean |
| incline-curl | 8 | `amend`; dry run; pv-3 | clean | clean | clean | clean |
| incline-curl | 9 | .coach/drafts/2026-11-04-program-2.toml; Draft; `.coach/drafts/2026-11-04-progra | clean | clean | clean | clean |
| incline-curl | 10 | `because`; `db_incline_curl`; `dose_off_band`; `mon-ohp`; `routine_drift`; `sche | clean | clean | clean | clean |
| incline-curl | 11 | Draft; `because`; `coach program show`; b-2026-11-01; coach program show; pv-1;  | clean | clean | clean | clean |
| incline-curl | 12 | `dose_off_band`; acknowledgement; b-2026-11-01; dose_off_band; plan draft; pv-4; | acknowledgement | acknowledgement | clean | clean |
| incline-curl | 13 | clean | acknowledgement | clean | clean | clean |
| incline-curl | 14 | `6937415`; `pages/week.md`; `plan apply`; `plan draft`; acknowledgements; pages/ | clean | clean | clean | clean |
| incline-curl | 15 | plan draft | clean | clean | clean | clean |
| plate-pool-link | 2 | `https://joeuk89.github.io/plate-pool/#inventory=…`; `https://joeuk89.github.io/ | `d33b57cc`; d33b57cc | `d33b57cc`; d33b57cc | clean | clean |
| plate-pool-link | 3 | `athlete.md`; `github.com/joeuk89/training`; `kit=d33b57cc`; `pages/routines/`;  | clean | clean | clean | clean |
| plate-pool-link | 4 | `#inventory=…`; ```; `coach --help`; `coach publish`; `d33b57cc`; `kit/home.achi | the repo | the repo | clean | clean |

## Reading the leftovers

Under the prompt rule plus the skill line, the six hits are: "weekly acknowledgement" and "the
engine's default" (real, one word each); "Draft refreshed", "the dry run shows", "it flags"
(two real, one English); "the deadlift dose acknowledgement" (echoing the athlete's own question);
"the repo" (real); and the kit code inside the plate-pool URL the athlete asked for (a false
positive: the URL is the answer). The heavy classes of the originals (ids, flag codes, paths,
verb names, code spans) do not appear at all.

The Stop-hook rewrite was clean in 18 of 18 and kept the content (see
`results/hook/2026-11-04-incline-curl-12.json`: "acknowledgement" became "the target you asked
about"). A Stop hook fires after the message has already streamed to the athlete, so it corrects
in view, it does not filter.

The runner subagent was clean in 17 of 18 at 4.8x the latency and two calls per reply; its brief
itself leaked ("the engine", "flag") and the coach cleaned it. Not run: an engine `say` field
(the leftovers are stray words, not envelope content, and the ad-hoc session leaked file paths no
verb produced) and a persona agent definition (a Claude Code subagent cannot address the athlete,
so the shape is the runner split inverted).
