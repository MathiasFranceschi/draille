# draille

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

Four stdlib-only Python scripts, ~350 lines total, no dependencies:

| Script | Role |
|---|---|
| `record.py` | write a durable record (markdown + frontmatter, stable content-hash id) |
| `prime.py` | rank all records (classification weight + outcome tally) into a budgeted digest for session start |
| `outcome.py` | append "this record demonstrably helped/failed" to an append-only log, keyed by immutable id |
| `migrate.py` | import legacy JSONL records into markdown |

Storage is just files in your repo:

```
memory/
  records/*.md        # one record per file — human-editable, git-diffable
  outcomes.jsonl      # append-only; git is the WORM/recovery layer
```

## Quickstart

```bash
python3 record.py decision foundational "Use Postgres" --body "Because RLS."
python3 prime.py          # ranked digest — paste/inject at session start
python3 outcome.py <id> success --note "constrained the schema choice"
```

Root resolution: `$MEMORY_ROOT` env var, else the git root of the cwd.
Mono-project by default (`memory/` at the repo root). Multi-scope routing via an
optional `memory/scopes.json` (`{"scope": "relative/home", "central": "."}`) —
homes must stay inside the root (absolute paths and `..` are rejected).
`--dir` is an explicit escape hatch that bypasses root and scope routing
entirely; don't pass it untrusted input.

## Agent bootstrap

Drop this in your `AGENTS.md` / `CLAUDE.md` (see [AGENTS.md](AGENTS.md)):

1. Session start: run `prime.py`, read `memory/HANDOVER.md`.
2. Session end, triage three tiers:
   - **HOT** → rewrite the CORE block of `memory/HANDOVER.md` (≤15 lines, merge — never stack),
   - **DURABLE** → `record.py <type> <classification> "<title>" --body "…"`,
   - **JOURNAL** → append `memory/journal/<YYYY-MM-DD>.md`.
3. Commit `session-end: <date>`. Never auto-push.

The system is the ritual, not the tooling — the scripts just keep the trail walkable.
