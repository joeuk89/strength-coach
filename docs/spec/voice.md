# The Coach's voice

How the coach speaks to the athlete, how a slip is counted, and how the coach reports a bug or
a gap in the system. The rule is one section of the generated athlete `CLAUDE.md`; the skills
restate nothing of it; the transcript benchmark counts what gets through. Decided on wayfinder
map [The coach's voice and reporting system problems](https://github.com/joeuk89/strength-coach/issues/223),
2026-11-07; the mechanism is ADR 0022.

## The rule

Everything written to the athlete is coaching in plain words: what they will do, what changed
and why. Nothing of the system reaches them: no command or verb name, Draft, flag or warning
code, id, file path, commit, exit code or code block, and no narration of what the engine did.
A result is said as what it means for their training, never as what it is called.

The one exception is a shape, not a phrase. When the system limits what the athlete wants, the
coach says so plainly, gives no detail, and may offer to report it ("Reporting"). A plain reason
that names a verb or a path is a leak. The same shape answers a developer question asked inside
the athlete instance: there is one register there, and engine talk belongs in the engine repo.

Where it lives, once: the generated athlete `CLAUDE.md` carries this section verbatim, about 90
tokens, after its bullet list (`instance.md`, "Generated CLAUDE.md"):

> ## The coach's voice
> Everything written to the athlete is coaching in plain words: what they will do, what changed
> and why. Nothing of the system reaches them: no command or verb name, Draft, flag or warning
> code, id, file path, commit, exit code or code block, and no narration of what the engine did.
> Say what a result means for their training, never what it is called. When the system limits
> what the athlete wants, say so plainly without the detail, and offer to report it.

Every session reads the generated `CLAUDE.md`, including the ad-hoc moment with no skill loaded,
where one of the three leak sessions happened. A skill-only rule would miss that class, and a
rule in both places is the duplication the never-list exists to stop (`skills.md`).

## Skills quote figures, never artefacts

Skill text is agent-facing. "The Draft", "the dry run", "the envelope" and a flag code stay in a
skill where they name a source or a signal to the agent. What changes is any sentence that
directs the athlete's view at a system artefact or narrates engine action to them.

The template's fixed closing line becomes, verbatim, in `skills.md` and every skill that carries
it:

> Run the verb's dry run and tell the athlete what it will record, every load quoted from it and
> nothing of the system named; they say yes before the verb records it.

The template's Explain placeholder reads "Every figure comes from an envelope or the rendered
draft, so none is retyped" in place of "is quoted from". The sentences below are the ones the
audit of 2026-11-07 found; the build issue that executes this table rewords these and no other
coaching content (map "Out of scope").

| Skill | Today | Becomes |
| --- | --- | --- |
| `kit`, Ask | "a plate pool they load themselves (bar, adjustable dumbbells, plates and collars), or fixed kit"; "the locking hardware, each implement's bare weight and limit, which hardware each implement uses (collars, screws or none) and whether a handle is loaded as a pair or single"; "the step per implement" | the same facts asked as an athlete would say them: do they load their own bar and dumbbells from a pile of plates, or use a rack and machines; what plates they have and how many, how the plates are held on, what the bare bar and each dumbbell handle weigh and how much they take, whether they load one dumbbell or a pair; for fixed kit, what the smallest jump on each machine is |
| `kit`, Judge | "a schema error is the athlete's answer to fix, never a value to guess" | "a fact the inventory format needs and the athlete has not given is a question for them, never a value to guess" |
| `kit`, Judge | "Say what the new tables reach that the old did not, and what they lose" | "Say what the new kit reaches that the old did not, and what it loses" |
| `kit`, Explain | "The location as it will be written, the rack change in loads, and which planned loads it touches. The athlete sees the files and says yes before `publish` commits them." | "Where they train and what is there, in their words; the rack change in loads; which planned loads it touches. Run the verb's dry run and tell the athlete what it will record, every load quoted from it and nothing of the system named; they say yes before the verb records it." |
| `plan-week`, Judge | "Say which planned loads move and to what, quoting the Draft." | "Say which planned loads move and to what, each load from the Draft." |
| `plan-week`, Judge | "Keep the change as an override with the athlete's reason, or let this week's push replace it; ask which when the reason is not plain." | "Keep the change with the athlete's reason, or let this week's plan replace it; ask them which, in those words, when the reason is not plain." |
| `plan-week`, Explain | "Quote every load and change from the Draft or the dry run; never retype one. Name each override and Decision and its reason in plain words." | "Every load and change comes from the Draft or the dry run; never retype one. Say each change and its reason in plain words." |
| `program`, Ask | "what the last block taught them that the report cannot show" | "what the last block taught them that the numbers cannot show" |
| `program`, Explain | "Quote every load, set count and filled default from the adopt dry run; never retype one. For a revision, lead with what the report says changed and what this version does about it." | "Every load, set count and default comes from the adopt dry run; never retype one. For a revision, lead with what changed over the block and what this program does about it." |
| `onboard`, Explain | "Then the Goal and Phase as the draft states them." | "Then the goal and where they are in it, as the Draft states them, in plain words." |
| `check-in`, Judge | "Cite the exposures or notes it rests on (`coach query`)." | "In the record, cite the exposures or notes it rests on (`coach query`)." |

The check-in card is relayed as one message and its fields are not renamed; the card builder
owns its labels, which are athlete-facing like a rendered page (map "Out of scope"). Every skill
has over 1,400 characters of budget left for the longer sentences (`skills.md`, "Budgets").

The never-list (`skills.md`) gains two rows: a sentence that shows the athlete a Draft, dry run,
flag or id lives in the generated `CLAUDE.md`'s voice section, skills quote figures; an offer to
report, or words for a report that could not be sent, lives in the generated `CLAUDE.md`'s
reporting line.

## A voice leak

A term from the engine's own **lexicon** in athlete-facing text: a `text` block on an
`assistant` record with `isSidechain` false. Tool calls, tool results and subagent records are
not. Every such block is in the denominator, narration before a tool call included.

The lexicon is derived at run time from the engine (`coach` on PATH, or `uv run coach` in the
repo; `--lexicon <json>` overrides it for a session measured against an older engine):

| Class | Source | Matched as |
| --- | --- | --- |
| `verb` | leaves from `coach --help` | the leaf name |
| `flag` | `coach schema --registry flags --full` | the code |
| `record` | `--registry record-kinds` | the kind and its id prefix |
| `view` | `--registry views` | `query <view>` only; a bare "lines" is English |
| `error` | `--registry errors` | the code; `exit` column as "exit code" or "exit 1/3/4/5" |
| `fixed` | the script | `Draft` (capital D), `envelope`, `the store`, `dry run`/`dry-run`, `verb`, `flag`/`flags`, `schema`, `registry`, `read view`, `the engine`, `the repo`, `acknowledgement`, `exit code` |
| `path` | pattern | anything under `.coach/`, `pages/`, `src/`, `export/`; a bare `*.toml`, `*.py`, `*.jsonl`, `*.md` filename |
| `store-id` | pattern | registry prefixes plus `pv-n`, `b-<date>`, `wp-<date>` |
| `hash` | pattern | 7 to 40 hex characters |
| `code` | pattern | any fenced block or backticked span, whatever it holds; a markdown table is not code |

**A link is not a leak.** A URL the athlete uses (the plate-pool set-up or per-line link,
`instance.md`) is stripped before matching, so its kit code and query string fire neither the
`hash` nor the `code` pattern.

The exception needs no exemption: by definition it holds no lexicon term and scores zero.
Developer-register replies inside the athlete instance count. The benchmark runs on athlete
sessions only, reports `leaking_messages` over `athlete_messages` as the headline and
`leak_hits` by class with the matched terms, and the `--md` table shows "Voice leaks" as
`leaking/messages`. The count is a floor: a leak in plain English ("a program amend") is not
seen. The hand-marked `scripts/benchmark/transcripts/README.md` is the reference, and a test
asserts the script's marks on the three transcripts equal it (`benchmark.md`, "Method").

## The ceiling

Two numbers per athlete session, in `benchmark.md`'s Targets:

- **Zero** hits in any registry or pattern class: `verb`, `flag`, `record`, `view`, `error`,
  `path`, `store-id`, `hash`, `code`.
- `fixed` leaks in **at most one athlete message in ten**.

The replay of the eighteen leaking moments under the rule (ADR 0022) left no hit in the heavy
classes and five stray fixed-list words, about one message in six, so the second number is the
target to work toward, not today's figure. If two consecutive milestone re-runs on real athlete
sessions miss the ceiling, the fallback named in ADR 0022 becomes a fresh effort; hooks are
outside this map.

## Reporting

The coach offers to report when the system fails (a **bug**) or cannot do what the athlete needs
(a **Gap**), never when it disagrees with an engine rule: the rule stands and the departure is
recorded (ADR 0020). The athlete approves the exact issue text; the coach never reads the body
aloud.

The one line, in the generated athlete `CLAUDE.md` beside the voice section and nowhere in a
skill (agent-facing, so it may name the verb):

> When the system fails or cannot do what the athlete needs, offer to report it: write the report
> as a Draft, run `coach report <draft>`, and tell them in plain words it is written and waits
> for their yes; the prompt shows them the exact text. Only a bug or a gap is reported, never a
> disagreement with a rule. If it cannot be sent, say so without the detail and that it is kept;
> the Draft stays for a later try.

### The verb

`coach report <draft> [--dry-run]`, the seventeenth leaf and the fifth Writing verb, declared
`writes: github`. Its table rows are `verbs.md`'s; the admission reason it meets is "a write the
agent must make that no existing verb can make".

- **Draft**: TOML with `kind` (`bug` | `gap`), `title`, `body` (markdown, developer register,
  athlete data allowed: the repo is public but only the owner and family use it), optional
  `verb` and `code`, validated against the verb and `errors` registries; an unknown value is
  `invalid_argument`, exit 1.
- **Footer**, appended by the engine and never written by the agent: athlete name from
  `profile.md` (the instance folder name if none), engine version, pin, schema version, Python
  and platform, the verb and code when given. Every family instance files with the owner's
  token, so the author is always the owner and the name says who it was for.
- **Labels**: `needs-triage` plus `bug` or `enhancement` by kind, fixed by the engine.
- **Transport**: direct REST, `POST /repos/joeuk89/strength-coach/issues`, through a urllib
  client shaped like the Hevy one (one allowed endpoint, timeout, token scrubbed from every error
  and envelope). No `gh`: nothing on an instance guarantees it, and `gh auth token` would lend a
  full `repo` token.
- **Token**: `COACH_GITHUB_TOKEN`, environment then `.env`, written by `init --github-token`
  beside `HEVY_API_KEY` (`instance.md`, "Secrets"). The owner mints one fine-grained Issues-write
  token and gives it to each instance, so labels stick.
- **Dry run**: repo, title, labels, the full body as it will be sent, and `similar[]`: open
  issues labelled `bug` or `enhancement` whose title shares two or more non-stopwords with the
  Draft's, as `{number, title, url}`; null with a warning when GitHub cannot be read, never a
  refusal. The real run never re-checks. The dry run is the fourth envelope allowed over 6 KB
  (`verbs.md`).
- **Result**: `{number, url, labels}`. No audit file, nothing stored.

### The prompt

The hook runs the dry run and the permission prompt shows the repo, the title, the labels and the
full body (ADR 0006). The body is what the athlete approves, so the prompt is exempt from the
40-line budget and never cuts it. `GATED_WRITES` and `ASKED` gain `github`: the generated
`settings.json` asks on `coach report` the way it asks on `plan apply`, `publish`, `upgrade` and
`init`.

### When it cannot be sent

| Case | Exit | Code | The coach says |
| --- | --- | --- | --- |
| no token | 5 | `github_token_missing` | the report could not be sent and is kept |
| unreachable, or any non-201 (hint naming the token on 401, 403, 404) | 4 | `github_unreachable` | the same |

No detail either way. The Draft stays in `.coach/drafts/` for a later try; nothing else is
written.

## Out of scope

Rendered pages and the check-in card (already athlete-facing; their wording is the renderer's).
The engine's error and warning text (it speaks to the agent). The hooks, including the hook
scanner learning `gh` or `api.github.com`. Coaching content and any skill rewrite beyond the
table above.
