#!/usr/bin/env python3
"""Tests for the task guard in handover.py — AC1 (stamp `- [t] ` bullets with
a unique `[t-xxxx]` id, untagged bullets untouched), AC2 (soft diff-guard:
drop/close/restore events logged to task-guard.jsonl, write never blocked),
AC3 (status.py counts open drops, exit code unaffected)."""
import subprocess, tempfile, os, sys, json, re

HERE = os.path.dirname(os.path.abspath(__file__))
HANDOVER = os.path.join(HERE, "draille", "handover.py")
STATUS = os.path.join(HERE, "draille", "status.py")
res = {"p": 0, "f": 0}


def ok(c, m):
    res["p" if c else "f"] += 1
    print(("  ok   " if c else "  FAIL ") + m)


def run_handover(args, env, input=None):
    return subprocess.run([sys.executable, HANDOVER] + args, capture_output=True,
                          text=True, env=env, input=input)


def run_status(env, *args):
    return subprocess.run([sys.executable, STATUS] + list(args), capture_output=True,
                          text=True, env=env)


def env_for(root):
    e = os.environ.copy()
    e["MEMORY_ROOT"] = root
    return e


def jsonl_events(mem_dir):
    path = os.path.join(mem_dir, "task-guard.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


FRONTMATTER = "---\nrole: handover\n---\n\n# Handover\n\n"


# --- AC1: stamp opt-in, unique ids, untagged bullets untouched byte-for-byte ---
with tempfile.TemporaryDirectory() as tmp:
    mem = os.path.join(tmp, "memory")
    os.makedirs(mem)
    with open(os.path.join(mem, "HANDOVER.md"), "w", encoding="utf-8") as f:
        f.write(FRONTMATTER + "## CORE\n\nold\n")
    env = env_for(tmp)

    body = "- [t] task A\n- plain bullet, no tag\n- [t] task B\nsome prose line\n"
    r = run_handover(["set"], env, input=body)
    ok(r.returncode == 0, "AC1: set exit 0")
    updated = open(os.path.join(mem, "HANDOVER.md"), encoding="utf-8").read()

    ids = re.findall(r"\[t-([0-9a-f]{4})\]", updated)
    ok(len(ids) == 2, "AC1: exactly 2 ids stamped (%r)" % ids)
    ok(len(set(ids)) == 2, "AC1: stamped ids are unique")
    ok("- plain bullet, no tag" in updated, "AC1: untagged bullet untouched byte-for-byte")
    ok("some prose line" in updated, "AC1: non-bullet line untouched byte-for-byte")
    ok("- [t] " not in updated, "AC1: no unstamped `- [t] ` placeholder remains")

    # re-set with a body that reuses an id already in the file -> must not collide
    existing_id = ids[0]
    body2 = "- [t] task C\n" + ("- [t-%s] carried over — closed: done\n" % existing_id)
    r2 = run_handover(["set"], env, input=body2)
    ok(r2.returncode == 0, "AC1b: set exit 0 on second write")
    updated2 = open(os.path.join(mem, "HANDOVER.md"), encoding="utf-8").read()
    new_ids = re.findall(r"\[t-([0-9a-f]{4})\]", updated2)
    ok(new_ids.count(existing_id) == 1, "AC1b: freshly minted id never collides with one already in the file")


# --- AC2: drop -> write still OK + stderr warning + JSONL dropped ---
with tempfile.TemporaryDirectory() as tmp:
    mem = os.path.join(tmp, "memory")
    os.makedirs(mem)
    with open(os.path.join(mem, "HANDOVER.md"), "w", encoding="utf-8") as f:
        f.write(FRONTMATTER + "## CORE\n\nold\n")
    env = env_for(tmp)

    r1 = run_handover(["set"], env, input="- [t] task A\nother line\n")
    tid = re.search(r"\[(t-[0-9a-f]{4})\]", open(os.path.join(mem, "HANDOVER.md"), encoding="utf-8").read()).group(1)

    # re-set WITHOUT task A -> dropped
    r2 = run_handover(["set"], env, input="other line\nsomething new\n")
    ok(r2.returncode == 0, "AC2: set exit 0 even when a pending id is dropped (soft, non-blocking)")
    ok(tid in r2.stderr and "dropped" in r2.stderr, "AC2: stderr warns about the dropped id")

    events = jsonl_events(mem)
    dropped = [e for e in events if e.get("kind") == "dropped" and e.get("id") == tid]
    ok(len(dropped) == 1, "AC2: JSONL has exactly one dropped event for the id")
    ok("task A" in dropped[0].get("line", ""), "AC2: dropped event carries the original line")
    ok("ts" in dropped[0], "AC2: dropped event carries a timestamp")

    # --- close: pending -> closed in new body -> JSONL closed ---
    r3 = run_handover(["set"], env, input="- [t] task B\n")
    tid_b = re.search(r"\[(t-[0-9a-f]{4})\]",
                       open(os.path.join(mem, "HANDOVER.md"), encoding="utf-8").read()).group(1)
    r4 = run_handover(["set"], env, input=("- [%s] task B — closed: done in abc123\n" % tid_b))
    ok(r4.returncode == 0, "AC2c: set exit 0 on close")
    events = jsonl_events(mem)
    closed = [e for e in events if e.get("kind") == "closed" and e.get("id") == tid_b]
    ok(len(closed) == 1, "AC2c: JSONL has exactly one closed event for the id")
    ok("closed" in closed[0].get("line", ""), "AC2c: closed event carries the new (closed) line")

    # --- restore: an id previously dropped reappears pending -> JSONL restored ---
    r5 = run_handover(["set"], env, input=("- [%s] task A is back\n" % tid))
    ok(r5.returncode == 0, "AC2r: set exit 0 on restore")
    events = jsonl_events(mem)
    restored = [e for e in events if e.get("kind") == "restored" and e.get("id") == tid]
    ok(len(restored) == 1, "AC2r: JSONL has exactly one restored event for the previously-dropped id")


# --- AC3: status --json open_task_drops counts correctly, exit code unaffected ---
with tempfile.TemporaryDirectory() as tmp:
    mem = os.path.join(tmp, "memory")
    os.makedirs(mem)
    with open(os.path.join(mem, "HANDOVER.md"), "w", encoding="utf-8") as f:
        f.write(FRONTMATTER + "## CORE\n\nold\n")
    env = env_for(tmp)

    run_handover(["set"], env, input="- [t] task A\n- [t] task B\n")
    # drop both
    run_handover(["set"], env, input="nothing tracked\n")

    r = run_status(env, "--json")
    d = json.loads(r.stdout)
    ok(d.get("open_task_drops") == 2, "AC3: open_task_drops == 2 (got %r)" % d.get("open_task_drops"))
    ok(r.returncode == 0, "AC3: status exit code unaffected by open drops (store is clean/no-git)")
    ok("task drops: 2 open" in run_status(env).stdout, "AC3: human output shows the open drop count")

    # missing task-guard.jsonl -> 0, not an error
    with tempfile.TemporaryDirectory() as tmp2:
        mem2 = os.path.join(tmp2, "memory")
        os.makedirs(mem2)
        env2 = env_for(tmp2)
        r2 = run_status(env2, "--json")
        d2 = json.loads(r2.stdout)
        ok(d2.get("open_task_drops") == 0, "AC3b: missing task-guard.jsonl -> open_task_drops == 0")


print("guard tests: %d passed, %d failed" % (res["p"], res["f"]))
sys.exit(0 if res["f"] == 0 else 1)
