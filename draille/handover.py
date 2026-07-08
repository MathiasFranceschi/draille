#!/usr/bin/env python3
"""Read/write the CORE block of <root>/memory/HANDOVER.md — the block an agent
edits live, mid-run, not just at session-end (Letta-style core memory block).

`show` prints the block (heading through the next level-2 heading, or EOF).
`set` reads the new body on stdin (no heading — one is generated: "## CORE —
consolidated <date>"), replaces the existing block in place, and preserves
everything else in the file byte-for-byte. Write is atomic (tmp file in the
same dir + os.replace) so a crash mid-write never leaves a half-written
HANDOVER.md. Stdlib only.

Task guard: `set` stamps every `- [t] ` bullet in the new body with a fresh
`- [t-<4hex>] ` id, then soft-diffs old CORE vs new body for pending ids
(`[t-xxxx]`, no `closed` marker on the line) that silently disappeared. The
write never blocks on this — it warns on stderr and logs dropped/closed/
restored events to <memory-dir>/task-guard.jsonl; `draille status` surfaces
the open-drop count.

Root resolution: $MEMORY_ROOT env var, else the git root of the cwd, else cwd.
--dir is an explicit escape hatch: it IS the memory dir (default: <root>/memory).

Usage: handover.py show [--dir MEMORY_DIR]
       handover.py set  [--dir MEMORY_DIR]   (new body on stdin)
"""
import sys, os, re, json, random, argparse, datetime, tempfile

MAX_LINES = 15
TASK_TAG = "- [t] "                                     # opt-in bullet stamped with an id on `set`
TASK_ID_RE = re.compile(r"\[t-([0-9a-f]{4,})\]")
TASK_CLOSED_RE = re.compile(r"(?i)\bclosed\b")


def memory_root():
    env = os.environ.get("MEMORY_ROOT")
    if env:
        return os.path.abspath(env)
    d = os.getcwd()
    while True:
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.getcwd()
        d = parent


def find_core_block(text):
    """Return (start, end) spanning the '## CORE...' heading through the next
    level-2 ('## ') heading or EOF. None if no CORE heading is present.
    A leading YAML frontmatter block is skipped first: a column-0 '## CORE'
    line inside it (a YAML comment) must never be mistaken for the heading."""
    off = 0
    fm = re.match(r"---[ \t]*\r?\n", text)
    if fm:
        close = re.search(r"(?m)^---[ \t]*$", text[fm.end():])
        if close:
            off = fm.end() + close.end()
    m = re.search(r"(?m)^## CORE\b.*$", text[off:])
    if not m:
        return None
    start = off + m.start()
    heading_end = off + m.end()
    nxt = re.search(r"(?m)^## ", text[heading_end:])
    end = heading_end + nxt.start() if nxt else len(text)
    return start, end


def stamp_new_tasks(body, existing_ids):
    """Mint a fresh `t-<4hex>` id on every `- [t] ` bullet in body, unique vs
    existing_ids (already-used ids, file-wide). Untagged bullets/lines pass
    through byte-for-byte."""
    used = set(existing_ids)
    out = []
    for line in body.splitlines():
        if line.startswith(TASK_TAG):
            while True:
                tid = "t-%04x" % random.randrange(0x10000)
                if tid not in used:
                    break
            used.add(tid)
            out.append("- [%s] %s" % (tid, line[len(TASK_TAG):]))
        else:
            out.append(line)
    return "\n".join(out)


def extract_task_states(text):
    """id -> (status, line) for every `[t-xxxx]` occurrence in text. status is
    "closed" if the word "closed" appears later on the same line, else
    "pending". Later lines win on duplicate ids."""
    states = {}
    for line in text.splitlines():
        for m in TASK_ID_RE.finditer(line):
            tid = "t-" + m.group(1)
            closed = bool(TASK_CLOSED_RE.search(line[m.end():]))
            states[tid] = ("closed" if closed else "pending", line)
    return states


def _task_guard_log(memory_dir, kind, tid, line=None):
    event = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "kind": kind, "id": tid}
    if line is not None:
        event["line"] = line
    with open(os.path.join(memory_dir, "task-guard.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _task_guard_history(memory_dir):
    """id -> most recent event kind in task-guard.jsonl (missing file -> {})."""
    path = os.path.join(memory_dir, "task-guard.jsonl")
    last = {}
    if not os.path.isfile(path):
        return last
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                ev = json.loads(ln)
            except Exception:                        # GUARD: skip malformed line, never crash
                continue
            tid, kind = ev.get("id"), ev.get("kind")
            if tid and kind:
                last[tid] = kind
    return last


def task_guard_diff(old_core, new_body, memory_dir):
    """SOFT diff-guard: never blocks the write. Warns on stderr + logs to
    task-guard.jsonl for every pending id present in old_core but absent from
    new_body (dropped), every pending id closed in new_body (closed), and
    every pending id in new_body that was last seen dropped (restored)."""
    old_states = extract_task_states(old_core)
    new_states = extract_task_states(new_body)

    for tid, (status, line) in old_states.items():
        if status != "pending":
            continue
        if tid not in new_states:
            sys.stderr.write("warn: task %s dropped -- %s\n" % (tid, line))
            _task_guard_log(memory_dir, "dropped", tid, line)
        elif new_states[tid][0] == "closed":
            _task_guard_log(memory_dir, "closed", tid, new_states[tid][1])

    history = _task_guard_history(memory_dir)
    for tid, (status, _line) in new_states.items():
        if status == "pending" and history.get(tid) == "dropped":
            _task_guard_log(memory_dir, "restored", tid)


def cmd_show(base):
    path = os.path.join(base, "HANDOVER.md")
    if not os.path.isfile(path):
        sys.stderr.write("error: %s not found -- run draille init first\n" % path)
        return 1
    text = open(path, encoding="utf-8").read()
    block = find_core_block(text)
    if block is None:
        sys.stderr.write("error: no CORE block found in %s\n" % path)
        return 1
    start, end = block
    print(text[start:end].rstrip("\n"))
    return 0


def cmd_set(base):
    path = os.path.join(base, "HANDOVER.md")
    if not os.path.exists(path):
        sys.stderr.write("error: %s not found -- run draille init first\n" % path)
        return 1
    # newline="" on read AND write: no universal-newline translation, so a
    # CRLF file's untouched regions really are preserved byte-for-byte
    text = open(path, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in text else "\n"
    body = sys.stdin.read().rstrip("\n")

    block = find_core_block(text)
    old_core = text[block[0]:block[1]] if block else ""

    # task guard: stamp `- [t] ` bullets, unique vs every [t-xxxx] id already
    # in the file (any section) or already stamped earlier in this body
    existing_ids = set("t-" + m.group(1) for m in TASK_ID_RE.finditer(text))
    body = stamp_new_tasks(body, existing_ids)

    heading = "## CORE — consolidated %s" % datetime.date.today().isoformat()
    content = heading + ("\n\n" + body if body else "")
    n_lines = len(content.splitlines())
    if n_lines > MAX_LINES:
        sys.stderr.write("warn: CORE block is %d lines (>%d) -- consolidate, don't stack\n" % (n_lines, MAX_LINES))
    if nl != "\n":
        content = content.replace("\n", nl)  # stdin body arrives LF-only (universal newlines)

    # SOFT diff-guard: write proceeds regardless, this only warns + logs
    task_guard_diff(old_core, body, base)

    if block is None:
        # no existing CORE block: append (prefix preserved verbatim, minus a
        # trailing-newline normalization so the appended block isn't glued on)
        prefix = text.rstrip("\r\n")
        new_text = (prefix + nl * 2 + content + nl) if prefix else (content + nl)
    else:
        start, end = block
        # prefix (text[:start]) and suffix (text[end:]) are untouched byte-for-byte
        sep = nl * 2 if end < len(text) else nl
        new_text = text[:start] + content + sep + text[end:]

    dirname = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=dirname, prefix=".handover-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        # mkstemp created tmp 0600; carry the real file's permission bits over
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        # os.replace() unlinks the dir entry at `path` and swaps `tmp` in --
        # if `path` is a symlink this replaces the LINK itself (atomic rename
        # semantics), never writes through it to the link's target.
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    sys.stderr.write("CORE block updated (%d lines)\n" % n_lines)
    return 0


def main(argv):
    p = argparse.ArgumentParser(prog=os.path.basename(argv[0]),
                                description="Read/write the live-edited CORE block of memory/HANDOVER.md.")
    sub = p.add_subparsers(dest="cmd", required=True)
    p_show = sub.add_parser("show", help="print the CORE block")
    p_show.add_argument("--dir", dest="base", default="",
                        help="explicit memory dir (default: <root>/memory)")
    p_set = sub.add_parser("set", help="replace the CORE block with content read from stdin")
    p_set.add_argument("--dir", dest="base", default="",
                       help="explicit memory dir (default: <root>/memory)")
    a = p.parse_args(argv[1:])
    base = a.base or os.path.join(memory_root(), "memory")
    return cmd_show(base) if a.cmd == "show" else cmd_set(base)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
