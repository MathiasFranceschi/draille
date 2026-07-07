#!/usr/bin/env python3
"""Scaffold a repo's draille memory: records/, journal/, and a starter HANDOVER.md.

Idempotent: re-running never overwrites an existing HANDOVER.md (session-end owns
that file's CORE block from here on) and directory creation is a no-op if already
present. Prints the AGENTS.md/CLAUDE.md bootstrap block to paste once. Stdlib only.

Root resolution: $MEMORY_ROOT env var, else the git root of the cwd, else cwd.
--dir is an explicit escape hatch: it IS the memory dir (default: <root>/memory).

Usage: init.py [--dir MEMORY_DIR]
"""
import sys, os, argparse


def memory_root():
    env = os.environ.get("MEMORY_ROOT")
    if env:
        return os.path.abspath(env)
    d = os.getcwd()
    while True:
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.getcwd()
        d = parent


HANDOVER_TEMPLATE = """---
role: handover
---

# Handover

## CORE

<!-- Session-end rewrites this block IN PLACE (≤15 lines total). Merge new -->
<!-- lines into existing ones by topic — never stack a new block on old ones. -->
"""

BOOTSTRAP_BLOCK = """## Memory (draille)

At session start: run `draille prime` (or `python3 draille/prime.py`) and read
`memory/HANDOVER.md` if present.

At session end ("session-end"): triage into three tiers —
- **HOT** -> rewrite the CORE block of `memory/HANDOVER.md` (<=15 lines, merge
  related lines - never stack blocks);
- **DURABLE** -> `draille record <decision|pattern|failure|convention|reference>
  <foundational|tactical|observational> "<title>" --body "<why + how>"`;
- **JOURNAL** -> append one `## HH:MM - <topic>` block to
  `memory/journal/<YYYY-MM-DD>.md` (append-only).

Commit `session-end: <YYYY-MM-DD>`. Never auto-push.
"""


def main(argv):
    p = argparse.ArgumentParser(prog=os.path.basename(argv[0]),
                                description="Scaffold a repo's draille memory (records/, journal/, HANDOVER.md).")
    p.add_argument("--dir", dest="base", default="",
                   help="explicit memory dir (default: <root>/memory)")
    a = p.parse_args(argv[1:])
    base = a.base or os.path.join(memory_root(), "memory")

    os.makedirs(os.path.join(base, "records"), exist_ok=True)
    os.makedirs(os.path.join(base, "journal"), exist_ok=True)

    handover = os.path.join(base, "HANDOVER.md")
    # O_EXCL ("x"): atomic create-if-absent that REFUSES to follow a symlink.
    # os.path.exists() follows links, so a HANDOVER.md symlink (dangling, or
    # aimed outside the root by an untrusted cloned repo) would be written
    # THROUGH — clobbering an arbitrary file and escaping the root. "x" fails
    # on any existing path incl. a symlink, preserving idempotence + the guard.
    try:
        with open(handover, "x", encoding="utf-8") as f:
            f.write(HANDOVER_TEMPLATE)
        sys.stderr.write("created %s\n" % handover)
    except FileExistsError:
        sys.stderr.write("memory/HANDOVER.md exists, skipped\n")

    print(BOOTSTRAP_BLOCK)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
