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
Dynamic routing: if scopes.json has a top-level "_resolver" command string,
each scope's value is resolved by running `<_resolver> <value>` (single-line
stdout, abs path ok) instead of used as a literal path; a failing/empty/
multi-line resolver blocks the write (exit 2). "_resolver" is a reserved
scope name, never a real scope.
_resolver only runs for a root listed in ~/.config/draille/trusted-roots
(no dedicated env override; resolved via $HOME like any user config — a
hostile $HOME already owns the account and is out of threat model) — an
untrusted root blocks (exit 2), never silently falls back to the literal
value.

Usage: record.py <type> <classification> <title> [--scope S] [--body TEXT] [--evidence-sha SHA] [--dir DIR] [--supersedes ID] [--remedy-impl VALUE --why TEXT]
--remedy-impl (failure/convention only, ADR-0031): 'none' (+ --why), a path, or an opaque
gotcha/task ref. Omitted or an invalid path -> <root>/memory/remedy-task-hook, else 'todo'.
"""
import sys, os, json, argparse, hashlib, re, datetime, subprocess, shlex

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


def remedy_hook_ref(root, rid, title, scope):
    """ADR-0031: no valid --remedy-impl -> ask <root>/memory/remedy-task-hook to make one.
    Absent/non-executable/failing/silent hook -> 'todo' (never blocks the write)."""
    hook = os.path.join(root, "memory", "remedy-task-hook")
    if os.path.isfile(hook) and os.access(hook, os.X_OK):
        try:
            r = subprocess.run([hook, rid, title, scope], capture_output=True, text=True, timeout=20)
            for line in (r.stdout or "").splitlines():
                if line.strip():
                    return line.strip()
        except Exception:
            pass
    return "todo"


def main(argv):
    p = argparse.ArgumentParser(prog=os.path.basename(argv[0]),
                                description="Create a durable markdown memory record; prints the new id on stdout.")
    p.add_argument("type", choices=TYPES)
    p.add_argument("classification", choices=CLASSES)
    p.add_argument("title")
    p.add_argument("--scope", default="", help="routing scope (required when memory/scopes.json is present)")
    p.add_argument("--body", default="")
    p.add_argument("--evidence-sha", default="", dest="sha")
    p.add_argument("--supersedes", default="", dest="supersedes",
                   help="id of a record this one replaces (hidden from prime/search ranking)")
    p.add_argument("--dir", default="", dest="dir_override",
                   help="explicit memory dir (escape hatch — bypasses root/scope routing)")
    p.add_argument("--remedy-impl", default=None, dest="remedy_impl",
                   help="failure/convention only: 'none' (+ --why), a path, or an opaque ref (gotcha/task id)")
    p.add_argument("--why", default="", dest="remedy_why",
                   help="one-line justification, required with --remedy-impl none")
    a = p.parse_args(argv[1:])
    typ, cls, title = a.type, a.classification, a.title
    body, sha, scope, dir_override = a.body, a.sha, a.scope, a.dir_override
    supersedes = a.supersedes
    # ADR-0031: never refuse the write (caller is often an LLM agent — a refusal invites
    # gaming). Sole exception: 'none' with no --why is a trivial usage error, not content
    # refusal. Type-gated here so failure/convention rejects it while other types no-op below.
    if typ in ("failure", "convention") and a.remedy_impl == "none" and not a.remedy_why:
        sys.stderr.write("error: --remedy-impl none requires --why (one-line justification)\n")
        return 2
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
        # "_resolver" is a reserved config key (see below), never a usable scope name
        home_dir = homes.get(scope) if scope != "_resolver" else None
        if home_dir is None:
            sys.stderr.write("warn: scope %r has no home in scopes.json -> parked in central\n" % scope)
            home_dir = homes.get("central", ".")
        # Dynamic routing: "_resolver" (a command string) turns the scope's value
        # (above, a topic NAME rather than a literal path) into an absolute dir by
        # running `<_resolver> <value>` — never fall back to the literal value on
        # failure, an ambiguous/malformed dir is worse than a blocked write.
        resolver = homes.get("_resolver")
        if isinstance(resolver, str) and resolver.strip():
            # trust gate: scopes.json may come from a cloned (untrusted) repo — running
            # an arbitrary "_resolver" command is code execution, so it only fires for a
            # root the user explicitly opted in. Never fall back to the literal value on
            # an untrusted root (that's the silent-divergence failure this feature exists
            # to prevent) — block instead, with both remedies spelled out.
            root_real = os.path.realpath(root)
            # no dedicated env override (a clone could point one at a self-listing file).
            # expanduser still honors $HOME — accepted trust boundary, same as git's
            # ~/.gitconfig: an attacker who sets $HOME already owns the shell.
            trusted_path = os.path.expanduser("~/.config/draille/trusted-roots")
            trusted = set()
            try:
                with open(trusted_path, encoding="utf-8") as tf:
                    for line in tf:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            trusted.add(line)
            except OSError:
                pass
            if root_real not in trusted:
                sys.stderr.write(
                    "error: scopes.json has \"_resolver\" but root %r is not trusted (%s).\n"
                    "  to trust it:      echo %s >> %s\n"
                    "  or to opt out:    remove \"_resolver\" from scopes.json\n"
                    % (root_real, trusted_path, root_real, trusted_path))
                return 2
            if not isinstance(home_dir, str):
                sys.stderr.write(
                    "error: scope %r value %r is not a string (scopes.json) — can't pass to _resolver\n"
                    % (scope, home_dir))
                return 2
            try:
                cmd = shlex.split(resolver) + [home_dir]
            except ValueError as e:
                sys.stderr.write("error: _resolver %r is malformed (bad quoting): %s\n" % (resolver, e))
                return 2
            try:
                rr = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            except (OSError, subprocess.SubprocessError) as e:
                sys.stderr.write(
                    "error: _resolver %r failed to run for scope %r (value %r): %s\n"
                    % (resolver, scope, home_dir, e))
                return 2
            out_lines = (rr.stdout or "").splitlines()
            if rr.returncode != 0 or len(out_lines) != 1 or not out_lines[0].strip():
                sys.stderr.write(
                    "error: _resolver %r did not resolve scope %r (value %r) to a single "
                    "path (exit=%s stdout=%r stderr=%r)\n"
                    % (resolver, scope, home_dir, rr.returncode, rr.stdout, rr.stderr))
                return 2
            home_dir = out_lines[0].strip()
        # scopes.json may come from a cloned (untrusted) repo — the resolved base
        # must stay inside root. realpath normalizes .., absolute/rooted/drive-
        # relative paths, and symlinks; a different Windows drive raises ValueError
        # in commonpath → also unsafe. (isabs alone misses /-rooted homes on Windows.)
        base = os.path.join(root, home_dir, "memory")
        root_r = os.path.realpath(root)
        try:
            contained = os.path.commonpath([root_r, os.path.realpath(base)]) == root_r
        except ValueError:
            contained = False
        if not contained:
            sys.stderr.write("error: unsafe home %r in scopes.json (escapes memory root)\n" % home_dir)
            return 2
    else:
        # mono-project mode: one memory store at the root of the repo
        scope = scope or os.path.basename(root)
        base = os.path.join(root, "memory")
    date = datetime.date.today().isoformat()
    rid = "%s-%s" % (slug(title, 24), hashlib.sha1((title + body).encode()).hexdigest()[:6])
    # ADR-0031 mvt 3: failure/convention always gets a remedy_impl pointer — 'none'+why,
    # a verified path, an opaque ref (gotcha/task id) verbatim, or (ABSENT: no flag, or an
    # invalid path) the remedy-task-hook / 'todo' fallback. Never gates the write itself.
    remedy_impl_val = remedy_why_val = None
    if typ in ("failure", "convention"):
        # frontmatter is line-based — same injection guard as title (a newline in the
        # value would smuggle a frontmatter key)
        ri = (a.remedy_impl or "").replace("\r", " ").replace("\n", " ").strip() or None
        a.remedy_why = a.remedy_why.replace("\r", " ").replace("\n", " ")
        if ri == "none":
            remedy_impl_val, remedy_why_val = "none", a.remedy_why
        elif ri and (ri.startswith("~") or "/" in ri):
            if os.path.exists(os.path.expanduser(ri)):
                remedy_impl_val = ri
            else:
                sys.stderr.write("warn: --remedy-impl path %r not found -> treated as absent\n" % ri)
        elif ri:
            remedy_impl_val = ri  # opaque id (gotcha/task ref) — accepted verbatim
        if remedy_impl_val is None:
            remedy_impl_val = remedy_hook_ref(root, rid, title, scope)
            sys.stderr.write(
                "⚠ remède non câblé — remedy_impl: %s (record %s). "
                "Câbler = code/gotcha row, le record n'est qu'un pointeur (ADR-0031).\n"
                % (remedy_impl_val, rid))
    rdir = os.path.join(base, "records")
    os.makedirs(rdir, exist_ok=True)
    fm = ["id: %s" % rid, "type: %s" % typ, "classification: %s" % cls,
          "scope: %s" % scope, 'evidence_sha: "%s"' % sha, "relates_to: []",
          "role: memory-record", "created: %s" % date,
          'summary: "%s"' % title[:120].replace('"', "")]
    if supersedes:
        fm.append("supersedes: %s" % supersedes)
    if remedy_impl_val is not None:
        fm.append("remedy_impl: %s" % remedy_impl_val)
        if remedy_why_val:
            fm.append('remedy_why: "%s"' % remedy_why_val.replace('"', ""))
    md = "---\n" + "\n".join(fm) + "\n---\n\n# " + title + "\n\n" + (body or "") + "\n"
    with open(os.path.join(rdir, "%s-%s-%s.md" % (date, slug(title), rid)), "w", encoding="utf-8") as f:
        f.write(md)
    sys.stderr.write("recorded %s [%s/%s]\n" % (rid, typ, cls))
    print(rid)  # stdout = the new id (for chaining an outcome reference)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
