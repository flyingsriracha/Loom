# Agentic Coding Memory Architecture — Research Report (April 2026)

> Research compiled for the SignalSpace / AutoBrain project.
> Evaluating graph databases, AI memory systems, hybrid RAG, and MCP integration
> for a long-term agentic coding memory system in the automotive ASAM domain.

---

## Table of Contents

1. [Graph Databases for AI/Agentic Workflows](#1-graph-databases)
2. [AI Agent Memory Systems](#2-ai-agent-memory-systems)
3. [Hybrid RAG & Knowledge Graph Systems](#3-hybrid-rag--knowledge-graph-systems)
4. [MCP (Model Context Protocol) Integration](#4-mcp-integration)
5. [Coding-Agent-Specific Memory Solutions](#5-coding-agent-specific-memory)
6. [Benchmarks & Data Points](#6-benchmarks--data-points)
7. [Real-World Implementations & Community Discussion](#7-real-world-implementations)
8. [Recommended Architecture for SignalSpace](#8-recommended-architecture)
9. [Sources](#9-sources)

---

## 1. Graph Databases

### Neo4j — The Incumbent

- **Type**: Native property graph, disk-backed with memory caching
- **Query Language**: Cypher (the industry standard)
- **Strengths**: Mature ecosystem, ACID transactions, Enterprise clustering (Raft-based), built-in Graph Data Science library with ML modeling, vector similarity search, and GraphRAG support
- **Weaknesses**: JVM-based (heavy ops overhead), pointer-based traversal slower for wide fan-out queries, expensive Enterprise license for clustering/RBAC
- **MCP Integration**: Official Neo4j MCP servers available — Cypher query execution, schema retrieval, write operations, memory knowledge graph management, and Aura instance control
- **AI Agent Use**: Graphiti (Zep's engine) runs on Neo4j as its primary backend. Neo4j integrates with LangGraph, Microsoft Agent Framework, and Strands Agents via MCP

> Sources: [neo4j.com/developer/genai-ecosystem/model-context-protocol-mcp](https://neo4j.com/developer/genai-ecosystem/model-context-protocol-mcp/), [wearedevelopers.com — MCP with Neo4j](https://www.wearedevelopers.com/en/magazine/604/everything-a-developer-needs-to-know-about-mcp-with-neo4j-604), [puppygraph.com/blog/falkordb-vs-neo4j](https://www.puppygraph.com/blog/falkordb-vs-neo4j)

### FalkorDB — The Speed Demon (RedisGraph Successor)

- **Type**: In-memory property graph, Redis-native module
- **Query Language**: openCypher-compatible
- **Internal Representation**: Sparse adjacency matrices using GraphBLAS — queries execute as linear algebra (matrix multiplication), not pointer-chasing
- **Performance**: Benchmarked at **496x faster than Neo4j at P99 latency** and **6x better memory efficiency** (per FalkorDB/Zep benchmarks). Sub-10ms query latencies. Reduces hallucinations by up to 90% vs traditional RAG
- **Strengths**: Purpose-built for GraphRAG and agent-based retrieval. Multi-graph/multi-tenant support. Vector similarity search + full-text search built in. Clustering via Redis replication
- **Weaknesses**: Redis transaction semantics (not full ACID). Persistence via AOF/snapshotting (not native WAL). Smaller community than Neo4j
- **AI Agent Use**: Graphiti (Zep) now officially supports FalkorDB as a backend. Used for agentic memory in production by multiple teams
- **GitHub**: [github.com/FalkorDB/FalkorDB](https://github.com/FalkorDB/FalkorDB)
- **GitLab Analysis**: GitLab's knowledge-graph team evaluated FalkorDB, Neo4j, and Memgraph — noted FalkorDB's smaller surface area and Redis-native deployment as advantages

> Sources: [blog.dailydoseofds.com — FalkorDB 496x faster](https://blog.dailydoseofds.com/p/graph-dbs-vs-falkordb), [orchestrator.dev — FalkorDB for AI](https://orchestrator.dev/blog/2025-12-11-falkordb), [blog.getzep.com — Graphiti FalkorDB support](https://blog.getzep.com/graphiti-knowledge-graphs-falkordb-support/), [gitlab.com — Graph DB vendor analysis](https://gitlab.com/gitlab-org/rust/knowledge-graph/-/work_items/254)

### Memgraph — In-Memory with Cypher

- **Type**: In-memory property graph, C++ native
- **Query Language**: Cypher
- **Key Feature (v3.4)**: Edge vector indexing, LLM model integration, quantization for vector indexes
- **Strengths**: Sub-millisecond traversals, Cypher-compatible (easy Neo4j migration), lower ops overhead than Neo4j, streaming analytics optimized
- **Weaknesses**: Persistence requires snapshotting, smaller community, datasets must fit in RAM
- **Memgraph 3**: Explicitly positioned to "solve the LLM context problem" — built-in vector indexing on edges, not just nodes
- **GitHub**: [github.com/memgraph/memgraph](https://github.com/memgraph/memgraph)
- **MemoryGraph MCP Server**: A community MCP server (`gregorydickson/memory-graph`) supports SQLite, Neo4j, AND Memgraph backends for coding agent persistent memory

> Sources: [memgraph.com/blog/memgraph-3](https://memgraph.com/blog/memgraph-3-graph-database-llm-context-problem), [memgraph.com — v3.4 release](https://memgraph.com/blog/memgraph-3-4-release-announcement), [puppygraph.com/blog/memgraph-vs-neo4j](https://www.puppygraph.com/blog/memgraph-vs-neo4j), [github.com/gregorydickson/memory-graph](https://github.com/gregorydickson/memory-graph)

### PuppyGraph — Zero-ETL Graph Query Engine

- **Type**: Graph query engine over existing relational data (NOT a graph database)
- **Query Languages**: Cypher AND Gremlin
- **Key Differentiator**: Queries existing data stores (MySQL, PostgreSQL, DuckDB, Iceberg, Hudi, Delta Lake) as a unified graph — no data migration or ETL
- **Performance**: Sub-3s latency on petabyte-scale, 6-hop queries across billions of edges
- **Customers**: Coinbase, Netskope, AMD
- **Funding**: $5M seed led by Defy.vc
- **AI Agent Use**: PuppyGraphAgent for agentic GraphRAG. MCP-compliant server for LLM access. PyPI package available
- **Relevance to SignalSpace**: Since you already have SQLite + ChromaDB, PuppyGraph could layer graph queries on top without migrating data. Worth a spike

> Sources: [puppygraph.com](https://puppygraph.com/), [puppygraph.com/blog/mcp-knowledge-graph](https://www.puppygraph.com/blog/mcp-knowledge-graph), [puppygraph.com/blog/graph-rag](https://www.puppygraph.com/blog/graph-rag), [pypi.org/project/puppygraph](https://pypi.org/project/puppygraph/)

### KuzuDB — Archived (Cautionary Tale)

- **Type**: Embedded property graph, columnar storage, Cypher-compatible
- **Status**: **Archived October 2025** — original team discontinued the project
- **Impact**: Vela Partners had built their multi-agent context graph on KuzuDB, had to fork it and add concurrent write support to ship to production
- **Lesson**: Embedded graph DBs are attractive for simplicity but carry abandonment risk. Graphiti initially supported Kuzu as an embedded option
- **Takeaway**: For production systems, prefer databases with commercial backing (Neo4j, FalkorDB, Memgraph) or large community forks

> Sources: [theregister.com — KuzuDB abandoned](https://www.theregister.com/2025/10/14/kuzudb_abandoned/), [vela.partners — KuzuDB fork](https://vela.partners/blog/kuzudb-ai-agent-memory-graph-database), [github.com/kuzudb/kuzu (archived)](https://github.com/kuzudb/kuzu)

### Graph Database Comparison Table

| Feature | Neo4j | FalkorDB | Memgraph | PuppyGraph |
|---|---|---|---|---|
| Type | Native graph DB | Redis module | In-memory graph | Query engine |
| Query Language | Cypher | openCypher | Cypher | Cypher + Gremlin |
| Storage | Disk + cache | In-memory (Redis) | In-memory | Queries existing stores |
| ACID | Full | Redis semantics | Limited | Depends on source |
| Performance | Good (deep traversal) | 496x faster P99 | Sub-millisecond | Sub-3s petabyte |
| Vector Search | Yes (built-in) | Yes | Yes (v3.4+) | Via source DBs |
| MCP Server | Official | Via Graphiti | Community | Official |
| Best For | System of record | AI inference/GraphRAG | Real-time analytics | Zero-ETL graph overlay |
| Risk | Ops overhead | Redis dependency | RAM limits | Early-stage company |

> Source: Compiled from [arcadedb.com — Neo4j alternatives 2026](https://arcadedb.com/blog/neo4j-alternatives-in-2026-a-fair-look-at-the-open-source-options/), [puppygraph.com/blog/best-graph-databases](https://www.puppygraph.com/blog/best-graph-databases)

---

## 2. AI Agent Memory Systems

The field has converged on **four memory types** that map to human cognition: working (short-term), procedural, semantic, and episodic. The 2026 consensus pattern is a **Dual-Layer Architecture**: Hot Path (recent messages + summarized graph state) and Cold Path (retrieval from Zep/Mem0/Pinecone), with a Memory Node that synthesizes what to save after each turn.

> Source: [digitalapplied.com — AI Agent Memory Systems Complete Guide](https://www.digitalapplied.com/blog/ai-agent-memory-systems-complete-guide), [blogs.oracle.com — Agent Memory](https://blogs.oracle.com/developers/agent-memory-why-your-ai-has-amnesia-and-how-to-fix-it)

### Zep / Graphiti — Temporal Knowledge Graph (Top Pick for State Fidelity)

- **Architecture**: Temporal knowledge graph engine. Episodes (text/JSON) decomposed into entities, edges, and temporal attributes. Every fact carries validity windows (valid_from, valid_to, invalid_at)
- **Benchmark**: **63.8% on LongMemEval** (GPT-4o). Up to **18.5% accuracy improvement** and **90% latency reduction** vs full-context baselines (arxiv 2501.13956)
- **Graph Backends**: Neo4j, FalkorDB, or Kuzu (embedded)
- **SDKs**: Python, TypeScript, Go
- **Pricing**: Free (1K credits) → $25/mo Flex (20K credits) → Enterprise custom
- **Compliance**: SOC 2 Type 2, HIPAA (cloud)
- **GitHub Stars**: ~24K (Graphiti)
- **Self-Hosting**: Zep Community Edition **deprecated**. Self-host via raw Graphiti only (manage graph DB yourself)
- **MCP Integration**: Graphiti MCP Server available — episodic memory, entity management, fact management on Neo4j/FalkorDB backend
- **Key Strength for SignalSpace**: Temporal reasoning is critical for tracking ASAM standard evolution, decision history, and session continuity. "What was true about Pipeline A quality on March 15th?" is a native Zep query
- **Academic Paper**: arxiv 2501.13956 — "A Temporal Knowledge Graph Architecture for Agent Memory"

> Sources: [blog.getzep.com — Temporal KG Architecture](https://blog.getzep.com/zep-a-temporal-knowledge-graph-architecture-for-agent-memory/), [arxiv.org/html/2501.13956v1](https://arxiv.org/html/2501.13956v1), [vectorize.io — Mem0 vs Zep](https://vectorize.io/articles/mem0-vs-zep), [help.getzep.com — Graphiti overview](https://help.getzep.com/v2/graphiti/getting-started/overview), [mcplane.com — Graphiti MCP](https://mcplane.com/mcp_servers/graphitiserver)

### Mem0 — Vector + Knowledge Graph (Largest Community)

- **Architecture**: Dual-store — vector DB (Qdrant/Chroma/Milvus/pgvector/Redis) + knowledge graph (Pro tier only at $249/mo)
- **Benchmark**: **49.0% on LongMemEval** (independent eval). Self-reported: 91% lower p95 latency and 90%+ token cost savings vs full-context (arxiv 2504.19413)
- **GitHub Stars**: ~48K (largest in category)
- **Funding**: $24M Series A (YC-backed, October 2025)
- **License**: Apache 2.0 (fully self-hostable)
- **Pricing**: Free (10K memories) → $19/mo Standard → $249/mo Pro (graph features)
- **Compliance**: SOC 2, HIPAA
- **Key Weakness**: Graph features gated behind $249/mo Pro tier. 13x price jump from Standard
- **arxiv Paper on Efficiency**: "mem0 significantly outperforms Graphiti in efficiency, with faster loading times, lower resource consumption, and minimal network overhead, while accuracy differences were not statistically significant" (arxiv 2601.07978)

> Sources: [vectorize.io — Mem0 vs Zep](https://vectorize.io/articles/mem0-vs-zep), [arxiv.org/html/2601.07978v2](https://arxiv.org/html/2601.07978v2), [arxiv.org/html/2504.19413](https://arxiv.org/html/2504.19413), [mem0.ai/blog — Benchmark](https://mem0.ai/blog/benchmarked-openai-memory-vs-langmem-vs-memgpt-vs-mem0-for-long-term-memory-here-s-how-they-stacked-up)

### Hindsight — Multi-Strategy Hybrid (Highest Benchmark Score)

- **Architecture**: Four parallel retrieval strategies — semantic search, BM25 keyword, entity graph traversal, temporal filtering — with cross-encoder reranking. Embedded PostgreSQL + pgvector
- **Benchmark**: **91.4% on LongMemEval** — first agent memory system to break 90% barrier. With open-source 20B model: 83.6% accuracy (outperforms full-context GPT-4o)
- **Key Feature**: `reflect` operation — LLM synthesizes across all relevant memories (not just retrieval)
- **Self-Hosting**: One Docker command, embedded PostgreSQL
- **MCP-First**: Works with Claude, Cursor, VS Code, Windsurf
- **SDKs**: Python, TypeScript, Go
- **Funding**: $3.5M (Vectorize.io, April 2024)
- **GitHub Stars**: ~4K (growing fast)
- **Academic Paper**: arxiv 2512.12818 — "Building Agent Memory that Retains, Recalls, and Reflects"

> Sources: [jangwook.net — Hindsight MCP](https://jangwook.net/en/blog/en/hindsight-mcp-agent-memory-learning/), [vectorize.io — Hindsight vs Zep](https://vectorize.io/articles/hindsight-vs-zep), [arxiv.org/html/2512.12818v1](https://arxiv.org/html/2512.12818v1), [vectorize.io — Best AI Agent Memory Systems](https://vectorize.io/articles/best-ai-agent-memory-systems)

### Letta (formerly MemGPT) — Agent Runtime with Self-Managed Memory

- **Architecture**: OS-inspired tiered memory — Core (always in context, like RAM), Recall (searchable history, like disk cache), Archival (long-term queryable, like cold storage). Agents self-edit their own memory blocks via tool calls
- **Origin**: UC Berkeley research paper on MemGPT
- **Funding**: $10M seed led by Felicis Ventures ($70M post-money valuation). Backed by Jeff Dean (Google DeepMind), Clem Delangue (Hugging Face), Ion Stoica
- **Key Feature**: Agent Development Environment (ADE) for visual debugging and memory inspection
- **Model-Agnostic**: OpenAI, Anthropic, Ollama, Vertex AI
- **Pricing**: Free self-hosted → $20/mo Pro → $750/mo Scale → Enterprise custom
- **GitHub**: [github.com/letta-ai/letta](https://github.com/letta-ai/letta) (~21K stars)
- **MCP Integration**: Yes — connect tools via MCP
- **Letta Code**: New product — model-agnostic agent harness with persistent memory, computer use, skills, subagents, git-backed memory

> Sources: [letta.com/blog/our-next-phase](https://www.letta.com/blog/our-next-phase), [vectorize.io — Hindsight vs Letta](https://vectorize.io/articles/hindsight-vs-letta), [vectorize.io — Mem0 vs Letta](https://vectorize.io/articles/mem0-vs-letta), [github.com/letta-ai/letta](https://github.com/letta-ai/letta)

### Cognee — Knowledge Graph from Diverse Sources

- **Architecture**: Pipeline-based ingestion from 30+ data sources. Produces subject-relation-object triplets. Runs on SQLite (relational) + LanceDB (vector) + Kuzu (graph) by default — no external services
- **Key Feature**: Multimodal — text, images, audio transcriptions. "Memory in 6 lines of code"
- **Funding**: €7.5M (~$8.1M) seed
- **GitHub**: [github.com/topoteretes/cognee](https://github.com/topoteretes/cognee) (~12K stars)
- **Weakness**: Python-only, smaller community
- **Best For**: Building knowledge graphs from diverse document sources (PDFs, Slack, Notion, images, audio)

> Sources: [vectorize.io — Zep vs Cognee](https://vectorize.io/articles/zep-vs-cognee), [cognee.ai/blog](https://cognee.ai/blog/tutorials), [vectorize.io — Hindsight vs Cognee](https://vectorize.io/articles/hindsight-vs-cognee)

### Memory System Comparison Table

| System | LongMemEval | Architecture | GitHub Stars | Self-Host | Graph | Temporal | Price (entry) |
|---|---|---|---|---|---|---|---|
| **Hindsight** | 91.4% | Multi-strategy hybrid | ~4K | Yes (Docker) | Yes | Yes | Free self-hosted |
| **SuperMemory** | 81.6% | Memory + RAG | N/A (closed) | Enterprise only | Yes | Partial | Free (1M tokens) |
| **Zep/Graphiti** | 63.8% | Temporal KG | ~24K | Via Graphiti | Yes (core) | Yes (best) | Free (1K credits) |
| **Mem0** | 49.0% | Vector + Graph | ~48K | Yes (Apache 2.0) | Pro only ($249) | No | Free (10K memories) |
| **Letta** | N/A | Tiered (OS-inspired) | ~21K | Yes | Via tools | No | Free self-hosted |
| **Cognee** | N/A | KG + Vector pipeline | ~12K | Yes | Yes (core) | No | Free open source |
| **LangMem** | N/A | Flat key-value + vector | ~1.3K | Yes (MIT) | No | No | Free (MIT) |
| **LlamaIndex Memory** | N/A | Composable buffers | Part of ~48K | Yes | No | No | Free (MIT) |

> Source: [vectorize.io — Best AI Agent Memory Systems 2026](https://vectorize.io/articles/best-ai-agent-memory-systems)

### Key Research Paper: Mem0 vs Graphiti Efficiency (arxiv 2601.07978)

A direct comparison of Mem0 and Graphiti in distributed multi-agent systems found:
- Mem0 significantly outperforms Graphiti in **efficiency** — faster loading times, lower resource consumption, minimal network overhead
- **Accuracy differences were NOT statistically significant** between the two
- Implication: If you need temporal reasoning, Graphiti/Zep is worth the overhead. If you don't, Mem0 is more efficient

> Source: [arxiv.org/html/2601.07978v2](https://arxiv.org/html/2601.07978v2)

### Key Research Paper: MemoriesDB (arxiv 2511.06179)

A novel unified architecture where each memory is a "time-semantic-relational entity" — simultaneously encoding when an event occurred, what it means, and how it connects to other events. Designed to avoid "decoherence across time, meaning, and relation."

> Source: [arxiv.org/html/2511.06179v1](https://arxiv.org/html/2511.06179v1)

---

## 3. Hybrid RAG & Knowledge Graph Systems

### LightRAG — Graph-Enhanced RAG (EMNLP 2025)

- **Architecture**: Dual-level retrieval — low-level (specific entity/relationship) and high-level (thematic/conceptual). Builds a knowledge graph during indexing, then uses both graph traversal and vector similarity for retrieval
- **Key Advantage**: Addresses flat data representation and limited contextual awareness in traditional RAG
- **GitHub**: [github.com/HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) — EMNLP 2025 paper
- **Weakness**: Optimized for batch ingestion, not incremental updates. Re-indexing story is rough for daily-changing codebases
- **Go Implementation**: [github.com/MegaGrindStone/go-light-rag](https://github.com/MegaGrindStone/go-light-rag)
- **Integration**: Works with LangChain, Ollama for local deployment

> Sources: [github.com/HKUDS/LightRAG](https://github.com/HKUDS/LightRAG), [arxiv.org/html/2410.05779](https://arxiv.org/html/2410.05779), [dasroot.net — Simple RAG Pipeline](https://dasroot.net/posts/2025/12/implementing-simple-rag-pipeline-local-llms-embeddings/)

### GraphRAG — Complete 2026 Guide

- **Concept**: Combines knowledge graphs with LLMs for context-rich, accurate responses. Builds "community summaries" for global understanding of indexed datasets
- **Key Implementations**:
  - Microsoft GraphRAG (end-to-end entity extraction + knowledge base construction)
  - Neo4j GraphRAG (LangChain + Gemini integration)
  - FalkorDB GraphRAG (sub-10ms, 90% hallucination reduction)
  - PuppyGraph Agentic GraphRAG (zero-ETL, petabyte scale)
- **GraphRAG-Bench**: New benchmark (arxiv 2506.02404) evaluating the entire pipeline — graph construction, knowledge retrieval, and answer generation

> Sources: [meilisearch.com/blog/graph-rag](https://www.meilisearch.com/blog/graph-rag), [towardsdatascience.com — Graph RAG into Production](https://towardsdatascience.com/graph-rag-into-production-step-by-step-3fe71fb4a98e), [arxiv.org/abs/2506.02404](https://arxiv.org/abs/2506.02404)

---

## 4. MCP Integration

### State of MCP in 2026

- **Adoption**: OpenAI, Google DeepMind, Microsoft, and thousands of developers have adopted MCP. Supported in Claude, ChatGPT, VS Code, Cursor, and dozens of enterprise tools
- **Scale**: Over 13,000 MCP servers launched on GitHub in 2025
- **Protocol**: JSON-RPC 2.0, supports local (stdio) and remote (HTTP/SSE) transports
- **Security**: OAuth 2.1, PKCE, per-client consent flows
- **Impact**: Up to 80% reduction in integration development time (early adopter benchmarks)
- **Complementary Protocol**: A2A (Agent-to-Agent) for horizontal agent communication; MCP for vertical tool integration

> Sources: [pento.ai — A Year of MCP](https://www.pento.ai/blog/a-year-of-mcp-2025-review), [a2a-mcp.org — What is MCP](https://a2a-mcp.org/blog/what-is-mcp), [publicapis.io — MCP Guide](https://publicapis.io/blog/mcp-model-context-protocol-guide)

### Database MCP Servers Available

| Database | MCP Server | Features |
|---|---|---|
| Neo4j | Official (multiple) | Cypher queries, schema, writes, memory KG, Aura management |
| FalkorDB | Via Graphiti MCP | Episodic memory, entities, facts |
| Memgraph | Community (memory-graph) | Entity/observation/relationship storage |
| SQLite | Multiple | Various implementations |
| PostgreSQL | Multiple | Query execution, schema |

### Key MCP Memory Servers

- **Graphiti MCP Server**: Knowledge graph for AI agents on Neo4j/FalkorDB. Episodic memory, entity management, fact management
- **MemoryGraph** (`gregorydickson/memory-graph`): Graph-based MCP server for coding agents. Supports SQLite, Neo4j, Memgraph backends. 18.7K+ stars on related projects
- **@modelcontextprotocol/server-memory**: Official Anthropic basic memory server using local knowledge graph (NDJSON)
- **mcp-memory-service** (PyPI): Open-source persistent memory with REST API + semantic search + knowledge graph + autonomous consolidation

> Sources: [mcpservers.org — memory-graph](https://mcpservers.org/en/servers/gregorydickson/memory-graph), [mcplane.com — Graphiti MCP](https://mcplane.com/mcp_servers/graphitiserver), [npmjs.com — server-memory](https://www.npmjs.com/package/@modelcontextprotocol/server-memory), [news.ycombinator.com — Memory-Graph](https://news.ycombinator.com/item?id=46091577)

---

## 5. Coding-Agent-Specific Memory

### Beads — Git-Backed Task Memory (Steve Yegge / Sourcegraph)

- **What**: Distributed, git-backed issue tracker designed specifically for AI coding agents. Stores agent thoughts and task dependencies as versioned files inside the Git repo
- **Problem Solved**: The "50 First Dates" problem — agents wake up with no memory of yesterday's work. After ~50 messages in context, agents lose the plot, forget fixes, hallucinate "Done"
- **Architecture**: Dependency-aware graph of tasks. Not a knowledge graph — a structured task/plan tracker that persists across sessions
- **GitHub**: [github.com/steveyegge/beads](https://github.com/steveyegge/beads) — 18.7K stars
- **Creator**: Steve Yegge (Sourcegraph)
- **Key Insight**: "Coding agents need to remember what solved problems, not just find similar content"

> Sources: [steve-yegge.medium.com — Introducing Beads](https://steve-yegge.medium.com/introducing-beads-a-coding-agent-memory-system-637d7d92514a), [decisioncrafters.com — Beads](https://decisioncrafters.com/beads-ai-agent-memory-system/), [yuv.ai/blog/beads](https://www.yuv.ai/blog/beads), [virtuslab.com — Beads](https://virtuslab.com/blog/ai/beads-give-ai-memory/)

### Signet — Local-First Persistent Memory

- **What**: Local-first memory layer for AI coding agents. Auto-summarizes code transcripts into structured knowledge
- **Stack**: SQLite + Markdown. No cloud reliance or vendor lock-in
- **Key Feature**: Retains context across sessions, cuts token waste

> Source: [thenextgentechinsider.com — Signet](https://www.thenextgentechinsider.com/pulse/signet-launches-local-first-persistent-memory-for-ai-coding-agents)

### EchoVault — Local SQLite Memory for Coding Agents

- **What**: Local memory system — SQLite database + Markdown files on your machine
- **Cost**: Zero. No cloud, no API keys

> Source: [muhammadraza.me — Building Local Memory](https://muhammadraza.me/2026/building-local-memory-for-coding-agents/)

### Mnemos — Scoped Memory for Coding Agents

- **What**: Project, workspace, and global memory scopes. Survives restarts in a single local SQLite file
- **Integrations**: Claude Code, Claude Desktop, generic MCP hosts, Codex
- **Key Feature**: Guided UI control plane for setup and host config

> Source: [mnemos.making-minds.ai](https://mnemos.making-minds.ai/)

### AgentFS (Turso) — SQLite-Based Agent State

- **What**: Unified interface for agents to manage all state in a single SQLite database
- **Key Feature**: Queryable via SQL, portable across environments, fully auditable

> Source: [turso.tech/blog/agentfs](https://turso.tech/blog/agentfs)

### Graphiti + FalkorDB for Claude Code (Real Implementation)

A detailed blog post describes building persistent AI memory for Claude Code:
1. Deploy Graphiti + FalkorDB (self-hosted)
2. Connect via MCP
3. Build a Stop hook that auto-captures every conversation
4. Backfill entire session history
- Result: "A system-level solution that works silently in the background"

> Source: [abisheklakandri.com — Persistent AI Memory Claude Code](https://abisheklakandri.com/blog/persistent-ai-memory-claude-code-graphiti)

### Auto-Claude Memory (Graphiti + LadybugDB)

- **What**: Graphiti-based persistent memory layer with embedded LadybugDB
- **Features**: Semantic search, knowledge graph of entities/relationships, CRUD memory operations
- **Available as**: LobeHub skill, Playbooks skill

> Sources: [lobehub.com — auto-claude-memory](https://lobehub.com/skills/adaptationio-skrillz-auto-claude-memory), [playbooks.com — auto-claude-memory](https://playbooks.com/skills/adaptationio/skrillz/auto-claude-memory)

---

## 6. Benchmarks & Data Points

### LongMemEval Benchmark Results (2026)

| System | Score | Model | Notes |
|---|---|---|---|
| Hindsight | **91.4%** | GPT-4o | First to break 90%. 4 parallel retrieval strategies |
| Hindsight | 83.6% | Open-source 20B | Outperforms full-context GPT-4o |
| SuperMemory | 81.6% | GPT-4o | Closed source |
| Zep/Graphiti | 63.8% | GPT-4o | Strongest on temporal queries |
| Mem0 | 49.0% | GPT-4o | Independent evaluation |

> Source: [vectorize.io — Best AI Agent Memory Systems](https://vectorize.io/articles/best-ai-agent-memory-systems), arxiv 2603.04814

### Performance Benchmarks

| Operation | Typical Latency | Notes |
|---|---|---|
| Vector-only retrieval | ~10-50ms | Single strategy, fastest but lowest recall |
| Graph traversal | ~50-150ms | Entity/relationship lookups |
| Multi-strategy retrieval | ~100-600ms | Depends on strategies + reranking |
| LLM synthesis (reflect) | ~800-3000ms | Full inference call |
| Memory ingestion | ~500-2000ms | LLM-based extraction, background |

### Graph Database Performance

| Metric | FalkorDB vs Neo4j |
|---|---|
| P99 Latency | FalkorDB **496x faster** |
| Memory Efficiency | FalkorDB **6x better** |
| Hallucination Reduction | Up to **90%** vs traditional RAG |

### Zep Performance (arxiv 2501.13956)

- Accuracy improvement: up to **18.5%** vs baselines
- Latency reduction: **90%** vs full-context methods

### Mem0 Efficiency (arxiv 2504.19413)

- P95 latency: **91% lower** than full-context
- Token cost savings: **>90%**

### Market Size

- AI agent memory market (within broader agentic AI): projected **$6.27B in 2025**, growing to **$28.45B by 2030** at 35.32% CAGR

> Source: [sparkco.ai — AI Agent Memory 2026](https://sparkco.ai/blog/ai-agent-memory-in-2026-comparing-rag-vector-stores-and-graph-based-approaches)

### Cost Impact

- Implementing persistent memory reduces context costs by **60%** (from $2,400/mo to $960/mo for 100K conversations)
- Response quality improvement: **35%** through learned user preferences

> Source: [iterathon.tech — AI Agent Memory Systems 2026](https://iterathon.tech/blog/ai-agent-memory-systems-implementation-guide-2026)

---

## 7. Real-World Implementations & Community Discussion

### Production Implementations

1. **Graphiti + FalkorDB for Claude Code** — Self-hosted knowledge graph that auto-captures every conversation via MCP Stop hook. Full session history backfill. [abisheklakandri.com](https://abisheklakandri.com/blog/persistent-ai-memory-claude-code-graphiti)

2. **Vela Partners KuzuDB Fork** — Built multi-agent context graph on KuzuDB, had to fork when it was archived Oct 2025. Added concurrent write support, shipped to production. [vela.partners](https://vela.partners/blog/kuzudb-ai-agent-memory-graph-database)

3. **memgraph-agent** — Graph-powered memory for AI agents using NER + co-occurrence graph + Personalized PageRank. Zero LLM cost, CPU-only, 82% faster than vector search. Inspired by SPRIG (arXiv 2602.23372). [github.com/yangyihe0305-droid/memgraph-agent](https://github.com/yangyihe0305-droid/memgraph-agent)

4. **Manus AI + TiDB X** — Uses TiDB X database branching for agentic workload isolation. 90% of new TiDB Cloud clusters are created by AI agents. [pingcap.com](https://www.pingcap.com/compare/best-database-for-ai-agents/)

5. **Cursor Memory Bank** — Modular, documentation-driven framework using Cursor custom modes (VAN, PLAN, CREATIVE, IMPLEMENT) for persistent memory. [github.com/vanzan01/cursor-memory-bank](https://github.com/vanzan01/cursor-memory-bank)

6. **Agno (formerly Phidata)** — Full-stack framework for multi-agent systems with memory, knowledge, and reasoning. [github.com/phidatahq/phidata](https://github.com/phidatahq/phidata)

### Community & Blog Discussions

- **Oracle Developers Blog**: "Building agent memory at enterprise scale is fundamentally a database problem. You need vectors, graphs, relational data, and ACID transactions working together." [blogs.oracle.com](https://blogs.oracle.com/developers/agent-memory-why-your-ai-has-amnesia-and-how-to-fix-it)

- **AI Plain English**: "Beyond Context Graphs: Why 2026 Must Be the Year of Agentic Memory, Causality, and Explainability" — argues agents need decision traces, not just execution rules. [ai.plainenglish.io](https://ai.plainenglish.io/beyond-context-graphs-why-2026-must-be-the-year-of-agentic-memory-causality-and-explainability-db43632dbdee)

- **Daily Dose of DS**: Tiger Data released "Agentic Postgres" — lets agents spin up full database forks in seconds, run destructive experiments safely, delete fork when done. [blog.dailydoseofds.com](https://blog.dailydoseofds.com/p/rag-agentic-rag-and-ai-memory)

- **Sparkco.ai**: Comprehensive comparison of PAG, MEMORY.md, and SQLite for persistent agent memory. PAG for complex relational queries, MEMORY.md for simple episodic storage, SQLite for durable queryable data. [sparkco.ai](https://sparkco.ai/blog/persistent-memory-for-ai-agents-comparing-pag-memorymd-and-sqlite-approaches)

- **Hacker News**: Discussion on Memory-Graph MCP server — "coding agents need to remember what solved problems, not just find similar content." [news.ycombinator.com](https://news.ycombinator.com/item?id=46091577)

- **Cisco Security Blog**: Warning about persistent memory compromise in Claude Code — agents maintaining notes about preferences and architecture can be attack vectors. [blogs.cisco.com](https://blogs.cisco.com/ai/identifying-and-remediating-a-persistent-memory-compromise-in-claude-code)

- **CSO Online**: "When AI nukes your database: The dark side of vibe coding" — Y Combinator Winter 2025 batch: 25% of startups have 95% AI-generated codebases. A vibe-coded payment gateway approved $2M in fraudulent transactions. [csoonline.com](https://www.csoonline.com/article/4053635/when-ai-nukes-your-database-the-dark-side-of-vibe-coding.html)

### GitHub Repos & Tools

| Repo | Stars | Description |
|---|---|---|
| [steveyegge/beads](https://github.com/steveyegge/beads) | 18.7K | Git-backed task memory for coding agents |
| [mem0ai/mem0](https://github.com/mem0ai/mem0) | ~48K | Vector + graph memory layer |
| [getzep/graphiti](https://github.com/getzep/graphiti) | ~24K | Temporal knowledge graph engine |
| [letta-ai/letta](https://github.com/letta-ai/letta) | ~21K | Stateful agent runtime (MemGPT) |
| [topoteretes/cognee](https://github.com/topoteretes/cognee) | ~12K | Knowledge engine for agent memory |
| [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) | Large | Graph-enhanced RAG (EMNLP 2025) |
| [FalkorDB/FalkorDB](https://github.com/FalkorDB/FalkorDB) | Large | GraphBLAS-based graph DB for AI |
| [memgraph/memgraph](https://github.com/memgraph/memgraph) | Large | In-memory graph DB |
| [gregorydickson/memory-graph](https://github.com/gregorydickson/memory-graph) | Growing | MCP memory server (SQLite/Neo4j/Memgraph) |
| [vanzan01/cursor-memory-bank](https://github.com/vanzan01/cursor-memory-bank) | Growing | Cursor persistent memory framework |
| [yangyihe0305-droid/memgraph-agent](https://github.com/yangyihe0305-droid/memgraph-agent) | New | Graph-powered agent memory, zero LLM cost |

### Academic Papers

| Paper | ID | Key Finding |
|---|---|---|
| Zep: Temporal KG for Agent Memory | arxiv 2501.13956 | 18.5% accuracy gain, 90% latency reduction |
| Mem0: Scalable Long-Term Memory | arxiv 2504.19413 | 91% lower p95 latency, 90%+ token savings |
| Mem0 vs Graphiti Efficiency | arxiv 2601.07978 | Mem0 more efficient; accuracy not significantly different |
| Hindsight: Retain, Recall, Reflect | arxiv 2512.12818 | 91.4% LongMemEval, 83.6% with open 20B model |
| MemoriesDB: Temporal-Semantic-Relational | arxiv 2511.06179 | Unified time-meaning-relation architecture |
| LightRAG: Simple and Fast RAG | arxiv 2410.05779 | Dual-level graph+vector retrieval |
| GraphRAG-Bench | arxiv 2506.02404 | Full pipeline evaluation benchmark |
| Vibe Coding Experience Report | arxiv 2603.11073 | Structured memory + RAG for agent projects |
| Long-Horizon Memory Evaluation | arxiv 2602.22769 | Evaluating agentic memory applications |
| KG Storage Comparison for LLM Agents | arxiv 2506.17001 | Flexible external memory framework |

---

## 8. Recommended Architecture for SignalSpace

Based on this research, here is the refined recommendation for the SignalSpace/AutoBrain project:

### Phase 1: Enhance What Works (Now)

Your current stack (SQLite + ChromaDB + steering files + progress tracker) is solid and proven. Don't rip it out.

**Additions:**
1. **Structured Session Snapshots** — Replace summary-based progress tracking with structured fact nodes (decisions + evidence chains, open threads + next steps, quality metrics)
2. **Beads** — Consider adopting Steve Yegge's git-backed task memory for long-horizon coding tasks. It solves exactly the "50 First Dates" problem you described
3. **MCP Memory Server** — Add `gregorydickson/memory-graph` or `@modelcontextprotocol/server-memory` for cross-session knowledge persistence via MCP

### Phase 2: Add Graph Layer (When Steering Files Break)

**Recommended Graph DB: FalkorDB**
- 496x faster than Neo4j at P99 — critical for MCP tool response times during coding flow
- Graphiti (Zep's engine) officially supports FalkorDB
- Redis-native — simpler ops than Neo4j's JVM stack
- Built for exactly your use case: GraphRAG + agent memory

**Recommended Memory Layer: Graphiti (self-hosted) on FalkorDB**
- Temporal knowledge graph — tracks how facts change over time
- Answers "What did we believe about Pipeline A quality on March 15th?"
- Supports contradiction detection natively via temporal edges
- MCP server available
- Open source (manage FalkorDB yourself, skip Zep Cloud costs)

**Alternative if temporal reasoning isn't critical: Hindsight**
- 91.4% LongMemEval (highest score)
- Embedded PostgreSQL (simpler than managing FalkorDB)
- `reflect` operation for cross-memory synthesis
- MCP-first design

### Phase 3: Scale to Team (3+ Engineers)

- Add **async write queue** for graph updates (Redis or simple message queue)
- Implement **git-hook triggered incremental re-indexing** for vector freshness
- Add **per-engineer steering scopes** in the graph
- Consider **PuppyGraph** as a zero-ETL graph overlay on your existing SQLite/ChromaDB — avoids data migration entirely

### Recommended Stack Summary

| Layer | Choice | Why |
|---|---|---|
| Knowledge Graph | FalkorDB | 496x faster P99, Redis-native, Graphiti-compatible |
| Temporal Memory | Graphiti (self-hosted on FalkorDB) | Best temporal reasoning, open source, MCP server |
| Vector Store | ChromaDB (keep existing) | 74K+ vectors invested, works |
| Structured Store | SQLite (keep existing) | 659+ rows invested, works |
| Task Memory | Beads (optional) | Git-backed, solves context amnesia for coding |
| Embeddings | all-MiniLM-L6-v2 (keep) | Consistent with existing data |
| MCP Interface | Existing tools + Graphiti MCP + memory-graph MCP | Incremental, not a rewrite |
| Indexing | Git-hook triggered incremental | Keeps vectors fresh |

### Key Decision: Zep/Graphiti vs Hindsight

| Factor | Graphiti/FalkorDB | Hindsight |
|---|---|---|
| Temporal reasoning | Best in class | Good (temporal filtering) |
| Benchmark score | 63.8% LongMemEval | 91.4% LongMemEval |
| Infrastructure | FalkorDB + Graphiti | Embedded PostgreSQL |
| Ops complexity | Medium (manage FalkorDB) | Low (one Docker command) |
| Synthesis | No native reflect | Yes (LLM-powered reflect) |
| Graph depth | Deep (full KG) | Lighter (entity graph) |
| Best for | "What was true at time X?" | "What have we learned overall?" |

**For SignalSpace specifically**: Graphiti/FalkorDB is the stronger fit because your ASAM domain requires tracking how standards, decisions, and pipeline quality evolve over time. The temporal reasoning is worth the extra infrastructure.

---

## 9. Sources

### Official Documentation & Products
- [neo4j.com — MCP Integrations](https://neo4j.com/developer/genai-ecosystem/model-context-protocol-mcp/)
- [docs.falkordb.com — Agentic Memory](https://docs.falkordb.com/agentic-memory/)
- [memgraph.com — Memgraph 3](https://memgraph.com/blog/memgraph-3-graph-database-llm-context-problem)
- [puppygraph.com](https://puppygraph.com/)
- [help.getzep.com — Graphiti](https://help.getzep.com/v2/graphiti/getting-started/overview)
- [blog.getzep.com — Temporal KG](https://blog.getzep.com/zep-a-temporal-knowledge-graph-architecture-for-agent-memory/)
- [mem0.ai](https://mem0.ai/)
- [letta.com](https://www.letta.com/blog/our-next-phase)
- [cognee.ai](https://cognee.ai/)
- [hindsight.vectorize.io](https://hindsight.vectorize.io/blog/2026/03/23/agent-memory-benchmark)
- [mnemos.making-minds.ai](https://mnemos.making-minds.ai/)
- [turso.tech/blog/agentfs](https://turso.tech/blog/agentfs)

### Comparison & Analysis Articles
- [vectorize.io — Best AI Agent Memory Systems 2026](https://vectorize.io/articles/best-ai-agent-memory-systems)
- [vectorize.io — Mem0 vs Zep](https://vectorize.io/articles/mem0-vs-zep)
- [vectorize.io — Hindsight vs Zep](https://vectorize.io/articles/hindsight-vs-zep)
- [vectorize.io — Zep vs Cognee](https://vectorize.io/articles/zep-vs-cognee)
- [vectorize.io — Hindsight vs Letta](https://vectorize.io/articles/hindsight-vs-letta)
- [puppygraph.com — FalkorDB vs Neo4j](https://www.puppygraph.com/blog/falkordb-vs-neo4j)
- [puppygraph.com — Memgraph vs Neo4j](https://www.puppygraph.com/blog/memgraph-vs-neo4j)
- [arcadedb.com — Neo4j Alternatives 2026](https://arcadedb.com/blog/neo4j-alternatives-in-2026-a-fair-look-at-the-open-source-options/)
- [pingcap.com — Best Database for AI Agents 2026](https://www.pingcap.com/compare/best-database-for-ai-agents/)
- [sparkco.ai — AI Agent Memory 2026](https://sparkco.ai/blog/ai-agent-memory-in-2026-comparing-rag-vector-stores-and-graph-based-approaches)
- [sparkco.ai — PAG vs MEMORY.md vs SQLite](https://sparkco.ai/blog/persistent-memory-for-ai-agents-comparing-pag-memorymd-and-sqlite-approaches)
- [digitalapplied.com — AI Agent Memory Complete Guide](https://www.digitalapplied.com/blog/ai-agent-memory-systems-complete-guide)
- [machinelearningmastery.com — 6 Best Memory Frameworks 2026](https://machinelearningmastery.com/the-6-best-ai-agent-memory-frameworks-you-should-try-in-2026/)
- [getmaxim.ai — Comparing Agent Memory Architectures](https://www.getmaxim.ai/articles/comparing-agent-memory-architectures-vector-dbs-graph-dbs-and-hybrid-approaches/)

### Blog Posts & Tutorials
- [blog.dailydoseofds.com — FalkorDB 496x Faster](https://blog.dailydoseofds.com/p/graph-dbs-vs-falkordb)
- [blog.getzep.com — Graphiti FalkorDB Support](https://blog.getzep.com/graphiti-knowledge-graphs-falkordb-support/)
- [orchestrator.dev — FalkorDB for AI](https://orchestrator.dev/blog/2025-12-11-falkordb)
- [abisheklakandri.com — Persistent AI Memory Claude Code](https://abisheklakandri.com/blog/persistent-ai-memory-claude-code-graphiti)
- [steve-yegge.medium.com — Introducing Beads](https://steve-yegge.medium.com/introducing-beads-a-coding-agent-memory-system-637d7d92514a)
- [blogs.oracle.com — Agent Memory](https://blogs.oracle.com/developers/agent-memory-why-your-ai-has-amnesia-and-how-to-fix-it)
- [ai.plainenglish.io — Beyond Context Graphs](https://ai.plainenglish.io/beyond-context-graphs-why-2026-must-be-the-year-of-agentic-memory-causality-and-explainability-db43632dbdee)
- [pento.ai — A Year of MCP](https://www.pento.ai/blog/a-year-of-mcp-2025-review)
- [muhammadraza.me — Local Memory for Coding Agents](https://muhammadraza.me/2026/building-local-memory-for-coding-agents/)
- [blogs.cisco.com — Persistent Memory Compromise](https://blogs.cisco.com/ai/identifying-and-remediating-a-persistent-memory-compromise-in-claude-code)

### Academic Papers (arxiv)
- [arxiv 2501.13956](https://arxiv.org/abs/2501.13956) — Zep: Temporal KG for Agent Memory
- [arxiv 2504.19413](https://arxiv.org/html/2504.19413) — Mem0: Scalable Long-Term Memory
- [arxiv 2601.07978](https://arxiv.org/html/2601.07978v2) — Mem0 vs Graphiti Cost/Accuracy
- [arxiv 2512.12818](https://arxiv.org/html/2512.12818v1) — Hindsight: Retain, Recall, Reflect
- [arxiv 2511.06179](https://arxiv.org/html/2511.06179v1) — MemoriesDB: Temporal-Semantic-Relational
- [arxiv 2410.05779](https://arxiv.org/html/2410.05779) — LightRAG
- [arxiv 2506.02404](https://arxiv.org/abs/2506.02404) — GraphRAG-Bench
- [arxiv 2603.11073](https://arxiv.org/html/2603.11073v1) — Vibe Coding Experience Report
- [arxiv 2602.22769](https://arxiv.org/html/2602.22769v2) — Long-Horizon Memory Evaluation
- [arxiv 2506.17001](https://arxiv.org/html/2506.17001v2) — KG Storage Comparison for LLM Agents

### GitHub Repositories
- [github.com/FalkorDB/FalkorDB](https://github.com/FalkorDB/FalkorDB)
- [github.com/memgraph/memgraph](https://github.com/memgraph/memgraph)
- [github.com/HKUDS/LightRAG](https://github.com/HKUDS/LightRAG)
- [github.com/letta-ai/letta](https://github.com/letta-ai/letta)
- [github.com/topoteretes/cognee](https://github.com/topoteretes/cognee)
- [github.com/steveyegge/beads](https://github.com/steveyegge/beads)
- [github.com/gregorydickson/memory-graph](https://github.com/gregorydickson/memory-graph)
- [github.com/vanzan01/cursor-memory-bank](https://github.com/vanzan01/cursor-memory-bank)
- [github.com/yangyihe0305-droid/memgraph-agent](https://github.com/yangyihe0305-droid/memgraph-agent)
- [github.com/kuzudb/kuzu (archived)](https://github.com/kuzudb/kuzu)
- [github.com/phidatahq/phidata](https://github.com/phidatahq/phidata)

### Community Discussions
- [news.ycombinator.com — Memory-Graph MCP](https://news.ycombinator.com/item?id=46091577)
- [gitlab.com — Graph DB Vendor Analysis](https://gitlab.com/gitlab-org/rust/knowledge-graph/-/work_items/254)
- [theregister.com — KuzuDB Abandoned](https://www.theregister.com/2025/10/14/kuzudb_abandoned/)
- [csoonline.com — Dark Side of Vibe Coding](https://www.csoonline.com/article/4053635/when-ai-nukes-your-database-the-dark-side-of-vibe-coding.html)

---

*Research compiled April 2, 2026. Content was rephrased for compliance with licensing restrictions. All data points sourced from publicly available articles, documentation, and academic papers.*


---

## Appendix A: Patterns Validated from Gemini Cross-Reference

> A second research paper (`research/Gemini Research Paper.md`) was generated by Gemini for the same architecture question, without ASAM/AutoBrain domain context. Its ~84 citations all pointed to internal Bosch Docupedia/SharePoint URLs (not publicly verifiable), and it missed the entire 2026 agent memory ecosystem (Zep, Mem0, Hindsight, Letta, FalkorDB, MCP, Beads). However, four architectural patterns from that paper were validated against independent public sources and are worth incorporating.
- **~5 URLs** point to `vertexaisearch.cloud.google.com/grounding-api-redirect/` — these are Vertex AI Search grounding redirects. Some resolve to real pages (e.g., one redirected to LangChain Zep docs), but the URLs themselves are opaque tokens, not stable citations.
### Pattern 1: Bitemporal Entity-State Separation for Graph Memory

The Gemini paper proposed a bitemporal model where every piece of information tracks two timelines: valid time (when the event actually occurred) and transaction time (when it was recorded in the agent's memory). This is implemented via an Entity-State Separation pattern.

**How it works:**
- Immutable Entity Nodes represent stable identities (e.g., a function, a requirement, a pipeline)
- Mutable State Nodes capture changing attributes (source code, quality grade, configuration)
- Versioned Relationships connect entities to states with four timestamps

```cypher
// Immutable entity
(:Pipeline {id: 'pipeline_a'})

// State at a point in time
(:PipelineState {grade: 'B-C', hallucination_rate: '7-15%', known_facts: '6/6'})

// Versioned relationship
-[r:HAS_STATE {
  validFrom: date('2026-03-15'),   // when this became true in reality
  validTo: NULL,                    // NULL = still current
  txFrom: datetime(),               // when recorded in the graph
  txTo: NULL                        // NULL = not yet superseded
}]->

// Historical time-slice query: "What was Pipeline A's state on March 1st?"
MATCH (:Pipeline {id: 'pipeline_a'})-[r:HAS_STATE]->(ps:PipelineState)
WHERE r.validFrom <= date('2026-03-01')
  AND (r.validTo > date('2026-03-01') OR r.validTo IS NULL)
RETURN ps.grade, ps.hallucination_rate
```

**Why this matters for SignalSpace:** This pattern directly solves the "what did we believe about Pipeline A quality on March 15th?" question. When a state changes, the old state isn't deleted — the relationship is invalidated by setting `validTo` and `txTo`, and a new state node is created. This preserves a complete, auditable history without data loss.

**Relationship to Zep/Graphiti:** Graphiti already implements temporal edges with `valid_from`, `valid_to`, and `invalid_at` markers natively. The Entity-State Separation pattern is a more granular implementation of the same concept that could be layered on top of Graphiti/FalkorDB for domain-specific entities like ASAM requirements and pipeline states.

**Validated by:**
- Neo4j official docs on versioning and temporal traversal: [neo4j.com/docs/getting-started/data-modeling/versioning](https://www.neo4j.com/docs/getting-started/data-modeling/versioning/)
- Neo4j community discussion on bitemporal modeling with millions of nodes: [community.neo4j.com/t/bitemporal-modeling](https://community.neo4j.com/t/bitemporal-modeling-with-millions-of-nodes-vm-stop-the-world/60184)
- "2D-Historization in a graph database" — detailed walkthrough of immutable entity + mutable state + timestamped relationships: [realfiction.net](https://realfiction.net/posts/2d-historization-in-a-graph-database)
- Springer paper: "Towards an Efficient Approach to Manage Graph Data Evolution" — enriches basic graphs with states and instances: [springer.com](https://link.springer.com/content/pdf/10.1007/978-3-030-75018-3_31)
- Bitemporal modeling overview (emergentmind): dual-temporal framework using valid and transaction times with interval algebra: [emergentmind.com](https://www.emergentmind.com/topics/bitemporal-modeling)
- Software Patterns Lexicon — Versioned Graphs pattern: [softwarepatternslexicon.com](https://softwarepatternslexicon.com/bitemporal-modeling/versioning-patterns/versioned-graphs/)
- Software Patterns Lexicon — Time Slice Query pattern: [softwarepatternslexicon.com](https://softwarepatternslexicon.com/bitemporal-modeling/time-travel-queries/time-slice-query/)
- AnyShift blog: "Building a Temporal Infrastructure Knowledge Graph" — real production experience with Neo4j temporal patterns at scale: [anyshift.io](https://anyshift.io/blog/building-temporal-infrastructure-knowledge-graph-neo4j)

---

### Pattern 2: Hierarchical Graph with Community Summaries (GraphRAG)

The Gemini paper described a three-layer hierarchical graph structure inspired by Microsoft's GraphRAG. This is a well-documented, production-proven pattern.

**The three layers:**
1. **Episodic Layer (Raw Data):** Ground truth — raw events, code changes, interaction history. Never summarized, never lossy. In our architecture, this is the existing SQLite + ChromaDB data.
2. **Structural/Semantic Layer (Full Graph):** Extracted code graph (ASTs, dependencies), ASAM standards graph, vectorized entities and relationships. This is the working layer agents query most often.
3. **Community Summary Layer (Global View):** Using community detection algorithms (Leiden clustering), the system identifies densely connected clusters in the graph. An LLM generates a summary for each community. These summaries enable scalable "global search" without traversing the entire graph.

**How Microsoft GraphRAG implements this:**
- Stage 1 (Indexing): LLM extracts entities and relationships from source documents → builds knowledge graph → runs Leiden community detection → generates hierarchical community summaries
- Stage 2 (Querying): Three search modes — Local Search (entity-focused), Global Search (community summaries via map-reduce), and Drift Search (hybrid)

**Why this matters for SignalSpace:** As the ASAM knowledge base grows (currently 74K+ vectors, 659+ rows), flat retrieval will degrade. Community summaries provide scalable abstractions — an agent can first identify which "community" (e.g., XCP protocol cluster, MDF file format cluster, UDS diagnostics cluster) is relevant, then drill into specific entities.

**Validated by:**
- Microsoft Research: "From Local to Global: A Graph RAG Approach to Query-Focused Summarization" (arxiv 2404.16130) — the foundational paper: [arxiv.org](https://arxiv.org/html/2404.16130v1)
- Microsoft Research blog: "GraphRAG: New tool for complex data discovery now on GitHub": [microsoft.com](https://www.microsoft.com/en-us/research/blog/graphrag-new-tool-for-complex-data-discovery-now-on-github/)
- Microsoft Research blog: "GraphRAG: Improving global search via dynamic community selection": [microsoft.com](https://www.microsoft.com/en-us/research/blog/graphrag-improving-global-search-via-dynamic-community-selection/)
- Microsoft GraphRAG official docs — community hierarchy output schema: [microsoft.github.io/graphrag](https://microsoft.github.io/graphrag/index/outputs/)
- Deep GraphRAG (arxiv 2601.11144): "A balanced approach to hierarchical retrieval and adaptive integration" — extends GraphRAG with reinforcement learning for retrieval optimization: [arxiv.org](https://arxiv.org/html/2601.11144)
- Core-based Hierarchies for Efficient GraphRAG (arxiv 2603.05207): proposes core-based decomposition as alternative to Leiden clustering for better hierarchy quality: [arxiv.org](https://arxiv.org/html/2603.05207v1)
- Memgraph blog: "How Would Microsoft GraphRAG Work Alongside a Graph Database?" — practical integration guide: [memgraph.com](https://memgraph.com/blog/how-microsoft-graphrag-works-with-graph-databases)
- Bertelsmann tech blog: "How Microsoft GraphRAG Works Step-By-Step" — detailed walkthrough of indexing and querying: [tech.bertelsmann.com](https://tech.bertelsmann.com/en/blog/articles/how-microsoft-graphrag-works-step-by-step-part-12)
- Critique: "Why GraphRAG Needs a Better Backbone Than Leiden Clustering" (2026) — argues Leiden has limitations for certain graph structures: [sariyuce.com](https://sariyuce.com/blog/2026/GraphRAG/)

---

### Pattern 3: Global-to-Local Retrieval Pipeline

The Gemini paper described a multi-stage retrieval process that moves from broad to narrow. This is the standard GraphRAG query pattern, already partially covered in our Section 3, but worth formalizing.

**The pipeline:**
1. **Global Search (Map Step):** Query high-level community summaries to identify relevant clusters. This answers "which area of the knowledge base is relevant?" without scanning everything.
2. **Local Search (Reduce Step):** Within the identified clusters, run hybrid search — vector similarity for semantic matching + graph traversal for structural context. The vector search finds semantically similar nodes; a Cypher/Gremlin query then traverses from those nodes to collect connected context.
3. **Reranking:** Combined results are reranked for relevance and diversity before being passed to the LLM.
4. **Construction:** Top-ranked nodes and relationships are synthesized into structured context for the LLM prompt.

**SignalSpace application:** When an agent asks "What are the known issues with our XCP implementation?", the pipeline would:
1. Global: Identify the XCP protocol community in the graph
2. Local: Vector search for "known issues" + graph traversal from XCP entities to related error codes, test results, and decision nodes
3. Rerank: Ensure both spec-level facts and implementation-level observations are included
4. Construct: Build a structured context block for the LLM

**Validated by:**
- Microsoft GraphRAG paper (arxiv 2404.16130) — defines the Local/Global/Drift search modes: [arxiv.org](https://arxiv.org/html/2404.16130v1)
- Deep GraphRAG (arxiv 2601.11144) — formalizes the global-to-local hierarchy: [arxiv.org](https://arxiv.org/html/2601.11144)
- PuppyGraph blog: "GraphRAG Architecture — Components, Workflow & Implementation Guide": [puppygraph.com](https://www.puppygraph.com/blog/graphrag-architecture)
- ToPG (arxiv 2601.04859): "A Navigational Approach for Comprehensive RAG via Traversal over Proposition Graphs" — implements Naive/Local/Global operational modes: [arxiv.org](https://arxiv.org/html/2601.04859)

---

### Pattern 4: MMR (Maximal Marginal Relevance) Reranking

The Gemini paper recommended MMR for reranking retrieval results. MMR balances relevance (how well a result matches the query) with diversity (how different it is from already-selected results). This prevents the common failure mode where all top results are near-duplicates of each other.

**Why this matters for SignalSpace:** When retrieving context about an ASAM protocol, you want both the rigid spec definition AND a stylistically relevant code example AND a related decision from the progress tracker — not three slightly different phrasings of the same spec paragraph. MMR ensures diversity in the retrieved context.

**Implementation:** In LangChain/LlamaIndex, set `search_type="mmr"` and tune `fetch_k` (initial candidate pool size) and `lambda_mult` (0 = max diversity, 1 = max relevance). Hindsight's cross-encoder reranker achieves a similar effect through its multi-strategy approach.

**Nuance from research:** A 2024 study (arxiv 2404.01037) found that MMR and Cohere rerank "did not exhibit notable advantages over a baseline Naive RAG system" in some configurations, while LLM reranking and HyDE significantly enhanced precision. This suggests MMR is useful but not a silver bullet — cross-encoder reranking (as used by Hindsight) may be more robust.

**Validated by:**
- Original MMR paper concept widely implemented in LangChain, LlamaIndex, and Zep (confirmed via Vertex AI redirect to LangChain Zep docs)
- arxiv 2404.01037: "Advanced RAG Output Grading" — found MMR less effective than LLM reranking in some scenarios: [arxiv.org](https://ar5iv.labs.arxiv.org/html/2404.01037)
- arxiv 2407.04573: "Rethinking Similarity and Diversity for Retrieval in LLMs" — notes MMR parameter sensitivity issues: [arxiv.org](https://arxiv.org/html/2407.04573v2)
- arxiv 2504.07104: "Scaling RAG Systems With Inference-Time Compute Via Multi-Criteria Reranking" — argues for multi-criteria approaches beyond pure relevance: [arxiv.org](https://arxiv.org/html/2504.07104)
- Towards Data Science: "RAG Explained: Reranking for Better Answers" — practical overview of reranking strategies: [towardsdatascience.com](https://towardsdatascience.com/rag-explained-reranking-for-better-answers/)

---

*Research compiled April 2, 2026. Content was rephrased for compliance with licensing restrictions. All data points sourced from publicly available articles, documentation, and academic papers.*
