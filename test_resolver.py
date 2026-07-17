#!/usr/bin/env python3
"""Tests for record.py's "_resolver" dynamic scope routing (scopes.json)."""
import subprocess, tempfile, os, sys, json, stat

HERE = os.path.dirname(os.path.abspath(__file__))
REC = os.path.join(HERE, "draille", "record.py")
res = {"p": 0, "f": 0}


def ok(c, m):
    res["p" if c else "f"] += 1
    print(("  ok   " if c else "  FAIL ") + m)


def run(args, env, cwd=None):
    return subprocess.run([sys.executable] + args, capture_output=True, text=True, env=env, cwd=cwd)


def env_for(root, trust=True):
    """MEMORY_ROOT=root, plus a hermetic HOME (inside root, cleaned up with the tempdir)
    so record.py's hardcoded ~/.config/draille/trusted-roots never touches the real
    trust store — there's no env override for that path anymore (RISK 1 fix)."""
    e = os.environ.copy()
    e["MEMORY_ROOT"] = root
    home = os.path.join(root, ".home")
    trust_dir = os.path.join(home, ".config", "draille")
    os.makedirs(trust_dir, exist_ok=True)
    if trust:
        with open(os.path.join(trust_dir, "trusted-roots"), "w") as f:
            f.write(os.path.realpath(root) + "\n")
    e["HOME"] = home
    return e


def write_script(path, body):
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# --- AC1: valid resolver echoes an absolute dir inside root -> record lands there ---
with tempfile.TemporaryDirectory() as tmp:
    target = os.path.join(tmp, "resolved-topic")
    os.makedirs(target)
    resolver = os.path.join(tmp, "resolve-ok.sh")
    write_script(resolver, 'echo "%s/$1"\n' % tmp)  # prints <tmp>/<value>, always inside root
    os.makedirs(os.path.join(tmp, "memory"), exist_ok=True)
    with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
        json.dump({"_resolver": resolver, "sport": "resolved-topic"}, f)

    env = env_for(tmp)
    r = run([REC, "pattern", "tactical", "resolved rec", "--scope", "sport"], env)
    ok(r.returncode == 0, "AC1: resolver-routed scope exit 0")
    rid = r.stdout.strip()
    rdir = os.path.join(target, "memory", "records")
    ok(os.path.isdir(rdir) and any(rid in x for x in os.listdir(rdir)),
       "AC1: record written under the resolver's printed dir + /memory/records/")

# --- AC2 (a): resolver exits non-zero -> exit 2, nothing written ---
with tempfile.TemporaryDirectory() as tmp:
    resolver = os.path.join(tmp, "resolve-fail.sh")
    write_script(resolver, 'echo "should not be used"\nexit 1\n')
    os.makedirs(os.path.join(tmp, "memory"), exist_ok=True)
    with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
        json.dump({"_resolver": resolver, "sport": "topic"}, f)

    env = env_for(tmp)
    r = run([REC, "pattern", "tactical", "fail rec", "--scope", "sport"], env)
    ok(r.returncode == 2, "AC2(a): resolver exit 1 -> record.py exit 2")
    for needle in ("sport", "topic", "should not be used"):
        ok(needle in r.stderr, "AC2(a): stderr mentions %r (scope/value/candidates)" % needle)
    ok(not os.path.exists(os.path.join(tmp, "topic")), "AC2(a): no directory created for the scope")

# --- AC2 (b): resolver prints empty output -> exit 2, nothing written ---
with tempfile.TemporaryDirectory() as tmp:
    resolver = os.path.join(tmp, "resolve-empty.sh")
    write_script(resolver, "true\n")
    os.makedirs(os.path.join(tmp, "memory"), exist_ok=True)
    with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
        json.dump({"_resolver": resolver, "sport": "topic"}, f)

    env = env_for(tmp)
    r = run([REC, "pattern", "tactical", "empty rec", "--scope", "sport"], env)
    ok(r.returncode == 2, "AC2(b): resolver empty output -> exit 2")
    ok("sport" in r.stderr and "topic" in r.stderr, "AC2(b): stderr mentions scope + value")
    ok(not os.path.exists(os.path.join(tmp, "topic")), "AC2(b): no directory created for the scope")

# --- AC2 (c): resolver prints two lines -> exit 2, nothing written ---
with tempfile.TemporaryDirectory() as tmp:
    resolver = os.path.join(tmp, "resolve-twolines.sh")
    write_script(resolver, 'echo "%s/one"\necho "%s/two"\n' % (tmp, tmp))
    os.makedirs(os.path.join(tmp, "memory"), exist_ok=True)
    with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
        json.dump({"_resolver": resolver, "sport": "topic"}, f)

    env = env_for(tmp)
    r = run([REC, "pattern", "tactical", "two line rec", "--scope", "sport"], env)
    ok(r.returncode == 2, "AC2(c): resolver two-line output -> exit 2")
    ok("sport" in r.stderr and "topic" in r.stderr, "AC2(c): stderr mentions scope + value")
    ok(not os.path.exists(os.path.join(tmp, "one")) and not os.path.exists(os.path.join(tmp, "two")),
       "AC2(c): no directory created for either candidate")

# --- AC3: no "_resolver" key -> byte-identical literal-path behavior ---
with tempfile.TemporaryDirectory() as tmp:
    os.makedirs(os.path.join(tmp, "memory"), exist_ok=True)
    with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
        json.dump({"sport": "vault/sport", "central": "."}, f)

    env = env_for(tmp)
    r = run([REC, "pattern", "tactical", "literal rec", "--scope", "sport"], env)
    ok(r.returncode == 0, "AC3: no _resolver -> known scope still routes as a literal path")
    rid = r.stdout.strip()
    sdir = os.path.join(tmp, "vault", "sport", "memory", "records")
    ok(os.path.isdir(sdir) and any(rid in x for x in os.listdir(sdir)),
       "AC3: record landed at the literal scopes.json path, unresolved")

# --- containment: resolver returns a path OUTSIDE root -> blocked by the existing check ---
with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "root")
    outside = os.path.join(tmp, "outside")
    os.makedirs(os.path.join(root, "memory"), exist_ok=True)
    resolver = os.path.join(tmp, "resolve-outside.sh")
    write_script(resolver, 'echo "%s"\n' % outside)
    with open(os.path.join(root, "memory", "scopes.json"), "w") as f:
        json.dump({"_resolver": resolver, "sport": "topic"}, f)

    env = env_for(root)
    r = run([REC, "pattern", "tactical", "outside rec", "--scope", "sport"], env)
    ok(r.returncode == 2, "containment: resolver escaping root -> exit 2")
    ok("unsafe home" in r.stderr, "containment: existing containment error message still fires")
    ok(not os.path.exists(outside), "containment: nothing written outside root")

# --- trust gate: untrusted root + _resolver -> exit 2, nothing written, remedies named ---
with tempfile.TemporaryDirectory() as tmp:
    resolver = os.path.join(tmp, "resolve-ok.sh")
    write_script(resolver, 'echo "%s/$1"\n' % tmp)
    os.makedirs(os.path.join(tmp, "memory"), exist_ok=True)
    with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
        json.dump({"_resolver": resolver, "sport": "topic"}, f)

    env = env_for(tmp, trust=False)
    r = run([REC, "pattern", "tactical", "untrusted rec", "--scope", "sport"], env)
    ok(r.returncode == 2, "trust gate: untrusted root -> exit 2")
    ok("trusted-roots" in r.stderr, "trust gate: stderr names the trusted-roots file")
    ok("_resolver" in r.stderr, "trust gate: stderr names the other remedy (remove _resolver)")
    ok(not os.path.exists(os.path.join(tmp, "topic")), "trust gate: nothing written for untrusted root")

# --- trust gate: trusted root -> AC1-style resolve still works (env_for default) ---
with tempfile.TemporaryDirectory() as tmp:
    target = os.path.join(tmp, "resolved-topic")
    os.makedirs(target)
    resolver = os.path.join(tmp, "resolve-ok.sh")
    write_script(resolver, 'echo "%s/$1"\n' % tmp)
    os.makedirs(os.path.join(tmp, "memory"), exist_ok=True)
    with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
        json.dump({"_resolver": resolver, "sport": "resolved-topic"}, f)

    env = env_for(tmp)  # trust=True default
    r = run([REC, "pattern", "tactical", "trusted rec", "--scope", "sport"], env)
    ok(r.returncode == 0, "trust gate: trusted root -> resolver still runs, exit 0")
    rid = r.stdout.strip()
    rdir = os.path.join(target, "memory", "records")
    ok(os.path.isdir(rdir) and any(rid in x for x in os.listdir(rdir)),
       "trust gate: trusted root -> record still lands under the resolved dir")

# --- risk fix: malformed _resolver quoting -> exit 2, clean error, no traceback ---
with tempfile.TemporaryDirectory() as tmp:
    os.makedirs(os.path.join(tmp, "memory"), exist_ok=True)
    with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
        json.dump({"_resolver": 'echo "unterminated', "sport": "topic"}, f)

    env = env_for(tmp)
    r = run([REC, "pattern", "tactical", "malformed rec", "--scope", "sport"], env)
    ok(r.returncode == 2, "malformed _resolver quoting -> exit 2")
    ok("Traceback" not in r.stderr, "malformed _resolver quoting -> clean error, no traceback")
    ok(not os.path.exists(os.path.join(tmp, "topic")), "malformed _resolver quoting -> nothing written")

# --- risk fix: non-string scope value -> exit 2, clean error, no traceback ---
with tempfile.TemporaryDirectory() as tmp:
    resolver = os.path.join(tmp, "resolve-ok.sh")
    write_script(resolver, 'echo "%s/$1"\n' % tmp)
    os.makedirs(os.path.join(tmp, "memory"), exist_ok=True)
    with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
        json.dump({"_resolver": resolver, "sport": 42}, f)

    env = env_for(tmp)
    r = run([REC, "pattern", "tactical", "nonstring rec", "--scope", "sport"], env)
    ok(r.returncode == 2, "non-string scope value -> exit 2")
    ok("Traceback" not in r.stderr, "non-string scope value -> clean error, no traceback")

print("resolver tests: %d passed, %d failed" % (res["p"], res["f"]))
sys.exit(0 if res["f"] == 0 else 1)
