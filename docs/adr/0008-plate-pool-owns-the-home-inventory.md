---
status: superseded in part by 0021 (ownership, import, the snapshot and the deep link; the rounding, warm-up, cap and frozen-prescription consequences stand)
date: 2026-10-26
amended: 2026-10-31 by wayfinder #42 (the load step is the location's alone: a plate-pool location's next row, a grid location's increment per implement kind; no exercise or catalogue increment exists)
---

# plate-pool owns the home inventory; the coach imports its achievable loads and rounds to them

Equipment is modelled per location, and a location is one of two kinds. A **plate-pool
location** (home) imports the achievable-load tables that plate-pool publishes
(`https://joeuk89.github.io/plate-pool/api/achievable.json`) and treats every implement as an
enumerated rack. A **grid location** (the PT's gym) is authored kit in `coach.toml`: increments,
optional base masses, optional dumbbell or kettlebell rack, no plate counts. The engine never
computes a plate breakdown; it rounds to loads that exist and links the athlete to plate-pool
for how to build them. Chosen over the athlete's first lean (the coach store owns equipment and
exports plate-pool's format) because plate-pool is already the specified, schema-checked, tested
owner with a public URL, and the coach needs only its output, not its input.

## Considered options

- **plate-pool owns the home inventory; the coach imports `achievable.json` (chosen).** One
  owner, one calculation, no cross-repo write. Cost: the home location depends on a deploy of
  another repo, so the import keeps a snapshot and serves it offline with an age warning.
- **The coach store owns equipment and exports plate-pool's inventory format.** Keeps every
  athlete fact in one store, but the coach would carry a second copy of plate-pool's inventory
  schema and have to push into a public repo at `publish` time.
- **Port plate-pool's calculation into the engine.** A Python copy of Load, List and Reverse to
  maintain beside the TypeScript one, for a question the published file already answers.
- **Keep the old grid for every location.** No plate counts, no screw capacity, no collar
  weight: it prescribes 125 lb on a bar that reaches 123 or 125.5 with clamp collars, and a
  120 lb dumbbell pair the pool cannot build twice.

## Consequences

- **Location is a noun.** Each session in a program version names its default location; a
  WeekPlan override moves a planned session to another. The load step is the location's alone
  (amended 2026-10-31): the next row of a plate-pool location's table, or a grid location's
  increment for the implement kind; no exercise or catalogue carries an increment. An exercise
  whose equipment kind the location cannot supply is a violation at prescribe time, never a
  silent fallback.
- **Exercise carries an equipment kind** (barbell, dumbbell, kettlebell, leg attachment, vest,
  machine, cable, band, bodyweight); each location maps kinds to its implements (home maps
  weighted bodyweight work to the vest, the gym to a dip belt).
- **Import.** `coach import` fetches the location's URL beside Hevy and stores the snapshot as
  a raw fact with URL, fetch time and content hash. The location fixes which tables apply:
  collars (clamp), uneven dumbbells (off), pair or single. Offline, the newest snapshot serves
  with an age warning, as the Hevy cache does.
- **Rounding at a plate-pool location** selects from the rows of the applicable table, with the
  direction rules of the parity checklist (a cut or hold rounds no heavier, a step-up nearest,
  assistance the other way). The grid model survives only for grid locations and for machines,
  cables and bands.
- **Warm-up sets round to easy loadings.** A warm-up picks the row with the fewest plates per
  side inside a band from 10 percent under the target up to the target, never above; ties go
  lighter, then to the row whose plates contain the previous warm-up's plates, so a ladder adds
  plates and never strips the bar. Work sets never use this rule.
- **Caps derive from kit.** The bar's limit (18 lb plus 210 lb of plates with clamp collars) is
  a row that exists or does not. An explicit per-exercise cap survives only as a safety ceiling
  the athlete sets with a reason (no spotter at home); the old `[caps]` table goes.
- **Frozen prescriptions never re-round.** A new snapshot applies from the next `prescribe`. A
  frozen load no longer in the newest snapshot for its location is a warning on the planned
  session, not a violation.
- **Routine pages carry a plate-pool deep link per loaded line**, built from the frozen
  prescription (`?barbell=175&collars=clamp`; both implements in one link for a superset).
  Nothing about plates reaches Hevy.
- **Pool sharing inside a session is out of scope for v1.** Every line rounds with the whole
  pool free; the superset case is the athlete's at the rack.
