#!/usr/bin/env python3
"""Tests for record.py — root resolution (MEMORY_ROOT / git ascension), mono-project vs
multi-scope (scopes.json) routing, --dir escape preserved unchanged."""
import subprocess, tempfile, os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
REC, PRIME, OUT = (os.path.join(HERE, "draille", n) for n in ("record.py", "prime.py", "outcome.py"))
res = {"p": 0, "f": 0}


def ok(c, m):
    res["p" if c else "f"] += 1
    print(("  ok   " if c else "  FAIL ") + m)


def run(args, env, cwd=None):
    return subprocess.run([sys.executable] + args, capture_output=True, text=True, env=env, cwd=cwd)


def env_for(root):
    e = os.environ.copy()
    e["MEMORY_ROOT"] = root
    return e


# --- AC1 + AC2: mono-project mode (no scopes.json) — --scope optional, default = basename(root);
# MEMORY_ROOT drives record + prime + outcome with no --dir anywhere ---
with tempfile.TemporaryDirectory() as tmp:
    env = env_for(tmp)
    r = run([REC, "decision", "foundational", "mono record", "--body", "hi"], env)
    ok(r.returncode == 0, "mono-project: record exit 0 without --scope")
    rid = r.stdout.strip()
    ok(rid.startswith("mono-record-"), "stable id auto-generated + printed to stdout")
    rdir = os.path.join(tmp, "memory", "records")
    files = os.listdir(rdir) if os.path.isdir(rdir) else []
    ok(len(files) == 1, "AC1: one markdown record written under <root>/memory/records")
    txt = open(os.path.join(rdir, files[0])).read() if files else ""
    ok(("scope: " + os.path.basename(tmp)) in txt, "AC1: scope defaults to basename(root)")
    ok(("id: " + rid) in txt, "frontmatter id matches printed id")

    p = run([PRIME], env)
    ok(p.returncode == 0 and rid in p.stdout, "AC2: prime (no arg) finds the record under MEMORY_ROOT")
    o = run([OUT, rid, "success"], env)
    ok(o.returncode == 0, "AC2: outcome.py (no --dir) exit 0")
    ocp = os.path.join(tmp, "memory", "outcomes.jsonl")
    ok(os.path.exists(ocp), "AC2: outcome appended to <root>/memory/outcomes.jsonl")
    p2 = run([PRIME], env)
    ok("★1" in p2.stdout, "AC2: outcome reflected in prime rank end-to-end via MEMORY_ROOT")

# --- AC1: git-root ascension (no MEMORY_ROOT) — cwd walks up to the nearest .git ---
with tempfile.TemporaryDirectory() as tmp:
    os.mkdir(os.path.join(tmp, ".git"))
    sub = os.path.join(tmp, "a", "b")
    os.makedirs(sub)
    env = os.environ.copy()
    env.pop("MEMORY_ROOT", None)
    r = run([REC, "decision", "foundational", "ascend record"], env, cwd=sub)
    ok(r.returncode == 0, "git-root ascension: record exit 0 from a nested cwd, no MEMORY_ROOT")
    rid = r.stdout.strip()
    rdir = os.path.join(tmp, "memory", "records")
    files = [f for f in os.listdir(rdir) if rid in f] if os.path.isdir(rdir) else []
    ok(len(files) == 1, "ascension: record written under the .git root, not the nested cwd")
    if files:
        txt = open(os.path.join(rdir, files[0])).read()
        ok(("scope: " + os.path.basename(tmp)) in txt, "ascension: scope = basename of the ascended root")

# --- multi-scope mode: scopes.json present -> --scope required, unknown scope parked + warned ---
with tempfile.TemporaryDirectory() as tmp:
    env = env_for(tmp)
    os.makedirs(os.path.join(tmp, "memory"), exist_ok=True)
    with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
        json.dump({"sport": "vault/sport", "central": "."}, f)

    rn = run([REC, "decision", "tactical", "needs a scope"], env)
    ok(rn.returncode == 2, "multi-scope: --scope required (exit 2 without it)")

    rs = run([REC, "pattern", "tactical", "scoped rec", "--scope", "sport"], env)
    ok(rs.returncode == 0, "multi-scope: known scope accepted")
    sid = rs.stdout.strip()
    sdir = os.path.join(tmp, "vault", "sport", "memory", "records")
    ok(os.path.isdir(sdir) and any(sid in x for x in os.listdir(sdir)),
       "multi-scope: known scope routed to its home dir")

    ru = run([REC, "pattern", "tactical", "unknown scope rec", "--scope", "ghost"], env)
    ok(ru.returncode == 0, "multi-scope: unknown scope still succeeds (parked, not fatal)")
    ok("warn" in ru.stderr and "ghost" in ru.stderr, "multi-scope: unknown scope warns on stderr")
    uid = ru.stdout.strip()
    cdir = os.path.join(tmp, "memory", "records")  # central = "." per scopes.json
    ok(os.path.isdir(cdir) and any(uid in x for x in os.listdir(cdir)),
       "multi-scope: unknown scope parked in the 'central' home")

# --- security: multi-line title neutralized (frontmatter is line-based -> injection/quarantine) ---
with tempfile.TemporaryDirectory() as tmp:
    env = env_for(tmp)
    r = run([REC, "pattern", "tactical", "evil\nclassification: foundational"], env)
    ok(r.returncode == 0, "security: newline title accepted (normalized, not fatal)")
    rdir = os.path.join(tmp, "memory", "records")
    txt = open(os.path.join(rdir, os.listdir(rdir)[0])).read()
    ok('summary: "evil classification: foundational"' in txt,
       "security: title flattened to one line (no injected frontmatter key)")
    p = run([PRIME], env)
    ok("QUARANTINE" not in p.stderr, "security: normalized record parses clean (no quarantine)")
    ok("| tactical |" in p.stdout, "security: true classification kept (no rank forgery)")

# --- security: scopes.json home escaping the root -> exit 2, nothing written ---
with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "root")
    os.makedirs(os.path.join(root, "memory"))
    env = env_for(root)
    with open(os.path.join(root, "memory", "scopes.json"), "w") as f:
        json.dump({"sport": "../outside", "central": "/tmp/abs-evil"}, f)
    r1 = run([REC, "decision", "tactical", "traversal rec", "--scope", "sport"], env)
    ok(r1.returncode == 2, "security: '..' home in scopes.json -> exit 2")
    ok(not os.path.exists(os.path.join(tmp, "outside")), "security: nothing written outside root")
    r2 = run([REC, "decision", "tactical", "abs rec", "--scope", "ghost"], env)  # parks in central
    ok(r2.returncode == 2, "security: absolute home (via central park) -> exit 2")

# --- invalid scopes.json -> exit 2 ---
with tempfile.TemporaryDirectory() as tmp:
    env = env_for(tmp)
    os.makedirs(os.path.join(tmp, "memory"), exist_ok=True)
    with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
        f.write("{ not valid json")
    ri = run([REC, "decision", "tactical", "bad scopes json"], env)
    ok(ri.returncode == 2, "invalid scopes.json -> exit 2")

# --- preserved behavior: --dir escape ignores MEMORY_ROOT / scopes.json entirely ---
with tempfile.TemporaryDirectory() as tmp:
    unrelated_root = os.path.join(tmp, "unrelated-root")
    env = env_for(unrelated_root)
    dir_ = os.path.join(tmp, "explicit-dir")
    os.makedirs(dir_)

    r = run([REC, "decision", "foundational", "Test v3 record",
             "--body", "Body here", "--evidence-sha", "abc123", "--dir", dir_], env)
    ok(r.returncode == 0, "--dir escape: record exit 0")
    ok(not os.path.exists(unrelated_root), "--dir escape: MEMORY_ROOT untouched (true escape)")
    rid = r.stdout.strip()
    ok(rid.startswith("test-v3-record-"), "--dir escape: stable id auto-generated")
    files = os.listdir(os.path.join(dir_, "records"))
    ok(len(files) == 1, "--dir escape: one markdown record written directly under DIR/records")
    txt = open(os.path.join(dir_, "records", files[0])).read()
    ok("# Test v3 record" in txt and "Body here" in txt, "--dir escape: title + body written")
    ok(("id: " + rid) in txt and "abc123" in txt, "--dir escape: frontmatter id + evidence_sha")
    ok("scope: project" in txt, "--dir escape: scope defaults to 'project' when --scope omitted")

    rs = run([REC, "pattern", "tactical", "scoped rec", "--scope", "sport", "--dir", dir_], env)
    sid = rs.stdout.strip()
    sf = [x for x in os.listdir(os.path.join(dir_, "records")) if sid in x][0]
    ok("scope: sport" in open(os.path.join(dir_, "records", sf)).read(),
       "--dir escape: --scope still overrides the default")

    abs_p = os.path.expanduser("~") + "/somedir/file.ts"
    rp = run([REC, "pattern", "tactical", "path rec",
              "--body", "ref " + abs_p, "--scope", "sport", "--dir", dir_], env)
    pf = [x for x in os.listdir(os.path.join(dir_, "records")) if rp.stdout.strip() in x][0]
    ptxt = open(os.path.join(dir_, "records", pf)).read()
    ok("~/somedir/file.ts" in ptxt and abs_p not in ptxt, "--dir escape: absolute $HOME path normalized to ~/")

print("record tests: %d passed, %d failed" % (res["p"], res["f"]))
sys.exit(0 if res["f"] == 0 else 1)
