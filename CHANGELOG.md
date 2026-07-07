# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/MathiasFranceschi/draille/releases/tag/v0.1.0
