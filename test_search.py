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


def no_env_builtin_unchanged():
    # baseline: with DRAILLE_SEARCH_CMD unset, search.py behaves exactly as before
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)
        with open(os.path.join(rdir, "r.md"), "w") as f:
            f.write("---\nid: n1\ntype: decision\nclassification: observational\nsummary: none\n---\n# widget\n")

        env = os.environ.copy()
        env.pop("DRAILLE_SEARCH_CMD", None)
        r = subprocess.run([sys.executable, SEARCH, "widget", "--dir", tmp],
                            capture_output=True, text=True, env=env)
        ok(r.returncode == 0 and "id:n1" in r.stdout, "no env: builtin scan runs and finds the record")


def env_cmd_delegates():
    with tempfile.TemporaryDirectory() as tmp:
        fake = os.path.join(tmp, "fake_engine.py")
        with open(fake, "w") as f:
            f.write(
                "import sys, os\n"
                "print('ARGS:' + ' '.join(sys.argv[1:]))\n"
                "print('ROOT:' + os.environ.get('MEMORY_ROOT', ''))\n"
                "sys.exit(7)\n"
            )
        env = os.environ.copy()
        env["DRAILLE_SEARCH_CMD"] = "%s %s" % (sys.executable, fake)
        env["MEMORY_ROOT"] = tmp

        r = subprocess.run([sys.executable, SEARCH, "widget", "gizmo"],
                            capture_output=True, text=True, env=env)
        ok(r.returncode == 7, "DRAILLE_SEARCH_CMD: child's exit code is propagated")
        ok("ARGS:widget gizmo" in r.stdout, "DRAILLE_SEARCH_CMD: query terms forwarded as args")
        ok(("ROOT:" + os.path.abspath(tmp)) in r.stdout, "DRAILLE_SEARCH_CMD: MEMORY_ROOT exported to child")


def engine_builtin_ignores_env():
    with tempfile.TemporaryDirectory() as tmp:
        fake = os.path.join(tmp, "fake_engine.py")
        with open(fake, "w") as f:
            f.write("import sys; print('SHOULD NOT RUN'); sys.exit(1)\n")

        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)
        with open(os.path.join(rdir, "r.md"), "w") as f:
            f.write("---\nid: b1\ntype: decision\nclassification: observational\nsummary: none\n---\n# widget\n")

        env = os.environ.copy()
        env["DRAILLE_SEARCH_CMD"] = "%s %s" % (sys.executable, fake)

        r = subprocess.run([sys.executable, SEARCH, "widget", "--dir", tmp, "--engine", "builtin"],
                            capture_output=True, text=True, env=env)
        ok(r.returncode == 0 and "id:b1" in r.stdout, "--engine builtin: scans internally")
        ok("SHOULD NOT RUN" not in r.stdout, "--engine builtin: ignores DRAILLE_SEARCH_CMD")


def env_cmd_hostile():
    # hostile DRAILLE_SEARCH_CMD values: clean errors, never a traceback,
    # and never executing the query terms as the command.
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["MEMORY_ROOT"] = tmp

        env["DRAILLE_SEARCH_CMD"] = 'foo "unbalanced'
        r = subprocess.run([sys.executable, SEARCH, "widget"], capture_output=True, text=True, env=env)
        ok(r.returncode != 0 and "Traceback" not in r.stderr,
           "unbalanced quote in DRAILLE_SEARCH_CMD: clean error, no traceback")

        marker = os.path.join(tmp, "pwned")
        evil = os.path.join(tmp, "evil.py")
        with open(evil, "w") as f:
            f.write("open(%r, 'w').close()\n" % marker)
        env["DRAILLE_SEARCH_CMD"] = "   "
        r = subprocess.run([sys.executable, SEARCH, sys.executable, evil],
                            capture_output=True, text=True, env=env)
        ok(r.returncode != 0 and not os.path.exists(marker),
           "blank DRAILLE_SEARCH_CMD: rejected, query terms NOT executed as a command")

        env["DRAILLE_SEARCH_CMD"] = "/nonexistent/bin/zzz"
        r = subprocess.run([sys.executable, SEARCH, "widget"], capture_output=True, text=True, env=env)
        ok(r.returncode == 127 and "Traceback" not in r.stderr and "cannot run" in r.stderr,
           "absent backend command: exit 127 with clean message")

        # --engine env with no DRAILLE_SEARCH_CMD at all: error, not silent builtin
        env2 = os.environ.copy()
        env2.pop("DRAILLE_SEARCH_CMD", None)
        r = subprocess.run([sys.executable, SEARCH, "widget", "--engine", "env"],
                            capture_output=True, text=True, env=env2)
        ok(r.returncode != 0 and "DRAILLE_SEARCH_CMD" in r.stderr,
           "--engine env without DRAILLE_SEARCH_CMD: explicit error, no silent builtin")


def dir_forces_builtin():
    with tempfile.TemporaryDirectory() as tmp:
        fake = os.path.join(tmp, "fake_engine.py")
        with open(fake, "w") as f:
            f.write("import sys; print('SHOULD NOT RUN'); sys.exit(1)\n")
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)
        with open(os.path.join(rdir, "r.md"), "w") as f:
            f.write("---\nid: dd1\ntype: decision\nclassification: observational\nsummary: none\n---\n# widget\n")
        env = os.environ.copy()
        env["DRAILLE_SEARCH_CMD"] = "%s %s" % (sys.executable, fake)

        r = subprocess.run([sys.executable, SEARCH, "widget", "--dir", tmp],
                            capture_output=True, text=True, env=env)
        ok(r.returncode == 0 and "id:dd1" in r.stdout and "SHOULD NOT RUN" not in r.stdout,
           "--dir with env cmd set: builtin scan of D, backend not invoked")

        r = subprocess.run([sys.executable, SEARCH, "widget", "--dir", tmp, "--engine", "env"],
                            capture_output=True, text=True, env=env)
        ok(r.returncode != 0 and "SHOULD NOT RUN" not in r.stdout,
           "--dir + --engine env: rejected (backend can't honor --dir)")


def superseded_hit_hidden_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        rdir = os.path.join(tmp, "records")
        os.makedirs(rdir)

        def rec(name, fm, body):
            with open(os.path.join(rdir, name + ".md"), "w") as f:
                f.write("---\n" + fm + "\n---\n" + body + "\n")

        rec("old", "id: old\ntype: decision\nclassification: observational\nsummary: none", "# widget old")
        rec("new", "id: new\ntype: decision\nclassification: observational\nsummary: none\nsupersedes: old",
            "# widget new")

        r = subprocess.run([sys.executable, SEARCH, "widget", "--dir", tmp],
                            capture_output=True, text=True)
        ok(r.returncode == 0, "supersession: exit 0")
        ok("id:new" in r.stdout and "id:old" not in r.stdout,
           "supersession: superseded hit hidden by default, superseding record shown")

        r2 = subprocess.run([sys.executable, SEARCH, "widget", "--dir", tmp, "--all"],
                             capture_output=True, text=True)
        ok("id:old" in r2.stdout and "id:new" in r2.stdout,
           "supersession: --all reincludes the superseded hit")


title_beats_body()
outcome_boosts_rank()
absent_term_no_matches()
corrupt_record_quarantined()
root_and_dir_respected()
no_env_builtin_unchanged()
env_cmd_delegates()
engine_builtin_ignores_env()
env_cmd_hostile()
dir_forces_builtin()
superseded_hit_hidden_by_default()

print("search tests: %d passed, %d failed" % (P, F))
sys.exit(0 if F == 0 else 1)
