#!/usr/bin/env python3
"""Memory prime — rank durable records into a budgeted digest for session start.

Glob records/*.md -> parse frontmatter -> JOIN outcomes.jsonl tally -> weighted rank -> budget digest.
4 guards: invalid frontmatter is QUARANTINED (stderr, never halt); orphan outcomes ignored;
on-demand (always reads live files -> stale != broken); git is the WORM layer (a deleted/
corrupted record is recoverable from git log). Stdlib only.

Obsolescence by supersession: a record's `supersedes: <id>` frontmatter key retires that id
from the digest (dead for ranking, still on disk). No recursive resolution — the hidden set
is every id named by any live record's supersedes.

Root resolution: $MEMORY_ROOT env var, else the git root of the cwd, else cwd.
Default scan: every <root>/**/memory/records (mono-project = just <root>/memory/records),
outcomes at <root>/memory/outcomes.jsonl.

Scope-blind by design: scans every scope home and reads the one central
outcomes log — scopes.json only changes record.py's routing.

Usage: prime.py [MEMORY_DIR] [--dir MEMORY_DIR]   (explicit dir has records/ + outcomes.jsonl; overrides root scan)
"""
import sys, os, json, glob

CLASS_W = {"foundational": 50, "tactical": 20, "observational": 10}
BUDGET = 6000  # bytes of digest


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
    recs, quarantined = [], []
    for path in sorted(glob.glob(os.path.join(glob.escape(records_dir), "*.md"))):
        try:
            with open(path, encoding="utf-8") as f:
                meta, body = parse_frontmatter(f.read())
            if not meta.get("id"):
                raise ValueError("missing id")
            meta["_title"] = next((l[2:].strip() for l in body.splitlines()
                                   if l.startswith("# ")), os.path.basename(path))
            recs.append(meta)
        except Exception as e:                       # GUARD: quarantine, never halt
            quarantined.append(path)
            sys.stderr.write("QUARANTINE %s: %s\n" % (os.path.basename(path), e))
    return recs, quarantined


def load_outcomes(path):
    tally = {}
    if not os.path.exists(path):
        return tally
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:                        # GUARD: skip malformed line, never crash
                continue
            rid, st = o.get("id"), o.get("status")
            if not rid:
                continue
            t = tally.setdefault(rid, {"success": 0, "failure": 0, "partial": 0})
            if st in t:
                t[st] += 1
    return tally


def score(rec, tally):
    t = tally.get(rec.get("id"), {})
    return (CLASS_W.get(rec.get("classification", "observational"), 10)
            + t.get("success", 0) * 30 - t.get("failure", 0) * 20)


def main(argv):
    if len(argv) > 2 and argv[1] == "--dir":  # same flag as record/outcome
        argv = [argv[0], argv[2]]
    if len(argv) > 1:                                   # explicit dir (tests / single scope)
        record_dirs = [os.path.join(argv[1], "records")]
        outcomes_path = os.path.join(argv[1], "outcomes.jsonl")
    else:                                               # default: every per-scope home under the root
        root = memory_root()
        record_dirs = glob.glob(os.path.join(glob.escape(root), "**", "memory", "records"), recursive=True)
        outcomes_path = os.path.join(root, "memory", "outcomes.jsonl")  # one central id-keyed log
    recs, quarantined = [], []
    for d in record_dirs:
        r, q = load_records(d)
        recs += r
        quarantined += q
    tally = load_outcomes(outcomes_path)
    # Obsolescence by supersession: a record naming another via `supersedes: <id>` retires
    # that id from the ranking (dead for prime/search, still on disk = git/history). No
    # recursive resolution needed: the hidden set is just every id that appears as *someone
    # else's* supersedes value (A supersedes B, C supersedes A -> hidden={A,B}, C stays).
    superseded_ids = {r["supersedes"] for r in recs if r.get("supersedes")}
    hidden = [r for r in recs if r.get("id") in superseded_ids]
    recs = [r for r in recs if r.get("id") not in superseded_ids]
    # orphan outcomes (an id with no record, e.g. its markdown was deleted) are ignored by
    # construction: we only ever emit `recs`, and score() reads the tally by the record's own id.
    recs.sort(key=lambda r: score(r, tally), reverse=True)
    out = ["# draille — durable memory (prime)\n"]
    size = len(out[0])
    for r in recs:
        star = tally.get(r["id"], {}).get("success", 0)
        block = ("## [%s] %s\n   id:%s | %s | ★%d | score=%d%s\n" % (
            r.get("type", "?"), r["_title"], r["id"], r.get("classification", "?"),
            star, score(r, tally), (" | " + r["summary"]) if r.get("summary") else ""))
        if size + len(block) > BUDGET:
            out.append("…(capped at %dB — %d records total)\n" % (BUDGET, len(recs)))
            break
        out.append(block)
        size += len(block)
    if quarantined:
        out.append("\n⚠ %d record(s) quarantined (invalid frontmatter) — see stderr\n"
                   % len(quarantined))
    if hidden:
        out.append("\n(%d superseded record(s) hidden)\n" % len(hidden))
    sys.stdout.write("".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
