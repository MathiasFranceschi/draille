#!/usr/bin/env python3
"""Retire a durable memory record — move it out of the scanned records glob into a sibling
memory/expired/ dir. Move-only, never deletes: reversible by hand (move the file back).

Structural retirement: search.py and prime.py only glob `memory/records/*.md`, so an
expired record stops surfacing by construction (nothing to filter in either scanner).

Usage: expire.py <id> [--dir MEMORY_DIR]

Root resolution + discovery = same contract as search.py: $MEMORY_ROOT env var, else git
root of cwd, else cwd. Default scan: every <root>/**/memory/records (mono-project = just
<root>/memory/records); a match's sibling <same-memory-dir>/expired is the destination.
--dir D: records at D/records, expired at D/expired.

Trace: appends {date, id, action: "expire"} to the central <root>/memory/outcomes.jsonl —
same file, same append-only JSONL mechanism as outcome.py (scope-blind: one log regardless
of which scope's records dir the record lived in). Not imported from outcome.py: every
draille/<name>.py is also a standalone script (`python3 draille/expire.py ...`, no install),
so cross-module imports here would break outside the package.
"""
import sys, os, glob, shutil, argparse, datetime, json


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


def record_id_of(path):
    """The frontmatter's 'id:' value, or None (unreadable / no id line)."""
    try:
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i == 0:
                    continue                      # opening '---'
                if line.strip() == "---":
                    break                          # end of frontmatter, no id found
                if line.startswith("id:"):
                    return line.split(":", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def find_by_id(dirs, rid):
    """First (dir, path) among `dirs` whose *.md frontmatter id == rid, else (None, None)."""
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(glob.escape(d), "*.md"))):
            if record_id_of(path) == rid:
                return d, path
    return None, None


def append_outcome_event(base, event):
    """Append one JSON line to <base>/outcomes.jsonl (same append-only log as outcome.py)."""
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, "outcomes.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return path


def main(argv):
    p = argparse.ArgumentParser(
        prog=os.path.basename(argv[0]),
        description="Expire a record: move it from memory/records to memory/expired (never deletes).")
    p.add_argument("record_id")
    p.add_argument("--dir", dest="base", default="",
                   help="explicit memory dir (records at DIR/records, expired at DIR/expired)")
    a = p.parse_args(argv[1:])
    rid, base = a.record_id, a.base

    if base:
        record_dirs = [os.path.join(base, "records")]
        expired_dirs = [os.path.join(base, "expired")]
        outcomes_base = base
    else:
        root = memory_root()
        record_dirs = glob.glob(os.path.join(glob.escape(root), "**", "memory", "records"), recursive=True)
        expired_dirs = [os.path.join(os.path.dirname(d), "expired") for d in record_dirs]
        outcomes_base = os.path.join(root, "memory")  # central, scope-blind (outcome.py's contract)

    src_dir, src_path = find_by_id(record_dirs, rid)
    if src_path is None:
        _, exp_path = find_by_id(expired_dirs, rid)   # not live -- maybe already expired
        if exp_path is not None:
            sys.stderr.write("already expired: %s -> %s\n" % (rid, exp_path))
            return 0
        sys.stderr.write("error: no record found for id %r\n" % rid)
        return 1

    dest_dir = os.path.join(os.path.dirname(src_dir), "expired")
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, os.path.basename(src_path))
    shutil.move(src_path, dest_path)

    append_outcome_event(outcomes_base, {
        "date": datetime.date.today().isoformat(),
        "id": rid,
        "action": "expire",
    })

    sys.stderr.write("expired %s -> %s\n" % (rid, dest_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
