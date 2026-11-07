# How the report verb reaches GitHub

Research note for wayfinder #225, read on #229 (the `coach report` contract): what a verb run
from an athlete's instance can rely on to create an issue on `joeuk89/strength-coach`. Facts
only, each with its source; the choice between shelling out to `gh issue create`, borrowing
`gh auth token`, and calling the REST API with a token in `.env` is #229's. Sources were read on
2026-11-07: the GitHub REST and token docs, the `gh` 2.103.3 manual, and this repo at 0.5.0.

## 1. What an instance can assume is installed

The engine is a Python package with no runtime dependencies, installed with
`uv tool install git+https://github.com/joeuk89/strength-coach`, which puts `coach` and
`coach-hook` on the PATH and nothing else (`pyproject.toml`: `dependencies = []`; `README.md`,
"Install the engine and plugin"). `gh` is a separate Go binary installed by Homebrew, WinGet or a
Linux package repository ([cli/cli README, Installation](https://github.com/cli/cli#installation)).
Nothing in the install path, the plugin's hooks or the generated instance files installs or
checks for `gh`: `hooks/hooks.json` checks only `command -v coach-hook`.

The engine repo's own agents use `gh` for everything (`docs/agents/issue-tracker.md`), but that is
the engine developer's machine. The athlete's generated `CLAUDE.md` and `settings.json` never
mention `gh` or GitHub (`src/coach/cli/generated.py`, `src/coach/render/instance_files.py`).

The repo is public (`gh repo view joeuk89/strength-coach --json visibility` says `PUBLIC`), so a
read needs no token at all; a write does.

## 2. Being logged in to `gh`

`gh auth login` stores a token in the system credential store, falling back to a plain-text file
in `GH_CONFIG_DIR` (default `$XDG_CONFIG_HOME/gh`, else `~/.config/gh`) when no store is found
([gh auth login](https://cli.github.com/manual/gh_auth_login); `gh help environment`). The
browser flow issues an OAuth token (prefix `gho_`) with scopes `gist`, `read:org`, `repo` and
`workflow` on this machine (`gh auth status` output, 2026-11-07); the documented minimum for a
token handed to `--with-token` is `repo`, `read:org` and `gist`. `repo` is a classic scope that
covers issues on every repository the user can reach.

Login state is testable: `gh auth status` exits 1 and writes to stderr when any account has an
authentication problem, and exits 0 with `--json` regardless; `--active --hostname github.com`
narrows it to the one account that matters ([gh auth status](https://cli.github.com/manual/gh_auth_status)).
`gh` exit codes are 0 success, 1 failure, 2 cancelled, 4 "requires authentication"
(`gh help exit-codes`).

`GH_TOKEN`, then `GITHUB_TOKEN`, in the environment take precedence over stored credentials for
`github.com` (`gh help environment`). The manual says to favour `GH_TOKEN` over `gh auth login
--with-token` for a fine-grained token, because a fine-grained token's resource scoping "may
cause confusing behaviour" once `gh` uses it for other repositories
([gh auth login](https://cli.github.com/manual/gh_auth_login)).

## 3. Borrowing gh's credential: `gh auth token`

`gh auth token` prints the stored token for the active account on the default host to stdout,
refreshing an expiring token first unless `--no-refresh` is given; `--hostname` and `--user`
select another ([gh auth token](https://cli.github.com/manual/gh_auth_token)). `gh auth status
--show-token` prints it too. So an engine can run `gh auth token`, read one line, and send it
itself as `Authorization: Bearer <token>`; GitHub accepts `Bearer` or `token` for a personal or
OAuth token ([Authenticating to the REST API](https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api)).
This still requires `gh` installed and logged in (sections 1 and 2); it only avoids `gh`
building the request. The token printed is the full `repo`-scoped OAuth token, not one narrowed
to issues on one repository.

## 4. A token of the instance's own: fine-grained personal access token

The create-issue endpoint accepts fine-grained personal access tokens, GitHub App user tokens
and installation tokens, and needs exactly one permission: "Issues" repository permission,
write ([Create an issue](https://docs.github.com/en/rest/issues/issues#create-an-issue);
[Permissions required for fine-grained PATs](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens),
row `POST /repos/{owner}/{repo}/issues`: write). A fine-grained token is limited to one resource
owner and can be limited to selected repositories of that owner; "Metadata: read" comes with it
([Managing your personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens),
"Creating a fine-grained personal access token").

**Lifetime.** Expiration is chosen at creation, from 1 to 366 days or none; the default is 30
days. Infinite lifetimes are allowed for a personal account and may be blocked by an
organisation or enterprise policy. A personal access token unused for a year is removed
automatically. There is a cap of 50 fine-grained tokens per account (same page).

**Who can mint one for this repo.** A fine-grained token's resource owner is the token owner's
own account or an organisation they belong to. The documented gaps are that a fine-grained token
cannot "contribute to public repos where the user is not a member" nor "to repositories where the
user is an outside or repository collaborator"; only a classic token "has write access for public
repositories that are not owned by you" (same page, "Fine-grained personal access tokens
limitations" and "Personal access tokens (classic)"). So a fine-grained token with Issues: write
on `joeuk89/strength-coach` can be minted by `joeuk89`; a family member's account cannot select
that repository as a resource. Map #223's notes say the repo is used by the owner and family, so
the token an instance holds would be the owner's, handed to each instance, or each family
member would need a classic token with `repo` scope.

**Minting is a browser step** at Settings, Developer settings, Fine-grained tokens, Generate
new token. GitHub supports pre-filled creation links, for example
`https://github.com/settings/personal-access-tokens/new?name=coach-report&target_name=joeuk89&expires_in=366&issues=write`,
which opens the form with the name, resource owner, expiry and permission set; the user still
picks the repository and clicks Generate (same page, "Pre-filling fine-grained personal access
token details using URL parameters"). Repository selection has no URL parameter.

**Where it would live.** `.env` at the instance root holds exactly `HEVY_API_KEY`, gitignored,
written by `init`, and the environment variable overrides it (`docs/spec/instance.md`, "Secrets
and the Hevy switch"; ADR 0011, "The client"). The reader is `src/coach/cli/hevy_key.py`:
environment first, then a hand parser of `.env` that accepts `export NAME=value` and single or
double quotes, but only for `KEY_NAME`. A second key means either generalising that reader to
a name argument or a second reader; `init` writes `.env` only when a Hevy key is given
(`src/coach/cli/verbs/init.py`). The spec sentence "holds exactly `HEVY_API_KEY`" and the
"No `.env.example`" rule would both need amending.

## 5. The REST call

`POST https://api.github.com/repos/{owner}/{repo}/issues`, headers
`Accept: application/vnd.github+json`, `Authorization: Bearer <token>`,
`X-GitHub-Api-Version: 2022-11-28` (the docs' current example shows `2026-03-10`; any
published version works and the header is optional). JSON body: `title` (required, string),
`body` (string, Markdown), `labels` (array of label names), plus `assignees`, `milestone`,
`type` and `parent_issue_id`. Labels, assignees, milestone and type are **silently dropped**
when the caller lacks push access to the repository: a family member's token without push
access creates the issue but loses `needs-triage` and `bug` without any error
([Create an issue](https://docs.github.com/en/rest/issues/issues#create-an-issue), body
parameters). The same applies to `gh issue create --label`, which calls this endpoint.

Responses: 201 with the issue, whose `number` and `html_url` are what a verb would print; 400,
403, 404 (also what an unauthenticated or wrongly scoped write to a repo gets), 410 when issues
are disabled, 422 "Validation failed, or the endpoint has been spammed", 503. Creating content
"too quickly" trips the secondary rate limit; the primary limit for a personal token is 5,000
requests per hour ([Rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)).

**Body length.** The GitHub docs state no limit for `body`. The API's validation error on an
oversize body reads "body is too long (maximum is 65536 characters)"; this note could not
confirm that against a primary page, and a live probe would have created a real issue, so treat
65,536 characters as the working figure to verify when the verb's tests are written. A
check-in-sized report is far below it.

**Near-duplicate check** (asked on #229) is a read:
`GET /repos/{owner}/{repo}/issues?state=open&labels=needs-triage` needs no token on a public
repo, 60 requests per hour unauthenticated per IP, and returns pull requests too, marked by a
`pull_request` key ([REST API endpoints for issues](https://docs.github.com/en/rest/issues/issues)).

## 6. `gh issue create` as the writer

`gh issue create --repo joeuk89/strength-coach --title <t> --body-file <path> --label
needs-triage --label bug` creates the issue and prints its URL to stdout; `--body-file -` reads
stdin; `--parent`, `--assignee`, `--type` and `--attach` exist. It prompts interactively when
`--title` or `--body` is missing, so a verb must pass both. It uses the stored credential or
`GH_TOKEN` (sections 2 and 3). Projects need an extra `project` scope; labels need push access
as in section 5 ([gh issue create](https://cli.github.com/manual/gh_issue_create)).

## 7. How the engine's Hevy client and gate are shaped, for the verb to follow

- **One client, allow-listed, audited.** `src/coach/hevy/client.py` is a `urllib` client with a
  hard allow-list of four write endpoints, a 30 s timeout, a 429 retry (sleep 30 s, three tries),
  a token bucket on writes, and two audit lines per write appended to `hevy/writes.jsonl`. The
  key goes in a header and is scrubbed from every error, envelope and audit line (`_scrub`).
  Its `opener` and `sleeper` are constructor wiring so tests use a recording opener that
  refuses every connection; `tests` run under a `support.no_network` plugin (`pyproject.toml`).
- **Key reading** is `src/coach/cli/hevy_key.py` (section 4), called by each pulling verb with
  `call.env` and `instance.root / ".env"`; a missing key is the Setup refusal `hevy_key_missing`,
  exit 5. An unreachable Hevy is `Unreachable`, exit 4, with a 401/403 hint naming the key.
- **The client reaches verbs through `MakeClient`**, a factory typed `(key, audit_path, clock)
  -> HevyClient` on the verb `Declaration` (`src/coach/cli/declaration.py`), so a GitHub client
  would be a second factory or a second protocol, not a branch in this one.
- **What is gated.** A `Declaration` carries `writes: "none" | "store" | "hevy" | "git"`. The
  PreToolUse hook gates every verb whose declaration says `hevy` or `git` through its dry run
  (`GATED_WRITES` in `src/coach/cli/hook/gate.py`), and the generated `settings.json` asks on
  exactly those verbs: `allow: Bash(coach:*)`, `ask: Bash(coach <verb>:*)` per gated verb,
  `deny` on the Hevy workouts URL and `WebFetch` to the Hevy host (`settings_json` in
  `src/coach/render/instance_files.py`). A `report` verb is gated only once a new `writes` value
  is added to that literal and to `GATED_WRITES`, which map #223 lists under "Not yet specified".
- **Raw calls.** The hook's command scanner (`src/coach/cli/hook/shell.py`) looks for `coach`
  verbs and for `curl`, `wget`, `http`, `xh` and interpreter one-liners that name the Hevy host.
  It knows nothing of `gh` or `api.github.com`: a `gh issue create` or a `curl` to GitHub typed
  by the agent falls through to Claude Code's ordinary Bash prompt, with no engine dry run and no
  audit line. The same is true of `gh auth token` in a `$(...)` substitution, which the scanner
  reports as `opaque` only when it wraps a `coach` call.
- **Permission "ask" rules are generated from the same declarations** (ADR 0006, "The hook"),
  so the mechanism, whichever it is, gets its prompt from the dry run the verb declares, with
  the exact issue text in it, as the map's notes require.

## 8. Facts in one table

| Question | Fact | Source |
| --- | --- | --- |
| Is `gh` installed with the engine | No; `uv tool install` ships `coach` and `coach-hook` only | `pyproject.toml`, `README.md` |
| Is `gh` logged in on an instance | Unknowable in advance; `gh auth status` exits 1 on a problem, 4 means "requires authentication" | `gh auth status` manual, `gh help exit-codes` |
| Can the engine borrow gh's token | Yes, `gh auth token` prints it, refreshed; it is the full `repo`-scoped OAuth token | `gh auth token` manual |
| Env var gh honours | `GH_TOKEN` then `GITHUB_TOKEN`, overriding stored credentials | `gh help environment` |
| Permission a direct call needs | Issues: write on the one repo; Metadata: read is implied | REST docs, create an issue |
| Who can mint a fine-grained token for this repo | The owner's account; not a non-member on a public repo, not a collaborator | PAT docs, limitations |
| Fine-grained token lifetime | 1 to 366 days or none, default 30; removed after a year unused; 50 per account | PAT docs |
| Endpoint | `POST /repos/joeuk89/strength-coach/issues`, JSON `title`, `body`, `labels` | REST docs |
| Labels without push access | Silently dropped, 201 anyway | REST docs |
| Body limit | Not documented; 65,536 characters reported by the API's validation error, unverified here | this note |
| Rate limit | 5,000 requests/hour per token; 60/hour unauthenticated reads | REST rate-limit docs |
| Where `.env` is read | `src/coach/cli/hevy_key.py`, one hard-coded name, env first | this repo |
| What the hook gates | Verbs declared `writes: hevy` or `git`; raw `gh` or GitHub calls are not scanned | `gate.py`, `shell.py`, `instance_files.py` |
