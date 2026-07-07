#!/usr/bin/env python3
"""Append an outcome event to outcomes.jsonl.

An outcome = "record <id> demonstrably constrained a decision" (success | failure | partial).
Append-only, keyed by the record's immutable id (no paths -> rename/delete-immune). Stdlib only.

Default log: <root>/memory/outcomes.jsonl, root = $MEMORY_ROOT env var, else git root of cwd.

Usage: outcome.py <record-id> <success|failure|partial> [--sha SHA] [--note TEXT] [--dir MEMORY_DIR]

Scope-blind: the log is central and id-keyed regardless of scope homes.
"""
import sys, os, json, argparse, datetime

STATUSES = ("success", "failure", "partial")


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


def main(argv):
    p = argparse.ArgumentParser(prog=os.path.basename(argv[0]),
                                description="Append an outcome event to outcomes.jsonl.")
    p.add_argument("record_id")
    p.add_argument("status", choices=STATUSES)
    p.add_argument("--sha", default="")
    p.add_argument("--note", default="")
    p.add_argument("--dir", dest="base", default="",
                   help="explicit memory dir (default: <root>/memory)")
    a = p.parse_args(argv[1:])
    rid, status, sha, note, base = a.record_id, a.status, a.sha, a.note, a.base
    if not base:
        base = os.path.join(memory_root(), "memory")
    os.makedirs(base, exist_ok=True)
    event = {"id": rid, "status": status,
             "sha": sha, "date": datetime.date.today().isoformat()}
    if note:
        event["note"] = note
    path = os.path.join(base, "outcomes.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stderr.write("outcome appended: %s %s\n" % (rid, status))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
