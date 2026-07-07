#!/usr/bin/env python3
"""Convert legacy JSONL memory records -> markdown records (+ outcome-log lines).

Maps each JSONL record to a markdown note (frontmatter: id, type, classification,
evidence_sha, created, role) + body. DROPS dir_anchors/files (paths — the whole
point is path-independence). Outcomes -> outcomes.jsonl, keyed by the immutable record id.
Idempotent per record: same id -> same filename -> overwrite. Stdlib only.

Usage: migrate.py <domain.jsonl> <out_records_dir> [<out_outcomes.jsonl>]
"""
import sys, os, json, re

def slug(s, n=40):
    return (re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:n] or "rec")

def title_of(d):
    return (d.get("name") or d.get("title")
            or (d.get("description") or d.get("content") or d.get("rationale") or d.get("id", ""))[:80]).replace("\n", " ").strip()

def body_of(d):
    t = d.get("type")
    if t == "failure":
        b = d.get("description", "")
        if d.get("resolution"):
            b += "\n\n**Resolution:** " + d["resolution"]
        return b.strip()
    if t == "decision":
        return (d.get("rationale", "")).strip()
    if t == "convention":
        return (d.get("content", "")).strip()
    return (d.get("description", "")).strip()  # pattern, reference

def main(argv):
    if len(argv) < 3:
        sys.stderr.write("usage: migrate.py <domain.jsonl> <out_records_dir> [outcomes.jsonl]\n")
        return 2
    src, outdir = argv[1], argv[2]
    out_oc = argv[3] if len(argv) > 3 else os.path.join(os.path.dirname(outdir.rstrip("/")), "outcomes.jsonl")
    os.makedirs(outdir, exist_ok=True)
    n_rec = n_out = 0
    out_f = None
    with open(src, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:
                sys.stderr.write("skip malformed jsonl line\n"); continue
            rid = d.get("id")
            if not rid:
                continue
            date = (d.get("recorded_at", "") or "")[:10]
            title = title_of(d)
            # slug the filename components — a hostile jsonl id like "../../x" must not
            # traverse out of outdir. The RAW id stays in frontmatter/outcomes (join key);
            # the filename is cosmetic (prime reads frontmatter, never parses filenames).
            fn = "%s-%s-%s.md" % (slug(date) if date else "undated", slug(title), slug(rid))
            fm = ["id: %s" % rid, "type: %s" % d.get("type", "?"),
                  "classification: %s" % d.get("classification", "observational"),
                  'evidence_sha: "%s"' % (d.get("evidence") or {}).get("commit", ""),
                  "relates_to: []", "role: memory-record", "created: %s" % date,
                  'summary: "%s"' % title[:120].replace('"', "")]
            md = "---\n" + "\n".join(fm) + "\n---\n\n# " + title + "\n\n" + body_of(d) + "\n"
            with open(os.path.join(outdir, fn), "w", encoding="utf-8") as o:
                o.write(md)
            n_rec += 1
            for oc in (d.get("outcomes") or []):
                evt = {"id": rid, "status": oc.get("status", "partial"), "sha": "",
                       "date": (oc.get("recorded_at", "") or date)[:10], "note": oc.get("notes", "")}
                if out_f is None:
                    out_f = open(out_oc, "a", encoding="utf-8")
                out_f.write(json.dumps(evt, ensure_ascii=False) + "\n")
                n_out += 1
    if out_f:
        out_f.close()
    sys.stderr.write("migrated %d records, %d outcomes from %s\n" % (n_rec, n_out, os.path.basename(src)))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
