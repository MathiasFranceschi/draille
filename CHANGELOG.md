# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-07-17

### Added

- `scopes.json` `"_resolver"` (dynamic scope routing): when set to a command
  string, each scope's value is a topic NAME resolved to a directory at write
  time by running `<_resolver> <value>` (single-line stdout, absolute path
  allowed). Moving a scoped directory no longer requires editing scopes.json
  as long as its name survives. Resolution failure (non-zero exit, empty or
  multi-line output, malformed resolver quoting, non-string value) blocks the
  write (exit 2) — never a silent fallback to the literal value. Trust gate:
  `_resolver` only executes for roots listed in
  `~/.config/draille/trusted-roots` (a cloned repo's scopes.json is untrusted
  input and must not gain command execution; no dedicated env override —
  `$HOME` is the accepted trust boundary, same as `~/.gitconfig`). Untrusted
  root + `_resolver` = blocking error naming both remedies. The existing
  containment check still applies to the resolved path. Absent `_resolver` =
  literal-path behavior, byte-identical. Design ratified via a 9-voice
  council (silent-fallback veto) in the reference deployment.

## [1.5.0] - 2026-07-16

### Added

- `record --remedy-impl` (failure/convention only): structural default that
  keeps executable remedies out of prose. Value is a verified path, an opaque
  gotcha/task ref, or `none` (requires `--why`, stored as `remedy_why`).
  Omitted or an invalid path → `record` calls the store's executable
  `memory/remedy-task-hook` (`<record-id> <title> <scope>`, 20s timeout, first
  stdout line = task ref) so the "wire this remedy" debt is filed in the same
  gesture as the record; no hook → `remedy_impl: todo`. Either way a loud
  stderr warning lands in the calling agent's context. The write itself never
  fails on this path — a hard gate would only teach LLM callers to stuff the
  field (design ratified via a 9-voice council, ADR-0031 in the reference
  deployment). Other record types are untouched.

## [1.4.0] - 2026-07-08

### Added

- Task guard: `handover set` stamps every `- [t] ` bullet in the new CORE
  body with a fresh, file-unique `- [t-<4hex>] ` id. A soft diff-guard then
  compares old CORE vs new body for pending ids (`[t-xxxx]` with no `closed`
  marker on the line) that silently disappeared — never blocks the write,
  but warns on stderr and logs `dropped`/`closed`/`restored` events to
  `<memory-dir>/task-guard.jsonl`. `draille status` surfaces the open-drop
  count (`open_task_drops` in `--json`) — advisory, doesn't affect exit code.
  Guards against the silent erosion of pending tasks under lossy LLM rewrites
  of the CORE block.

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
