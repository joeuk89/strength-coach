# Domain docs

This repo is single-context: one `GLOSSARY.md` at the root and one ADR per locked decision in
`docs/adr/`. Before working in an area, read the glossary and the ADRs that touch that area. The
`mattpocock-skills:domain-modeling` skill, run from `mattpocock-skills:grilling` and the
`mattpocock-skills:wayfinder` map, adds terms and ADRs as they are resolved; nothing creates
them upfront.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a spec paragraph, a test name), use
the term as `GLOSSARY.md` defines it. Don't drift to a synonym the entry avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing
language the project doesn't use (reconsider) or there's a real gap (add the entry through
`mattpocock-skills:domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR 0007 (engine as package and plugin), but worth reopening because…_
