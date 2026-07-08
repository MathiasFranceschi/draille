#!/usr/bin/env python3
"""Tests for status.py — dirty (git persistence) + health (counts/quarantine),
--json, MEMORY_ROOT/--dir, and no shell-injection via hostile paths."""
import subprocess, tempfile, os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
STATUS = os.path.join(HERE, "draille", "status.py")
P = F = 0


def ok(cond, msg):
    global P, F
    if cond:
        P += 1; print("  ok   " + msg)
    else:
        F += 1; print("  FAIL " + msg)


def rec(rdir, name, fm, body=None):
    with open(os.path.join(rdir, name + ".md"), "w") as f:
        f.write("---\n" + fm + "\n---\n" + (body or "# " + name) + "\n")


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def git_init_commit(tmp):
    git(["init"], tmp)
    git(["add", "-A"], tmp)
    git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"], tmp)


def run_status(env, *args):
    return subprocess.run([sys.executable, STATUS] + list(args), capture_output=True, text=True, env=env)


def clean_committed_store():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "memory", "records")
        os.makedirs(rdir)
        rec(rdir, "a", "id: a\ntype: decision\nclassification: foundational\nsummary: A")
        with open(os.path.join(tmp, "memory", "outcomes.jsonl"), "w") as f:
            f.write(json.dumps({"id": "a", "status": "success"}) + "\n")
        git_init_commit(tmp)

        env = os.environ.copy()
        env["MEMORY_ROOT"] = tmp
        r = run_status(env)
        ok(r.returncode == 0, "AC1: clean committed store -> exit 0")
        ok("dirty: no" in r.stdout, "AC1: dirty:no reported")
        ok("1 records" in r.stdout and "1 outcomes" in r.stdout, "AC1: counts reported")


def uncommitted_record():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "memory", "records")
        os.makedirs(rdir)
        rec(rdir, "a", "id: a\ntype: decision\nclassification: foundational\nsummary: A")
        git_init_commit(tmp)
        # new record written after the commit -> untracked memory file
        rec(rdir, "b", "id: b\ntype: pattern\nclassification: tactical\nsummary: B")

        env = os.environ.copy()
        env["MEMORY_ROOT"] = tmp
        r = run_status(env)
        ok(r.returncode == 1, "AC2: uncommitted record -> exit 1")
        ok("dirty: yes" in r.stdout, "AC2: dirty:yes reported")

        r_json = run_status(env, "--json")
        d = json.loads(r_json.stdout)
        ok(d["dirty"] is True and d["uncommitted_count"] >= 1,
           "AC2: --json dirty=true, uncommitted_count>=1")


def store_outside_git():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "memory", "records")
        os.makedirs(rdir)
        rec(rdir, "a", "id: a\ntype: decision\nclassification: foundational\nsummary: A")
        # no git init here

        env = os.environ.copy()
        env["MEMORY_ROOT"] = tmp
        r = run_status(env)
        ok(r.returncode == 0, "AC3: store outside git -> exit 0 (unknown isn't a failure)")
        ok("dirty: unknown" in r.stdout, "AC3: dirty:unknown reported")

        d = json.loads(run_status(env, "--json").stdout)
        ok(d["dirty"] is None, "AC3: --json dirty is null/None")


def corrupted_record():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "memory", "records")
        os.makedirs(rdir)
        rec(rdir, "corrupt", "id c no colon here\nnot valid yaml")
        # no git -> isolates quarantine as the sole cause of exit 1

        env = os.environ.copy()
        env["MEMORY_ROOT"] = tmp
        r = run_status(env)
        ok(r.returncode == 1, "AC4: corrupted record -> exit 1")
        ok("quarantined" in r.stdout, "AC4: quarantined reported in human output")

        d = json.loads(run_status(env, "--json").stdout)
        ok(d["quarantined"] == 1, "AC4: --json quarantined count == 1")


def json_output_parsable():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "memory", "records")
        os.makedirs(rdir)
        rec(rdir, "a", "id: a\ntype: decision\nclassification: foundational\nsummary: A")
        git_init_commit(tmp)

        env = os.environ.copy()
        env["MEMORY_ROOT"] = tmp
        r = run_status(env, "--json")
        ok(r.returncode == 0, "AC5: healthy --json -> exit 0")
        try:
            d = json.loads(r.stdout)
            parsable = isinstance(d, dict) and d.get("records") == 1
        except Exception:
            parsable = False
        ok(parsable, "AC5: --json emits a parsable dict with expected keys")


def dir_and_memory_root_respected():
    """--dir overrides MEMORY_ROOT's store, same escape-hatch contract as doctor.py."""
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "memory", "records")
        os.makedirs(rdir)
        rec(rdir, "r", "id: root-1\ntype: decision\nclassification: foundational\nsummary: R")
        git_init_commit(tmp)

        env = os.environ.copy()
        env["MEMORY_ROOT"] = tmp
        r = run_status(env)
        ok(r.returncode == 0 and "1 records" in r.stdout,
           "AC6: MEMORY_ROOT drives default scan")

        with tempfile.TemporaryDirectory() as other:
            odir = os.path.join(other, "records")
            os.makedirs(odir)
            r2 = run_status(env, "--dir", other)
            ok(r2.returncode == 0 and "0 records" in r2.stdout,
               "AC6: --dir overrides MEMORY_ROOT, scans the explicit dir instead")


def hostile_paths_no_shell_injection():
    """A hostile filename/dirname must never reach a shell — git runs via subprocess
    list args, so shell metacharacters in a path are inert."""
    with tempfile.TemporaryDirectory() as tmp:
        evil = os.path.join(tmp, "$(touch pwned)-;rm -rf-- 'x'")
        os.makedirs(evil)
        rdir = os.path.join(evil, "memory", "records")
        os.makedirs(rdir)
        rec(rdir, "$(id)", "id: a\ntype: decision\nclassification: foundational\nsummary: A")
        git_init_commit(evil)
        # uncommitted file with a hostile name too
        rec(rdir, "; touch pwned2 #", "id: b\ntype: pattern\nclassification: tactical\nsummary: B")

        env = os.environ.copy()
        env["MEMORY_ROOT"] = evil
        r = run_status(env)
        ok(r.returncode == 1, "AC7: runs cleanly on hostile paths (dirty due to untracked file)")
        ok(not os.path.exists(os.path.join(tmp, "pwned")) and not os.path.exists(os.path.join(evil, "pwned2")),
           "AC7: no injected command executed (subprocess list, never shell=True)")


def glob_metachar_root():
    """A store root whose path contains a glob charclass ('[..]') must NOT make
    the recursive records scan silently match nothing — that would report a
    corrupt store as clean (exit 0), and a `draille status || persist` hook
    would skip persistence. Root is glob.escape()'d before scanning."""
    with tempfile.TemporaryDirectory() as parent:
        root = os.path.join(parent, "proj[a]")
        rdir = os.path.join(root, "memory", "records")
        os.makedirs(rdir)
        rec(rdir, "good", "id: g\ntype: decision\nclassification: foundational\nsummary: G")
        rec(rdir, "bad", "no frontmatter here")  # corrupt -> must be quarantined
        # no git -> quarantine is the sole cause of any exit 1

        env = os.environ.copy()
        env["MEMORY_ROOT"] = root
        r = run_status(env)
        ok(r.returncode == 1, "AC8: glob-metachar root still sees the store -> exit 1 on corruption")
        d = json.loads(run_status(env, "--json").stdout)
        ok(d["records"] == 1 and d["quarantined"] == 1,
           "AC8: '[' in root path doesn't swallow records/quarantine via glob charclass")


clean_committed_store()
uncommitted_record()
store_outside_git()
corrupted_record()
json_output_parsable()
dir_and_memory_root_respected()
hostile_paths_no_shell_injection()
glob_metachar_root()

print("status tests: %d passed, %d failed" % (P, F))
sys.exit(0 if F == 0 else 1)
