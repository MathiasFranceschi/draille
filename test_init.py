#!/usr/bin/env python3
"""Tests for init.py — scaffolds records/, journal/, HANDOVER.md (never overwritten),
root resolution (MEMORY_ROOT / git ascension), --dir escape."""
import subprocess, tempfile, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
INIT = os.path.join(HERE, "draille", "init.py")
res = {"p": 0, "f": 0}


def ok(c, m):
    res["p" if c else "f"] += 1
    print(("  ok   " if c else "  FAIL ") + m)


def run(args, env, cwd=None):
    return subprocess.run([sys.executable, INIT] + args, capture_output=True, text=True, env=env, cwd=cwd)


def env_for(root):
    e = os.environ.copy()
    e["MEMORY_ROOT"] = root
    return e


# --- AC1: fresh repo -> creates HANDOVER.md + journal/ + records/, prints bootstrap block, exit 0 ---
with tempfile.TemporaryDirectory() as tmp:
    env = env_for(tmp)
    r = run([], env)
    ok(r.returncode == 0, "AC1: init exit 0 on a fresh root")
    mem = os.path.join(tmp, "memory")
    ok(os.path.isdir(os.path.join(mem, "records")), "AC1: memory/records/ created")
    ok(os.path.isdir(os.path.join(mem, "journal")), "AC1: memory/journal/ created")
    handover_path = os.path.join(mem, "HANDOVER.md")
    ok(os.path.isfile(handover_path), "AC1: memory/HANDOVER.md created")
    original = open(handover_path, encoding="utf-8").read()
    ok("role: handover" in original, "AC1: HANDOVER.md has minimal frontmatter")
    ok("## CORE" in original, "AC1: HANDOVER.md has a CORE block")
    ok(len(original.splitlines()) <= 15, "AC1: HANDOVER.md template is <=15 lines")
    ok("draille prime" in r.stdout, "AC1: bootstrap block printed on stdout")

    # --- AC2: re-run is idempotent, HANDOVER.md preserved byte-for-byte ---
    with open(handover_path, "a", encoding="utf-8") as f:
        f.write("\n<!-- user edit -->\n")
    edited = open(handover_path, encoding="utf-8").read()
    r2 = run([], env)
    ok(r2.returncode == 0, "AC2: re-run exit 0")
    ok("exists, skipped" in r2.stderr, "AC2: re-run signals HANDOVER.md exists, skipped")
    ok(open(handover_path, encoding="utf-8").read() == edited,
       "AC2: HANDOVER.md preserved byte-for-byte across re-run")
    ok(os.path.isdir(os.path.join(mem, "records")) and os.path.isdir(os.path.join(mem, "journal")),
       "AC2: records/ + journal/ still present after re-run")

# --- AC1: git-root ascension (no MEMORY_ROOT) — cwd walks up to the nearest .git ---
with tempfile.TemporaryDirectory() as tmp:
    os.mkdir(os.path.join(tmp, ".git"))
    sub = os.path.join(tmp, "a", "b")
    os.makedirs(sub)
    env = os.environ.copy()
    env.pop("MEMORY_ROOT", None)
    r = run([], env, cwd=sub)
    ok(r.returncode == 0, "ascension: init exit 0 from a nested cwd, no MEMORY_ROOT")
    ok(os.path.isfile(os.path.join(tmp, "memory", "HANDOVER.md")),
       "ascension: memory/ scaffolded under the .git root, not the nested cwd")
    ok(not os.path.exists(os.path.join(sub, "memory")),
       "ascension: nothing written under the nested cwd")

# --- AC3: MEMORY_ROOT respected, nothing written outside root ---
with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "root")
    os.makedirs(root)
    outside = os.path.join(tmp, "outside")
    env = env_for(root)
    r = run([], env, cwd=outside if os.path.isdir(outside) else tmp)
    ok(r.returncode == 0, "AC3: init exit 0 with MEMORY_ROOT set")
    ok(os.path.isdir(os.path.join(root, "memory", "records")), "AC3: scaffolded under MEMORY_ROOT")
    ok(not os.path.exists(outside), "AC3: nothing written outside MEMORY_ROOT")

# --- AC4: --dir escape ignores MEMORY_ROOT entirely, D itself is the memory dir ---
with tempfile.TemporaryDirectory() as tmp:
    unrelated_root = os.path.join(tmp, "unrelated-root")
    env = env_for(unrelated_root)
    dir_ = os.path.join(tmp, "explicit-dir")
    os.makedirs(dir_)

    r = run(["--dir", dir_], env)
    ok(r.returncode == 0, "--dir escape: init exit 0")
    ok(not os.path.exists(unrelated_root), "--dir escape: MEMORY_ROOT untouched (true escape)")
    ok(os.path.isdir(os.path.join(dir_, "records")), "--dir escape: records/ created directly under DIR")
    ok(os.path.isdir(os.path.join(dir_, "journal")), "--dir escape: journal/ created directly under DIR")
    ok(os.path.isfile(os.path.join(dir_, "HANDOVER.md")), "--dir escape: HANDOVER.md created directly under DIR")

# --- SECURITY: a HANDOVER.md symlink must NOT be followed (no write-escape, no clobber) ---
with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "root")
    mem = os.path.join(root, "memory")
    os.makedirs(mem)
    victim = os.path.join(tmp, "victim.txt")  # outside the root
    os.symlink(victim, os.path.join(mem, "HANDOVER.md"))  # dangling link aimed outside root
    env = env_for(root)
    r = run([], env)
    ok(r.returncode == 0, "symlink: init exit 0")
    ok("exists, skipped" in r.stderr, "symlink: existing HANDOVER.md symlink treated as present, skipped")
    ok(not os.path.exists(victim), "symlink: nothing written through the link outside the root")

print("init tests: %d passed, %d failed" % (res["p"], res["f"]))
sys.exit(0 if res["f"] == 0 else 1)
