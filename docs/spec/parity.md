# Parity: which old behaviours the rebuilt engine reproduces

> **Status: historical reference.** This is the 2026-10-26 review of the old system. Later decisions
> changed or dropped many rows; where a spec document or ADR differs, it wins. No test cites a row
> here (`docs/spec/testing.md`).

Resolves wayfinder #10. Sources mined read-only: the old template's `tests/` (131 files, 43.6k
lines), `docs/design/coach-contract.md` (C1–C55), `coach/`, the old instance's CLAUDE.md
"Coaching principles", the research notes (`research/*.md`, all 16 `current` on 2026-10-26) and
template issue #257. Every behaviour below is judged on merit, not on existence:

- **(a)** a real domain rule, safety invariant or data-integrity rule; `rn:` refs given where a
  research claim backs the number (maths and safety rules often have none).
- **(b)** a workaround for the old design's shape: stored projections and drift checks, markdown
  parsed as data, file-order rules, overlay + proposal + draft copies, post-approval edit guards,
  flag keys built from messages.
- **(c)** accretion: a one-off guard, or a test asserting English wording (skills, CLAUDE.md,
  rationale sentences, flag messages, status lines).

Counts over the table: **(a) 171**, **(b) 54**, **(c) 14**, plus one safety gap (240 rows; the
agents' finer rows were merged). Tests reading skill or CLAUDE.md prose: 18 files by path plus
about 10 through `tests/support/skills.py`, in line with the review's 43 of 131. All are (c).

## Parity checklist

Class (a) rows only. The core loop (check-in, program-week, Hevy push) must pass every **Core
loop** item before cutover; **Outside the core loop** items are (a) too but gate the v1-scope
decision. Each item is tested with values, never with a sentence.

### Core loop: return after a layoff and prescription validity

- [ ] Return bands by days off: 0–10 none; 11–21 load ×0.95, −1 set; 22–42 ×0.90, −1 set; 43+ ×0.85, −1 set, every set RPE ≤ 7, re-test (rn:detraining-return.3).
- [ ] A return cut is measured **once**, from the pre-layoff working load (newest ordinary exposure before the layoff, else the program start load). Re-proposing, rebuilding or re-planning midweek a week that already carries the cut reproduces its loads (#257).
- [ ] Proposal and validator cut from the same base; a sibling session re-planned after the first return session keeps its line, never re-cut from that session's log.
- [ ] Days off for a lift = max(layoff, exposure age − its usual interval); layoff counts coach-led lifting; a lift overdue past its own gap decays without a layoff (rn:detraining-return.1). Interval = median of the last ≤ 4 gaps clamped 7–14 days, grace 10 days (heuristic).
- [ ] Set cut floor: max(1, min(prescribed, derived-from sets) − 1); a borrowed exposure is a load base only.
- [ ] Cut from the lower of the proposed and the derived-from load: a return week never carries a progression.
- [ ] Return week's logged loads are next week's baseline; a deload's are not; after recovery, sets restore at the load the return week logged, never up.
- [ ] Illness: `ill` day in the gap caps every set of the first session back at RPE 7, whatever the gap; block until 48 h symptom-free is confirmed; whole-body symptoms route to a professional (rn:detraining-return.4).
- [ ] Prescription never carries a load forward past the band its days off fall in; a decayed line is valid only when band, load ≤ cut(base), sets and RPE cap all agree.

### Core loop: loads, kit and the dumbbell model

- [ ] Eight load modes (total, per_hand_x2, single_implement, bodyweight, assisted, band, duration, distance); band/duration/distance carry no load.
- [ ] Dumbbell two numbers: per_hand_x2 → Hevy total = 2 × per hand, displayed `25/hand (Hevy: 50)`; single_implement = one number; assisted stores assistance as the Hevy weight; `hevy_kg` = round(total × 0.45359237, 4) for lb.
- [ ] Round trip Hevy kg ↔ athlete unit exact for all loaded modes; unit and ×2 arithmetic live only in the Load type; a corrected mode re-expresses every stored load with an explicit basis.
- [ ] Kit rounding: barbell loads from plate combinations per side, fewest plates; dumbbell and kettlebell racks are enumerated loads; machine/cable grid from 0; smith/EZ/trap bars from a declared base mass or `load_geometry_unknown`; dip-belt loads from single plates; a cap excludes rack loads.
- [ ] Rounding direction: a cut or hold rounds to the nearest kit load no heavier than the target (ties lighter); assistance rounds the other way (more assistance = easier); a step-up rounds nearest; a kit that cannot go lighter holds the load and says so; a cap is never crossed.
- [ ] Increment precedence location > main > catalogue; scheme increments request a step, never define the grid; a historical off-grid load is never an anchor.

### Core loop: schedule, rotation and planned sessions

- [ ] Program model: sessions with kind, tier, status and optional location; one exercise per session line with set groups (reps xor range; warm-up pin by load xor percent); start loads per hand in athlete units; external (coach-led) sessions with weekday and estimated sets; a schedule rule; `hard_weeks_ceiling` 4–8 (rn:deloads.3).
- [ ] Schedule rules: fixed weekdays, explicit calendar, next-in-sequence, alternating template anchored on an external session; a rotation position that is not confirmed is flagged, never silently assumed. Infer it from the coach-led log, then the program's position, then the newest check-in, and state it for confirmation.
- [ ] Planned sessions exist only from adoption on; a midweek adoption plans only the days left; a replaced program never reaches back.
- [ ] A moved session is planned once, on its new day; a pending move leaves no miss on the old day.
- [ ] Coach-led sessions: planned by weekday; recorded minutes/RPE/modality override the defaults (60 min, RPE 6) field by field (rn:running-load.7); modality `lifting`/`mixed` sets the last lifting date, `conditioning` is a quality activity; a trainer cancellation is not a miss and removes the obligation.
- [ ] Status days: ill, injured, travel, open-ended spans, withdraw not delete; `no_training` breaks pause the hard-week count but still count as days off.
- [ ] Session time caps per session or athlete default; estimated duration flags over-cap sessions (constants are guesses).

### Core loop: hard weeks, fatigue triggers, deload ceiling and skip rule

- [ ] Session gate: ≥ 2/3 of prescribed working sets logged and mean logged RPE no more than 1.5 below target (missing RPE counts as on target); coach-led passes when it happened (rn:deloads.11). Decide explicitly what a session with zero prescribed working sets does (the old code passed it).
- [ ] Completed hard week: ordinary week with ≥ 75 % of planned core + coach-led sessions passing the gate → count +1 (rn:deloads.2).
- [ ] Reset: light week, return week, or < 50 % trained → block ends, count 0; 50–75 % neither counts nor resets; one-off, minimum and break weeks pause (rn:deloads.2, rn:deloads.13). A partial break prorates the planned set.
- [ ] Week kind precedence is one deterministic order (break, light, minimum, one-off, layoff, illness).
- [ ] Ceiling: count ≥ `hard_weeks_ceiling` (default 6, 4–8) proposes a light week whatever else is true; declined at the ceiling → re-proposed at the next close (rn:deloads.3).
- [ ] Four triggers: reported readiness; compound RPE drift two exposures running (each set vs its own prescription, no extra/heavier/longer sets, after an earlier steady exposure at the prescription, never inside deload/light/return work; two drifts with no baseline = calibration, not a trigger) (rn:autoregulation.4); a niggle `aggravated` inside the week or still aggravated on day one; measured sleep ≥ 4 of the last 7 nights under 7 h with ≥ 4 nights of data (tracker or diary; "felt fine" is readiness). Two → propose; one → watch; a run spike → review, never a trigger (rn:deloads.5).
- [ ] Skip rule: two triggers below 3 completed hard weeks → `skipped (<n> hard weeks)` (rn:deloads.4).
- [ ] Light-week type: ceiling or drift/niggle → deload (2/3 sets, loads −10 % target rounded to kit, RPE 6); readiness/sleep only → light (2/3 sets, loads held, RPE ≤ 8); the coach may override with a reason (rn:deloads.8–10).
- [ ] Illness in a low week proposes a return week only when days off > 10; otherwise the RPE 7 cap is the whole return.
- [ ] Recovery ceilings: a niggle cap, deload/light/return RPE or the illness cap lowers the proposed load to what the e1RM model allows at that RPE; logged sets over a cap flag `recovery_ceiling_exceeded` and are excluded from drift.
- [ ] Deep review due when the last deep review is ≥ 42 days old, a light week is newly proposed, adherence requires a restructure, or a catch-up deferred it (rn:deloads.12).

### Core loop: concurrent training

- [ ] Lift and a quality activity on one day: lift first, ≥ 6 h gap; untimed bouts get an info, not a warn (rn:concurrent-training.4).
- [ ] No quality activity ending < 24 h before a heavy squat/hinge session (working set RPE ≥ 7, or ≤ 6 reps with no RPE; a range read by its start) (rn:concurrent-training.5).
- [ ] Easy activities never collide; rules flag, never move or drop (rn:concurrent-training.6). Quality = kind conditioning, or logged session RPE ≥ 7, or the matched plan says so, or the name does (rn:running-load.6).
- [ ] Cardio flags: run > 1.10 × longest run in 30 days once ≥ 14 days of history (rn:running-load.1, .4); quality cap 2/week (rn:running-load.5); two quality bouts on the same or consecutive days.
- [ ] An optional conditioning session is dropped on sleep debt, a status day or a quality stack; a core session is kept with a warn.

### Core loop: progression schemes and evidence

- [ ] Double progression: hold the program's sets, range and RPE; add the increment only when every working set hits the top of the range at or under target RPE; a set ≥ 2 RPE over or below the range bottom flags a mismatch (rn:progression-training-age.2).
- [ ] Linear: a short attempted set is a miss, an unlogged set is incomplete, not a miss; at the miss limit reset to 90 % rounded to kit and start a new count once a lighter exposure is logged.
- [ ] RPE-anchored: top set from e1RM at target reps and RPE floored to the increment; back-offs at top RPE − 1 or a percent, never above the top set; no e1RM → hold, provisional (rn:progression-training-age.6, .8).
- [ ] 5/3/1 wave: TM 90 % of e1RM, 65/75/85, 70/80/90, 75/85/95 %, deload 40/50/60 %; last set rep-out capped RPE 9; a week completes only when logs match its 3 wave sets at that TM; 3 completed weeks raise TM 2.5/5 kg (5/10 lb) (rn:progression-training-age.9).
- [ ] Assistance ladder: up one rung when every set hits target reps at or under target RPE; a return steps 0/1/2/3 rungs back by band, never a load cut (rn:bodyweight-skill-progression.3).
- [ ] Maintenance: newest valid exposure's top load, never higher (rn:minimum-effective-dose.1). Baseline = newest exposure neither excluded, suspect nor from a deload week; unknown historical prescriptions are never filled from today's program.
- [ ] e1RM only from a set of ≤ 12 reps to failure (reps + 10 − RPE) in a 42-day window; bodyweight/assisted e1RM is total system mass from a weigh-in within 14 days; dumbbell single-leg variants give no e1RM (rn:autoregulation.5).
- [ ] Feasibility: implied RPE > 10.5 at the fewest reps allowed = unearned load; an RPE target with no whole rep count within ±1 is infeasible; a recovery ceiling flags only when > 1 too hard; without an e1RM a top load > 2 increments above the newest exposure is unearned (rn:autoregulation.6).
- [ ] Stall: 3 exposures at equal sets with no gain on any metric → `stalled`; deload/return exposures skipped.
- [ ] Per-line pipeline, each step applied once: scheme → standing override → decay (days off > 10) → transform → constraints (strictest binds) → caps → RPE ceilings → rounding → warm-ups (60 %; 50/75 %; 40/60/80 %).
- [ ] Standing overrides: newest active wins; `until` default 4 weeks, max 8, judged on the session's date; kept sets re-derived only through decay/transform/constraints/caps/rounding; withdrawal stops it.
- [ ] A "choose the load" line is an explicit flagged state, never a silent null; coach line guidance and week focus survive a re-plan.

### Core loop: minimum dose, structure and adherence

- [ ] Fractional sets: direct 1, indirect 0.5; a hard set is a working set not at RPE ≤ 5 (rn:volume-frequency.2, rn:proximity-to-failure.5).
- [ ] Weekly range 10–20 hard sets per muscle; per-session ceiling 11 fractional sets (warn planned, info logged); undershoot judged on the cycle average and on delivered dose in ≥ 3 of the trailing 4 ordinary weeks (rn:volume-frequency.1, .3).
- [ ] Dose targets 0–40 per muscle; default 10 for primary muscles of active core lifts under a hypertrophy or null goal; the nutrition phase never selects a lifting goal; ≈ 60+ lifters keep more (rn:minimum-effective-dose.2).
- [ ] Priority lift floor: 2 hard sets at the prescribed load in a disrupted week, tried after the program's missed-day rules, topped up never above the prescription; unplaceable → flagged (rn:minimum-effective-dose.4).
- [ ] Missed-day rules: fold (default 2 sets, never more than prescribed, at prescribed load and the lower RPE), shift to the first free listed weekday inside the span, skip, or ask the athlete (move-to or drop) (rn:minimum-effective-dose.5).
- [ ] Minimum week: ≤ 2 standby sessions within time caps, every priority floor present, each muscle ≥ 1/3 of the ordinary programmed fractional dose including coach-led estimates (rn:minimum-effective-dose.1, .6).
- [ ] Adherence = trained/planned over the trailing 4 ordinary weeks (coach-led in; optional, unconfirmed, cancelled out; shortened sessions count); ordinary excludes break, light, minimum, constrained one-off, layoff and illness weeks; < 4 weeks → insufficient.
- [ ] < 70 % → present a smaller schedule with the same weekly hard sets per muscle; < 80 % → block any new recurring session (swaps fine) (rn:deloads.6, .7).
- [ ] Against-the-prescription report, separate from the gate (effort ±1.5 RPE, reps missed, RPE missing); streak and consistency leave illness and break weeks out with a reason.

### Core loop: Hevy push, approval and write safety

- [ ] The client holds a hard allow-list of write endpoints (routines PUT/POST, routine folders POST, exercise templates POST, workout POST); anything else raises. Permission config denies non-GET on `/v1/workouts*`. The old client had no allow-list and its docs instructed a workout PUT: close this before cutover.
- [ ] Every non-GET request appends one audit line (method, path, status, routine id, plan id, plan hash, body digest), success or failure, after retries; writes refuse to run without an audit path.
- [ ] API key only in the header; scrubbed from every error, envelope, cache and audit line; environment wins over `.env`.
- [ ] 401/403 → exit 5 naming the key; timeout/unreachable/5xx → exit 4; other 4xx → validation with status; 429 → wait 30 s, give up after 3; writes throttled (burst then 1 per 3 s).
- [ ] The athlete approved exactly what gets pushed: the write binds to the hash (or version id) of the reviewed plan; a mismatch refuses before any request. The agent cannot self-approve.
- [ ] Optimistic concurrency: GET every routine in the span first; refuse before any PUT if any live `updated_at` differs from the cache, with no bypass flag.
- [ ] Per routine in order: PUT, GET back, diff by position (weight within 0.001 kg, absent == null, swapped template = structural); a differing read-back stops the run, logs `verified: false`, exits 1; later routines `not_reached`; a re-run after success sends nothing.
- [ ] Guards that survive the single-plan-record design: no approval; span ended; an unresolved `block` flag; app edit since cache; read-back differs; invalid reuse choice; retire target missing from cache.
- [ ] Routine body: `weight_kg` is the load's `hevy_kg` only, none for null or unweighted bodyweight; a line without a template id is an error; no nulls, no routine-level notes.
- [ ] Routine note per exercise: absolute `Target:` (equal sets collapse to `N×reps`, rep-out `5+ (stop at RPE 9)`, `choose the load` once), `Focus:`/`Cues:`; the first exercise carries the week line because Hevy drops routine notes on PUT.
- [ ] One routine per session: create a missing routine, reuse a free spare, never take a spare mapped by another session; ids recorded only after a verified write; retire = rename `(unused)` keeping exercises, never DELETE, only after the span ended and no live plan carries it.
- [ ] Preflight before approval (unresolved templates, unmapped sessions, orphans); a dry run of every writing verb writes nothing and matches the real run.
- [ ] Drift: a routine whose cache differs from the plan in force warns; the card tells structural app edits (keep-or-replace) from load edits (fact) and flags a plan never written.
- [ ] Fixture transport refuses every write; recorded fixtures use GETs only and are anonymised.

### Core loop: history import and corrections

- [ ] Incremental pull with a 10-minute overlap, full pull on demand, a cache age check; imported workouts are append-only and a Hevy deletion becomes a tombstone (the old mirror followed deletions: do not reproduce).
- [ ] Per-set load resolved once with the mode in force (annotation > plan > library); re-resolve only through an explicit rebuild; unknown exercises keep a null id and warn.
- [ ] Corrections are annotations applied on read (discount, repair, load mode, unknown convention, confirm, miss, external, trained-unlogged) with stable ids never reused, withdrawn by a later annotation, never written into imported rows and never sent to Hevy; a repair changes e1RM and leaves the import alone.
- [ ] Exposure = exercise in a resolved workout with a working set left after annotations; suspect and excluded flags; last lifting date counts coach-led lifting; cancelled is not a miss.
- [ ] Manual log (Hevy off): prefill fixed reps and loads only, ask for range reps, RPE and chosen loads, never invent RPE; refuse unchanged ranged drafts, rep-outs below minimum, future dates, unit or mode mismatches; same day needs an explicit repeat; void appends with a reason and removes from history; a stale copy never resurrects a voided workout.

### Core loop: check-in, ledger and research citations

- [ ] Due = last review + cadence (7 days); catch-up when the gap exceeds the first return band (10 days), which defers the deep tier to the next check-in; first due date anchors to the earliest known start.
- [ ] The card as data: fields in a fixed order, inapplicable fields dropped, prefill states what data knows and asks only what it cannot; e1RM rows compounds first; athlete notes quoted verbatim, never auto-classified as niggles; the deep tier adds misses by tag since the last deep review.
- [ ] Catch-up proposes the return week from the band and tags each untagged missed core session with one annotation.
- [ ] Decisions ledger: kinds override / adherence trigger / light week / training max; outcomes adopted / declined / deferred with a revisit date; computed status; never deleted; stable ids. `contradicts rn:<ref>: <reason>` becomes a typed decision field.
- [ ] Follow-ups: stable ids, review dates, events raised/deferred/kept/resolved/dropped; due ones surface in planning and the card; a deep check-in must give every open one a disposition.
- [ ] Niggles: stable ids, statuses aggravated/watching/easing/resolved/chronic, one history entry per report day with back-dating bounded by the newest entry and today; standing and flare load constraints (patterns, exercises, activity kinds; strictest binds; chronic always applies); three consecutive aggravated/watching entries or a worsening → recommend a qualified professional.
- [ ] Flags: typed `{code, severity info/warn/block, scope, params}` with a stable key from the condition (not the message), resolve by key; `block` refuses a push; run mode downgrades structural flags to info, never `block`.
- [ ] Research notes as data: sources, numbered claims with basis and status, `review_by` ≤ 24 months; `rn:<note>.<n>` resolves only to a current claim; expired → rationale says "evidence under review", nothing blocked; local notes may supersede template claims; rehab notes carry the professional-assessment line. Every threshold in code carries its claim ref.

### Outside the core loop (class (a), scheduled by the v1-scope decision)

- [ ] Protein: reference mass FFM > goal weight on a positive high-body-fat cue (> 25 %/35 %, BMI ≥ 30, goal ≥ 10 % below) > bodyweight; target 1.6 g/kg (2.0 FFM), stretch 2.2, minimum 1.2; floor = recent intake + 15–20 g clamped to [minimum, target], raised by 10 g only after two consecutive readings at or above it; app target below the floor flags; three unmeasured readings prompt calibration (rn:protein-energy-deficit.3–.9, .17–.20).
- [ ] App user gets no calorie number from the repo; a dated override expires ≤ 21 days with an exit condition and flags a second renewal; no-app estimate = Mifflin–St Jeor × PAL + phase rate × 7700/7, rounded to 50 (rn:protein-energy-deficit.13–.16).
- [ ] Bodyweight: one observation per date (wellness > Hevy > reading), trend over ≥ 14 days on one basis, a ±0.45 kg/week drift at maintenance is a review. Dieting sleep gate: 14-night mean < 7.0 h → recomp (rn:sleep-dieting.3, .4), distinct from the fatigue trigger's 4-of-7 rule.
- [ ] Exercise library: catalogue + instance overrides, custom ids prefixed, Hevy muscle set with delts split, unique aliases/titles/template ids, substitutes exist; confirmed load mode only (a proposal never counts); seed heuristic from Hevy exercise type, title and equipment; writes never overwrite a confirmed mode; per-exercise increment per unit; avoid with reason.
- [ ] Program import from Hevy: top working load kept, differing-rep sets split, retired routines skipped, notes → cues, assisted lines from least assistance, unconfirmed mode refuses; every source adopts through one draft path; starters fit stated minutes, swap kit, never swap in an avoided or aggravated-niggle exercise.
- [ ] Activity: append-only records with content hashes, read-time dedup within 15 minutes, Apple Health export adapter; recipe card macro and ingredient rules; meal plan totals, floor and slot flags, shopping batches.
- [ ] Strict TOML config; both dumbbell numbers shown only when Hevy is on; `--dry-run` on every writing verb; disabled features exit 5 naming the key.

## The table

| Behaviour | Class | Reason |
| --- | --- | --- |
| **Return bands and #257** | | |
| Bands 0–10 / 11–21 ×0.95 −1 / 22–42 ×0.90 −1 / 43+ ×0.85 −1, RPE ≤ 7, re-test (rn:detraining-return.3) | a | The layoff rule; every number traces to the claim |
| Days off = max(layoff, exposure age − interval); interval = median of ≤ 4 gaps clamped 7–14, grace 10 (rn:detraining-return.1) | a | A stale lift decays without a layoff; clamps are stated heuristics |
| Set cut floor max(1, min(prescribed, derived) − 1); borrowed exposure is a load base only | a | Stops a light session elsewhere thinning a slot |
| Cut from the lower of proposed and derived-from load | a | A return week never progresses |
| #257 fix: `start_load` skips recovery prescriptions when cutting; else last approved line holds | a | The invariant (cut once from the pre-layoff base) is right; the branch is a patch, store the anchor instead |
| Pre-layoff base borrowing from any slot dated on or before the layoff; sibling session keeps its approved line | a | Proposal and validator must share one base |
| 43+ "re-test": next week's loads from what was logged | a | Only the generic baseline rule in code; make it explicit |
| Return week logs are the baseline; deload logs are not; recovery `hold` never rises | a | Return ≠ deload |
| Illness: RPE 7 cap on first session back, block until 48 h symptom-free confirmed (rn:detraining-return.4) | a | Safety rule with a claim |
| `stale_prescription` arithmetic (band, load ≤ cut(base), sets, cap) | a | Validity check of a decayed line |
| `stale_prescription` inferred provenance and `--write` flag merging | b | Exists because overlays are hand-edited JSON |
| Capacity series "as-of": a later approval never reclassifies stored provenance | b | Replaying mutable files over history |
| **Loads, kit, dumbbells** | | |
| Eight load modes; band/duration/distance carry null load | a | Domain vocabulary |
| Load object `{mode, unit, per_hand, hevy_total, hevy_kg}`; per_hand_x2 doubles; `25/hand (Hevy: 50)` | a | How Hevy stores dumbbells |
| `hevy_kg` 4 dp; `from_hevy_kg` rounds to 3 dp before halving; round trip exact 0–142.5 | a | Conversion fidelity |
| `check_load` recomputes and names the field that disagrees | a | Self-checking arithmetic |
| Assisted prints `BW-20 assist (Hevy: 20)` | a | Keep the semantics; the duplicate number carries nothing |
| `format_load` ≤ 2 dp, half-up, no unit; `rep_range_text` | a | Display helpers |
| `convert_mode` and `reconcile-mode` with an explicit basis (old or confirmed) | a | A mode correction must settle stored loads |
| AST ban on `*2`, `/2`, `0.45359237` outside `units.py` | b | A typed Load with one constructor gives the guarantee |
| `round_to_increment` nearest/up/down; grid anchored at a base mass with cap | a | Kit maths |
| Plate breakdown by combination, fewest plates; dumbbell/kettlebell racks as enumerated loads; dip-belt single plates | a | Kit facts |
| Increment precedence location > main > catalogue; kettlebell grid independent; scheme increments never define the grid | a | Separates progression step from available load |
| Smith/EZ/trap base mass declared or `load_geometry_unknown`; zero is known | a | Disclose, never guess bar mass |
| Kit-less equipment takes the requested load, capped only by `[caps]` | a | No facts, no snapping |
| Direction-aware rounding (cut/hold lighter, assistance up, step-up nearest, held load on coarse kit rounds down, `load_cut_held`) | a | Progression lands on a load that exists |
| Ladder rungs exact; off-kit rung flagged not snapped | a | Rung is the unit |
| Historical off-grid load is not an anchor | a | Sensible |
| `load_caps` check: per-exercise cap beats `dumbbell_max` | a | Real ceiling |
| `bare_hevy_values` prose parser (~420 lines) and the per-hand `--reason` regex | b | Exists only because loads lived in prose; typed loads remove it |
| Readable-number helpers (`whole`, `signed_whole`, RPE gap in words) | a | Cheap, athlete-facing |
| Readable-number exact-sentence tests | c | Lock copy |
| **Rotation, schedule, program, status days** | | |
| Program document and validation (dup ids, exercise once per session, timed modes, locations, mode ≠ confirmed) | a | The program model |
| Session id `program` reserved (page name clash) | b | File-layout artefact |
| Routine pages rendered from program.json + `routine_render_fresh` | b | Stored projection |
| Program warnings `fixed_reps_no_e1rm`, `priority_no_e1rm`, `e1rm_scheme_unsupported` | a | Real e1RM limits |
| State: `program_adopted` never moves forward; rotation {position, confirmed}; scheme state per slot | a | Adoption gates planning; rotation is state |
| Four schedule rules; `rotation_unconfirmed` until confirmed | a | Confirm, never assume |
| Rotation inference order (coach-led log → program → newest check-in) | a | Prose only in the old system, no code or test; implement it |
| Planned sessions from adoption on; midweek adoption; replaced program never reaches back | a | Fair adherence |
| Moved session planned once; extra session is a second planned session | a | Counting rule |
| Miss/trained-unlogged annotations re-targeting a moved copy | b | Patch over overlay `moved_from` |
| Coach-led detail overrides field by field, labelled default; cancellation semantics; modality | a | Real PT semantics (rn:running-load.7) |
| Status days (ill/injured/travel, spans, withdraw, `no_training`) | a | Real rules (rn:deloads.13) |
| Session time caps; duration estimate (reps×4 s + rest + 60 s/exercise + 300 s, scaled 0.7–1.5) | a | Useful; constants are guesses |
| "Recovery windows either side of an edited day" | c | Prose only; covered by quality_stack and the interference rules |
| **Hard weeks, triggers, ceiling, skip** | | |
| Session gate 2/3 sets and RPE delta ≥ −1.5; coach-led passes when done (rn:deloads.11) | a | Fatigue count, not compliance |
| Gate passes when prescribed working sets = 0 | a | Decide explicitly; old behaviour was accidental |
| Against-prescription report (effort ±1.5, reps missed, RPE missing) | a | Distinct signal; one 1.5 constant |
| Hard 75 %, low < 50 %, partial between, nothing-planned = partial (rn:deloads.2) | a | The count |
| Paused kinds one-off / minimum / break; partial break prorates (rn:deloads.13) | a | Keeps disrupted weeks out |
| One-off overlay only on break days is not a one-off week | b | Precedence between two overlapping stores |
| Light or return week ends the block; decayed line with no layoff is not return | a | Block boundary |
| Kind precedence break > light > minimum > one_off > layoff > illness | a | One order needed; the order is a choice |
| Ceiling default 6, 4–8, proposed whatever else; declined → again next close (rn:deloads.3) | a | Core |
| Four triggers, 2 → due, 1 → watch, 0 → none (rn:deloads.5) | a | Core |
| Skip below 3 hard weeks (rn:deloads.4) | a | Core |
| Trigger → type map (deload vs light), coach override with reason | a | Reasonable |
| Deload 2/3 sets, −10 %, RPE 6; light 2/3, held, RPE ≤ 8; return −1 set, RPE ≤ 8 (rn:deloads.9, .10) | a | Concrete prescriptions |
| RPE drift definition with steady baseline and calibration fallback (rn:autoregulation.4) | a | Avoids flagging mis-set loads |
| Niggle trigger dated inside the week; later resolution never erases it | a | Event-dated |
| Measured sleep trigger 4 of 7 nights < 7 h, ≥ 4 nights data; period means count for no night | a | Measured vs felt |
| `--sleep` override with reason, source enum and migration | b | Override fine; enum/migration is shape |
| Run spike never a trigger | a | Explicit non-rule |
| Recovery ceilings lower loads via the e1RM model; breaches flagged and excluded from drift | a | Constraint propagation |
| Illness in a low week → return week only when > 10 days off | a | Sensible |
| Illness week: adherence skips, block classes, travel alone is neither | a | Separates "trains the plan" from "was ill" |
| Deep review at 42 days, newly proposed light week, restructure, deferred catch-up (rn:deloads.12) | a | Timing rule |
| `repeated_decline` walk to suppress a repeat deep flag | b | 30 lines over two stores; a snooze date does it |
| `block decide` state machine (declined needs reason, agreed week refuses a second decision until withdrawn) | b | Mechanics over decisions.json; keep the decision kinds |
| Re-close semantics (newest replaces, undoes block end, older exits 1) | b | Closes are stored projections |
| `block init`, `state.deload` migration, ledger v1→v3 migrations | b | Migration path |
| `block_state` drift check; `light_week_overlay` cross-store warn | b | Two copies of one truth |
| Status line rendered verbatim into program.md; Watch sentences; "Light — " title wording | c | Prose assertions |
| **Concurrent training, cardio, conditioning** | | |
| Same-day lift first + 6 h; untimed → info; across midnight elapsed (rn:concurrent-training.4, .6) | a | Rule |
| Quality < 24 h before heavy lower; 22 h warn, 26 h none; untimed warn (rn:concurrent-training.5) | a | Rule |
| Easy never collides; rules flag never move; empty list turns off; refresh keeps identical flag's resolution | a | Sound |
| Bout timing: end = end or start + minutes; default minutes never time a bout; DST-safe | a | Correct |
| Quality precedence kind → RPE ≥ 7 → plan → name | a | Cardio identity |
| Session-RPE load with method ladder, information only (rn:running-load.2, .3) | a | Figure is real; "no threshold" sentence tests are (c) |
| Cardio flags: cap breach, spike 1.10× in 30 d after 14 d, quality stack, sleep debt, status active, niggle link | a | Cited defaults |
| Reconcile planned vs logged with a 7-step tie-break ladder and 36 identity tests | a | Keep explicit link + nearest date within 3 days + ambiguous; drop the rest of the ladder |
| Conditioning schemes emom_density and circuit_rounds with step/cap/decay | a | Reasonable; constants are config |
| Drop rule for optional conditioning; core kept with warn; restore | a | Autoregulation |
| **Progression schemes and evidence** | | |
| Double progression with mismatch flag at ≥ 2 RPE over (rn:progression-training-age.2) | a | Core scheme |
| Linear misses, incomplete exposure, 90 % reset, new count after a lighter exposure | a | Intricate but sound |
| rpe_anchored top/back-off rules; no e1RM holds | a | Standard |
| wave_531 numbers, completion gate within 1 increment or 2.5 %, TM raise, deload, decay keeps TM | a | Faithful 5/3/1 |
| assistance_ladder up ≤ 1 rung, decay by band in rungs, override onto a rung | a | Right lever |
| maintenance scheme | a | Simple (rn:minimum-effective-dose.1) |
| Stall after 3 flat exposures; deload/return skipped | a | Honest signal |
| Baseline selection (not excluded, suspect or deload-week); history matched per slot, e1RM exercise-wide | a | Clean evidence |
| Unknown historical prescriptions never filled from today's program | a | Prevents invented misses |
| e1RM ≤ 12 reps, 42-day window, veto by newer easy work, total-system mass for BW/assisted, 14-day weigh-in | a | Keeps the model honest (rn:autoregulation.5) |
| Feasibility 10.5 / ±1 / recovery > 1; no-e1RM 2-increment guard (rn:autoregulation.6) | a | Cites a heuristic claim; treat as policy |
| Transforms deload/light/return | a | (rn:deloads.9) |
| Pipeline order, each step once | a | The order is the policy |
| RPE ceiling changes the load; `rpe_ceiling_unchecked` with no estimate | a | A cap must bind |
| Standing override semantics (until 4/8 weeks, newest wins, withdrawn stops) | a | Coach override |
| One-week override kept on midweek rebuild only if the approved overlay carries it | b | Approved overlay vs draft coexistence |
| Scheme state `pending` → promote on matching hash; `state_basis` hash refuses finalize after a TM change | b | Pending/promote dance between files |
| Draft lifecycle (stale, rebuild keeps resolutions, discard, finalize exit 1/3) | b | Hand-edited drafts vs `.proposed.json` |
| First-load `no_data` auto-resolution with dated English messages | b | Flag bookkeeping over a draft file |
| Flag identity includes `message`; band-only message to keep keys stable | b | Key on the condition |
| CLAUDE.md band table matched by regex; "48 h"/"RPE 7" literal ban outside validity.py | c | Wording and one-off duplication guards |
| ~170 rationale sentence assertions ("the kit makes 25/hand") | c | Lock copy; keep target/actual/held as fields |
| Skill-step wording tests in test_validity, test_propose, test_week_rebuild, test_wave_531 and others | c | Skill prose |
| **Minimum dose, structure, adherence** | | |
| Missed-day rules fold/shift/skip/manual by list order (rn:minimum-effective-dose.5) | a | Real recovery |
| Unmatched miss: athlete chooses move-to or drop; apply refuses without a choice | a | Good fallback |
| Priority floor 2 sets after program rules, topped up never above; whole-session shift carries it (rn:minimum-effective-dose.4) | a | Minimum dose |
| Priority KPIs and weekly planned/trained/missed/replaced | a | Reporting that drives coaching |
| Fold-line markers and `overlay_folds_expired`; midweek apply appends three lines under `## Mid-week` | b | Overlay shape leaking; record prose mechanics |
| Minimum week ≤ 2 standby sessions, floors, 1/3 dose (rn:minimum-effective-dose.1, .6) | a | Sound; compare against the cycle average, not name-matched rotation positions |
| Fractional sets, hard set definition, e1RM cap (rn:volume-frequency.2, rn:proximity-to-failure.5) | a | Dose arithmetic |
| Dose targets, fallback 10, pending for strength/maintenance, older-lifter caveat | a | Explicit targets (rn:volume-frequency.1) |
| `session_volume_high` > 11.0 | a | (rn:volume-frequency.3) |
| Weekly balance per rotation position, undershoot in ≥ 3 of 4 weeks, coverage gap for 13 muscles | a | Real check; coverage list is a product choice |
| Adherence definition, ordinary-week definition, < 4 weeks insufficient | a | Denominator |
| < 70 % restructure, < 80 % no new session type (rn:deloads.6, .7) | a | Thresholds |
| `adherence_trigger` suppression windows (4 ordinary weeks, 28 days, revisit_on) and `structure decide` refusals | b | A single snooze date on the flag does it |
| Coach-led planned by weekday, `done` delivers estimated sets, unconfirmed out | a | Whole-week accounting |
| Dry-run and byte-identical re-render tests | b | Harness guarantee, fine as one generic test |
| Skill and CLAUDE.md sentence tests (block, fatigue, missed, draft balance, priority registration, "no pencil") | c | Wording |
| **Hevy client, gate, routines** | | |
| Audit line per non-GET, success or failure; writes need an audit path | a | Durable audit |
| Key hygiene; `.env` with environment winning | a | Secrets |
| Error classes → exit 5 / 4 / validation; no key → exit 5 before any request | a | Drives retry vs fix |
| 429 sleep 30 s, 3 tries; write token bucket; reads never throttled | a | Hevy limits |
| Pagination to `page_count`; cache envelope with schema_version; traversal guard | a | Raw cache is input of record; envelope layout is shape |
| Newer cache schema refused naming framework-sync | b | Template/instance sync artefact |
| `hevy pull` incremental with 10-minute overlap; deleted workouts removed from the mirror | a | Incremental sync yes; removal becomes a tombstone |
| Cache age check | a | Stale data |
| FixtureTransport refuses writes; layered fixtures; recorded fixtures anonymised, GETs only | a | Offline safety |
| No endpoint allow-list in the client; docs instruct `PUT /v1/workouts` | gap | The rebuild's allow-list closes it at the transport |
| Gate: dry run → ASK with a summary; DENY when the dry run refuses or approval missing | a | Human sees what will be written; implement as the plan-apply prompt |
| Gate: bypassPermissions → DENY every Hevy write | a | No self-approval |
| Gate: raw curl/wget/httpie write → ASK | a | Right shape, should DENY on workouts |
| Gate shell scanner (cd, env, `bash -c`, `$(...)`, heredocs, depth 4) | b | Exists because the agent runs arbitrary Bash |
| Settings allow-list tests; PATH_MAP PostToolUse checks; SessionStart 12-line budget | b | Harness plumbing; 12 lines is accretion |
| `test_claude_md_puts_the_session_start_status_first` | c | Documentation word order |
| Intended routine body rules | a | Correct PUT body |
| C12 note format; week line on the first exercise | a | Athlete instruction; week line is a Hevy workaround worth keeping |
| `diff` by position, weight tolerance, prescription vs structural class | a | Read-back and edit detection |
| Refuse before any PUT on a live `updated_at` change, no bypass | a | Optimistic concurrency |
| PUT → GET → diff per routine; stop on first failure; idempotent re-run | a | Verification |
| Exit-3 guards: no approval, span ended, unresolved block | a | Survive as status checks |
| Exit-3 guards: hash broken by an edit, superseded by a later overlay, rebuild of an approved overlay refused | b | One immutable approved record removes them |
| Session → routine resolution split across overlay and state.json | b | One mapping table |
| `routines create`, spare reuse, One-off folder, ids recorded after success | a | Creating missing routines; folder/state placement is shape |
| `--expect-plan` hash binds create and retire to the reviewed preview | a | Approved exactly what gets written |
| `--reuse` refusals (unknown, busy, duplicate, mapped spare) | a | One routine per session |
| Retire = rename `(unused)`, never DELETE, only after span end | a | Preserves history linkage |
| Preflight readiness; approve refuses missing templates | a | Catch unpushable plans early |
| `overlay_hevy_drift` warn | a | Plan vs app drift |
| **Overlay, approval, history, manual log** | | |
| Overlay build resolves every load; validate re-checks arithmetic, exclusivity, flags, duplicate days | a | Core validation; id-collision suffix rule is (b) |
| Null working load only with `no_data`; warm-ups may be open | a | Explicit state |
| Approval = sha256 of canonical doc minus `approval`; any edit breaks it; approve refuses blocks/unconfirmed modes/missing templates | a | The invariant "approved exactly this" stays; hashing a mutable file after approval is the (b) part, dropped |
| Hand-resolved `load_mode_unconfirmed` never satisfies approval; `merge_flags` never carries it | b | Guard against editing JSON past a gate |
| `in_force(date)` layering of overlapping overlays | b | One current plan per span |
| `overlay render --into` regions and `overlay_render_fresh` | b | Stored markdown projection |
| C21 provenance per line (scheme, derived_from, inferred, decay, rationale) | a | Traceability |
| History months frozen; re-resolve only on rebuild; `include_unsynced` reads live | a | Durable record |
| Annotations applied on read, ids never reused, never sent to Hevy | a | Corrections never touch Hevy |
| Exposure definition; suspect/excluded; last lifting date; cancelled not a miss | a | Feeds progression and layoff |
| Load-mode precedence annotation > overlay > library | a | Correct interpretation of old sets |
| Manual log prefill/add/void rules | a | Observed, not prescribed |
| `log add` immediate history sync with `next_step` on failure | b | Projection concern |
| Goal events countdown, agreed window, `event_window_heavy_lower` | a | Domain rule |
| Skill-text tests in test_load_mode_reconcile, test_one_off_load_modes, test_history_skill, test_events | c | Wording |
| **Check-in, ledger, research, checks, pages** | | |
| Due by cadence; deep at 42 days or by reason; catch-up over 10 days defers deep; first due anchor | a | Timing rules (rn:deloads.12) |
| Catch-up card table and four questions; return brief with `lines_digest` match; tag-gap | a | The catch-up conversation |
| Card fields, prefill/ask split, app-edit detection, e1RM rows, verbatim notes, deep misses | a | The product |
| Card parts plugin seam | b | Old module split |
| Record H1 regex, `# Program start`, `unrecognised` kind | b | Markdown parsed as data |
| `checkin skeleton` regions, `--refresh` only on newest record | b | Rendered regions inside prose |
| Nine `*_render_fresh` checks and `render_fresh_sweep` | b | Committed rendered output |
| `checkin_record_words` 600/1000; `checkin_records` title check | b | Prose heuristics |
| `pages plan` / `pages publish --include` commit rules | b | Git as approval ledger; keep "one approval, one atomic write" |
| Three standing pages with `pages_line_ceiling` 60 | b | Render on demand |
| Brief content priorities (Changed 5 then more, priority first, Watch blocks first) | a | What the athlete sees first is coaching |
| Streak and consistency maths | a | Adherence the athlete sees |
| Progress page bodyweight weekly means; app trend outranks scale | a | Source ranking |
| Decisions ledger kinds, outcomes, computed status, stable ids | a | Heart of "program with intent" |
| `contradicts rn:` prose convention | a | Make it a typed decision field |
| Follow-ups ids, events, due flag, deep disposition rule | a | Coach's memory |
| Niggles ids, statuses, dated history, standing and flare limits, escalation warn | a | Rehab-adjacent safety |
| Niggle v1→v2 migration "confirm standing limits" question; `--from-profile` import | b | One-off bridges |
| Flag object, registry, severities, `block` refuses push, run-mode downgrade | a | Typed flags |
| `flag_key` on message; `ref` digest; resolve by ref | b | Key on the condition |
| Research note data block, claim status, expiry, local supersession, rehab line, graceful `evidence_expired` | a | Evidence-tracked numbers |
| Citation scope split (framework cites template only) | b | Template/instance artefact |
| `research_render_fresh` | b | Rendered table in the source file |
| Pinned-value tests on `CITES` constants | c | Regression accretion; citing itself is (a) |
| ~15 `*_schema` checks, cross-store id checks, `schema_versions` | b | Validate on write; FKs replace them |
| `env_untracked`, `python_floor`, stdlib-only, 3.11-parse checks | b | Repo hygiene, fine as CI, not as coach checks |
| Migrations registry, backups, mini JSON-schema validator, TOML data-block reader | b | Needed by hand-edited multi-version JSON |
| Workspace identity, `/framework-sync` exclusions | b | Template/instance mechanics |
| Program drafts: one adoption path, `--replace` archives and carries state | a | Audit of what was kept |
| Hevy import mapping rules | a | Real import decisions |
| Starters fit, kit swaps, niggle-aware substitution | a | Starter coaching |
| `config suggest` kit tables; setup ≤ 10 replies; strict TOML | a | Defaults and validation |
| Athlete-facing text rules (both numbers only with Hevy on, no raw JSON, RPE key for beginners) | a | Readable output |
| Guidance carry-over across a midweek rebuild | a | Don't lose coach edits |
| Skill-rule and wiring pins (line counts, named phrases, allow-list, glossary terms) | c | Prompt-file wording |
| Coaching-principles pins: "every numbered line cites an rn:" | b | Useful lint on the engine's constants, not on prose |
| Coaching-principles pins: named phrases present | c | Wording |
| **Nutrition, bodyweight, sleep, meals, activity, library** | | |
| Reference mass and high-body-fat cues (rn:protein-energy-deficit.3, .4, .5, .19) | a | Thresholds with claims |
| 1.6 / 2.2 / 1.2 g/kg, FFM equivalents (rn:protein-energy-deficit.6, .7, .17, .18) | a | The numbers |
| Floor from intake, raise after two readings, `floor_since` (rn:protein-energy-deficit.8, .9) | a | Reachable target |
| App target vs floor flag; unmeasured readings flag (rn:protein-energy-deficit.20) | a | App owns the number |
| Override dated, ≤ 21 days, renewal flagged at 2 | a | Dated departure |
| No calorie number with an app; no-app Mifflin × PAL + phase (rn:protein-energy-deficit.13–.16) | a | Framework rule in data |
| Repo-wide grep that only `calories.py` mentions BMR/TDEE | c | Source lint for a one-off worry |
| Config strictness for the nutrition table | a | Validation is real; the key layout is old shape |
| Bodyweight trend basis, 14-day rate, fallback, fresh series after leaving the app | a | Honest rate |
| Observation precedence wellness > Hevy > reading; `bodyweight record` | a | One dated weight |
| Maintenance drift ±0.45 kg/wk → review via /goals | a | Rule (the test asserts skill prose, (c)) |
| Dieting sleep gate 14 nights < 7.0 h (rn:sleep-dieting.3, .4) | a | Explicit evidence rules |
| Readings series fields, one per date, `days_logged`, staleness flags | a | Data model |
| `nutrition status` brief line and fixed question wording | b | Prose projection |
| Goals publish close-out and freshness | b | Stored pages workflow |
| Recipe card macro gap, density, aisles, variations | a | Structural rules |
| Recipe import drafts a review table, writes nothing | a | Draft-then-review |
| Recipe render regions and index freshness | b | Projections |
| Meal plan template + exceptions + pool; totals; flags; shopping batches; anchors | a | Planning arithmetic |
| Meal plan approval by content hash; rebuild of an approved plan exits 3 | b | Hash of a projection |
| Food profile section parsed from profile.md | b | Prose as data |
| Activity append-only JSONL with hashes; void survives sync | a | Event log |
| Read-time dedup 15 min, source precedence per field | a | Merge rule |
| hevy_conditioning and apple_health adapters; `activity_source_fresh` | a | Adapter contract |
| Wellness file location toggle | b | Storage layout |
| Weekly card asks only applicable fields | a | Context-aware prompt |
| Library catalogue + overrides, custom prefix, muscles, uniqueness, substitutes | a | Core data |
| Confirmed load mode only; checks fail unconfirmed routine/overlay lines | a | The dumbbell rule's source |
| Template-id lookup and seed match order; seed heuristic rows | a | Hevy mapping |
| Library writes never overwrite a confirmed mode; create refuses mapping fields | a | Safe writes |
| Skill/doc wording tests across nutrition, meals, goals, bodyweight, card docs | c | Wording |
| **CLI and harness** | | |
| One JSON envelope, exit codes 1/3/4/5, `main(argv, env, stdout)` | a | The contract to keep |
| `--dry-run` on every writing verb; disabled features exit 5 naming the key | a | Uniform |
| Checks name file, line and JSONPath | b | Useful only while data is hand-edited files |
| Fake Hevy (bumps `updated_at`, drops notes on PUT, 429 after 7 writes, corruptible read-back) and anonymised fixtures | a | Exercises every concurrency path offline |

## Judgements worth flagging

1. **#257 is fixed as a branch, not a model.** The old `start_load` skips recovery prescriptions when cutting. The rebuild stores the pre-layoff anchor once per layoff and cuts from it; idempotence then follows from data. Regression test: propose, approve, rebuild and re-plan midweek a 43+ line; the load is unchanged.
2. **The approval hash is an invariant, not a mechanism.** Keep "the write binds to exactly what was reviewed". Drop the hash over a mutable JSON file and the four guards that exist only because the agent can edit that file after approval.
3. **Rotation inference has no code behind it.** The old system claimed coach-led log → program → check-in; the schedule rule advanced by calendar weeks and flagged until confirmed. Implement the claim or stop making it.
4. **The gate asks, never denies.** A workout PUT or DELETE was one "yes" away and the docs instructed it. The client allow-list and permission deny are the fix; the Bash scanner is not ported.
5. **Prose tests are a quarter of the suite by file count** and all go: rationale sentences, status lines, skill steps, CLAUDE.md tables, flag messages. The behaviours under them stay as the checklist above.
6. **Two sleep rules share a name.** The fatigue trigger (4 of 7 nights < 7 h) and the dieting gate (14-night mean < 7.0 h) are different rules; name them apart.
7. **Deleted Hevy workouts were removed from the mirror.** The rebuild keeps a tombstone.

Not judged: nothing material. Two rows rest on code reading only, with no test behind them: the zero-prescribed-sets gate pass and the 43+ "re-test" baseline rule.
