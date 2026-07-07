#!/usr/bin/env bash
# Example BYO search backend for draille (see ../../docs/backends.md).
# Contract: $MEMORY_ROOT is set by draille's search.py; query terms arrive as
# args; stdout is free-form (draille only forwards the exit code). Portable:
# uses ripgrep if installed, falls back to plain grep -r otherwise — no other
# dependencies. Wire it up with:
#   DRAILLE_SEARCH_CMD="adapters/search/ripgrep.sh" draille search <terms...>
set -euo pipefail

root="${MEMORY_ROOT:-.}"
if [ "$#" -eq 0 ]; then
    echo "usage: ripgrep.sh <term> [term...]" >&2
    exit 2
fi

# One case-insensitive alternation pattern from the query terms (OR match).
pattern=$(printf '%s\n' "$@" | paste -sd'|')

if command -v rg >/dev/null 2>&1; then
    # Search only under memory/records dirs, any depth (mono- or multi-scope).
    rg -i --no-heading --line-number \
        --glob '**/memory/records/*.md' \
        -- "$pattern" "$root" || true
else
    # ponytail: no ripgrep on PATH -> grep -r fallback, same output shape
    find "$root" -type f -path '*/memory/records/*.md' -print0 2>/dev/null \
        | xargs -0 -r grep -inE -- "$pattern" || true
fi
