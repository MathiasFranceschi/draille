# draille — agent instructions

Public OSS repo (MIT). Everything here is public: no private paths, hostnames,
or personal-system names in code, docs, or commit messages. English only.

## What this is

Plain-markdown durable memory for AI agents. Four stdlib-only tools in
`draille/` (`record`, `prime`, `outcome`, `migrate`) + `cli.py` dispatcher
(`draille <subcommand>`). Tests at repo root (`test_*.py`). Storage =
`memory/records/*.md` + `memory/outcomes.jsonl` in the consumer's repo.

## Invariants — do not weaken

- **Stdlib only, zero dependencies.** No pip requirements, ever. A tiny
  hand-rolled parser beats a dependency here by design.
- **Each tool stays standalone-runnable** (`python3 draille/record.py …`):
  no package-relative imports inside the four tools (only `cli.py` imports
  them). Duplicated helpers (`memory_root()`, `slug()`) are deliberate —
  do not extract a shared module.
- **Security guards** (proven by tests, never remove):
  - scopes.json homes: absolute paths and `..` components rejected
    (`record.py`) — a cloned repo's scopes.json is untrusted input;
  - filenames are always slugged; the RAW record id lives only in
    frontmatter/outcomes (join key) — filename is cosmetic;
  - titles are normalized to one line (frontmatter is line-based;
    a multi-line title = key injection / rank forgery).
- **Root contract:** `$MEMORY_ROOT` env > git root of cwd > cwd. Mono-project
  (no scopes.json): `--scope` optional, writes `<root>/memory/records/`.
  Multi-scope (scopes.json present): `--scope` required. Optional
  `"_resolver"` key (reserved, never a scope): scope values become topic
  names resolved by running `<_resolver> <value>` at write time — gated on
  the root being listed in `~/.config/draille/trusted-roots` (untrusted
  scopes.json must never gain command execution), and any resolution failure
  blocks the write (exit 2, no literal fallback). See CHANGELOG 1.6.0.
- **Append-only outcomes**, keyed by immutable id. Git is the WORM/recovery
  layer. Never rewrite records in place except by the same id (idempotence).

## Dev loop

```bash
python3 test_record.py && python3 test_prime.py && python3 test_migrate.py
```

No framework on purpose (`ok(cond, msg)` style, exit 1 on failure). Every
behavior change lands with a test in the matching `test_*.py`. CI mirrors
this (ubuntu/macos × py3.9/3.13) + a `pip install .` smoke — keep 3.9 compat
(no `match`, no 3.10+ syntax). Docs (`README`, `adapters/`, `examples/`,
`docs/comparison.md`) state real, executed behavior — if you change a flag
or an output format, update them in the same change.

## Memory (dogfood — this repo uses draille itself)

At session start: run `draille prime` (or `python3 draille/prime.py`) and read
`memory/HANDOVER.md` if present.

At session end (« session-end »): triage into three tiers —
- **HOT** → rewrite the CORE block of `memory/HANDOVER.md` (≤15 lines, merge
  related lines — never stack blocks);
- **DURABLE** → `draille record <decision|pattern|failure|convention|reference>
  <foundational|tactical|observational> "<title>" --body "<why + how>"`;
- **JOURNAL** → append one `## HH:MM · <topic>` block to
  `memory/journal/<YYYY-MM-DD>.md` (append-only).
- **Pending tasks** → tag them `- [t] <task>` in the CORE (an id `[t-xxxx]`
  is stamped on write); close with `closed: <reason>` on the line — never
  silently drop (the guard logs drops; `draille status` surfaces them).

Commit `session-end: <YYYY-MM-DD>`. Never auto-push.

Full ritual: see [PROTOCOL.md](PROTOCOL.md) — the runtime-agnostic version of
the same triage (judgment criteria per tier, the persistence check via `draille
status`), which this bootstrap block is a condensed
pointer to.
