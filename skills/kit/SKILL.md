---
name: kit
description: Where the athlete trains and with what. Use after `coach init` when coach.toml has
  no location, or when the athlete reports equipment bought or lost or a new place to train.
  Writes the location, its inventory and its kit tables; the athlete runs nothing. Also /kit.
---

## Read first
`coach status`, for the locations recorded and whether any kit tables are stale. For a change,
the location's `kit/<name>.json` as it stands.

## Ask
Where they train, and for each place: a plate pool they load themselves (bar, adjustable
dumbbells, plates and collars), or fixed kit (a dumbbell rack, machines, a bar with a known
step). For a plate pool: every plate with its count and weight, the locking hardware, each
implement's bare weight and limit, which hardware each implement uses (collars, screws or
none) and whether a handle is loaded as a pair or single. For fixed kit: the step per
implement, the bar's weight, the dumbbells on the rack. A new purchase: what it is, how many,
what it weighs.

## Judge
- **Kind.** A place where the athlete builds loads from plates is `plate-pool`; anything else
  is `grid`. One pair of adjustable dumbbells with a dial is `grid` with an increment and a
  maximum.
- **Inventory.** Write `kit/<name>.json` in plate-pool's inventory format 1: `format: 1`,
  `name`, `lengthUnit`, `bore` on each plate type, `stackLength` on each plate but a `block`
  one, `kind` on each implement; no `positions` or `symmetric`. Mark a weight `verified` only when the maker states
  it, `owner` when the athlete weighed it, else `unverified`. Then run
  `npx plate-pool achievable --inventory kit/<name>.json > kit/<name>.achievable.json`; a
  schema error is the athlete's answer to fix, never a value to guess.
- **Location.** `[location.<name>]` is `kind = "plate-pool"`, `kit = "<name>"`, `implements`,
  and one `[location.<name>.implement.<id>]` table per implement `implements` names. Give
  `hardware` (an id from that implement's hardware options, or `none`) to every implement with
  options, the dumbbell included; never leave it to a default. Add `single = true` only on a
  handle loaded single.
- **Map.** `implements` names one implement at the location for every equipment kind the
  athlete's exercises use, or the kind is unsupplied there and `equipment_unsupplied` says so
  at adopt.
- **Rack change.** Say what the new tables reach that the old did not, and what they lose:
  the bar's top row, the heaviest pair, any load in the plan in force that no longer exists
  (`frozen_load_off_rack` at the next draft).

## Explain
The location as it will be written, the rack change in loads, and which planned loads it
touches. The athlete sees the files and says yes before `publish` commits them.

## Verbs
`coach status`, `coach publish`
