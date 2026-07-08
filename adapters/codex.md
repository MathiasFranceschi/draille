# Codex

Paste the block below into your project's `AGENTS.md`.

```markdown
# Memory (draille)

At session start: run `draille prime` for the durable memory digest, and read
`memory/HANDOVER.md` (current state) if present.

At session end ("session-end"): triage the session into three tiers —
- **HOT** → rewrite the CORE block of `memory/HANDOVER.md` (≤15 lines, merge
  related lines — never stack blocks);
- **DURABLE** (decisions/patterns/failures worth keeping) →
  `draille record <decision|pattern|failure|convention|reference> <foundational|tactical|observational> "<title>" --body "<why + how>"`;
- **JOURNAL** → append one `## HH:MM · <topic>` block to
  `memory/journal/<YYYY-MM-DD>.md` (append-only, never rewrite prior blocks).

Commit `session-end: <YYYY-MM-DD>`. Never auto-push.
```

**Multi-scope store?** If your root has a `memory/scopes.json`, `--scope <scope>`
is required on every `draille record` — add it to the DURABLE line above
(`--scope` = a key of `scopes.json`; records route to that scope's home).
