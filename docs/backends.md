# Backends — bring your own search

`draille search` ships with a builtin scan (title/summary/body token counts +
classification + outcomes, all stdlib, no index). If you already have a
better retrieval engine — a semantic index, embeddings, whatever — you can
point `search` at it instead of re-implementing ranking in draille.

## The contract

Set `DRAILLE_SEARCH_CMD` to a shell-style command line (parsed with
`shlex.split`, never run through a shell — no `&&`, pipes, or globbing).
When it's set, `draille search <terms...>` runs your command instead of the
builtin scan:

- **args**: your command is invoked with the query terms appended, in order,
  as extra arguments — `DRAILLE_SEARCH_CMD="mytool"` + `draille search foo
  bar` runs `mytool foo bar`.
- **env**: `$MEMORY_ROOT` is exported to the child, resolved the same way
  the builtin scan resolves it ($MEMORY_ROOT env if already set, else git
  root, else cwd) — so your engine knows where the records live without
  re-implementing root discovery.
- **stdout/stderr**: yours to format however you like; draille doesn't parse
  them, it just forwards the child's exit code.

## Example: a semantic engine

```bash
export DRAILLE_SEARCH_CMD="qmd search"
draille search "why did the migration fail"
```

This runs `qmd search "why did the migration fail"` with `MEMORY_ROOT` set,
and returns whatever `qmd` prints and exits with. Any CLI that reads
`$MEMORY_ROOT` and accepts free-text args as its query works the same way —
`qmd` is just one example, not a dependency of draille.

## `--engine`

- `--engine env` (default when `DRAILLE_SEARCH_CMD` is set): delegate.
  Errors out if `DRAILLE_SEARCH_CMD` is empty or unparsable, and exits 127
  with a one-line message if the command can't be executed — never a
  traceback.
- `--engine builtin`: force the internal scan even if `DRAILLE_SEARCH_CMD`
  is set — useful to sanity-check the builtin ranking still works, or if
  your external engine is down.
- `--dir` always uses the builtin scan: it bypasses root discovery, so a
  backend keyed on `$MEMORY_ROOT` couldn't honor it. Combining `--dir` with
  `--engine env` is an error.

## When to stay on the builtin

The builtin scan has no setup, no index to keep in sync, and no extra
process — for most repos (a few hundred records) it's plenty fast and it's
what the test suite exercises by default. Reach for a BYO backend only once
you have a retrieval need the token-count heuristic genuinely can't cover
(semantic queries, cross-repo indexes, etc.).
