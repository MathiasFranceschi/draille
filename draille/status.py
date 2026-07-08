#!/usr/bin/env python3
"""Memory store status — fast persistence + health check for hooks/gates.

Same discovery contract as doctor.py/prime.py: $MEMORY_ROOT env var, else git
root of cwd, else cwd. Default scan: every <root>/**/memory/records
(mono-project = just <root>/memory/records), outcomes at
<root>/memory/outcomes.jsonl. --dir D: records at D/records, outcomes at
D/outcomes.jsonl.

Two dimensions:
  1. DIRTY (persistence) — are there uncommitted memory writes? Git-backed:
     `git status --porcelain` scoped to the memory dir(s), cwd = store root.
     No .git at the store root (or git binary missing) -> dirty="unknown"
     (can't tell, not an error).
  2. HEALTH (fast) — record/outcome counts + quarantined (invalid frontmatter,
     same rule as doctor.py). NOT doctor's deep audit (no orphan/dangling/dup
     checks) — status is the fast hot-path check; doctor is the deep audit.

Exit 0 if (committed or unknown) and zero quarantined; 1 if dirty=yes or any
quarantined (so a hook can do `draille status || persist`).

Usage: status.py [--dir MEMORY_DIR] [--json]
"""
import sys, os, json, glob, argparse, subprocess


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


def parse_frontmatter(text):
    """Tiny hand-rolled YAML-subset parser. (meta, body) or raise ValueError on invalid."""
    if not text.startswith("---"):
        raise ValueError("no frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("unterminated frontmatter")
    meta = {}
    for line in parts[1].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in (" ", "\t"):          # indented continuation / block-list item (tags:\n  - x) — tolerate, not a key
            continue
        if ":" not in line:
            raise ValueError("bad frontmatter line: %r" % line)
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, parts[2].strip()


def load_records(records_dir):
    """Returns (recs, quarantined_paths). recs = list of (meta, path)."""
    recs, quarantined = [], []
    for path in sorted(glob.glob(os.path.join(glob.escape(records_dir), "*.md"))):
        try:
            with open(path, encoding="utf-8") as f:
                meta, _body = parse_frontmatter(f.read())
            if not meta.get("id"):
                raise ValueError("missing id")
        except Exception as e:                       # GUARD: quarantine, never halt
            quarantined.append(path)
            sys.stderr.write("QUARANTINE %s: %s\n" % (os.path.basename(path), e))
            continue
        recs.append((meta, path))
    return recs, quarantined


def count_outcomes(path):
    n = 0
    if not os.path.exists(path):
        return n
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:                        # GUARD: skip malformed line, never crash
                continue
            if o.get("id"):
                n += 1
    return n


def check_dirty(root, scope_paths):
    """(dirty, uncommitted_count). dirty is True/False/None (None = unknown:
    no .git at root, or git binary missing — not an error)."""
    if not os.path.isdir(os.path.join(root, ".git")):
        return None, 0
    try:
        r = subprocess.run(["git", "status", "--porcelain", "--"] + scope_paths,
                            cwd=root, capture_output=True, text=True)
    except FileNotFoundError:                        # git binary not installed
        return None, 0
    if r.returncode != 0:
        return None, 0
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    return (len(lines) > 0), len(lines)


def main(argv):
    p = argparse.ArgumentParser(prog=os.path.basename(argv[0]),
                                description="Fast persistence + health check of the durable memory store.")
    p.add_argument("--dir", dest="dir_override", default="",
                   help="explicit memory dir (escape hatch — bypasses root scan)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    a = p.parse_args(argv[1:])
    dir_override = a.dir_override

    if dir_override:
        record_dirs = [os.path.join(dir_override, "records")]
        outcomes_path = os.path.join(dir_override, "outcomes.jsonl")
        root = dir_override
        scope_paths = ["."]
    else:
        root = memory_root()
        record_dirs = glob.glob(os.path.join(glob.escape(root), "**", "memory", "records"), recursive=True)
        outcomes_path = os.path.join(root, "memory", "outcomes.jsonl")
        scope_dirs = set(os.path.relpath(os.path.dirname(d), root) for d in record_dirs)
        scope_dirs.add(os.path.relpath(os.path.dirname(outcomes_path), root))
        scope_paths = sorted(scope_dirs)

    recs, quarantined = [], []
    for d in record_dirs:
        r, q = load_records(d)
        recs += r
        quarantined += q

    n_outcomes = count_outcomes(outcomes_path)
    dirty, uncommitted = check_dirty(root, scope_paths)

    report = {
        "records": len(recs),
        "outcomes": n_outcomes,
        "quarantined": len(quarantined),
        "quarantined_paths": sorted(quarantined),
        "dirty": dirty,
        "uncommitted_count": uncommitted,
    }
    issues = (1 if dirty else 0) + (1 if report["quarantined"] else 0)

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if issues == 0 else 1

    if dirty is None:
        dirty_s = "unknown"
    elif dirty:
        dirty_s = "yes %d uncommitted" % uncommitted
    else:
        dirty_s = "no"
    health_s = "clean" if not report["quarantined"] else "%d quarantined" % report["quarantined"]
    sys.stdout.write("draille status: %d records, %d outcomes | dirty: %s | %s\n"
                     % (report["records"], report["outcomes"], dirty_s, health_s))
    return 0 if issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
