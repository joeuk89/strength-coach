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
Where they train, and for each place: do they load their own bar and dumbbells from a pile of
plates, or use a rack and machines. For their own plates: what plates they have and how many,
how the plates are held on each bar and handle (collars, screws or nothing), what the bare bar
and each dumbbell handle weigh and how much they take, and whether they load one dumbbell or a
pair. For a rack and machines: what the smallest jump on each machine is, the bar's weight, the
dumbbells on the rack. A new purchase: what it is, how many, what it weighs.

## Judge
- **Kind.** A place where the athlete builds loads from plates is `plate-pool`; anything else
  is `grid`. One pair of adjustable dumbbells with a dial is `grid` with an increment and a
  maximum.
- **Inventory.** Write `kit/<name>.json` in plate-pool's inventory format 1: `format: 1`,
  `name`, `lengthUnit`, `bore` on each plate type, `stackLength` on each plate but a `block`
  one, `kind` on each implement; no `positions` or `symmetric`. Mark a weight `verified` only when the maker states
  it, `owner` when the athlete weighed it, else `unverified`. Then run
  `npx plate-pool achievable --inventory kit/<name>.json > kit/<name>.achievable.json`; a
  fact the inventory format needs and the athlete has not given is a question for them, never
  a value to guess.
- **Location.** `[location.<name>]` is `kind = "plate-pool"`, `kit = "<name>"`, `implements`,
  and one `[location.<name>.implement.<id>]` table per implement `implements` names. Give
  `hardware` (an id from that implement's hardware options, or `none`) to every implement with
  options, the dumbbell included; never leave it to a default. When the options each reach part
  of the implement's range (one screw to 80 lb, a longer one from 67.5 to 120 lb), give a list
  instead, preferred hardware first, since the first id keeps a load two tables share; add
  `none` to keep the bare handle. Add `single = true` only on a handle loaded single.
- **Map.** `implements` names one implement at the location for every equipment kind the
  athlete's exercises use, or the kind is unsupplied there and `equipment_unsupplied` says so
  at adopt.
- **Rack change.** Say what the new kit reaches that the old did not, and what it loses:
  the bar's top row, the heaviest pair, any load in the plan in force that no longer exists
  (`frozen_load_off_rack` at the next draft).

## Explain
Where they train and what is there, in their words; the rack change in loads; which planned
loads it touches.

Run the verb's dry run and tell the athlete what it will record, every load quoted from it and
nothing of the system named; they say yes before the verb records it.

## Verbs
`coach status`, `coach publish`
