# Walkthrough — draille end to end

A real session on a fictional project (`shipd`, a small job-queue service).
Every command below was actually executed; outputs are pasted verbatim
(long file listings truncated with `…`). Your ids and dates will differ —
ids are content hashes, dates are the day you run this.

## 0. Setup

```bash
mkdir shipd && cd shipd
git init . && git commit --allow-empty -m "init"

pip install git+https://github.com/MathiasFranceschi/draille
# or pipx install …, or just copy draille/<name>.py — stdlib only
```

No config, no init step. `draille` resolves its root from `$MEMORY_ROOT` if
set, else the git root of the cwd. With no `memory/scopes.json` present you
are in mono-project mode: everything lands in `./memory/`.

## 1. Session one — record as you work

Three things worth keeping came out of this session: a decision, a pattern,
and a failure.

```bash
draille record decision foundational "Use SQLite for the job queue" \
  --body "One writer, <100 jobs/s. Postgres adds an ops dependency for nothing; WAL mode covers the concurrency we actually have. Revisit only if we shard workers."
```

```
recorded use-sqlite-for-the-job-q-e8eebf [decision/foundational]
use-sqlite-for-the-job-q-e8eebf
```

stdout is the new id (stderr carries the human line) — capture it if you
want to chain an outcome later: `id=$(draille record … 2>/dev/null)`.

```bash
draille record pattern tactical "Retry webhooks with jittered backoff, cap at 6 attempts" \
  --body "Straight exponential backoff synchronized thundering herds after an outage. Full jitter (random 0..2^n s) plus a hard cap of 6 attempts drained the backlog without hammering receivers."

draille record failure observational "Alembic autogenerate silently dropped a CHECK constraint" \
  --body "autogenerate does not detect CHECK constraints; the 0042 migration dropped ck_jobs_status on rebuild. Fix: name all constraints and diff schema dumps in CI before merging a migration."
```

```
recorded retry-webhooks-with-jitt-0321f8 [pattern/tactical]
retry-webhooks-with-jitt-0321f8
recorded alembic-autogenerate-sil-868bd9 [failure/observational]
alembic-autogenerate-sil-868bd9
```

Each record is one plain markdown file:

```
$ find memory -type f
memory/records/2026-07-07-use-sqlite-for-the-job-queue-use-sqlite-for-the-job-q-e8eebf.md
memory/records/2026-07-07-retry-webhooks-with-jittered-backoff-cap-…-0321f8.md
memory/records/2026-07-07-alembic-autogenerate-silently-dropped-a--…-868bd9.md
```

```
$ cat memory/records/2026-07-07-use-sqlite-for-the-job-queue-*.md
---
id: use-sqlite-for-the-job-q-e8eebf
type: decision
classification: foundational
scope: shipd
evidence_sha: ""
relates_to: []
role: memory-record
created: 2026-07-07
summary: "Use SQLite for the job queue"
---

# Use SQLite for the job queue

One writer, <100 jobs/s. Postgres adds an ops dependency for nothing; WAL mode covers the concurrency we actually have. Revisit only if we shard workers.
```

Hand-editable, git-diffable. The id never changes even if you rename the file.

## 2. Prime — the ranked digest

```bash
draille prime
```

```
# draille — durable memory (prime)
## [decision] Use SQLite for the job queue
   id:use-sqlite-for-the-job-q-e8eebf | foundational | ★0 | score=50 | Use SQLite for the job queue
## [pattern] Retry webhooks with jittered backoff, cap at 6 attempts
   id:retry-webhooks-with-jitt-0321f8 | tactical | ★0 | score=20 | Retry webhooks with jittered backoff, cap at 6 attempts
## [failure] Alembic autogenerate silently dropped a CHECK constraint
   id:alembic-autogenerate-sil-868bd9 | observational | ★0 | score=10 | Alembic autogenerate silently dropped a CHECK constraint
```

Base score = classification weight (foundational 50, tactical 20,
observational 10). Outcomes shift it next.

## 3. Outcomes — the trail gets worn in

The SQLite decision actually constrained the queue rewrite, and the retry
pattern got reused. Say so:

```bash
draille outcome use-sqlite-for-the-job-q-e8eebf success \
  --sha 3f2c1aa --note "constrained the queue rewrite; no Postgres spun up"
draille outcome retry-webhooks-with-jitt-0321f8 success \
  --note "reused verbatim for the email sender retries"
```

```
outcome appended: use-sqlite-for-the-job-q-e8eebf success
outcome appended: retry-webhooks-with-jitt-0321f8 success
```

The log is append-only JSONL, keyed by id (rename/delete-immune):

```
$ cat memory/outcomes.jsonl
{"id": "use-sqlite-for-the-job-q-e8eebf", "status": "success", "sha": "3f2c1aa", "date": "2026-07-07", "note": "constrained the queue rewrite; no Postgres spun up"}
{"id": "retry-webhooks-with-jitt-0321f8", "status": "success", "sha": "", "date": "2026-07-07", "note": "reused verbatim for the email sender retries"}
```

`prime` now ranks by demonstrated usefulness (+30 per success, −20 per failure):

```
$ draille prime
# draille — durable memory (prime)
## [decision] Use SQLite for the job queue
   id:use-sqlite-for-the-job-q-e8eebf | foundational | ★1 | score=80 | Use SQLite for the job queue
## [pattern] Retry webhooks with jittered backoff, cap at 6 attempts
   id:retry-webhooks-with-jitt-0321f8 | tactical | ★1 | score=50 | Retry webhooks with jittered backoff, cap at 6 attempts
## [failure] Alembic autogenerate silently dropped a CHECK constraint
   id:alembic-autogenerate-sil-868bd9 | observational | ★0 | score=10 | Alembic autogenerate silently dropped a CHECK constraint
```

## 4. Session-end ritual — session one

Triage what happened into three tiers:

- **DURABLE** — already done above: the three `draille record` calls.
- **HOT** — current working state. Rewrite the CORE block of
  `memory/HANDOVER.md` (≤15 lines, merge related lines — never stack blocks):

```markdown
# HANDOVER — shipd

## CORE
- Queue: SQLite WAL, single writer — decided, do not reopen (see prime).
- Webhook retries: full jitter, 6-attempt cap — shipped in sender.py.
- OPEN: migration 0042 must be re-reviewed before deploy (dropped CHECK constraint).
```

- **JOURNAL** — narrative, append-only. One block in
  `memory/journal/2026-07-07.md`:

```markdown
## 14:30 · queue backend + webhook retries
Benchmarked SQLite WAL vs Postgres for the job queue; SQLite wins on ops
simplicity at our write rate. Ported the jittered-backoff retry helper to
the webhook sender. Caught Alembic dropping ck_jobs_status in 0042.
```

Then commit (never auto-push):

```
$ git add -A && git commit -m "session-end: 2026-07-07"
$ git show --stat --format="%h %s" HEAD
607d8c3 session-end: 2026-07-07

 memory/HANDOVER.md                                        |  6 ++++++
 memory/journal/2026-07-07.md                              |  4 ++++
 memory/outcomes.jsonl                                     |  2 ++
 ...silently-dropped-a--alembic-autogenerate-sil-868bd9.md | 15 +++++++++++++++
 ...ittered-backoff-cap-retry-webhooks-with-jitt-0321f8.md | 15 +++++++++++++++
 ...e-for-the-job-queue-use-sqlite-for-the-job-q-e8eebf.md | 15 +++++++++++++++
 6 files changed, 57 insertions(+)
```

Git is the WORM/recovery layer: a corrupted or deleted record is one
`git log` away.

## 5. Session two — prime in, outcomes out

New session (new agent, new human, doesn't matter). Start by priming and
reading the handover:

```bash
draille prime          # paste/inject the digest into the session context
cat memory/HANDOVER.md
```

During the session, receiver X goes down for 30 minutes and the 6-attempt
retry cap dead-letters 400 jobs. The pattern demonstrably failed — log it,
and record the follow-up convention from last session's Alembic failure:

```bash
draille outcome retry-webhooks-with-jitt-0321f8 failure \
  --note "6-attempt cap too low for receiver with 30-min outage window; jobs dead-lettered"

draille record convention tactical "Name every constraint explicitly (naming_convention in metadata)" \
  --body "Follow-up to the Alembic CHECK-constraint drop: set naming_convention on MetaData so autogenerate can track constraints by name. Applied in models/base.py."
```

```
outcome appended: retry-webhooks-with-jitt-0321f8 failure
recorded name-every-constraint-ex-96b442 [convention/tactical]
name-every-constraint-ex-96b442
```

The failure pulls the retry pattern down (50 → 30) without erasing it —
the record still tells you *why* the cap existed:

```
$ draille prime
# draille — durable memory (prime)
## [decision] Use SQLite for the job queue
   id:use-sqlite-for-the-job-q-e8eebf | foundational | ★1 | score=80 | Use SQLite for the job queue
## [pattern] Retry webhooks with jittered backoff, cap at 6 attempts
   id:retry-webhooks-with-jitt-0321f8 | tactical | ★1 | score=30 | Retry webhooks with jittered backoff, cap at 6 attempts
## [convention] Name every constraint explicitly (naming_convention in metadata)
   id:name-every-constraint-ex-96b442 | tactical | ★0 | score=20 | Name every constraint explicitly (naming_convention in metadata)
## [failure] Alembic autogenerate silently dropped a CHECK constraint
   id:alembic-autogenerate-sil-868bd9 | observational | ★0 | score=10 | Alembic autogenerate silently dropped a CHECK constraint
```

Session-end again. HOT is a **rewrite**, not an append — the CORE block is
merged in place (stale lines die, related lines fuse):

```markdown
# HANDOVER — shipd

## CORE
- Queue: SQLite WAL, single writer — decided, do not reopen (see prime).
- Webhook retries: full jitter; 6-attempt cap FAILED for long receiver
  outages — dead-letter queue added, cap now configurable per endpoint.
- Migration 0042 re-reviewed and merged; naming_convention set in
  models/base.py so autogenerate tracks constraints.
```

JOURNAL is an **append** — a new `## HH:MM · topic` block under the same
day file, prior blocks untouched:

```markdown
## 18:05 · retry cap post-mortem
Receiver X was down 30 min; the 6-attempt jitter cap dead-lettered 400 jobs.
Logged a failure outcome on the retry pattern, made the cap per-endpoint,
recorded the constraint-naming convention.
```

```
$ git add -A && git commit -m "session-end: 2026-07-07 (2)"
$ git log --oneline
6a0f0cf session-end: 2026-07-07 (2)
607d8c3 session-end: 2026-07-07
6612940 init
```

## 6. Multi-scope — one repo, several homes

When the repo grows sub-projects, add `memory/scopes.json` at the root.
Keys map a scope name to a home directory (relative to the root; absolute
paths and `..` are rejected):

```bash
cat > memory/scopes.json <<'EOF'
{"api": "services/api", "worker": "services/worker", "central": "."}
EOF
```

Its mere presence switches `record` to multi-scope mode — `--scope` becomes
mandatory:

```
$ draille record decision tactical "Pin uvicorn to 0.30.x" --body "0.31 broke our lifespan hooks."
error: --scope SCOPE required (scopes.json present = multi-scope mode)
```

```
$ draille record decision tactical "Pin uvicorn to 0.30.x" --scope api \
    --body "0.31 broke our lifespan hooks; re-test on each minor bump."
recorded pin-uvicorn-to-0-30-x-638dc4 [decision/tactical]
pin-uvicorn-to-0-30-x-638dc4
```

An unknown scope parks in `central` with a warning instead of failing —
a flat dump can't recur silently:

```
$ draille record pattern observational "Worker heartbeat via SQLite table, not process signals" \
    --scope billing --body "Heartbeat row per worker; reaper marks stale >90s."
warn: scope 'billing' has no home in scopes.json -> parked in central
recorded worker-heartbeat-via-sql-f0be41 [pattern/observational]
worker-heartbeat-via-sql-f0be41
```

Records now live in per-scope homes; outcomes stay in one central id-keyed
log:

```
memory/records/…                                   # central (root scope)
memory/outcomes.jsonl                              # ONE log for all scopes
memory/scopes.json
services/api/memory/records/2026-07-07-pin-uvicorn-to-0-30-x-…-638dc4.md
```

`prime` is scope-blind: it scans every `**/memory/records` under the root
and joins the single outcomes log, so the digest stays one ranked view:

```
$ draille prime
# draille — durable memory (prime)
## [decision] Use SQLite for the job queue
   id:use-sqlite-for-the-job-q-e8eebf | foundational | ★1 | score=80 | Use SQLite for the job queue
## [pattern] Retry webhooks with jittered backoff, cap at 6 attempts
   id:retry-webhooks-with-jitt-0321f8 | tactical | ★1 | score=30 | Retry webhooks with jittered backoff, cap at 6 attempts
## [convention] Name every constraint explicitly (naming_convention in metadata)
   id:name-every-constraint-ex-96b442 | tactical | ★0 | score=20 | Name every constraint explicitly (naming_convention in metadata)
## [decision] Pin uvicorn to 0.30.x
   id:pin-uvicorn-to-0-30-x-638dc4 | tactical | ★0 | score=20 | Pin uvicorn to 0.30.x
## [failure] Alembic autogenerate silently dropped a CHECK constraint
   id:alembic-autogenerate-sil-868bd9 | observational | ★0 | score=10 | Alembic autogenerate silently dropped a CHECK constraint
## [pattern] Worker heartbeat via SQLite table, not process signals
   id:worker-heartbeat-via-sql-f0be41 | observational | ★0 | score=10 | Worker heartbeat via SQLite table, not process signals
```

## Recap

| Moment | Command / action |
|---|---|
| Session start | `draille prime` + read `memory/HANDOVER.md` |
| Something durable happens | `draille record <type> <classification> "<title>" --body "…"` |
| A record demonstrably helped/failed | `draille outcome <id> success\|failure\|partial --note "…"` |
| Session end — HOT | rewrite CORE block of `memory/HANDOVER.md` (merge, never stack) |
| Session end — JOURNAL | append `## HH:MM · topic` to `memory/journal/<date>.md` |
| Session end — commit | `git commit -m "session-end: <date>"` — never auto-push |

The system is the ritual, not the tooling.
