# Research notes the engine ships

Settled on wayfinder ticket [Research notes on main and every number cited](https://github.com/joeuk89/strength-coach/issues/40),
2026-10-31. ADR 0004 and ADR 0020 say where notes live and who reads them; this document lists
which notes exist, how a citation names a claim, and which numbers rest on no citation.

## Where they live and who reads them

Every research note is a file in `docs/spec/` of the engine repo, beside the spec. Notes are not
package data, not in the plugin and not in the instance; a running agent never reads one (ADR
0020). They exist for two readers: the person deciding a rule, and the ref test. Rendered pages
link a flag's `rn` to the note at the pinned engine tag on GitHub, so the directory is the link
target.

## Two forms, two ref grammars

| Form | Written | Cited as | Resolves to |
| --- | --- | --- | --- |
| claims note | TOML front matter in an HTML comment: `[[claims]]` rows with `n`, `text`, `basis`, `sources`, `status`; a rendered table and an answer below | `rn:<note>.<n>` | the claim numbered `n` with `status = "current"` |
| prose note | numbered sections `## <n>. <title>`, each claim marked evidence or opinion in the sentence | `rn:<note> §<n>` | the section numbered `n` |

The eleven notes carried from the old repos are claims notes; the four written on this map are
prose notes. A note is never renumbered: a claim is retired in place (`status = "retired"`) and a
new one appended; a section keeps its number. The **ref test** (ADR 0004, ADR 0020) resolves
every `rn:` in code and in the flag registry (`validation.md`) to a current claim or an existing
section and fails on anything else, so a retired claim surfaces where it is cited.

## Precedence

A note records evidence and the proposals made from it at the time. Where a note's Implications
section, a proposal or a claim that states this framework's **old** policy (the two-thirds
standard deload of rn:deloads.9, the "lower half of the band" dose) differs from a spec document
or an ADR, the spec wins and the note is cited for its evidence only. The three prose notes
written before the decisions say so in their header; the claims notes say nothing and are read
under this rule.

## The notes

| Note | Form | Claims the spec reads and the numbers they own | Read by |
| --- | --- | --- | --- |
| `deloads` | claims | .2 hard week 75 % and the 50 % reset; .3 ceiling 6 hard weeks (4–8); .4 no light week under 3; .5 two triggers propose, one watches; .6 adherence under 70 %; .7 under 80 %; .8–.10 deload shape, load held on readiness or sleep; .11 the session gate, two thirds of sets and RPE within 1.5; .12 deep check-in at 42 days; .13 weeks that count for nothing | `week.md`, `goals.md`, `validation.md` |
| `detraining-return` | claims | .3 the return bands by days off (0–10, 11–21, 22–42, 43+) and their load factors 0.95, 0.90, 0.85; .4 illness RPE 7 | `prescription.md`, `validation.md` |
| `autoregulation` | claims | .1 RPE loading matches percentages; .4 RPE drift (1 over on 2 sets, two exposures running); .5 e1RM from 12 or fewer reps to failure, reps plus 10 minus RPE; .6 unearned load above RPE 10.5 and the infeasible target | `prescription.md`, `week.md`, `validation.md` |
| `progression-training-age` | claims | .2 double progression; .3 linear for session-to-session jumps; .6 and .8 the RPE-anchored top set and back-offs; .9 the 5/3/1 waves, 90 % training max and the 2.5 / 5 kg step | `prescription.md`, `program.md`, `validation.md` |
| `volume-frequency` | claims | .1 10–20 hard sets per muscle per week; .2 fractional sets, 1 direct and 0.5 indirect; .3 11 fractional sets per session | `week.md`, `validation.md`, ADR 0009 |
| `proximity-to-failure` | claims | .5 a hard set is a working set above RPE 5 | `week.md` |
| `minimum-effective-dose` | claims | .1 maintenance at about a third of the dose; .4 a priority lift keeps 2 hard sets in a disrupted week | ADR 0009, `validation.md` |
| `bodyweight-skill-progression` | claims | .3 the assistance ladder moves one rung on a full hit | `prescription.md` |
| `running-load` | claims | .1 a run over 1.10 × the longest in 30 days; .4 judged only after 14 days of history; .5 two quality bouts a week; .6 quality is session RPE 7 or more | `week.md`, `validation.md` |
| `concurrent-training` | claims | .4 lift first, 6 hours between; .5 no quality run in the 24 hours before heavy squat or hinge | `week.md`, `validation.md` |
| `sleep-dieting` | claims | .1 adults need 7 or more hours; nothing else (claims 2–5 are nutrition, out of scope, ADR 0004) | `week.md`, `validation.md` |
| `program-practice` | prose | mesocycle shape, what moves weekly, swaps, the 3–6 week deload interval | ADR 0003, ADR 0015 |
| `goal-programming` | prose | §1 reps and load per goal; §2 proximity to failure; §3 weekly dose per goal; §4 progression model; §5 stall; §6 deload shape; §7 order; §9 rest | `goals.md`, `program.md`, `validation.md` |
| `training-level` | prose | §2 graduation as a stall under a cadence, the second miss, the 5 % / 10 % reset by age; §4 phase strategy, keep volume in a deficit, the loss and gain rates | `goals.md`, `prescription.md`, `validation.md` |
| `progression-methods` | prose | §1 the catalogue, set structures save time not muscle; §2 the registry judged; §3 the scheme per emphasis and exercise kind; §4 the switching rule, resets before a scheme change, the training max down about 10 % | `goals.md`, `program.md`, `prescription.md`, `validation.md` |

Old notes **not carried**: `endurance-fuelling`, `protein-energy-deficit`, `resting-hr`,
`strength-for-running` and the local `creatine-dosing` note. They back nutrition, the cardio
layer and the Sleep gate, all out of v1 (ADR 0004). `parity.md` still names some of them; it is
historical and no test reads it.

## Numbers that rest on no citation

Each is an engine constant with `rn = null` beside it, marked opinion where the spec states it.
A later ticket may cite one by adding a claim to a note and the ref beside the constant; nothing
else changes.

| Number | Where | Why no citation |
| --- | --- | --- |
| 90-day anchor window (any-session fallback) | `prescription.md`, the anchor | two Blocks at the default ceiling; this framework's |
| 42-day e1RM window | `prescription.md` | one Block at the default ceiling (rn:deloads.3 gives the ceiling, not the window) |
| usual interval clamped to 7–14 days | `prescription.md`, days off | this framework's |
| three exposures to a `stall_streak` | `prescription.md`, Stalls | the sources say read the trend and name no count |
| RPE 2 over the authored target as `rep_range_missed`; the one-row cap on `top_backoff`; `load_for` rounding down | `prescription.md`, the move | this framework's |
| the test single at RPE 9 | `prescription.md`, The test set | this framework's |
| the warm-up ramp 60; 50/75; 40/60/80; 40–80 | `prescription.md`, Warm-ups | this framework's (#39) |
| deload defaults 40/0/8 and 30/0/8 | `goals.md`, Defaults per emphasis | the direction is rn:goal-programming §6 and rn:deloads.8–.10; the percentages are this framework's |
| the strength line's default 8 hard sets and 5–15 band floor 2–6 | `goals.md` | marked opinion in `goals.md` |
| 4 short nights of 7 and the 4-night floor | `week.md`, Fatigue triggers | 7 hours is rn:sleep-dieting.1; the counts are this framework's |
| `dose_under_target` in three of the trailing four weeks | `week.md`, Dose | the range is rn:volume-frequency.1; three of four is this framework's |
| 14-day Weigh-in average, two weigh-ins minimum, 28-day observed-rate window | `goals.md`, Milestone and Phase | this framework's |
| Phase band half-widths ±50 % of rate and ±0.25 % BW | `goals.md`, What the Phase changes | marked opinion under rn:training-level §4 |
| catch-up at a window over 10 days; check-in cadence default 7 | `week.md`, When a check-in is due | the cadence is an `[athlete]` fact; 10 days is this framework's |
| `snapshot_stale` age limits: plate-pool 90 days, Hevy 7 days | `validation.md` | a plan reads last week's exposures, so a mirror older than a week is stale; kit changes rarely |
| the `linear` reset `misses_before_reset = 2`, `reset_factor = 0.9` | `prescription.md`, Stalls | **cited**: rn:training-level §2; 0.9 is the over-40 figure, named here because the default bakes in an age band and the line may set 0.95 |
