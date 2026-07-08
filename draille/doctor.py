#!/usr/bin/env python3
"""Memory store health check — diagnose before it rots.

Same discovery contract as prime.py: $MEMORY_ROOT env var, else git root of
cwd, else cwd. Default scan: every <root>/**/memory/records (mono-project =
just <root>/memory/records), outcomes at <root>/memory/outcomes.jsonl.
--dir D: records at D/records, outcomes at D/outcomes.jsonl.

Checks (one line each, with counts):
  - quarantined records (invalid frontmatter, same parser+rule as prime.py)
  - orphan outcomes (id in outcomes.jsonl with no matching record)
  - dangling supersedes (a record's `supersedes:` field names an id absent
    from the store)
  - invalid scopes.json homes, if <root>/memory/scopes.json exists (absolute
    path, `..`, or escaping root — same realpath+commonpath check as record.py)
  - duplicate ids (same id claimed by 2+ record files)

Exit 0 if clean, exit 1 if any issue (CI / pre-commit friendly). --json for
machine-readable output.

Usage: doctor.py [--dir MEMORY_DIR] [--json]
"""
import sys, os, json, glob, argparse


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
    """Returns (recs, quarantined_paths). recs = list of (meta, path).
    Dup-id detection lives in main() — it must span every scope home the
    default recursive scan aggregates, not just one records dir."""
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


def load_outcome_ids(path):
    ids = set()
    if not os.path.exists(path):
        return ids
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:                        # GUARD: skip malformed line, never crash
                continue
            rid = o.get("id")
            if rid:
                ids.add(rid)
    return ids


def check_scopes(root):
    """Same containment rule as record.py, applied to every home in scopes.json."""
    scopes_path = os.path.join(root, "memory", "scopes.json")
    if not os.path.exists(scopes_path):
        return None
    try:
        with open(scopes_path, encoding="utf-8") as f:
            homes = json.load(f)
    except Exception as e:
        return {"error": "invalid scopes.json: %s" % e, "invalid": []}
    root_r = os.path.realpath(root)
    invalid = []
    for scope, home_dir in homes.items():
        base = os.path.join(root, home_dir, "memory")
        try:
            contained = os.path.commonpath([root_r, os.path.realpath(base)]) == root_r
        except ValueError:
            contained = False
        if not contained:
            invalid.append("%s -> %r" % (scope, home_dir))
    return {"error": None, "invalid": invalid}


def main(argv):
    p = argparse.ArgumentParser(prog=os.path.basename(argv[0]),
                                description="Check the health of the durable memory store.")
    p.add_argument("--dir", dest="dir_override", default="",
                   help="explicit memory dir (escape hatch — bypasses root scan)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    a = p.parse_args(argv[1:])
    dir_override = a.dir_override

    if dir_override:
        record_dirs = [os.path.join(dir_override, "records")]
        outcomes_path = os.path.join(dir_override, "outcomes.jsonl")
        root = dir_override
    else:
        root = memory_root()
        record_dirs = glob.glob(os.path.join(glob.escape(root), "**", "memory", "records"), recursive=True)
        outcomes_path = os.path.join(root, "memory", "outcomes.jsonl")

    recs, quarantined = [], []
    for d in record_dirs:
        r, q = load_records(d)
        recs += r
        quarantined += q
    # dup ids span the whole aggregated store (two scope homes claiming one id
    # breaks the central outcomes.jsonl join key) — not per records dir.
    seen, dups = {}, []
    for meta, path in recs:
        rid = meta["id"]
        if rid in seen:
            dups.append((rid, seen[rid], path))
        else:
            seen[rid] = path

    ids = set(meta["id"] for meta, _path in recs)
    outcome_ids = load_outcome_ids(outcomes_path)
    orphan_outcomes = sorted(outcome_ids - ids)

    dangling = []
    for meta, path in recs:
        sup = meta.get("supersedes", "")
        for sid in (s.strip() for s in sup.split(",")):
            if sid and sid not in ids:
                dangling.append((meta["id"], sid, path))

    scopes = None if dir_override else check_scopes(root)

    report = {
        "n_records": len(recs),
        "n_outcomes": len(outcome_ids),
        "quarantined": sorted(quarantined),
        "orphan_outcomes": orphan_outcomes,
        "dangling_supersedes": ["%s -> %s" % (rid, sid) for rid, sid, _p in dangling],
        "invalid_scopes": (scopes or {}).get("invalid", []) if scopes else [],
        "scopes_error": (scopes or {}).get("error") if scopes else None,
        "duplicate_ids": ["%s (%s, %s)" % (rid, os.path.basename(p1), os.path.basename(p2))
                          for rid, p1, p2 in dups],
    }
    issues = (len(report["quarantined"]) + len(report["orphan_outcomes"])
              + len(report["dangling_supersedes"]) + len(report["invalid_scopes"])
              + len(report["duplicate_ids"]) + (1 if report["scopes_error"] else 0))

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if issues == 0 else 1

    lines = ["draille doctor: %d records, %d outcomes | issues: %s"
            % (report["n_records"], report["n_outcomes"], issues if issues else "none")]
    if report["quarantined"]:
        lines.append("  quarantined records (%d): %s" % (len(report["quarantined"]), ", ".join(report["quarantined"])))
    if report["orphan_outcomes"]:
        lines.append("  orphan outcomes (%d): %s" % (len(report["orphan_outcomes"]), ", ".join(report["orphan_outcomes"])))
    if report["dangling_supersedes"]:
        lines.append("  dangling supersedes (%d): %s" % (len(report["dangling_supersedes"]), ", ".join(report["dangling_supersedes"])))
    if report["scopes_error"]:
        lines.append("  scopes.json: %s" % report["scopes_error"])
    if report["invalid_scopes"]:
        lines.append("  invalid scopes.json homes (%d): %s" % (len(report["invalid_scopes"]), ", ".join(report["invalid_scopes"])))
    if report["duplicate_ids"]:
        lines.append("  duplicate ids (%d): %s" % (len(report["duplicate_ids"]), ", ".join(report["duplicate_ids"])))
    sys.stdout.write("\n".join(lines) + "\n")
    return 0 if issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
