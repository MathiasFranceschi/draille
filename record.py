#!/usr/bin/env python3
"""Create a durable markdown memory record.

Auto-generates a STABLE id (slug + content hash, never hand-typed), writes
frontmatter + body under the memory root. Prints the id on stdout (chain
outcomes via outcome.py). Absolute $HOME paths in title/body are normalized
to ~/ so records stay portable across machines sharing the repo. Stdlib only.

Root resolution: $MEMORY_ROOT env var, else the git root of the cwd, else cwd.
Scope routing: if <root>/memory/scopes.json exists (multi-scope mode), --scope
is required and maps to a home dir; otherwise (mono-project mode) records land
in <root>/memory/records and --scope defaults to the root's basename.

Usage: record.py <type> <classification> <title> [--scope S] [--body TEXT] [--evidence-sha SHA] [--dir DIR]
"""
import sys, os, json, argparse, hashlib, re, datetime

TYPES = ("decision", "pattern", "failure", "convention", "reference")
CLASSES = ("foundational", "tactical", "observational")


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


def slug(s, n=40):
    return (re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:n] or "rec")


def main(argv):
    p = argparse.ArgumentParser(prog="record.py",
                                description="Create a durable markdown memory record; prints the new id on stdout.")
    p.add_argument("type", choices=TYPES)
    p.add_argument("classification", choices=CLASSES)
    p.add_argument("title")
    p.add_argument("--scope", default="", help="routing scope (required when memory/scopes.json is present)")
    p.add_argument("--body", default="")
    p.add_argument("--evidence-sha", default="", dest="sha")
    p.add_argument("--dir", default="", dest="dir_override",
                   help="explicit memory dir (escape hatch — bypasses root/scope routing)")
    a = p.parse_args(argv[1:])
    typ, cls, title = a.type, a.classification, a.title
    body, sha, scope, dir_override = a.body, a.sha, a.scope, a.dir_override
    # frontmatter + heading are line-based — a multi-line title would inject keys
    # (prime quarantine, or rank forgery via an injected classification: line)
    title = title.replace("\r", " ").replace("\n", " ")
    # Normalize absolute $HOME paths to ~/ so records stay portable across machines
    # (a different $HOME breaks /home/<user>/… but ~/… resolves). Guard: prevents path regression.
    home = os.path.expanduser("~") + "/"
    title = title.replace(home, "~/")
    body = body.replace(home, "~/")
    root = memory_root()
    scopes_path = os.path.join(root, "memory", "scopes.json")
    if dir_override:
        base, scope = dir_override, (scope or "project")
    elif os.path.exists(scopes_path):
        # multi-scope mode: scopes.json maps scope -> home dir (relative to root).
        # An unknown scope parks in "central" + warns (a flat dump can't recur silently).
        try:
            with open(scopes_path, encoding="utf-8") as f:
                homes = json.load(f)
        except Exception as e:
            sys.stderr.write("error: invalid scopes.json: %s\n" % e)
            return 2
        if not scope:
            sys.stderr.write("error: --scope SCOPE required (scopes.json present = multi-scope mode)\n")
            return 2
        home_dir = homes.get(scope)
        if home_dir is None:
            sys.stderr.write("warn: scope %r has no home in scopes.json -> parked in central\n" % scope)
            home_dir = homes.get("central", ".")
        # scopes.json may come from a cloned (untrusted) repo — never let a home
        # escape the root (absolute path or .. component = arbitrary-write primitive)
        if os.path.isabs(home_dir) or os.pardir in home_dir.replace("\\", "/").split("/"):
            sys.stderr.write("error: unsafe home %r in scopes.json (absolute or ..)\n" % home_dir)
            return 2
        base = os.path.join(root, home_dir, "memory")
    else:
        # mono-project mode: one memory store at the root of the repo
        scope = scope or os.path.basename(root)
        base = os.path.join(root, "memory")
    date = datetime.date.today().isoformat()
    rid = "%s-%s" % (slug(title, 24), hashlib.sha1((title + body).encode()).hexdigest()[:6])
    rdir = os.path.join(base, "records")
    os.makedirs(rdir, exist_ok=True)
    fm = ["id: %s" % rid, "type: %s" % typ, "classification: %s" % cls,
          "scope: %s" % scope, 'evidence_sha: "%s"' % sha, "relates_to: []",
          "role: memory-record", "created: %s" % date,
          'summary: "%s"' % title[:120].replace('"', "")]
    md = "---\n" + "\n".join(fm) + "\n---\n\n# " + title + "\n\n" + (body or "") + "\n"
    with open(os.path.join(rdir, "%s-%s-%s.md" % (date, slug(title), rid)), "w", encoding="utf-8") as f:
        f.write(md)
    sys.stderr.write("recorded %s [%s/%s]\n" % (rid, typ, cls))
    print(rid)  # stdout = the new id (for chaining an outcome reference)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
