# draille vs. the agent-memory frameworks

How draille relates to mem0, Letta (MemGPT), Zep/Graphiti, and Cognee — and when you should pick one of them instead.

The short version: those are memory **engines** (databases, graphs, runtimes). draille is a memory **convention** — plain markdown files in your repo, plus ~400 lines of stdlib-only Python to record, rank, and prime them. It competes on a different axis: portability, inspectability, and zero lock-in, not retrieval benchmarks.

## Comparison table

| | draille | mem0 | Letta (ex-MemGPT) | Zep / Graphiti | Cognee |
|---|---|---|---|---|---|
| **What it is** | markdown records + ranking scripts, lives in your git repo | memory layer you bolt onto an existing agent | agent runtime where the agent *is* its memory (OS-style) | temporal knowledge-graph memory (every fact timestamped, with a validity window) | knowledge graph built from your documents, entities, and code |
| **Storage** | one `.md` file per record + append-only `outcomes.jsonl` | hybrid vector + graph + KV store | core / recall / archival tiers behind a REST API | graph database (Graphiti) | graph database |
| **Runs** | anywhere Python 3 runs; no server, no API calls | hosted or self-host (graph features are on the paid Pro plan) | self-host or cloud | Zep cloud; Graphiti is the OSS core | self-host (OSS, V1 launched June 2026) |
| **Agent runtime** | any — Claude Code, Codex, Cursor, Gemini, or a human with a text editor | SDK integration (Python, ~5 lines) | agents run *inside* Letta | SDK integration | SDK integration |
| **Human-editable** | yes — records are markdown, fix them with any editor, review them in a PR | no — opaque store | no — via API/tools | no — graph store | no — graph store |
| **Versioning / recovery** | git; the repo history is the WORM layer | store-dependent | store-dependent | store-dependent | store-dependent |
| **Ranking signal** | classification weight + real usage outcomes (`success` boosts, `failure` penalizes; `partial` is logged only) | relevance / recency | agent self-edits what stays in core memory | temporal validity + graph traversal | graph relevance |
| **Dependencies** | Python stdlib only; each tool is a copyable single file | Python SDK + backing stores | full runtime + REST API | graph DB + SDK | graph DB + LLM pipeline |
| **License / traction** | MIT | ~60K GitHub stars; open core, hosted product | OSS runtime; $10M seed round | Graphiti OSS + Zep commercial; 63.8% on LongMemEval (vs. mem0's 49%) | OSS |
| **Lock-in** | none — delete the scripts, the markdown still reads | store format + API | runtime | graph schema + API | graph schema |

## Same shape as Letta's tiers

Letta's core insight — memory in tiers of decreasing heat — is right, and draille's recommended bootstrap uses the same three:

| Letta | draille |
|---|---|
| core memory (in-context "RAM") | **HOT** — a `memory/HANDOVER.md` CORE block, rewritten each session |
| recall memory (recent cache) | **JOURNAL** — append-only `memory/journal/<date>.md` |
| archival memory (unbounded disk) | **DURABLE** — `draille record`, ranked by `draille prime` |

The difference is the substrate. Letta keeps the tiers inside a runtime and lets the agent edit them through API tools; draille keeps them as files the agent edits with the same tools it edits your code with, and git provides history, review, and recovery for free.

The second difference is the ranking signal. Most frameworks rank memories by embedding similarity or recency. draille's `prime` ranks by classification weight **joined with the outcomes log**: an `outcome <id> success` event means "following this record demonstrably helped." Records earn their place in the session-start digest by being useful in practice, not by being semantically nearby.

## The file-based wave (2026)

As of July 2026, "memory as plain files" is no longer just draille's bet — it's a visible trend with its own critics. voxos.ai claims [60,000+ projects now store AI coding agent memory in plain markdown files](https://voxos.ai/blog/how-to-give-ai-coding-agents-long-term-m/index.html). The scale is being contested from the other side: mem0 published ["Your AI Agent's Memory Is Just a File? That's the Problem"](https://mem0.ai/blog/your-ai-agents-memory-is-just-a-file-thats-the-problem), arguing flat files break down at semantic recall, multi-user, and memory-as-a-service scale — a direct shot at the approach draille takes, and itself a signal the niche is now worth attacking. The pattern has also gone mainstream at the tool layer: [Claude Code ships native memory](https://code.claude.com/docs/en/memory) — a per-project auto memory directory indexed by a `MEMORY.md` digest (first ~200 lines loaded at session start). Same markdown-index shape as draille's `prime`, scoped instead to one user, one tool.

### Closest neighbors

Three 2026 arrivals sit closest to draille's corner (markdown-first, no heavy backing store):

- **[memsearch](https://github.com/zilliztech/memsearch)** (zilliztech) — "persistent unified memory layer for AI agents (Claude Code, Codex), backed by Markdown and Milvus." Markdown-first like draille, but it's a search layer over a vector DB (Milvus is a real dependency to run), not a triage protocol — no HOT/DURABLE/JOURNAL ritual, no outcome-based ranking.
- **[TencentDB Agent Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory)** (MIT, May 2026) — fully local 4-tier pipeline, zero external API calls. Local like draille, but the store is SQLite: opaque to `cat`, not git-diffable, no PR review of what the agent remembers.
- **[engramory](https://github.com/tinqiao-oss/engramory)** — an opinionated, zero-infrastructure memory protocol for markdown files plus a validator, closest in philosophy (protocol + curation discipline over raw storage). Where it differs: no outcomes log — curation stays a judgment call rather than draille's success/failure tally — and no tiered HOT/DURABLE/JOURNAL session-end ritual.

## When to use draille

Use draille when your memory should live **with the project, in the open**. If you work across multiple agent runtimes (Claude Code today, something else next quarter), if you want to read a record with `cat`, fix a wrong one with your editor, review memory changes in a pull request, and clone the repo onto a new machine with the memory already in it — draille is the fit. It is also the right default when the record count is human-scale (tens to low thousands): `prime` reads live files on every run, there is no index to rebuild or drift, and the whole system fits in your head. Nothing to deploy, nothing to pay for, nothing phones home.

## When NOT to use draille

Don't use draille when you need **retrieval at scale or semantic search**. There are no embeddings and no vector index; `prime` is a ranked digest, not a query engine. If your agents need "find every fact related to X across 100K memories," mem0 or a vector store will serve you better. Same if you need **multi-user memory-as-a-service** — mem0's pitch is a shared memory layer behind an API, serving many users and agents from one hosted store; draille assumes one repo, one team, files on disk — no server, no per-user ACLs, no hosted tier to point a fleet of agents at. Likewise if you need **temporal fact tracking** — knowing that "user lives in London" was true until March and "lives in Tokyo" after — that is exactly what Zep/Graphiti's timestamped validity windows are built for, and draille only gives you git history as a proxy.

Don't use it either when you want the **agent's runtime to own memory management** — self-editing core memory mid-conversation, automatic paging between tiers — which is Letta's whole design; or when your problem is graph-shaped — entities and relations extracted from a large document or code corpus — which is Cognee's territory. draille is a convention plus small tools; if you need an engine, use an engine. The two compose fine: nothing stops a draille repo from also feeding a vector index, since the records are just markdown.
