#!/usr/bin/env python3
"""Tests for prime.py — explicit-dir mode unchanged (rank+budget, quarantine, orphan ignored),
plus the new default mode: no-arg recursive scan under MEMORY_ROOT / git-root ascension,
with the outcomes log centralized at <root>/memory/outcomes.jsonl regardless of scope home."""
import subprocess, tempfile, os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
PRIME = os.path.join(HERE, "draille", "prime.py")
REC = os.path.join(HERE, "draille", "record.py")
OUT = os.path.join(HERE, "draille", "outcome.py")
P = F = 0


def ok(cond, msg):
    global P, F
    if cond:
        P += 1; print("  ok   " + msg)
    else:
        F += 1; print("  FAIL " + msg)


def explicit_dir_mode():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)

        def rec(name, fm, body=None):
            with open(os.path.join(rdir, name + ".md"), "w") as f:
                f.write("---\n" + fm + "\n---\n" + (body or "# " + name) + "\n")

        rec("found", "id: a\ntype: decision\nclassification: foundational\nsummary: F")  # score 50
        rec("obs", "id: b\ntype: pattern\nclassification: observational\nsummary: O")     # 10 + 2*30 = 70
        rec("blocktags", "id: d\ntype: pattern\nclassification: tactical\ntags:\n  - x\n  - y\nsummary: BT")  # block-style list -> tolerated
        rec("corrupt", "id c no colon here\nnot valid yaml")                              # invalid -> quarantine
        with open(os.path.join(tmp, "outcomes.jsonl"), "w") as f:
            f.write(json.dumps({"id": "b", "status": "success", "sha": "x", "date": "d"}) + "\n")
            f.write(json.dumps({"id": "b", "status": "success", "sha": "y", "date": "d"}) + "\n")
            f.write(json.dumps({"id": "GHOST", "status": "success", "sha": "z", "date": "d"}) + "\n")  # orphan
            f.write("{ this is not json\n")  # malformed outcome line

        r = subprocess.run([sys.executable, PRIME, tmp], capture_output=True, text=True)

        # AC2 — corrupt record quarantined, run still succeeds
        ok(r.returncode == 0, "explicit-dir: exit 0 despite a corrupt record + malformed outcome line")
        ok("QUARANTINE" in r.stderr, "explicit-dir: corrupt record warned to stderr")
        ok("quarantined" in r.stdout, "explicit-dir: quarantine noted in digest")
        # AC1 — valid records emitted, ranked by classification + outcomes
        ok("id:a" in r.stdout and "id:b" in r.stdout, "explicit-dir: both valid records emitted")
        ok("id:d" in r.stdout, "fix: block-style YAML list frontmatter tolerated, not quarantined")
        ia, ib = r.stdout.find("id:a"), r.stdout.find("id:b")
        ok(0 <= ib < ia, "explicit-dir: high-success observational (★2=70) outranks plain foundational (50)")
        ok("★2" in r.stdout, "explicit-dir: success outcomes tallied into ★ count")
        # AC3 — orphan outcome ignored, no crash
        ok("GHOST" not in r.stdout, "explicit-dir: orphan outcome (deleted record) ignored, not emitted")

        # outcome.py round-trip (explicit --dir, unchanged): append success for 'a' (50 -> 80) -> outranks 'b' (70)
        subprocess.run([sys.executable, OUT, "a", "success", "--sha", "z", "--dir", tmp],
                       capture_output=True, text=True)
        r2 = subprocess.run([sys.executable, PRIME, tmp], capture_output=True, text=True)
        ja, jb = r2.stdout.find("id:a"), r2.stdout.find("id:b")
        ok(0 <= ja < jb, "explicit-dir: outcome.py --dir round-trip lifts 'a' (50->80) above 'b' (70)")


def default_root_mode():
    """AC2: MEMORY_ROOT drives the whole chain — multi-scope record -> recursive prime scan
    -> outcome.py's centralized log, independent of which scope home the record lives under."""
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["MEMORY_ROOT"] = tmp
        os.makedirs(os.path.join(tmp, "memory"), exist_ok=True)
        with open(os.path.join(tmp, "memory", "scopes.json"), "w") as f:
            json.dump({"alpha": "team/alpha", "root": "."}, f)

        # scopes.json present -> multi-scope mode -> --scope required for every record, including
        # the one that ends up parked at the root's own memory/ (mapped to "." here).
        r1 = subprocess.run([sys.executable, REC, "decision", "foundational", "root rec", "--scope", "root"],
                             capture_output=True, text=True, env=env)
        r2 = subprocess.run([sys.executable, REC, "pattern", "tactical", "alpha rec", "--scope", "alpha"],
                             capture_output=True, text=True, env=env)
        id1, id2 = r1.stdout.strip(), r2.stdout.strip()
        ok(r1.returncode == 0 and r2.returncode == 0,
           "AC2 setup: records created via MEMORY_ROOT (multi-scope: root home + alpha home)")

        p = subprocess.run([sys.executable, PRIME], capture_output=True, text=True, env=env)
        ok(p.returncode == 0, "AC2: prime (no arg) exit 0")
        ok(id1 in p.stdout and id2 in p.stdout,
           "AC2: prime (no arg) recursively finds records across every scope home")

        subprocess.run([sys.executable, OUT, id2, "success"], capture_output=True, text=True, env=env)
        o = subprocess.run([sys.executable, OUT, id2, "success"], capture_output=True, text=True, env=env)
        ok(o.returncode == 0, "AC2: outcome.py (no --dir) exit 0")
        ocp = os.path.join(tmp, "memory", "outcomes.jsonl")
        ok(os.path.exists(ocp), "AC2: outcome.py (no --dir) writes the CENTRAL log at <root>/memory/outcomes.jsonl")
        ok(('"id": "%s"' % id2) in open(ocp).read(),
           "AC2: central log keyed by the record id, regardless of its scope home")

        p2 = subprocess.run([sys.executable, PRIME], capture_output=True, text=True, env=env)
        i1, i2 = p2.stdout.find(id1), p2.stdout.find(id2)
        ok(0 <= i2 < i1, "AC2: 2 successes lift the scoped tactical record (20+60=80) above the plain foundational one (50)")
        ok("★2" in p2.stdout, "AC2: outcomes tallied through the central log for a scoped record")


def ascension_mode():
    """git-root ascension (no MEMORY_ROOT): prime.py and outcome.py both walk cwd up to the nearest .git."""
    with tempfile.TemporaryDirectory() as tmp:
        os.mkdir(os.path.join(tmp, ".git"))
        rdir = os.path.join(tmp, "memory", "records")
        os.makedirs(rdir)
        with open(os.path.join(rdir, "r.md"), "w") as f:
            f.write("---\nid: asc-1\ntype: decision\nclassification: foundational\nsummary: A\n---\n# asc\n")
        sub = os.path.join(tmp, "x", "y")
        os.makedirs(sub)
        env = os.environ.copy()
        env.pop("MEMORY_ROOT", None)

        r = subprocess.run([sys.executable, PRIME], capture_output=True, text=True, env=env, cwd=sub)
        ok(r.returncode == 0 and "asc-1" in r.stdout,
           "ascension: prime (no arg) from a nested cwd finds records at the .git root")

        o = subprocess.run([sys.executable, OUT, "asc-1", "success"], capture_output=True, text=True, env=env, cwd=sub)
        ok(o.returncode == 0, "ascension: outcome.py (no --dir) from a nested cwd exit 0")
        ok(os.path.exists(os.path.join(tmp, "memory", "outcomes.jsonl")),
           "ascension: outcome.py (no --dir) writes to the .git root's memory/outcomes.jsonl")


def supersession_mode():
    """Records naming another via `supersedes: <id>` retire that id from the digest
    (chain, no recursion needed) and dangling supersedes (target id not on disk) is not fatal."""
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)

        def rec(name, fm, body=None):
            with open(os.path.join(rdir, name + ".md"), "w") as f:
                f.write("---\n" + fm + "\n---\n" + (body or "# " + name) + "\n")

        # chain: c supersedes a, a supersedes b -> a and b hidden, c shown
        rec("b", "id: b\ntype: decision\nclassification: foundational\nsummary: B")
        rec("a", "id: a\ntype: decision\nclassification: foundational\nsummary: A\nsupersedes: b")
        rec("c", "id: c\ntype: decision\nclassification: foundational\nsummary: C\nsupersedes: a")
        # dangling: points at an id that doesn't exist on disk -> not fatal, record still shown
        rec("d", "id: d\ntype: decision\nclassification: foundational\nsummary: D\nsupersedes: ghost-id")

        r = subprocess.run([sys.executable, PRIME, tmp], capture_output=True, text=True)
        ok(r.returncode == 0, "supersession: exit 0")
        ok("id:c" in r.stdout, "supersession: superseding record (c) shown")
        ok("id:a" not in r.stdout and "id:b" not in r.stdout,
           "supersession: chain hides both intermediate (a) and original (b) records")
        ok("id:d" in r.stdout, "supersession: dangling supersedes (target not on disk) -> record still shown, no crash")
        ok("2 superseded record(s) hidden" in r.stdout, "supersession: hidden count reported in digest footer")


def glob_metachar_root_mode():
    """MEMORY_ROOT / dir containing a glob class like [a] must not silently match nothing
    (glob.escape on the path portion). A bug here reports 0 records on a non-empty store."""
    with tempfile.TemporaryDirectory() as tmp:
        weird = os.path.join(tmp, "proj[a]")
        rdir = os.path.join(weird, "memory", "records")
        os.makedirs(rdir)
        with open(os.path.join(rdir, "r.md"), "w") as f:
            f.write("---\nid: meta-1\ntype: decision\nclassification: foundational\nsummary: M\n---\n# m\n")
        env = os.environ.copy()
        env["MEMORY_ROOT"] = weird
        r = subprocess.run([sys.executable, PRIME], capture_output=True, text=True, env=env)
        ok(r.returncode == 0 and "meta-1" in r.stdout,
           "glob-metachar root: record under a '[a]' path is still found (glob.escape)")


explicit_dir_mode()
default_root_mode()
ascension_mode()
supersession_mode()
glob_metachar_root_mode()

print("prime tests: %d passed, %d failed" % (P, F))
sys.exit(0 if F == 0 else 1)
