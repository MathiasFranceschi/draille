# Search adapters — bring your own engine

Full contract: [`../../docs/backends.md`](../../docs/backends.md). Short
version: set `DRAILLE_SEARCH_CMD` to a shell-style command line; `draille
search <terms...>` runs it with the terms appended as args and `$MEMORY_ROOT`
exported, and just forwards stdout/stderr/exit code — draille never parses
your output.

## Example: `ripgrep.sh`

[`ripgrep.sh`](ripgrep.sh) is a ~20-line portable search engine: ripgrep if
it's on `PATH`, `grep -r` fallback otherwise, no other dependencies. It reads
`$MEMORY_ROOT`, greps every `memory/records/*.md` under it for the query
terms (OR'd, case-insensitive), and prints one line per hit (`path:line:
matched text`).

Wire it up:

```bash
export DRAILLE_SEARCH_CMD="adapters/search/ripgrep.sh"
draille search widget
```

Real run against a two-record demo store (no `rg` binary installed, so this
exercised the `grep -r` fallback path):

```
$ MEMORY_ROOT=$D DRAILLE_SEARCH_CMD=adapters/search/ripgrep.sh python3 draille/search.py widget
/…/memory/records/2026-07-07-widget-setup-abc123.md:10:summary: "widget setup notes"
/…/memory/records/2026-07-07-widget-setup-abc123.md:13:# widget setup
/…/memory/records/2026-07-07-widget-setup-abc123.md:15:Use the small bracket, not the big one, for the widget mount.
exit=0

$ MEMORY_ROOT=$D DRAILLE_SEARCH_CMD=adapters/search/ripgrep.sh python3 draille/search.py gizmo
/…/memory/records/2026-07-07-gizmo-notes-def456.md:10:summary: "gizmo notes"
/…/memory/records/2026-07-07-gizmo-notes-def456.md:13:# gizmo notes
/…/memory/records/2026-07-07-gizmo-notes-def456.md:15:The gizmo calibration drifts if left in the sun.
exit=0
```

## Semantic backends

`ripgrep.sh` is a lexical example, but the contract doesn't care what's
behind `DRAILLE_SEARCH_CMD` — a semantic/embeddings/vector engine plugs in
identically. Any CLI that:

1. reads `$MEMORY_ROOT` from its environment to find the records, and
2. accepts free-text query terms as trailing args,

works with zero changes to draille — a hand-rolled embeddings index, a
wrapper around `sqlite-vec`, a call into a hosted vector search API, whatever
you already run. draille stays agnostic: it doesn't know or care whether the
backend is grepping strings or doing nearest-neighbor lookup over vectors.
