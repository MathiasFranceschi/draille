#!/usr/bin/env python3
"""Tests for handover.py — show/set the CORE block of memory/HANDOVER.md
(root resolution, byte-for-byte preservation of everything else, atomic
write, >15-line warning, missing-file/missing-block errors)."""
import subprocess, tempfile, os, sys, datetime, stat

HERE = os.path.dirname(os.path.abspath(__file__))
HANDOVER = os.path.join(HERE, "draille", "handover.py")
TODAY = datetime.date.today().isoformat()
res = {"p": 0, "f": 0}


def ok(c, m):
    res["p" if c else "f"] += 1
    print(("  ok   " if c else "  FAIL ") + m)


def run(args, env, cwd=None, input=None):
    return subprocess.run([sys.executable, HANDOVER] + args, capture_output=True,
                          text=True, env=env, cwd=cwd, input=input)


def env_for(root):
    e = os.environ.copy()
    e["MEMORY_ROOT"] = root
    return e


FRONTMATTER = "---\nrole: handover\n---\n\n# Handover\n\n"
OTHER = "\n## OTHER\n\nother stuff, untouched\n"


# --- AC1: show extracts exactly the CORE block (heading through next ## or EOF) ---
with tempfile.TemporaryDirectory() as tmp:
    mem = os.path.join(tmp, "memory")
    os.makedirs(mem)
    original = FRONTMATTER + "## CORE\n\nsome durable fact\n" + OTHER
    with open(os.path.join(mem, "HANDOVER.md"), "w", encoding="utf-8") as f:
        f.write(original)
    env = env_for(tmp)
    r = run(["show"], env)
    ok(r.returncode == 0, "AC1: show exit 0")
    ok(r.stdout.rstrip("\n") == "## CORE\n\nsome durable fact", "AC1: show prints exactly the CORE block")
    ok("OTHER" not in r.stdout, "AC1: show does not leak the next section")

    # --- AC2: set replaces ONLY the CORE block; frontmatter + other sections byte-for-byte ---
    r2 = run(["set"], env, input="fact A\nfact B\n")
    ok(r2.returncode == 0, "AC2: set exit 0")
    updated = open(os.path.join(mem, "HANDOVER.md"), encoding="utf-8").read()
    ok(updated.startswith(FRONTMATTER), "AC2: frontmatter preserved byte-for-byte")
    ok(updated.endswith(OTHER), "AC2: trailing OTHER section preserved byte-for-byte")
    ok(("## CORE — consolidated %s" % TODAY) in updated, "AC2: new heading has today's date")
    ok("fact A\nfact B" in updated, "AC2: new body present")
    ok("some durable fact" not in updated, "AC2: old body gone")


# --- AC3: set with no HANDOVER.md at all -> exit 1, advises init ---
with tempfile.TemporaryDirectory() as tmp:
    env = env_for(tmp)
    r = run(["set"], env, input="x\n")
    ok(r.returncode == 1, "AC3: set exit 1 when HANDOVER.md is missing")
    ok("draille init" in r.stderr, "AC3: stderr advises running draille init")


# --- AC4: new block >15 lines -> warns on stderr but still writes ---
with tempfile.TemporaryDirectory() as tmp:
    mem = os.path.join(tmp, "memory")
    os.makedirs(mem)
    with open(os.path.join(mem, "HANDOVER.md"), "w", encoding="utf-8") as f:
        f.write(FRONTMATTER + "## CORE\n\nshort\n")
    env = env_for(tmp)
    big_body = "\n".join("line %d" % i for i in range(15))  # heading+blank+15 = 17 lines
    r = run(["set"], env, input=big_body)
    ok(r.returncode == 0, "AC4: set exit 0 even over the line budget")
    ok(">15" in r.stderr or "consolidate" in r.stderr, "AC4: stderr warns about the line budget")
    updated = open(os.path.join(mem, "HANDOVER.md"), encoding="utf-8").read()
    ok("line 14" in updated, "AC4: oversized block is written anyway")


# --- AC5: show with a HANDOVER.md that has no CORE block -> exit 1 ---
with tempfile.TemporaryDirectory() as tmp:
    mem = os.path.join(tmp, "memory")
    os.makedirs(mem)
    with open(os.path.join(mem, "HANDOVER.md"), "w", encoding="utf-8") as f:
        f.write(FRONTMATTER + "## OTHER\n\nno core section here\n")
    env = env_for(tmp)
    r = run(["show"], env)
    ok(r.returncode == 1, "AC5: show exit 1 with no CORE block")


# --- AC6: atomicity through a symlink -- os.replace() swaps the LINK, not the target ---
with tempfile.TemporaryDirectory() as tmp:
    mem = os.path.join(tmp, "memory")
    os.makedirs(mem)
    target = os.path.join(tmp, "real_handover.md")  # lives OUTSIDE memory/, on purpose
    target_original = FRONTMATTER + "## CORE\n\noriginal via link\n"
    with open(target, "w", encoding="utf-8") as f:
        f.write(target_original)
    link_path = os.path.join(mem, "HANDOVER.md")
    os.symlink(target, link_path)
    env = env_for(tmp)
    r = run(["set"], env, input="new via link\n")
    ok(r.returncode == 0, "AC6: set exit 0 through a symlinked HANDOVER.md")
    # os.replace(tmp, link_path) unlinks the directory entry at link_path and
    # puts the tmp file there instead -- POSIX rename(2) semantics never
    # dereference the final path component, so this replaces the SYMLINK
    # itself with a regular file; it does not open/truncate/write through it.
    ok(not os.path.islink(link_path), "AC6: HANDOVER.md path is now a regular file, not a symlink")
    ok(open(link_path, encoding="utf-8").read().find("new via link") != -1,
       "AC6: the (now regular) file at the link's path has the new content")
    ok(open(target, encoding="utf-8").read() == target_original,
       "AC6: the symlink's original TARGET file is untouched")


# --- AC7: MEMORY_ROOT resolution + --dir escape ---
with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "root")
    mem = os.path.join(root, "memory")
    os.makedirs(mem)
    with open(os.path.join(mem, "HANDOVER.md"), "w", encoding="utf-8") as f:
        f.write(FRONTMATTER + "## CORE\n\nvia MEMORY_ROOT\n")
    env = env_for(root)
    r = run(["show"], env)
    ok(r.returncode == 0 and "via MEMORY_ROOT" in r.stdout, "AC7: MEMORY_ROOT is respected (no --dir)")

    unrelated_root = os.path.join(tmp, "unrelated-root")
    explicit_dir = os.path.join(tmp, "explicit-dir")
    os.makedirs(explicit_dir)
    with open(os.path.join(explicit_dir, "HANDOVER.md"), "w", encoding="utf-8") as f:
        f.write(FRONTMATTER + "## CORE\n\nvia --dir\n")
    env2 = env_for(unrelated_root)  # points MEMORY_ROOT somewhere unrelated/nonexistent
    r2 = run(["show", "--dir", explicit_dir], env2)
    ok(r2.returncode == 0 and "via --dir" in r2.stdout, "AC7: --dir escape overrides MEMORY_ROOT entirely")
    ok(not os.path.exists(unrelated_root), "AC7: --dir escape never touches MEMORY_ROOT")


# --- AC8: CRLF file -- untouched regions preserved byte-for-byte, block written CRLF ---
with tempfile.TemporaryDirectory() as tmp:
    mem = os.path.join(tmp, "memory")
    os.makedirs(mem)
    path = os.path.join(mem, "HANDOVER.md")
    with open(path, "wb") as f:
        f.write(b"---\r\nrole: handover\r\n---\r\n\r\n# H\r\n\r\n## CORE\r\n\r\nold\r\n\r\n## OTHER\r\n\r\nkeep\r\n")
    env = env_for(tmp)
    r = run(["set"], env, input="new\n")
    raw = open(path, "rb").read()
    ok(r.returncode == 0, "AC8: set exit 0 on a CRLF file")
    ok(raw.startswith(b"---\r\nrole: handover\r\n---\r\n\r\n# H\r\n\r\n"),
       "AC8: CRLF prefix preserved byte-for-byte")
    ok(raw.endswith(b"## OTHER\r\n\r\nkeep\r\n"), "AC8: CRLF suffix preserved byte-for-byte")
    ok(b"consolidated" in raw and b"\r\nnew\r\n" in raw, "AC8: new block written with CRLF endings")

# --- AC9: '## CORE' at column 0 inside frontmatter (YAML comment) is NOT the heading ---
with tempfile.TemporaryDirectory() as tmp:
    mem = os.path.join(tmp, "memory")
    os.makedirs(mem)
    decoy_fm = "---\nrole: handover\n## CORE decoy comment\n---\n\n# H\n\n"
    with open(os.path.join(mem, "HANDOVER.md"), "w", encoding="utf-8") as f:
        f.write(decoy_fm + "## CORE\n\nreal fact\n" + OTHER)
    env = env_for(tmp)
    r = run(["show"], env)
    ok(r.returncode == 0 and "real fact" in r.stdout and "decoy" not in r.stdout,
       "AC9: show skips the frontmatter decoy and prints the real block")
    r2 = run(["set"], env, input="updated\n")
    updated = open(os.path.join(mem, "HANDOVER.md"), encoding="utf-8").read()
    ok(r2.returncode == 0 and updated.startswith(decoy_fm),
       "AC9: set leaves frontmatter (incl. decoy line) byte-for-byte")
    ok("updated" in updated and "real fact" not in updated and updated.endswith(OTHER),
       "AC9: set replaced the real block, suffix intact")

# --- AC10: permission bits survive the atomic replace (mkstemp is 0600) ---
with tempfile.TemporaryDirectory() as tmp:
    mem = os.path.join(tmp, "memory")
    os.makedirs(mem)
    path = os.path.join(mem, "HANDOVER.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("## CORE\n\nold\n")
    os.chmod(path, 0o644)
    env = env_for(tmp)
    r = run(["set"], env, input="new\n")
    mode = stat.S_IMODE(os.stat(path).st_mode)
    ok(r.returncode == 0 and mode == 0o644,
       "AC10: mode 644 preserved after set (got %o)" % mode)

print("handover tests: %d passed, %d failed" % (res["p"], res["f"]))
sys.exit(0 if res["f"] == 0 else 1)
