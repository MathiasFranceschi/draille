# PROTOCOL — the draille session ritual

draille (`record`, `prime`, `outcome`, `search`, `handover`, `doctor`, `status`,
`migrate`, `init`) gives you the primitives: write a record, rank a digest, log
an outcome, search, read/write live core state, health-check the store, check
persistence. None of that is a
ritual by itself — this document is. It's the ordered sequence any runtime
(Claude Code, Cursor, Codex, a human at a terminal) runs around those
primitives, session after session, so memory actually accumulates instead of
rotting.

It is deliberately **not** a CLI command. Session-end triage — deciding what's
HOT vs DURABLE vs disposable JOURNAL noise — needs agent judgment about *this*
session's content. That judgment doesn't belong in a script; the script only
holds the primitives the judgment acts on.

**Path-configurable.** Every path below (`memory/`, `memory/HANDOVER.md`,
`memory/journal/`, `memory/records/`) is draille's default layout, resolved
under `$MEMORY_ROOT` (env override, else git root of cwd, else cwd — see
`draille prime --help`). A host embedding this ritual is free to point
`$MEMORY_ROOT` elsewhere; the ritual doesn't hardcode a location, only the
relative shape under whatever root you give it.

## Session start

```bash
draille prime
```

Prints a ranked digest of the durable record store, budgeted so it's cheap to
read every session — classification weight and recorded outcomes decide what
surfaces first, superseded records are hidden by default. Read it, then read
`memory/HANDOVER.md` if it exists: the file's CORE block is the current live
state (open threads, in-flight decisions) that hasn't graduated to a durable
record yet.

## During the session

Capture as you go, not in a end-of-session scramble — a decision is easiest to
write down while you still remember *why*.

```bash
draille record <decision|pattern|failure|convention|reference> \
  <foundational|tactical|observational> "<title>" --body "<why + how>"
```

Use `--supersedes <old-id>` the moment a prior record becomes wrong (moved off
Postgres, a convention changed) — it marks the old one obsolete so `prime` and
`search` stop surfacing stale facts (still on disk, still in git history;
`search --all` brings superseded records back). Use `--scope <name>` if this
repo has a `memory/scopes.json` (multi-scope routing); omit it in a mono-repo.

```bash
draille search "<terms>"
```

Ranked full-text search over the store when you need to find whether a
decision already exists before re-deciding it. Delegates to
`$DRAILLE_SEARCH_CMD` if set (see `docs/backends.md`), otherwise a builtin
token-count scan.

## Session end — the three-tier triage

This is the part that needs judgment, not just tooling. Everything from the
session lands in exactly one of three tiers:

**HOT → `memory/HANDOVER.md` CORE block.**

```bash
echo "<new CORE content>" | draille handover set
```

The CORE block is live working state: what's in flight, what the next session
needs to pick up immediately. Judgment call: **rewrite, don't append.** Read
the current block first (`draille handover show`), then fold this session's
changes into it — merge a line that's now resolved into the line that
superseded it, drop what's no longer relevant,
keep it under ~15 lines. A HANDOVER that only ever grows is a HANDOVER nobody
reads; if it wouldn't fit on one screen, something in it belongs in DURABLE
instead (it's a decision, not live state) or nowhere (it was never load-
bearing).

**DURABLE → a `draille record` per decision/pattern/failure worth keeping.**

Judgment call: the test is "would the next session (or a different agent)
repeat a mistake, re-litigate a decision, or re-discover a constraint without
this note?" If yes, record it — pick the type (`decision`/`pattern`/`failure`/
`convention`/`reference`) and classification (`foundational` = holds regardless
of what changes next; `tactical` = holds for the current approach;
`observational` = worth knowing, not load-bearing) honestly, since `prime`
weights by both. If a DURABLE record makes an existing one wrong, record the
new one with `--supersedes <old-id>` in the same breath — don't leave both
live.

**JOURNAL → append a timestamped block, never rewrite.**

```bash
printf '## %s · <topic>\n<what happened, one paragraph>\n' "$(date +%H:%M)" \
  >> memory/journal/$(date +%F).md
```

Everything that's neither live state nor a durable lesson — narrative color,
what was tried, dead ends not worth a `failure` record — goes here. Append-
only by construction: a journal file is a log, not a document you edit
after the fact.

**Then commit.** `git commit -m "session-end: <YYYY-MM-DD>"` (or your
runtime's convention) covering whatever combination of `memory/HANDOVER.md`,
new `memory/records/*.md`, and `memory/journal/<date>.md` this session
touched. Never auto-push — commit is the local durability boundary; pushing is
a separate, deliberate act.

## Persistence check

```bash
draille status
```

Exits non-zero if the store has uncommitted memory writes (dirty) **or** any
quarantined record (invalid frontmatter) — so a hook can gate on it:
`draille status || <persist>`. It's the fast hot-path check (counts +
persistence + quarantine, not `doctor`'s deep audit), git-backed and scoped to
`memory/`, so it catches both the "triage ran but nothing got committed" case
*and* a corrupt record that a bare `git status` would show as clean. Outside a
git repo, or with no git binary, dirty reports `unknown` and the check still
exits 0 rather than erroring. A runtime wires this into whatever end-of-session
gate it has (a Stop hook, a pre-PR check, a CI step) — this ritual owns the
detection, the trigger is the runtime's to own.

## See also

- [`docs/backends.md`](docs/backends.md) — bring-your-own search engine via
  `$DRAILLE_SEARCH_CMD`, for when the builtin scan stops being enough.
- [`adapters/`](adapters/) — ready-to-paste bootstrap blocks per runtime
  (Claude Code, Cursor, Codex, Gemini, Copilot). Those are the short
  session-start/session-end summary for a runtime's own memory file; this
  document is the full ritual they're a condensed pointer to.
