#!/usr/bin/env python3
"""Tests for migrate.py — legacy jsonl -> markdown + outcome-log, then prime reads it.
migrate.py takes an explicit (domain.jsonl, out_records_dir, out_outcomes.jsonl) — no root
resolution involved, so it is unaffected by MEMORY_ROOT / scopes.json. Copied verbatim."""
import subprocess, tempfile, os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
MIG = os.path.join(HERE, "migrate.py")
PRIME = os.path.join(HERE, "prime.py")
res = {"p": 0, "f": 0}


def ok(c, m):
    res["p" if c else "f"] += 1
    print(("  ok   " if c else "  FAIL ") + m)


with tempfile.TemporaryDirectory() as tmp:
    src = os.path.join(tmp, "dom.jsonl")
    with open(src, "w") as f:
        f.write(json.dumps({"id": "mx-1", "type": "decision", "classification": "foundational",
                            "recorded_at": "2026-06-01T10:00:00Z", "evidence": {"commit": "abc123"},
                            "dir_anchors": ["01_X/Y"], "title": "Use Postgres", "rationale": "Because RLS."}) + "\n")
        f.write(json.dumps({"id": "mx-2", "type": "failure", "classification": "tactical",
                            "recorded_at": "2026-06-02T10:00:00Z", "description": "Boom", "resolution": "Fix it",
                            "outcomes": [{"status": "success", "recorded_at": "2026-06-03T10:00:00Z", "notes": "worked"}]}) + "\n")
        f.write("{ bad json line\n")
    rdir = os.path.join(tmp, "records")
    ocp = os.path.join(tmp, "outcomes.jsonl")
    r = subprocess.run([sys.executable, MIG, src, rdir, ocp], capture_output=True, text=True)
    ok(r.returncode == 0, "migrate exit 0 (skips malformed jsonl line)")
    files = os.listdir(rdir)
    ok(len(files) == 2, "2 valid records -> 2 markdown files (bad line skipped)")
    txt = open(os.path.join(rdir, [f for f in files if "mx-1" in f][0])).read()
    ok("01_X/Y" not in txt, "dir_anchors path DROPPED (path-independence)")
    ok("evidence_sha:" in txt and "abc123" in txt, "evidence.commit -> evidence_sha frontmatter")
    ok("# Use Postgres" in txt and "Because RLS" in txt, "decision title + rationale in body")
    ocs = open(ocp).read()
    ok('"id": "mx-2"' in ocs and '"status": "success"' in ocs, "outcome migrated to log, keyed by id")
    p = subprocess.run([sys.executable, PRIME, tmp], capture_output=True, text=True)
    ok(p.returncode == 0 and "mx-1" in p.stdout and "mx-2" in p.stdout, "prime reads the migrated records (round-trip)")
    ok("★1" in p.stdout, "migrated outcome reflected in prime ★ rank")

# --- security: hostile jsonl id must not traverse out of outdir (filename is slugged, raw id kept as join key) ---
with tempfile.TemporaryDirectory() as tmp:
    src = os.path.join(tmp, "evil.jsonl")
    with open(src, "w") as f:
        f.write(json.dumps({"id": "../../esc-target", "type": "decision", "classification": "tactical",
                            "recorded_at": "2026-06-01T00:00:00Z", "title": "evil rec", "rationale": "x"}) + "\n")
    rdir = os.path.join(tmp, "out", "records")
    r = subprocess.run([sys.executable, MIG, src, rdir, os.path.join(tmp, "out", "oc.jsonl")],
                       capture_output=True, text=True)
    ok(r.returncode == 0, "security: hostile id migrate still exit 0")
    inside = os.listdir(rdir)
    ok(len(inside) == 1 and inside[0].endswith(".md"), "security: record written INSIDE outdir")
    ok(not os.path.exists(os.path.join(tmp, "esc-target")) and not any(
        "esc-target" in f for f in os.listdir(tmp)), "security: no file escaped outdir via ../../ id")
    txt = open(os.path.join(rdir, inside[0])).read()
    ok("id: ../../esc-target" in txt, "security: RAW id preserved in frontmatter (join key intact)")

print("migrate tests: %d passed, %d failed" % (res["p"], res["f"]))
sys.exit(0 if res["f"] == 0 else 1)
