# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-07-08

### Added

- `draille status` — fast persistence + health check for hooks/gates: detects
  uncommitted memory writes (git-dirty), counts records/outcomes/quarantined.
  Exit 1 if dirty or corrupt so a runtime can gate on `draille status || persist`;
  `unknown` (store not under git) does not fail. The runtime-agnostic detection
  primitive a durable-memory tool must own (vs each consumer reinventing it).
- `PROTOCOL.md` — the runtime-agnostic 3-tier ritual (HOT/DURABLE/JOURNAL) as a
  reusable, path-configurable agent protocol. draille ships the method; a runtime
  binds it to its own events (Stop hook, PR gate). Per-runtime hook adapters are
  a deliberate non-goal until a second consumer exists.

### Fixed

- Store discovery used unescaped `glob` — a memory root containing a glob class
  (e.g. `proj[a]`) silently matched nothing, so `prime`/`search`/`doctor`/`status`
  reported an empty store on a non-empty one. All globs now `glob.escape` the path.

## [1.2.0] - 2026-07-07

### Added

- Superseding: `draille record --supersedes <id>` marks a prior record obsolete.
  `prime` and `search` hide superseded records by default (still on disk / in git;
  `search --all` reincludes them). The markdown-shaped answer to the top named
  pain of agent memory — stale facts that keep ranking and misleading. Handles
  chains, cycles, self-supersede, and dangling/cross-scope targets safely.
- `draille doctor` — store health check: corrupt records, orphan outcomes,
  dangling `supersedes`, unsafe scope homes, duplicate ids (cross-scope aware).
  Exit 1 on any issue for CI/pre-commit; `--json` for machine output.
- `adapters/search/ripgrep.sh` — a concrete, portable BYO search backend example
  (ripgrep with grep fallback), proving the `DRAILLE_SEARCH_CMD` seam end to end.
- README "Non-goals" section: per-turn auto-extraction, embedded vector DB, and a
  hosted multi-user layer are deliberate non-goals, not gaps.

## [1.1.1] - 2026-07-07

### Fixed

- Windows: the scopes.json containment guard used `os.path.isabs`, which on
  Python 3.13+ returns False for a rooted-but-driveless home like `/esc` — so a
  hostile scopes.json could still escape the memory root on Windows. Replaced
  with a realpath + commonpath containment check (platform-agnostic; also covers
  drive-relative and cross-drive paths). CI matrix now green on Windows.

## [1.1.0] - 2026-07-07

### Added

- `draille handover` — show/set the CORE block of `memory/HANDOVER.md`
  programmatically (Letta-style agent-editable core memory): atomic write
  (tmp + rename), preserves the rest of the file byte-for-byte (CRLF included),
  preserves permissions, warns beyond 15 lines.
- BYO search backends: `DRAILLE_SEARCH_CMD` delegates `draille search` to any
  external engine (semantic or otherwise); `--engine builtin|env` selects
  explicitly. Contract in `docs/backends.md`. The builtin pure-scan stays the
  zero-config default.
- Positioning docs refreshed against the July 2026 landscape (file-based memory
  wave, Claude Code native memory, memsearch / TencentDB Agent Memory / engramory).

### Security

- search: a blank `DRAILLE_SEARCH_CMD` caused the query terms themselves to be
  executed as the delegate command (arbitrary execution from search input) —
  now rejected; malformed/missing commands fail cleanly (exit 2/127, no shell).
- handover: a `## CORE` decoy inside the YAML frontmatter could corrupt the
  file on `set` — the frontmatter is now skipped before block matching.

## [1.0.0] - 2026-07-07

### Added

- `draille init` — scaffold `memory/` (HANDOVER.md template with CORE block,
  `journal/`, `records/`) and print the agent bootstrap block to paste into
  `AGENTS.md`/`CLAUDE.md`. Idempotent; never overwrites an existing HANDOVER.md.
- `draille search <terms…>` — ranked full-text search over records: pure scan,
  no index, no state. Title matches outrank body matches; classification weight
  and `success` outcomes boost the score. `-n` caps results.
- Windows added to the CI matrix (3 OS x 2 Python versions), UTF-8 forced for
  the digest glyphs.

### Security

- init: HANDOVER.md is created with `O_EXCL`, closing a symlink write-escape
  (a `memory/HANDOVER.md` symlink pointing outside the root could otherwise
  receive the template write).

## [0.1.0] - 2026-07-07

### Added

- Durable-memory toolchain extracted from a private workspace vault as a
  standalone, stdlib-only project: `record`, `prime`, `outcome`, `migrate`.
- Unified `draille` CLI (`draille record|prime|outcome|migrate`); each tool
  remains usable as a standalone script under `draille/`.
- Root resolution contract: `$MEMORY_ROOT` env var, else the git root of the
  cwd, else the cwd itself. Mono-project layout (`memory/` at the root) by default; optional
  multi-scope routing via `memory/scopes.json`.
- pip/pipx packaging (`pyproject.toml`, `draille` entry point), MIT license.
- CI running the test suite on GitHub Actions.

### Security

- `scopes.json` containment: scope homes are constrained to the memory root —
  absolute paths and `..` traversal are rejected.
- Record filenames are derived from a slugged, normalized title, preventing
  path or shell injection through user-supplied titles.

[1.3.0]: https://github.com/MathiasFranceschi/draille/releases/tag/v1.3.0
[1.2.0]: https://github.com/MathiasFranceschi/draille/releases/tag/v1.2.0
[1.1.1]: https://github.com/MathiasFranceschi/draille/releases/tag/v1.1.1
[1.1.0]: https://github.com/MathiasFranceschi/draille/releases/tag/v1.1.0
[1.0.0]: https://github.com/MathiasFranceschi/draille/releases/tag/v1.0.0
[0.1.0]: https://github.com/MathiasFranceschi/draille/releases/tag/v0.1.0
