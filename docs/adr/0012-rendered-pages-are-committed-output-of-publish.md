---
status: accepted
date: 2026-10-27
---

# Rendered pages are committed, written only by publish, never read or checked

The weekly sheet, routine pages, check-in records, the athlete page and the progress page are
markdown files committed to the instance repo. `publish` is the only writer: each publish
regenerates every page wholesale from the store, deterministically, and deletes the orphans. No
code reads a page, nothing checks a page for freshness, and nobody edits one by hand. A page is
what the store looked like at the last publish, and that staleness is accepted by definition.

## Context

The old instance committed its pages and then defended them with nine freshness checks, run on
every edit, because a page could lag the data it was rendered from. Historical check-in records
had to match today's renderer, so a wording change forced a rewrite of a two-week-old record. The
review's principle is that documents are output, never input. The athlete reads the pages on a
phone through the GitHub app on the private instance repo; Hevy carries the set-by-set.

## Considered options

- **Committed, regenerated wholesale by `publish`, unchecked (chosen).** Phone access and a
  readable history come free with git. The cost that made committed pages painful was the
  checks, not the files; with one writer that rewrites everything, a stale page cannot survive a
  publish, so there is nothing to check.
- **Gitignored, rendered on demand.** Removes the checks too, but loses the phone channel and the
  history. A hosted site or Notion would have to replace it, a new delivery channel for v1.
- **Committed and frozen per record.** Each check-in record written once and never touched. Any
  renderer change or later annotation then either rewrites history or hides from old pages, the
  exact problem the review named.

## Consequences

- Pages live in one directory, `pages/`, so "delete everything and re-render" is one operation
  and the instance root stays data plus config. `pages/week.md`, `pages/routines/<session>.md`
  (one per active Session, named as its Hevy routine), `pages/check-ins/<date>.md` (one per
  `current` check-in), `pages/athlete.md` (ADR 0009) and `pages/progress.md`. A root `README.md`
  is the GitHub app landing page and points at them.
- Every page is a live view. An old check-in record is regenerated at every publish from its row
  and the store as it stands, so a later match annotation or Hevy import improves it; its read
  stays byte-identical because it is stored text. The git diff of an old page shows what the
  store learned.
- Rendering is deterministic: an unchanged store produces an unchanged page and no diff.
- A retired session's routine page and a superseded check-in's record are orphans and are deleted
  at the next publish.
- A hand edit to a page is overwritten silently at the next publish. There is no check for it and
  no warning. Pages carry a generated header saying so.
- No render verb. Rendering is a step inside `publish`. Previewing a plan before approval is the
  draft's job; whether a read verb prints a page to stdout is for the Verb set.
- Loads on pages are in athlete units with a plate-pool deep link per loaded line, from the frozen
  prescription (ADR 0008). The generated sections of a check-in record are tested against the
  store; the read is never parsed (`docs/spec/check-in.md`).
