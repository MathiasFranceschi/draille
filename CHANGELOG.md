# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.1.0]: https://github.com/MathiasFranceschi/draille/releases/tag/v1.1.0
[1.0.0]: https://github.com/MathiasFranceschi/draille/releases/tag/v1.0.0
[0.1.0]: https://github.com/MathiasFranceschi/draille/releases/tag/v0.1.0
