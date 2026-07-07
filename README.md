# draille

![tests](https://github.com/MathiasFranceschi/draille/actions/workflows/ci.yml/badge.svg)

Plain-markdown durable memory for AI agents. Any runtime, local, git-versioned, hand-editable, zero lock-in.

## Why « draille »

A *draille* is a transhumance trail in the mountains of southern France — a path
not built, but **worn into the land by herds walking it season after season**.
Nobody designed it; repeated passage made it, and it remembers the way for
whoever comes next.

That is exactly what agent memory should be: not a database bolted on the side,
but a trace left by work itself — records worn in by sessions, ranked by how
often following them actually led somewhere (`outcomes`), readable by the next
traveler (human or agent) with no tooling at all.

## What it is

Stdlib-only Python tools, no dependencies:

| Command | Role |
|---|---|
| `draille init` | scaffold `memory/` (HANDOVER template, journal) and print the agent bootstrap block |
| `draille record` | write a durable record (markdown + frontmatter, stable content-hash id); `--supersedes <id>` marks a prior record obsolete |
| `draille prime` | rank all records (classification weight + outcome tally) into a budgeted digest for session start |
| `draille outcome` | append "this record demonstrably helped/failed" to an append-only log, keyed by immutable id |
| `draille search` | ranked full-text search over records (pure scan, no index) — or delegate to your own engine via `DRAILLE_SEARCH_CMD` ([BYO backends](docs/backends.md)) |
| `draille handover` | show/set the CORE block of `memory/HANDOVER.md` (atomic, Letta-style core memory) |
| `draille doctor` | health-check the store: corrupt records, orphan outcomes, dangling `supersedes`, unsafe scope homes, duplicate ids (exit 1 on any issue — CI-friendly) |
| `draille migrate` | import legacy JSONL records into markdown |

**Superseding — stale memory that stops misleading.** Outdated facts are the
named failure of agent memory: "we use Postgres" lingers and misleads long after
the project moved to SQLite. `draille record … --supersedes <old-id>` marks the
old record obsolete; `prime` and `search` hide it by default (still on disk, still
in git history — `search --all` brings it back). One frontmatter line, no graph,
no TTL daemon: the markdown-shaped answer to temporal decay.

Each is also a standalone script (`draille/<name>.py`) you can copy anywhere — no install needed.

Storage is just files in your repo:

```
memory/
  records/*.md        # one record per file — human-editable, git-diffable
  outcomes.jsonl      # append-only; git is the WORM/recovery layer
```

## draille vs. Claude Code's native memory

Claude Code now ships its own memory: a per-project auto memory directory indexed by `MEMORY.md`, but it's per-user and per-tool — it lives outside the repo and only Claude Code reads it. draille is project-owned: records live in the repo, travel with `git clone`, and are legible to any runtime (Claude Code, Codex, Cursor, or a human with `cat`). The two compose fine — native memory for personal prefs and scratch state, draille for what the *project* has learned.

## Non-goals

- **No per-turn auto-extraction.** Frameworks like mem0/Letta watch every turn
  and write memory automatically. draille doesn't, on purpose: automatic
  extraction produces noisy memory, and the whole point here is a *curated*,
  human-editable, git-diffable trail. Capture is a deliberate act (`record`, or
  the session-end ritual), not a background process. If you want the agent to
  hold live working state mid-session, that's what `handover set` is for.
- **No embedded vector database.** Semantic recall is a `DRAILLE_SEARCH_CMD`
  backend you bring, not infrastructure draille ships ([BYO backends](docs/backends.md)).
- **No hosted service / multi-user layer.** draille is a local, per-repo store.
  For memory-as-a-service at scale, that's a different tool.

## Install

```bash
pipx install git+https://github.com/MathiasFranceschi/draille
# or: pip install git+https://github.com/MathiasFranceschi/draille
# or: git clone and run the scripts directly — stdlib only, nothing to install
```

## Quickstart

```bash
draille init              # scaffold memory/ + print the agent bootstrap block
draille record decision foundational "Use Postgres" --body "Because RLS."
draille prime             # ranked digest — paste/inject at session start
draille outcome <id> success --note "constrained the schema choice"
draille search postgres   # ranked hits across all records
```

Root resolution: `$MEMORY_ROOT` env var, else the git root of the cwd.
Mono-project by default (`memory/` at the repo root). Multi-scope routing via an
optional `memory/scopes.json` (`{"scope": "relative/home", "central": "."}`) —
homes must stay inside the root (absolute paths and `..` are rejected).
`--dir` is an explicit escape hatch that bypasses root and scope routing
entirely; don't pass it untrusted input.

## Agent bootstrap

Drop this in your `AGENTS.md` / `CLAUDE.md` (see [AGENTS.md](AGENTS.md)):

1. Session start: run `draille prime`, read `memory/HANDOVER.md`.
2. Session end, triage three tiers:
   - **HOT** → rewrite the CORE block of `memory/HANDOVER.md` (≤15 lines, merge — never stack),
   - **DURABLE** → `draille record <type> <classification> "<title>" --body "…"`,
   - **JOURNAL** → append `memory/journal/<YYYY-MM-DD>.md`.
3. Commit `session-end: <date>`. Never auto-push.

The system is the ritual, not the tooling — the scripts just keep the trail walkable.
