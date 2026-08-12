#!/usr/bin/env python3
"""Tests for expire.py — the retraction path (move-only, never deletes) and its structural
effect on search.py/prime.py (they only glob memory/records/*.md)."""
import subprocess, tempfile, os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
REC = os.path.join(HERE, "draille", "record.py")
SEARCH = os.path.join(HERE, "draille", "search.py")
PRIME = os.path.join(HERE, "draille", "prime.py")
EXPIRE = os.path.join(HERE, "draille", "expire.py")
res = {"p": 0, "f": 0}


def ok(c, m):
    res["p" if c else "f"] += 1
    print(("  ok   " if c else "  FAIL ") + m)


def run(path, args, env, cwd=None):
    return subprocess.run([sys.executable, path] + args, capture_output=True, text=True, env=env, cwd=cwd)


def env_for(root):
    e = os.environ.copy()
    e["MEMORY_ROOT"] = root
    return e


# --- end-to-end: record -> visible in search/prime -> expire -> invisible in both,
# file present under memory/expired/, outcomes.jsonl gets the expire event ---
with tempfile.TemporaryDirectory() as tmp:
    env = env_for(tmp)
    r = run(REC, ["decision", "foundational", "widget config", "--body", "widget notes"], env)
    ok(r.returncode == 0, "setup: record created")
    rid = r.stdout.strip()

    s1 = run(SEARCH, ["widget"], env)
    ok(rid in s1.stdout, "before expire: search finds the record")
    p1 = run(PRIME, [], env)
    ok(("id:" + rid) in p1.stdout, "before expire: prime lists the record")

    src = os.path.join(tmp, "memory", "records")
    src_file = [f for f in os.listdir(src) if rid in f][0]
    src_path = os.path.join(src, src_file)
    src_text = open(src_path).read()

    e1 = run(EXPIRE, [rid], env)
    ok(e1.returncode == 0, "expire: exit 0 on a known id")
    ok(not os.path.exists(src_path), "expire: file gone from memory/records/")

    exp_dir = os.path.join(tmp, "memory", "expired")
    exp_files = os.listdir(exp_dir) if os.path.isdir(exp_dir) else []
    ok(len(exp_files) == 1, "expire: exactly one file landed in memory/expired/")
    ok(exp_files and open(os.path.join(exp_dir, exp_files[0])).read() == src_text,
       "expire: move-only — content byte-identical, nothing deleted")

    s2 = run(SEARCH, ["widget"], env)
    ok(rid not in s2.stdout, "AC1: after expire, search no longer finds the record (structural: glob-based)")
    p2 = run(PRIME, [], env)
    ok(("id:" + rid) not in p2.stdout, "AC1: after expire, prime no longer lists the record (structural)")

    ocp = os.path.join(tmp, "memory", "outcomes.jsonl")
    ok(os.path.exists(ocp), "expire: outcomes.jsonl written")
    events = [json.loads(ln) for ln in open(ocp) if ln.strip()]
    match = [e for e in events if e.get("id") == rid and e.get("action") == "expire"]
    ok(len(match) == 1, "expire: exactly one {id, action: expire} event traced")
    ok("date" in match[0], "expire: traced event carries a date")

# --- unknown id: hard error, exit non-zero, nothing written ---
with tempfile.TemporaryDirectory() as tmp:
    env = env_for(tmp)
    r = run(EXPIRE, ["no-such-id-ffffff"], env)
    ok(r.returncode != 0, "unknown id: exit non-zero")
    ok("no-such-id-ffffff" in r.stderr, "unknown id: error message names the id")
    ok(not os.path.exists(os.path.join(tmp, "memory", "expired")),
       "unknown id: no memory/expired/ dir created")

# --- already expired: second call is a clear no-op, not a crash ---
with tempfile.TemporaryDirectory() as tmp:
    env = env_for(tmp)
    r = run(REC, ["pattern", "tactical", "dup expire target"], env)
    rid = r.stdout.strip()
    e1 = run(EXPIRE, [rid], env)
    ok(e1.returncode == 0, "already-expired setup: first expire exit 0")
    e2 = run(EXPIRE, [rid], env)
    ok("already expired" in e2.stderr, "already-expired: second call reports it clearly")
    exp_dir = os.path.join(tmp, "memory", "expired")
    ok(len(os.listdir(exp_dir)) == 1, "already-expired: still exactly one file, no duplicate/crash")

# --- --dir escape (explicit memory dir, mirrors record/outcome/search --dir contract) ---
with tempfile.TemporaryDirectory() as tmp:
    rdir = os.path.join(tmp, "records")
    os.makedirs(rdir)
    with open(os.path.join(rdir, "manual.md"), "w") as f:
        f.write("---\nid: manual-id-123\ntype: reference\nclassification: observational\nsummary: x\n---\n\n# manual\n")
    env = os.environ.copy()
    env.pop("MEMORY_ROOT", None)

    r = run(EXPIRE, ["manual-id-123", "--dir", tmp], env)
    ok(r.returncode == 0, "--dir escape: expire exit 0")
    ok(not os.path.exists(os.path.join(rdir, "manual.md")), "--dir escape: file gone from DIR/records")
    ok(os.path.exists(os.path.join(tmp, "expired", "manual.md")), "--dir escape: file landed in DIR/expired")
    ocp = os.path.join(tmp, "outcomes.jsonl")
    ok(os.path.exists(ocp), "--dir escape: outcomes.jsonl written directly under DIR")
    events = [json.loads(ln) for ln in open(ocp) if ln.strip()]
    ok(any(e.get("id") == "manual-id-123" and e.get("action") == "expire" for e in events),
       "--dir escape: expire event traced under DIR/outcomes.jsonl")

print("expire tests: %d passed, %d failed" % (res["p"], res["f"]))
sys.exit(0 if res["f"] == 0 else 1)
