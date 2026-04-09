# Loom System — Design Decisions & Background Context

> This document captures all design decisions, engineer feedback, architectural reasoning,
> and open questions from the Loom system design conversations (April 2-3, 2026).
> This is the single source of truth for WHY decisions were made.

---

## 1. Project Identity

- **Project Name**: Loom
- **What it is**: A modular system for AI-assisted automotive software development
- **What it solves**: Domain knowledge gaps, context rot, memory loss, and fidelity degradation when engineers use AI coding agents for ASAM/AUTOSAR development
- **Who uses it**: 2-3 engineers initially, scaling to 10+. Mixed IDEs (Claude Code, Kiro, Cursor, VS Code, Antigravity)
- **Platform**: Engineers primarily on Windows laptops. Admin (Jerry) on MacBook Pro.

---

## 2. The Three Problems

### Problem 1: AI Memory Syndrome (AMS)
AI coding agents lose fidelity after extended multi-session work. The butterfly effect:
- Agent hallucinates slightly during "summarize your chat"
- After multiple chat sessions, that small hallucination compounds
- Initial intent gets lost, steering commands get summarized away
- Architecture decisions silently change
- After 20+ sessions, the agent is working on a different project than what was specified

This is NOT a domain knowledge problem. This is a session memory problem.

### Problem 2: Domain Knowledge Gap
LLMs have shallow knowledge of ASAM/AUTOSAR standards. They hallucinate protocol details,
invent error codes, and guess at timing constraints. The existing SignalSpace/AutoBrain
project has already solved the ingestion side (4 pipelines, 385K+ vectors) but the current
SQLite + ChromaDB setup lacks relationship awareness — you can find similar text but can't
traverse "which standard constrains which module."

### Problem 3: No Orchestration Discipline
Without enforcement, agents skip the research step and hallucinate protocol details.
There's no workflow that forces: look up standards → check memory → draft → verify → output.
Engineers manually remind agents to check the database, which is error-prone.

---

## 3. The Modular Architecture

The system is NOT one monolithic tool. It's a stack of purpose-built modules:

```
┌─────────────────────────────────────────────────────┐
│                Engineer's IDE                        │
│   (Claude Code / Kiro / Cursor / VS Code / etc)      │
└──────────────────────┬──────────────────────────────┘
                       │ MCP (single entry point)
┌──────────────────────▼──────────────────────────────┐
│      LangGraph Orchestrator (Phase 1 — required)     │
│   Routes queries to the right module automatically    │
│   Enforces: Research → Memory → Draft → Verify        │
│   Exposed as single MCP server to all IDEs            │
└───────┬──────────────┬──────────────┬───────────────┘
        │              │              │
   Tool │         Tool │         Tool │
        ▼              ▼              ▼
┌──────────────┐ ┌───────────┐ ┌──────────────┐
│ Loom         │ │ AMS       │ │ CMM          │
│ (FalkorDB)   │ │ Solver    │ │ (codebase-   │
│              │ │(Hindsight │ │  memory-mcp) │
│ ASAM/AUTOSAR │ │ or other) │ │              │
│ Knowledge    │ │           │ │ Code         │
│ Graph        │ │ Per-eng.  │ │ Structure    │
│              │ │ session   │ │ (tree-sitter │
│ Centralized  │ │ memory    │ │  + SQLite)   │
│ Admin-write  │ │ Local     │ │              │
│ Team-read    │ │ Windows   │ │ Per-repo     │
└──────────────┘ └───────────┘ └──────────────┘
```

### Decision: LangGraph is Phase 1, not Phase 3
Originally LangGraph was planned as Phase 3. Engineer feedback changed this:
- Without LangGraph, engineers must manually juggle 3+ MCP servers
- LangGraph acts as the single MCP entry point that routes internally
- This solves the "MCP routing problem" — engineers talk to one server, it calls the right tools
- LangGraph also enforces the compliance workflow (research before coding)

### Decision: AMS is solved by existing open-source, not built from scratch
The AMS layer (Hindsight or alternative) is an existing tool we integrate, not something we build.
Candidates evaluated:
- Hindsight (91.4% LongMemEval, MCP-first, Docker, retain/recall/reflect)
- claude-mem (Claude Code only — too narrow)
- MCP Memory Keeper (simple key-value — too basic)
- Engram (SQLite + FTS5, agent-agnostic — good fallback)
- Beads (task tracking, not session memory — complementary)

### Decision: CMM is a bolt-on, zero build effort
codebase-memory-mcp is a single static binary. Install it, point it at the repo, done.
It gives agents structural code awareness (call graphs, dependencies, impact analysis).
It does NOT solve AMS or domain knowledge — it's purely code structure.

---

## 4. Module Details

### Module: Loom (Automotive Knowledge Graph)

**What it is**: Centralized graph database consolidating all ASAM + AUTOSAR domain knowledge.

**Current state (being migrated)**:
- Pipeline A (asam-db): Mistral OCR → azrouter. 570 rows, 3,194 vectors, 64 files
- Pipeline B (docling): Docling + Apple MLX VLM. 2,009 tables, 70,892 vectors, 39 PDFs
- Fusion AB (ASAMKnowledgeDB): Kimi-K2.5 merge. 659 rows, 74,086 vectors
- VirtualECU/AUTOSAR: 127 rows, 310,686 vectors, 9,477 docs (AUTOSAR CP, ASAM MCD3MC, XIL, FMI, SSP, DCP, FIBEX, OSI)

**Target**: Single FalkorDB graph database with:
- Property graph schema (Standard, Requirement, Protocol, Parameter, Table, ErrorCode, Command nodes)
- Typed edges (DEFINES, CONSTRAINS, REFERENCES, PART_OF, SUPERSEDES)
- Vector embeddings (all-MiniLM-L6-v2) for hybrid graph+vector retrieval
- Bitemporal model (validFrom/validTo/txFrom/txTo on all state relationships)
- Hierarchical community summaries (Leiden clustering) for scalable global search
- Full provenance on every fact (source doc, page, pipeline, confidence)

**Why FalkorDB over Neo4j**:
- 496x faster at P99 latency (benchmarked)
- 6x better memory efficiency
- Redis-native (simpler ops than Neo4j's JVM)
- Graphiti officially supports it
- Runs in Docker with configurable RAM cap

**Access control**:
- Admin (Jerry Chen) writes/updates knowledge
- Engineers read-only via MCP/REST
- Future: mechanism for engineers to flag corrections (see Issue 4 below)

**Deployment**:
- Phase 1: Docker on Jerry's MacBook Pro
- Phase 1 alt: Ship as Docker image to engineer laptops
- Future: Azure Container Services, accessible to whole company

### Module: AMS Solver (Agent Memory)

**What it is**: Per-engineer local memory system that prevents context rot and fidelity loss.

**Key requirements**:
- Runs locally on engineer's Windows laptop
- Captures session state automatically at wrap-up
- Extracts structured facts (decisions, steering commands, bugs, architecture changes)
- Stores raw transcripts for audit
- Provides compact resumption context for new sessions
- Steering commands are PERMANENT — never summarized away
- Must track relationships between chat sessions with IDs
- Engineers work on multiple projects, sessions span days
- Must maintain "main objective" thread across scattered sessions

**Session ID and relationship tracking** (critical for AMS):
- Each chat session gets a unique session_id
- Sessions are linked to a project_id (the thing being built/fixed)
- Sessions are linked to an objective_id (the goal being pursued)
- When an engineer starts a new chat about the same issue, the AMS links it to the same objective
- This prevents the "agent forgets what we're actually trying to do" problem
- The objective carries: original intent, active steering commands, key decisions, current status

**Top candidate**: Hindsight (91.4% LongMemEval, MCP-first, Docker)
**Fallback**: Engram (SQLite + FTS5, agent-agnostic, lighter weight)

### Module: CMM (Codebase Memory MCP)

**What it is**: Single static binary that indexes codebases into a structural knowledge graph.
**What it does**: AST parsing (66 languages), call graphs, dependency tracking, impact analysis, dead code detection.
**Install**: `curl -fsSL ... | bash` — done.
**No build effort required.**

### Module: LangGraph Orchestrator

**What it is**: Python state machine that routes queries and enforces engineering discipline.
**Exposed as**: Single MCP server (the only one engineers need to configure)
**Internally calls**: Loom, AMS Solver, CMM as tools
**Workflow**: Research Standards → Check Memory → Draft → Verify Compliance → Output
**HITL**: If compliance check fails, pauses and asks engineer

---

## 5. Open Design Issues & Decisions

### Issue 1: MCP Routing (RESOLVED)
**Problem**: Multiple MCP servers means engineers must know which tool to call.
**Decision**: LangGraph is Phase 1 (not Phase 3). It acts as the single MCP entry point.
Engineers configure one MCP server. LangGraph routes internally to Loom, AMS, CMM.

### Issue 2: Ongoing Ingestion Pipeline for Loom (OPEN)
**Problem**: Migration is one-time. But new standards documents need to be ingested going forward.
**Decision needed**: Build a new "load into graph" step that takes Mistral OCR / Docling output and creates nodes/edges in FalkorDB.
**Current thinking**: Reuse existing extraction pipelines (they work), add a new graph-loading stage.

### Issue 3: Feedback Loop — AMS to Loom (IMPORTANT)
**Problem**: When an engineer discovers something during coding (e.g., "the XCP spec says X but actual behavior is Y"), that discovery lives in the AMS layer. It should eventually flow into Loom so all engineers benefit.
**Engineer feedback**:
- AMS sits locally on engineer's Windows laptop
- Engineers work on multiple projects, sessions span days
- AMS needs session IDs and objective IDs to maintain relationships
- Main objectives must not get lost across scattered sessions
- This feedback loop (local discovery → shared knowledge) is Phase 2/3

**Design implication**: AMS data model must support:
- session_id (unique per chat)
- project_id (what's being built)
- objective_id (what goal is being pursued)
- Links between sessions pursuing the same objective
- Tagging facts as "local discovery" vs "confirmed knowledge"
- Future: promotion mechanism from AMS → Loom

### Issue 4: Engineer Corrections to Loom (IMPORTANT)
**Problem**: Multiple scenarios where Loom's knowledge needs updating:
1. Engineer wants to add new standards/docs
2. Engineer finds incorrect data in existing docs
3. Agent references wrong section of documentation
4. Engineer corrects the agent — how does this correction flow back to Loom?

**Engineer feedback**: "How do I know if engineers want to add new standards, find issues with incorrect docs, or when an agent references a wrong section and the engineer corrects it?"

**Design implication**:
- Loom needs a "correction queue" — engineers can flag issues but not directly edit
- Admin reviews and approves corrections before they enter the knowledge graph
- Agent corrections captured in AMS should be taggable as "knowledge correction"
- Future: automated detection of repeated corrections → auto-flag for admin review
- Versioning: when a correction is applied, old data is invalidated (bitemporal model), not deleted

### Issue 5: Knowledge Graph Versioning (DECIDED)
**Problem**: Standards get updated. Extractions can be wrong. Need to re-ingest without corruption.
**Decision**: Bitemporal model handles this natively:
- Old facts get validTo/txTo timestamps set (invalidated, not deleted)
- New facts get new validFrom/txFrom timestamps
- Full history preserved for audit
- Re-ingestion creates new state nodes, old ones remain queryable by time

### Issue 6: Offline/Disconnected Mode (DEFERRED)
**Decision**: Not addressing in Phase 1. Loom runs locally in Docker during Phase 1 anyway.
When Loom moves to cloud (Phase 2+), revisit.

---

## 6. Build Phases

### Phase 1: Loom + LangGraph Orchestrator
- Migrate 4 existing databases into FalkorDB graph
- Build MCP server for Loom (query, search, provenance)
- Build LangGraph orchestrator as single MCP entry point
- Build ongoing ingestion pipeline (new docs → graph)
- Docker Compose for local development
- **Deliverable**: Engineer can ask "What are the XCP timing constraints?" through any IDE and get a cited answer from the graph

### Phase 2: AMS Integration
- Evaluate and deploy Hindsight (or alternative) as local per-engineer memory
- Integrate AMS into LangGraph orchestrator as a tool
- Implement session_id / project_id / objective_id tracking
- Implement steering command persistence
- **Deliverable**: Engineer can resume work after 50+ chat clears with full fidelity

### Phase 3: CMM + Feedback Loop
- Install CMM (zero build effort)
- Integrate CMM into LangGraph orchestrator
- Build correction queue (engineer flags → admin reviews → Loom updates)
- Build AMS → Loom promotion mechanism (local discoveries → shared knowledge)
- **Deliverable**: Full stack operational, corrections flow back to knowledge graph

### Phase 4: Team Scaling
- Move Loom to Azure Container Services
- Federate local AMS databases into shared team knowledge layer
- Scale to 10+ concurrent engineers
- Role-based access control
- **Deliverable**: Team-wide deployment with shared knowledge and isolated progress

---

## 7. Technology Stack (Final)

| Component | Technology | Role |
|---|---|---|
| Knowledge Graph | FalkorDB (Redis module, Docker) | Loom — ASAM/AUTOSAR domain knowledge |
| Temporal Engine | Graphiti (on FalkorDB) | Bitemporal fact tracking, contradiction detection |
| Vector Embeddings | all-MiniLM-L6-v2 | Hybrid graph+vector retrieval |
| AMS Solver | Hindsight (or Engram fallback) | Per-engineer session memory, context rot prevention |
| Code Structure | codebase-memory-mcp (binary) | AST-based code knowledge graph |
| Orchestrator | LangGraph (Python) | Single MCP entry point, workflow enforcement |
| MCP Server | FastMCP (Python) | Protocol layer for all IDE connections |
| REST API | FastAPI (Python) | Non-MCP access for custom tooling |
| Local Storage | SQLite | AMS local per-engineer database |
| Deployment | Docker Compose | Local dev + Azure Container Services production |
| Language | Python 3.11+ | All custom code |

---

## 8. Key Numbers

### Existing Data (to migrate into Loom)
- Total vectors: ~385,000+ across 4 pipelines
- Total documents: ~10,000+
- Total structured rows: ~1,400+
- Standards covered: ASAM XCP, MDF, ODX, AUTOSAR CP, ASAM MCD3MC, XIL, FMI, SSP, DCP, FIBEX, OSI
- Known data quality issues: `protocol_parameters` loosely structured, `uds_nrc_codes` empty, `odx_file_types` has some hallucinated entries

### Performance Targets
- Knowledge retrieval: < 2 seconds
- Context cost reduction: 60%+ vs full-context
- Session continuity: 100% accuracy on initial constraints after unlimited chat clears
- FalkorDB RAM budget: 4GB (configurable) for local dev

### Benchmark References
- Hindsight: 91.4% LongMemEval (highest)
- Zep/Graphiti: 63.8% LongMemEval
- FalkorDB: 496x faster than Neo4j at P99
- MCP ecosystem: 13,000+ servers, industry standard

---

## 9. Vibe Coding Lessons Applied

From `archived/Mastering Vibe Coding_ A Framework for AI Development Optimization.md`:

| Lesson | How Loom Addresses It |
|---|---|
| Context Rot | AMS layer captures structured facts, provides resumption context |
| Summary Compression (Lost Details) | Steering commands stored as permanent constraints, never summarized |
| Mockup Shell Trap | Loom provides real domain knowledge so agents don't hallucinate placeholders |
| Lazy LLM Syndrome | LangGraph forces research step before coding — agent must cite sources |
| Components Built in Isolation | LangGraph compliance loop verifies integration before output |
| Zero-Skip Policy | Enforced via steering files + LangGraph verification node |
| Plan-Implement-Run | AMS tracks progress across sessions, LangGraph enforces workflow |

---

## 10. References

- `research/agentic_memory_architecture_2026.md` — comprehensive research (732 lines)
- `research/Gemini Research Paper.md` — Gemini's analysis (evaluated, partially incorporated)
- `research/geminiSpec.md` — Gemini's LangGraph spec (evaluated, architecture concepts kept)
- `archived/Mastering Vibe Coding_ A Framework for AI Development Optimization.md` — lessons learned
- `.kiro/steering/signalspace-core.md` — legacy project rules (ARCHIVED)
- `.kiro/steering/loom-core.md` — active Loom steering
- `.kiro/steering/loom-progress.md` — active Loom progress tracker
- `.kiro/specs/aaems-system-architecture/requirements.md` — formal requirements (needs update to reflect modular architecture)

---

## 11. Conversation Log — Design Refinement (April 3, 2026)

### Creator Identity
- **Jerry Chen** (chj1ana) — creator of the Loom system and all SignalSpace/AutoBrain work.

### Jerry's Original Problem Statement (verbatim)
> "I need another database for keeping track of the coding progress due to context window used up
> and then agent has to compress and summary the chat into new chat, i found out after certain
> amount of chat sessions, we lost fidelity, initial intent, minor details and small hallucination
> became big or part of the major requirement items. so I want to avoid that, when i use claude code,
> i have steering files, skills and progress tracker files. and i want to use a database combined
> with what you said above to have a comprehensive coding set up for me and for others."

> "Engineer A needs to start a project but it requires deep technical knowledge of automotive ASAM
> standard, LLM model can do some shallow coding but doesn't have the domain knowledge. Then he
> would use one of the above database to ingest all standards, examples, and background. Then
> connect that database as MCP to VS code, Kiro, or Claude or any coding agent to start the spec
> session. During spec session the agent will use MCP to call background info and combine with
> engineer A's input and requirements to produce requirement, design and tasks list. Then during
> development to execute task by coding agents, those agents will also use MCP to look up info on
> the database. But also every time a chat session is wrapped up, progress will be recorded into a
> progress database, any interaction between engineer and agents will be recorded too for debug,
> and if engineer is trying to steer AI coding agent to fix or steer the direction, these will not
> get lost from chat context window filled up."

### Jerry's Modular Architecture Clarification
> "We are not solving all of these problems with one tool. I'm looking at the problem with different
> layers and modules. Agent memory layer, to solve AMS issue, instead of building our own, we can
> use Hindsight or something else. Second part, automotive knowledge, the Loom part, we already
> have vector DB locally, but we need to migrate to a more efficient and better context awareness
> for AI to look up domain knowledge, hence we switch to graph database. And then lastly there is
> a whole framework, I believe LangGraph can put it all together."

### Issue 1 Resolution: LangGraph as Phase 1
- Jerry decided LangGraph should be Phase 1 (not Phase 3)
- Reason: solves MCP routing problem — engineers configure one server, not three
- Risk acknowledged: LangGraph on critical path. Mitigation: build Loom MCP standalone first, wrap with LangGraph after

### Issue 3 Resolution: AMS Dual Purpose + Feedback Loop
Jerry's vision for AMS:
> "AMS system serves dual purpose. Like a mini brain to bigger Loom brain. AMS belongs to the
> engineers. First batch of users will get AMS as a system with just my coding experience with
> coding agent, retaining memory and a set of steerings for coding agent. Then as users kept
> using AMS, this becomes engineer's digital twin who understands engineer's better. Like a
> second brain. Who is just not tracking projects, dev sessions, context, spec sessions that
> evolves but also feed back into my main design."

Kiro's feedback on this:
- Digital twin concept is real and achievable — AMS learning engineer patterns works
- Knowledge correction dump flowing back to Loom is tricky (Wikipedia editing problem)
- At 2-3 engineers, admin review works. At 10+, admin becomes bottleneck
- Recommendation: ship minimal AMS template (hard rules only), let engineers evolve organically
- Pull common patterns from everyone's AMS into shared template over time (bottom-up, not top-down)

Jerry's response:
> "Shelf the knowledge correction dump for now. But leave a placeholder in the design so we can
> revisit when I chat with others."

### Issue 4 Resolution: Three Correction Types
Kiro proposed splitting corrections into three types:
1. `data_quality` — fact is wrong in source document → triggers re-ingestion
2. `retrieval_quality` — agent cited wrong section → retrieval tuning needed
3. `practical_knowledge` — spec says X but real behavior is Y → new "practical notes" layer

Jerry agreed with the approach. Implementation shelved for later phases.

Design implication: Loom graph needs a "practical notes" layer that sits alongside authoritative spec data, clearly tagged as experiential. Agents present both: "The ASAM spec says X (source: MCD-1 page 47). Note: Engineer A reported that in practice, Y (source: session 2026-03-15)."

### AMS Session Tracking Requirements (from Jerry)
- Engineers primarily on Windows laptops
- Engineers work on multiple projects simultaneously
- Sessions span across multiple days and multiple chat sessions
- AMS needs IDs to create relationships between chats and sessions
- Main objectives must not get lost across scattered sessions
- session_id (unique per chat), project_id (what's being built), objective_id (goal being pursued)

### Windows Testing Note
Engineers primarily on Windows. Docker on Windows (WSL2) historically flakier than Mac/Linux.
Decision: test full Docker Compose stack on Windows early in Phase 1.

### Steering File Changes
- `.kiro/steering/signalspace-core.md` → changed to `inclusion: manual` (ARCHIVED)
- `.kiro/steering/progress-tracker.md` → marked as ARCHIVED in title
- `.kiro/steering/loom-core.md` → CREATED, `inclusion: always` (ACTIVE)
- `.kiro/steering/loom-progress.md` → CREATED, `inclusion: manual` (ACTIVE)

---

*Document updated April 3, 2026. This is a living document — update as decisions evolve.*


### CMM as Development Tool (Added April 3, 2026)

Jerry requested that CMM (codebase-memory-mcp) be used during Loom development itself, not just as a bolt-on for end users. CMM v0.5.7 has been downloaded, installed, and indexed against the AutoBrain repo.

**Index results**: 604 nodes, 830 edges, 29 Python files indexed in 262ms. The `.cbmignore` file excludes FromMarc/, virtualECU/, archived/, vector stores, and binary files to keep the index focused on actual code.

**CMM capabilities available during development**:
- `search_graph` — find functions, classes, variables by name pattern
- `trace_call_path` — who calls what, up to 5 hops deep
- `detect_changes` — map git diff to affected symbols with risk classification
- `query_graph` — Cypher-like queries against the code graph
- `get_architecture` — codebase overview (languages, packages, routes, hotspots)
- `get_code_snippet` — read source by qualified name
- `search_code` — grep-like text search within indexed files
- `manage_adr` — Architecture Decision Records that persist across sessions

**CLI usage**: `loom/plugins/codebase-memory-mcp/codebase-memory-mcp cli <tool> '<json_args>'`

**Decision**: CMM will be used during Loom development for:
1. Understanding existing code structure before modifying it
2. Impact analysis when changing shared modules (lookup.py, db_setup.py, server.py)
3. Tracking call chains across the migration pipeline
4. Storing ADRs for architectural decisions made during development
