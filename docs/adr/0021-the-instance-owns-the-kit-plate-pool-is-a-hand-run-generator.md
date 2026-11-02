---
status: accepted
date: 2026-10-31
amended: 2026-11-02 by #195 (a plate-pool location names a hardware choice and `single` per implement in place of `collars` and `dumbbells`; the set-up and per-line links take plate-pool format 1's shapes)
supersedes: 0008 in part (ownership, import, the snapshot, the deep link); 0008's rounding, warm-up, cap and frozen-prescription consequences stand
---

# The instance owns the athlete's kit; plate-pool is a hand-run generator whose output the instance commits

The athlete's inventory lives in the instance as `kit/<name>.json`, written in plate-pool's
`inventory.schema.json`, and beside it `kit/<name>.achievable.json`, the achievable-load tables
that `npx plate-pool achievable --inventory kit/<name>.json` emits. A plate-pool location names
its kit; the engine parses the tables file into racks (`core/kit.py`, ADR 0019) and never reads
the inventory, runs Node or fetches anything. Decided on wayfinder ticket
[Who owns the athlete's kit](https://github.com/joeuk89/strength-coach/issues/49), 2026-10-31,
which reopened ADR 0008 after the any-athlete principle (wayfinder #48) made the deploy coupling a
defect: ADR 0008 tied every athlete to their own plate-pool deployment, since plate-pool bakes one
inventory into its CLI, site and `api/achievable.json`.

ADR 0008 rejected this option for two reasons that no longer hold. "The coach would carry a second
copy of plate-pool's inventory schema": it carries none, because it reads only plate-pool's
output, exactly as before. "It would push into a public repo at `publish` time": nothing leaves
the instance; the athlete commits two files to their own repo.

## Considered options

- **The instance owns the kit; plate-pool generates the tables by hand (chosen).** Every athlete
  fact in the instance; the engine stays stdlib and a consumer of a file; plate-pool's inventory
  schema is the contract between the repos. Cost: Node once per kit change, which an athlete using
  plate-pool already has, and which the `kit` skill runs for them.
- **Keep ADR 0008 and make plate-pool multi-inventory.** One deploy per athlete, forever.
- **Port Load, List and Reverse into the engine.** About 1,950 lines of TypeScript whose List is
  a walker over a shared-pool plate search with screw capacity, stack length and uneven
  dumbbells: a second implementation to keep in step, for a question a committed file answers.
- **A `coach kit build` verb that shells to `npx`.** Node becomes a runtime dependency of the
  engine and a fourth seam beside the store, Hevy and the filesystem.

## Consequences

- **Two files per plate-pool location, both athlete-authored** (ADR 0013): `kit/<name>.json`
  and `kit/<name>.achievable.json`. The tables file carries a header the engine reads:
  `format` (the document format number the engine states it parses), `plate_pool` (the version
  that wrote it) and `inventory_sha256` (the inventory it was built from). `[location.<name>]`
  is `kind = "plate-pool"` with `kit = "<name>"`, the equipment-kind map, and one
  `implement.<id>` table per implement it maps, naming a `hardware` choice and, on a handle,
  `single`, which choose the table per implement, hardware and pair; no URL. A grid location
  is as ADR 0008 has it. The two kinds stay: a grid location has no inventory and no tables, so
  one shape would carry two empty halves.
- **Stale tables are a setup refusal.** Every verb that rounds (`plan draft`, `program adopt`)
  hashes the inventory and compares it with the header; a mismatch stops with exit 5,
  `kit_tables_stale`, naming the location and the command to run. Not a warning, because a
  warning lets a plan freeze loads the rack cannot build. `status` reports it. No hash is ever
  stored in the store.
- **No kit import.** The `kit_snapshot` table, the `ks-` prefix, `import --only kit`, the
  plate-pool source of the import-age warning and the kit lines of `import` and `status` go. `import`
  is Hevy's alone. `core/kit.py` keeps its job; `cli` reads the committed file and hands it to
  the service as a value, so no fetch exists anywhere.
- **`frozen_load_off_snapshot` becomes `frozen_load_off_rack`, raised by `plan draft`.** With no
  import there is no moment to compare snapshots; instead the draft checks every frozen load it
  carries forward against the current rack and warns per line. The clearing rule stands: the next
  WeekPlan freezes on the new rack, and a frozen load never re-rounds.
- **Routine pages.** Each plate-pool location gets one set-up link, with the inventory inline in
  the URL fragment (`#inventory=`, raw deflate and base64url; a few kilobytes), that one tap
  installs on the phone. The per-line link names the implement by inventory id
  (`?barbell=175lb&barbell.hardware=collar-clamp`, `?dumbbell.single=` for a single handle) and
  adds the kit's short hash, so plate-pool can say when the kit stored on the device is not the
  one the loads were rounded to.
- **plate-pool's side of the contract** is its issue 52: version `inventory.schema.json` as the
  public contract; an `achievable` command that emits the tables document with the header; a kit
  screen that loads an inventory from the set-up link, a pasted file or local storage, with the
  bundled inventory as a sample and the hash check on every link; and the first npm release.
  plate-pool's own site stays its owner's gym; the engine never depends on it.
- **A fifth skill, `kit`**, owns every location write: it edits the inventory or the grid table,
  runs the generator, explains the rack change and commits on the athlete's yes through
  `publish`. Its When covers the first locations after `coach init`; `onboard` names no skill.
  The athlete says what they bought and says yes; they never run a command.
- **`publish` commits athlete-authored files too** (`coach.toml`, `profile.md`, `kit/`), listing
  them in its dry run, so one asked verb covers the instance's state after a conversation.
- **`init` asks nothing about kit.** It writes `kit/` empty and `[location.<name>]` examples of
  both kinds, commented. The minimum kit for an athlete with one pair of adjustable dumbbells is
  a grid location with an increment and a maximum: no plate-pool, no Node.
- **Cutover.** Joe's instance commits `kit/home.json` copied from plate-pool's committed
  inventory and runs the generator once; the PT's gym is a grid location. Two copies of one
  inventory exist by design: one is a product's sample, the other an athlete's fact.
