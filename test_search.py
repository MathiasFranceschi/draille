#!/usr/bin/env python3
"""Tests for search.py — ranked, stateless search over memory records."""
import subprocess, tempfile, os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
SEARCH = os.path.join(HERE, "draille", "search.py")
OUT = os.path.join(HERE, "draille", "outcome.py")
P = F = 0


def ok(cond, msg):
    global P, F
    if cond:
        P += 1; print("  ok   " + msg)
    else:
        F += 1; print("  FAIL " + msg)


def title_beats_body():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)

        def rec(name, fm, body):
            with open(os.path.join(rdir, name + ".md"), "w") as f:
                f.write("---\n" + fm + "\n---\n" + body + "\n")

        rec("titlehit", "id: t1\ntype: decision\nclassification: observational\nsummary: none",
            "# widget setup\n\nunrelated body text")
        rec("bodyhit", "id: t2\ntype: decision\nclassification: observational\nsummary: none",
            "# unrelated title\n\nsomething about widget in the body")

        r = subprocess.run([sys.executable, SEARCH, "widget", "--dir", tmp],
                            capture_output=True, text=True)
        ok(r.returncode == 0, "title-vs-body: exit 0")
        it, ib = r.stdout.find("id:t1"), r.stdout.find("id:t2")
        ok(0 <= it < ib, "title match (weight 3) outranks body match (weight 1)")


def outcome_boosts_rank():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)

        def rec(name, fm, body):
            with open(os.path.join(rdir, name + ".md"), "w") as f:
                f.write("---\n" + fm + "\n---\n" + body + "\n")

        rec("a", "id: a\ntype: decision\nclassification: observational\nsummary: none", "# gizmo tool")
        rec("b", "id: b\ntype: decision\nclassification: observational\nsummary: none", "# gizmo tool")

        subprocess.run([sys.executable, OUT, "b", "success", "--dir", tmp], capture_output=True, text=True)

        r = subprocess.run([sys.executable, SEARCH, "gizmo", "--dir", tmp],
                            capture_output=True, text=True)
        ia, ib = r.stdout.find("id:a"), r.stdout.find("id:b")
        ok(0 <= ib < ia, "record with a success outcome outranks an identical-text one without")


def absent_term_no_matches():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)
        with open(os.path.join(rdir, "r.md"), "w") as f:
            f.write("---\nid: x\ntype: decision\nclassification: observational\nsummary: none\n---\n# hello\n")

        r = subprocess.run([sys.executable, SEARCH, "nonexistentterm", "--dir", tmp],
                            capture_output=True, text=True)
        ok(r.returncode == 0, "absent term: exit 0")
        ok("no matches" in r.stderr, "absent term: 'no matches' on stderr")
        ok(r.stdout == "", "absent term: no stdout hits")

        r = subprocess.run([sys.executable, SEARCH, "hello", "-n", "0", "--dir", tmp],
                            capture_output=True, text=True)
        ok(r.returncode != 0 and "-n must be >= 1" in r.stderr,
           "-n 0: rejected (would silently slice hits away)")


def corrupt_record_quarantined():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)
        with open(os.path.join(rdir, "good.md"), "w") as f:
            f.write("---\nid: g1\ntype: decision\nclassification: observational\nsummary: none\n---\n# widget\n")
        with open(os.path.join(rdir, "bad.md"), "w") as f:
            f.write("id c no colon here\nnot valid frontmatter\n")

        r = subprocess.run([sys.executable, SEARCH, "widget", "--dir", tmp],
                            capture_output=True, text=True)
        ok(r.returncode == 0, "corrupt record: exit 0, no crash")
        ok("QUARANTINE" in r.stderr, "corrupt record: warned to stderr")
        ok("id:g1" in r.stdout, "corrupt record: sibling valid record still returned")


def root_and_dir_respected():
    # --dir: records live at D/records, path shown relative to D
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)
        with open(os.path.join(rdir, "r.md"), "w") as f:
            f.write("---\nid: d1\ntype: decision\nclassification: observational\nsummary: none\n---\n# thingamajig\n")
        r = subprocess.run([sys.executable, SEARCH, "thingamajig", "--dir", tmp],
                            capture_output=True, text=True)
        ok(r.returncode == 0 and "id:d1" in r.stdout, "--dir: finds record under D/records")
        ok(("records" + os.sep + "r.md") in r.stdout, "--dir: path shown relative to D")

    # MEMORY_ROOT env var: no-arg recursive scan under <root>/**/memory/records
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "team", "memory", "records")
        os.makedirs(rdir)
        with open(os.path.join(rdir, "r.md"), "w") as f:
            f.write("---\nid: e1\ntype: decision\nclassification: observational\nsummary: none\n---\n# doohickey\n")
        env = os.environ.copy()
        env["MEMORY_ROOT"] = tmp
        r = subprocess.run([sys.executable, SEARCH, "doohickey"], capture_output=True, text=True, env=env)
        ok(r.returncode == 0 and "id:e1" in r.stdout, "MEMORY_ROOT: recursive scan finds a scoped record")


title_beats_body()
outcome_boosts_rank()
absent_term_no_matches()
corrupt_record_quarantined()
root_and_dir_respected()

print("search tests: %d passed, %d failed" % (P, F))
sys.exit(0 if F == 0 else 1)
