#!/usr/bin/env python3
"""Ranked search over durable memory records — no index, no state, pure stdlib.

For each record, counts query tokens (lowercased) in title (x3), summary (x2),
and body (x1). A record with zero token matches is excluded outright (its
classification/outcome weight never rescues it into the results). Surviving
records add a classification weight (foundational 5 / tactical 2 /
observational 1) and an outcomes tally (+2 success, -1 failure, from
outcomes.jsonl, same join-by-id contract as prime.py). Records superseded by
another live record (`supersedes: <id>` in its frontmatter) are hidden by
default; pass --all/--include-superseded to reinclude them.

Root resolution + discovery = same contract as prime.py: $MEMORY_ROOT env var,
else git root of cwd, else cwd. Default scan: every <root>/**/memory/records
(mono-project = just <root>/memory/records), outcomes at
<root>/memory/outcomes.jsonl. --dir D: records at D/records, outcomes at
D/outcomes.jsonl. Invalid frontmatter is quarantined (stderr), never halts.

BYO backend: if $DRAILLE_SEARCH_CMD is set (and neither --engine builtin nor
--dir is passed), delegates to it instead of scanning — see docs/backends.md.

Usage: search.py <term> [term ...] [-n N] [--dir MEMORY_DIR] [--engine builtin|env]
"""
import sys, os, glob, json, argparse, shlex, subprocess

CLASS_BONUS = {"foundational": 5, "tactical": 2, "observational": 1}


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
    """Like prime.py's load_records, but also keeps the raw body (for scoring) and path (for display)."""
    recs, quarantined = [], []
    for path in sorted(glob.glob(os.path.join(records_dir, "*.md"))):
        try:
            with open(path, encoding="utf-8") as f:
                meta, body = parse_frontmatter(f.read())
            if not meta.get("id"):
                raise ValueError("missing id")
            meta["_title"] = next((l[2:].strip() for l in body.splitlines()
                                   if l.startswith("# ")), os.path.basename(path))
            meta["_body"] = body
            meta["_path"] = path
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


def text_score(rec, tokens):
    title, summary, body = rec["_title"].lower(), rec.get("summary", "").lower(), rec["_body"].lower()
    s = 0
    for tok in tokens:
        s += title.count(tok) * 3 + summary.count(tok) * 2 + body.count(tok) * 1
    return s


def score(rec, tokens, tally):
    """(text_score, total_score). Caller drops records whose text_score is 0."""
    ts = text_score(rec, tokens)
    if ts == 0:
        return 0, 0
    t = tally.get(rec.get("id"), {})
    total = ts + CLASS_BONUS.get(rec.get("classification", "observational"), 1) \
        + t.get("success", 0) * 2 - t.get("failure", 0) * 1
    return ts, total


def main(argv):
    p = argparse.ArgumentParser(prog=os.path.basename(argv[0]),
                                description="Ranked search over durable memory records.")
    p.add_argument("terms", nargs="+", help="search terms (matched case-insensitively)")
    p.add_argument("-n", type=int, default=10, help="max results (default 10)")
    p.add_argument("--dir", dest="dir_override", default="",
                   help="explicit memory dir (escape hatch — bypasses root scan)")
    p.add_argument("--engine", choices=["builtin", "env"], default=None,
                   help="builtin: internal scan. env: delegate to $DRAILLE_SEARCH_CMD. "
                        "Default: env if DRAILLE_SEARCH_CMD is set, else builtin.")
    p.add_argument("--all", "--include-superseded", dest="include_superseded", action="store_true",
                   help="include records superseded by another record (hidden by default)")
    a = p.parse_args(argv[1:])
    if a.n < 1:
        p.error("-n must be >= 1")               # GUARD: -n 0/-1 would silently slice hits away

    env_cmd = os.environ.get("DRAILLE_SEARCH_CMD", "")
    # --dir is the builtin escape hatch: it never routes to a backend implicitly
    engine = a.engine or ("env" if env_cmd and not a.dir_override else "builtin")
    if engine == "env":
        if a.dir_override:
            p.error("--dir only works with the builtin engine")
        try:
            cmd = shlex.split(env_cmd)
        except ValueError as e:                      # GUARD: unbalanced quotes → clean error, no traceback
            p.error("invalid DRAILLE_SEARCH_CMD: %s" % e)
        if not cmd:                                  # GUARD: empty/blank cmd would exec the query terms
            p.error("--engine env requires a non-empty DRAILLE_SEARCH_CMD")
        child_env = os.environ.copy()
        child_env["MEMORY_ROOT"] = memory_root()
        try:
            return subprocess.call(cmd + a.terms, env=child_env)  # no shell=True — terms are untrusted input
        except OSError as e:                         # GUARD: missing/non-executable backend
            sys.stderr.write("cannot run DRAILLE_SEARCH_CMD %r: %s\n" % (cmd[0], e))
            return 127

    tokens = [t.lower() for t in a.terms if t]

    if a.dir_override:
        root_disp = a.dir_override
        record_dirs = [os.path.join(a.dir_override, "records")]
        outcomes_path = os.path.join(a.dir_override, "outcomes.jsonl")
    else:
        root_disp = memory_root()
        record_dirs = glob.glob(os.path.join(root_disp, "**", "memory", "records"), recursive=True)
        outcomes_path = os.path.join(root_disp, "memory", "outcomes.jsonl")

    recs = []
    for d in record_dirs:
        r, _ = load_records(d)
        recs += r
    tally = load_outcomes(outcomes_path)

    # Obsolescence by supersession (same contract as prime.py): hide any record whose id is
    # named by another live record's `supersedes` — unless --all/--include-superseded.
    if not a.include_superseded:
        superseded_ids = {r["supersedes"] for r in recs if r.get("supersedes")}
        recs = [r for r in recs if r.get("id") not in superseded_ids]

    hits = []
    for rec in recs:
        ts, total = score(rec, tokens, tally)
        if ts == 0:
            continue
        hits.append((total, rec))
    hits.sort(key=lambda h: h[0], reverse=True)

    if not hits:
        sys.stderr.write("no matches\n")
        return 0

    for total, rec in hits[:a.n]:
        rel = os.path.relpath(rec["_path"], root_disp)
        print("score=%d [%s] %s — id:%s — %s" % (
            total, rec.get("type", "?"), rec["_title"], rec.get("id", "?"), rel))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
