---
status: accepted
date: 2026-10-28
---

# A program version travels as one whole file, an instance has one Program, and the version's kind decides whether the block resets

A new Program version is authored as one TOML Draft holding the entire next version, never as a
patch against the current one. `program show --draft` emits the current version in that form,
the agent edits it, and `program adopt <file>` validates it, fills every default the emphasis
owns, computes the diff against the previous version and records the new one. An instance has
exactly one Program in v1, so nothing ever "starts a new Program"; instead every version carries
a kind, `amend` or `redesign`, and the kind decides what adoption does to the open Block and the
rotation position. Spec: `docs/spec/program.md`.

## Context

The Program version is the one record the athlete may author by hand (ADR 0001). ADR 0002 said
"a program patch travels as a file" without saying what the file holds, and the glossary gave
Program an identity across versions without saying when a new identity begins. The old instance
kept one `program.json`, edited in place, with `--replace` archiving the previous file and a
hand-maintained `status` field on sessions; the diff between two programs was whatever git
showed.

## Considered options

- **Whole version per file, one Program, version kind (chosen).** A diff computed by adopt from
  two stored versions is exact and needs no base hash; a patch language would need a merge rule
  and a way to say which version it patched. One Program per instance removes a question with no
  consumer: nothing in the loop reads Program identity except through its current version. The
  kind puts the one real consequence of "is this a new program" (does the hard-week count restart)
  on the record that causes it.
- **Patch files against the current version.** Rejected: the agent must then know the base and
  the engine must merge; a stale patch lands silently or needs the same hash dance as approval.
- **Several Programs per instance, a new Program on redesign.** Rejected: it duplicates the
  version kind with a heavier noun and makes the Routine map, parked sessions and history
  matching cross a boundary for no gain.
- **Adopt infers the kind from the size of the diff.** Rejected: the block reset is a coaching
  decision with a reason, not a property of how many lines changed.

## Consequences

- `program adopt` takes a path; the Draft is the whole version. The diff and the filled defaults
  are shown in the dry run and derived afterwards from the two version rows, never stored.
- A version row carries `kind` and `because`. `amend` continues the open Block and the rotation
  position; `redesign` closes the Block, opens a new one dated at adoption and restarts the
  rotation at its first week unless `--position` says otherwise. A redesign with an open Block
  warns; it does not refuse.
- Session ids are the stable key across versions. An id the new version lacks is a retired
  session; its routine goes to the Retired folder at the next apply (ADR 0011). Promoting a
  one-week swap is an `amend` whose Draft `program show --draft --apply-plan` writes.
- The schema has one `program_version` table with a sequence number per instance and no
  `program` table beyond a name on the version; no `patch` or `archive` table.
- ADR 0002 is read as "the next version travels as a file".
