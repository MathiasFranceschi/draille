#!/usr/bin/env python3
"""Tests for doctor.py — quarantine, orphan outcomes, dangling supersedes,
invalid scopes.json homes, duplicate ids, --json, MEMORY_ROOT/--dir."""
import subprocess, tempfile, os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
DOCTOR = os.path.join(HERE, "draille", "doctor.py")
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


def healthy_store():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)
        rec(rdir, "a", "id: a\ntype: decision\nclassification: foundational\nsummary: A")
        rec(rdir, "b", "id: b\ntype: pattern\nclassification: tactical\nsummary: B")
        with open(os.path.join(tmp, "outcomes.jsonl"), "w") as f:
            f.write(json.dumps({"id": "a", "status": "success"}) + "\n")

        r = subprocess.run([sys.executable, DOCTOR, "--dir", tmp], capture_output=True, text=True)
        ok(r.returncode == 0, "AC1: healthy store -> exit 0")
        ok("2 records" in r.stdout and "1 outcomes" in r.stdout, "AC1: counts reported")


def quarantined_record():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)
        rec(rdir, "corrupt", "id c no colon here\nnot valid yaml")

        r = subprocess.run([sys.executable, DOCTOR, "--dir", tmp], capture_output=True, text=True)
        ok(r.returncode == 1, "AC2: corrupt record -> exit 1")
        ok("corrupt.md" in r.stdout, "AC2: quarantined path listed")


def orphan_outcome():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)
        rec(rdir, "a", "id: a\ntype: decision\nclassification: foundational\nsummary: A")
        with open(os.path.join(tmp, "outcomes.jsonl"), "w") as f:
            f.write(json.dumps({"id": "GHOST", "status": "success"}) + "\n")

        r = subprocess.run([sys.executable, DOCTOR, "--dir", tmp], capture_output=True, text=True)
        ok(r.returncode == 1, "AC3: orphan outcome -> exit 1")
        ok("GHOST" in r.stdout, "AC3: orphan outcome id listed")


def dangling_supersedes():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)
        rec(rdir, "a", "id: a\ntype: decision\nclassification: foundational\nsummary: A\nsupersedes: GONE")

        r = subprocess.run([sys.executable, DOCTOR, "--dir", tmp], capture_output=True, text=True)
        ok(r.returncode == 1, "AC4: dangling supersedes -> exit 1")
        ok("a -> GONE" in r.stdout, "AC4: dangling supersedes pair listed")


def json_output():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)
        rec(rdir, "a", "id: a\ntype: decision\nclassification: foundational\nsummary: A")

        r = subprocess.run([sys.executable, DOCTOR, "--dir", tmp, "--json"], capture_output=True, text=True)
        ok(r.returncode == 0, "AC5: healthy --json -> exit 0")
        try:
            d = json.loads(r.stdout)
            parsable = isinstance(d, dict) and d.get("n_records") == 1
        except Exception:
            parsable = False
        ok(parsable, "AC5: --json emits a parsable dict with expected keys")


def duplicate_ids():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)
        rec(rdir, "a1", "id: dup\ntype: decision\nclassification: foundational\nsummary: A1")
        rec(rdir, "a2", "id: dup\ntype: decision\nclassification: foundational\nsummary: A2")

        r = subprocess.run([sys.executable, DOCTOR, "--dir", tmp], capture_output=True, text=True)
        ok(r.returncode == 1, "duplicate ids -> exit 1")
        ok("dup" in r.stdout, "duplicate id reported")


def cross_scope_duplicate_ids():
    """Two scope homes claiming one id must be caught by the recursive scan —
    it breaks the central outcomes.jsonl join key."""
    with tempfile.TemporaryDirectory() as tmp:
        for team in ("teamA", "teamB"):
            rdir = os.path.join(tmp, team, "memory", "records")
            os.makedirs(rdir)
            rec(rdir, team, "id: shared\ntype: decision\nclassification: tactical\nsummary: " + team)
        env = os.environ.copy()
        env["MEMORY_ROOT"] = tmp
        r = subprocess.run([sys.executable, DOCTOR], capture_output=True, text=True, env=env)
        ok(r.returncode == 1, "cross-scope duplicate id -> exit 1")
        ok("shared" in r.stdout, "cross-scope duplicate id reported")


def invalid_scopes():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "memory"))
        with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
            json.dump({"ok": "team/ok", "evil": "/etc", "escape": "../../outside"}, f)
        rdir = os.path.join(tmp, "memory", "records")
        os.makedirs(rdir)

        env = os.environ.copy()
        env["MEMORY_ROOT"] = tmp
        r = subprocess.run([sys.executable, DOCTOR], capture_output=True, text=True, env=env)
        ok(r.returncode == 1, "AC6: invalid scopes.json homes -> exit 1")
        ok("evil" in r.stdout and "escape" in r.stdout, "invalid scopes.json homes named")


def root_and_dir_respected():
    """AC6: MEMORY_ROOT drives default discovery; --dir overrides it."""
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "memory", "records")
        os.makedirs(rdir)
        rec(rdir, "r", "id: root-1\ntype: decision\nclassification: foundational\nsummary: R")

        env = os.environ.copy()
        env["MEMORY_ROOT"] = tmp
        r = subprocess.run([sys.executable, DOCTOR], capture_output=True, text=True, env=env)
        ok(r.returncode == 0 and "1 records" in r.stdout,
           "AC6: MEMORY_ROOT drives default recursive scan")

        # --dir escape hatch points elsewhere and ignores MEMORY_ROOT's store
        with tempfile.TemporaryDirectory() as other:
            odir = os.path.join(other, "records")
            os.makedirs(odir)
            r2 = subprocess.run([sys.executable, DOCTOR, "--dir", other], capture_output=True, text=True, env=env)
            ok(r2.returncode == 0 and "0 records" in r2.stdout,
               "AC6: --dir overrides MEMORY_ROOT, scans the explicit dir instead")


healthy_store()
quarantined_record()
orphan_outcome()
dangling_supersedes()
json_output()
duplicate_ids()
cross_scope_duplicate_ids()
invalid_scopes()
root_and_dir_respected()

print("doctor tests: %d passed, %d failed" % (P, F))
sys.exit(0 if F == 0 else 1)
