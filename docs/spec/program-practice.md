# How coaches write and evolve a program

Research note for wayfinder #14: what coaches hold fixed, what they move weekly, and why, in the glossary's provisional terms (Program, Block, WeekPlan, Prescription). Claims are marked evidence or opinion.

## The shape coaches use

Every source nests cycles: a microcycle (usually a week), a mesocycle of two to six microcycles, and blocks or macrocycles above ([NSCA](https://nsca.com/education/articles/kinetic-select/hierarchical-structure-of-periodization-cycles), [JTS](https://www.jtsstrength.com/the-terms-of-the-deal/)). JTS defines a mesocycle as "an organized sequence of microcycles ordered to elicit a set of distinct training adaptations", typically three to five accumulation weeks plus one deload week, 3:1 classic and 4:1 common for hypertrophy (opinion, [JTS](https://www.jtsstrength.com/the-terms-of-the-deal/)). RP's hypertrophy mesocycle is the same shape: four to six weeks then a deload (opinion, [RP](https://rpstrength.com/blogs/articles/progressing-for-hypertrophy)).

The evidence behind the shape is modest. Periodised beats non-periodised for strength by a small, consistent margin, larger in trained lifters ([Nuckols, ~60 studies](https://www.strongerbyscience.com/periodization/)). For hypertrophy, linear and daily-undulating models are indistinguishable: 13 studies, pooled d = −0.02, CI [−0.25, 0.21] ([Grgic 2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5571788/)). Week counts and ratios are coaching convention, not research cut-offs.

## Fixed for a block

Coaches hold three things constant for the length of a mesocycle.

- **Exercise selection.** RP rotates exercises only between mesocycles. Barbell Medicine calls frequent swapping a mistake because "each new exercise resets the conditions under which performance is measured" ([BBM](https://www.barbellmedicine.com/blog/progress-chest-training-hypertrophy/)). Helms cites studies where weekly swappers gained less muscle ([Helms](http://www.boostcamp.app/blogs/modify-your-training-program)). The systematic review agrees: planned variation across muscle regions helps, "excessive rotation of different exercises" harms, and variation on skill-based strength lifts is unfavourable (evidence, [Kassiano 2022](https://biolayne.com/reps/issue-7/exercise-variation-for-strength-and-hypertrophy-change-is-not-always-good/)).
- **Rep range and proximity-to-failure scheme.** JTS gives 5–10 for hypertrophy, 3–6 for strength, 1–3 for peaking (opinion, [JTS](https://www.jtsstrength.com/nonsense-periodization-powerlifting/)). The SBS bundle fixes a block at seven weeks and shifts range and intensity only at block boundaries ([SBS](https://www.strongerbyscience.com/program-bundle/)).
- **The progression model.** The rule turning last week's result into this week's target is chosen once per block: linear load jumps, double progression, RIR autoregulation, or percentage of a training max ([Helms/Morgan](https://rippedbody.com/progression/), [SBS](https://www.strongerbyscience.com/program-bundle/)).

## What changes weekly

Within a block only the dose moves, and it moves by rule.

- **Load.** Barbell Medicine's default is to raise estimated 1RM each week when possible, planning 1–5 lb or 1–5% above last week and letting the day's RPE "supersede our plans" ([BBM coaches](https://forum.barbellmedicine.com/t/clarification-on-weekly-progression-using-templates/5667)). e1RM is "calculated based on your actual performance during the session", never set by hand ([BBM](https://forum.barbellmedicine.com/t/how-much-should-e1rm-increase-from-week-to-week/10913)). Starting loads must leave room to add weight all block ([JTS](https://www.jtsstrength.com/selecting-and-progressing-your-weights/)).
- **Reps.** Under double progression, reps climb within the range first, then load goes up and reps fall back. Progress is judged on trends; a weak week is normal ([Helms/Morgan](https://rippedbody.com/progression/)).
- **Sets and RIR.** RP starts near minimum effective volume, adds sets weekly until performance drops, and walks RIR from about 4 down to 1 (opinion, [RP](https://rpstrength.com/blogs/articles/in-defense-of-set-increases-within-the-hypertrophy-mesocycle)).
- **Nothing else.** A flat load is not a stall when reps, execution or recovery improve ([BBM](https://www.barbellmedicine.com/blog/progress-chest-training-hypertrophy/)).

## When an exercise is swapped or added

Three agreed triggers:

1. **Block boundary.** The planned place for new exercises, including introducing next block's lifts during the deload (95% agreement, [Bell 2023](https://pmc.ncbi.nlm.nih.gov/articles/PMC10511399/)).
2. **Pain or missing kit.** Swap within the movement pattern, keeping rep range and RPE target: a barbell bench with shoulder pain becomes a dumbbell bench ([Helms](http://www.boostcamp.app/blogs/modify-your-training-program)). On a strength program the swap must preserve transfer, so it is the coach's call.
3. **A stall over a meaningful timeframe.** Not one session. Try more volume or redistributed work before a new exercise ([BBM](https://www.barbellmedicine.com/blog/progress-chest-training-hypertrophy/)).

Rejected: swapping because a week went badly, or for novelty.

## Deload and re-test

The coach consensus defines a deload as "a period of reduced training stress designed to mitigate physiological and psychological fatigue" ([Bell 2023 Delphi](https://pmc.ncbi.nlm.nih.gov/articles/PMC10511399/)). The panel agreed (100%) it can be pre-planned, autoregulated, or both, sits between mesocycles or whenever the athlete is fatigued, and cuts days, sets or reps while keeping exercises familiar and the main lifts in. No consensus on a fixed length or interval; "every 4–6 weeks" is background literature, not the panel. Helms/Morgan cut sets 30–50% and keep load and effort ([rippedbody](https://rippedbody.com/progression/)); JTS halves reps and keeps the weight heavy ([JTS](https://www.jtsstrength.com/nonsense-periodization-powerlifting/)). Sources differ on the cut, not on when.

A formal re-test is a strength-sport device: a realisation week with an AMRAP or heavy single that sets the next block's training max. Hypertrophy coaches do not re-test; next block's loads come from "your previous block", adjusted "by feel on the day" ([JTS](https://www.jtsstrength.com/selecting-and-progressing-your-weights/)), or from the logged e1RM (BBM). For this athlete the re-test is the logged performance, not an event.

## Implications for the domain model

**Fits practice.**

- **Program** as the block-level fixture: sessions, exercise selection, rep range and RIR scheme, progression model, block length and deload policy. Versioned and immutable once adopted matches "fixed for the mesocycle". A new version is cut at a block boundary or for a pain or kit swap.
- **Block** as the mesocycle: a counted run of hard weeks under one program version, ended by a deload or reset. The Delphi consensus supports both a ceiling and fatigue triggers, which is what the old code did.
- **Prescription** as the week's concrete numbers per exercise: load, reps, sets, RPE or RIR target, derived from the program's rule and the latest logged exposure.

**Tensions.**

- **Is a weekly load bump a WeekPlan or progression state?** Neither: it is the progression rule applied to new facts. Every source derives this week's load from last week's log (e1RM, reps at RIR, sets completed). That argues for Prescription being a *derived* value, `prescribe(program_version, history, date)`, with no stored weekly delta. A stored weekly load row copies derived data and reintroduces the #257 double-cut: a delta over a delta.
- **What WeekPlan is for, then.** Practice has three kinds of weekly departure: a deload or light week, a disrupted week (travel, illness, return band), and a one-off swap for pain or kit. All are overrides *to the rule*, not to the numbers: "sets ×0.5, load held", "return band −10%", "exercise X → Y this week". WeekPlan fits as a small set of typed overrides over the program for a date span, applied before derivation, with approval bound to the prescriptions it produces. It does not fit if it carries every week's loads.
- **Exercise swap: WeekPlan or Program version?** Practice splits it. A pain swap for one week is a WeekPlan override. A swap that persists is a new program version, because it resets the performance baseline for that slot (BBM). The model needs both, and a rule for promoting one to the other.
- **ProgressionState is per lift, not per program.** e1RM, best reps-at-RIR and the double-progression position belong to an exercise-in-slot and are recomputed from history. If stored at all it is a cache, never an input.
- **Block end is an event, not a week.** The Delphi panel's "deload whenever fatigued" means the block boundary is decided at check-in, not pre-dated. The old code's "count resets when the check-in closes the week" is right.

**Does not fit.** A WeekPlan that is "a delta over a program version" with no restriction on what the delta may touch. Coaches never edit the plan weekly; they apply a rule, or override the rule for a named reason.
