# Requirements Document — Loom System

## Introduction

Loom is an internal AI-assisted automotive engineering product for standards research, spec-session authoring, development execution, and traceable workflow visibility. It combines a centralized ASAM/AUTOSAR knowledge graph, per-engineer session memory, code structure awareness, and a LangGraph orchestrator that enforces research-before-output discipline. A separate Loom-native product surface will provide novice onboarding, manual traceability tools, and a development journey dashboard on top of those existing services. Phase 1 seeds Loom from two curated fused source systems: `tools/ASAMKnowledgeDB` for ASAM knowledge and `tools/autosar-fusion` for AUTOSAR, virtual ECU, FMI, SSP, DCP, FIBEX, and related knowledge. These curated sources preserve upstream provenance from Mistral OCR, Docling, Kimi-K2.5, and virtualECU ingestion pipelines; they do not imply that every raw file on disk has already been processed. The system is designed for 2-3 engineers initially, scaling to 10+, across heterogeneous IDEs (Claude Code, Kiro, Cursor, VS Code, Antigravity).

## Glossary

- **Loom**: The centralized automotive knowledge graph and standards-grounding layer (FalkorDB + Graphiti) consolidating ASAM and AUTOSAR domain knowledge
- **AMS_Solver**: The per-engineer local memory module (Hindsight or alternative) that prevents context rot and fidelity loss across chat sessions
- **Orchestrator**: The LangGraph state machine acting as the single MCP entry point, routing queries to the correct module
- **CMM**: Codebase Memory MCP — bolt-on static binary providing AST-based code structure awareness
- **FalkorDB**: In-memory Redis-native graph database using GraphBLAS; the graph backend for Loom
- **Graphiti**: Zep's open-source temporal knowledge graph engine on FalkorDB; the required temporal layer for Loom
- **Curated_Source_System**: A final fused SQLite + vector source database used as the Phase 1 system of record for migration into Loom
- **Bitemporal_Model**: Data model tracking valid time and transaction time per fact
- **GraphRAG**: Retrieval combining graph traversal with vector search and community summaries
- **Community_Summary**: LLM-generated summary of a graph cluster for scalable global search
- **Evidence_Chain**: Traceable link from a fact to its source document, page, pipeline, and confidence
- **Spec_Session**: A standards-grounded workflow that produces or updates `requirements.md`, `design.md`, and `tasks.md`
- **Artifact_Lineage**: Traceable chain linking prompt, steering context, retrieved evidence, generated artifact sections, and later revisions
- **Steering_Command**: Permanent engineering directive that must never be summarized away
- **Correction_Queue**: (Placeholder — Phase 3) Engineer-to-admin knowledge correction mechanism
- **Migration_Pipeline**: Process transforming the two Curated_Source_Systems into the Loom graph while preserving upstream extraction and fusion provenance

---

## Module 1: Loom — Automotive Knowledge Graph

### Requirement 1: Knowledge Database Consolidation

**User Story:** As an admin, I want to consolidate the two curated final knowledge source systems into a single FalkorDB graph database, so that all ASAM and AUTOSAR domain knowledge is queryable from one source with preserved provenance, fusion history, and relationships.

#### Acceptance Criteria

1. WHEN the Migration_Pipeline is executed against `tools/ASAMKnowledgeDB`, THE Migration_Pipeline SHALL transform the final fused ASAM source system (659 structured rows, 74,086 vectors, 1,956 raw Docling tables) into graph nodes and edges while preserving `source_pipeline`, `confidence`, `source_file`, `comparison_report`, and `fusion_log` lineage.
2. WHEN the Migration_Pipeline is executed against `tools/autosar-fusion`, THE Migration_Pipeline SHALL transform the final post-cleanup AUTOSAR source system (1,789 structured rows, 310,686 vectors, 31,613 Docling reference tables) into graph nodes and edges while preserving `source_pipeline`, `confidence`, `source_file`, cleanup adjustments, and fusion audit metadata.
3. THE Migration_Pipeline SHALL preserve upstream extraction lineage from `mistral_azrouter`, `docling_kimi25`, `virtualECU_text_ingestion`, `cleanup_fix`, and future approved `user_*` or admin-curated sources.
4. THE Migration_Pipeline SHALL treat the two Curated_Source_Systems as the Phase 1 system of record and SHALL NOT require re-migrating historical pre-fusion SQLite databases to build the initial Loom graph.
5. THE Loom graph SHALL use a property graph schema with typed nodes (Standard, Requirement, Protocol, Parameter, Table, ErrorCode, Command) and typed edges (DEFINES, CONSTRAINS, REFERENCES, PART_OF, SUPERSEDES).
6. THE Loom graph SHALL maintain vector embeddings (all-MiniLM-L6-v2) for all text content nodes to support hybrid graph-plus-vector retrieval.
7. WHEN a migration completes, THE Migration_Pipeline SHALL produce a migration report containing: total nodes created, total edges created, total vectors indexed, records skipped with reasons, per-source row-count reconciliation, and upstream pipeline counts.
8. THE migration report SHALL distinguish curated-source coverage from raw-disk corpus coverage and SHALL NOT imply that all raw predecessor documents have already been processed.

### Requirement 2: Graph Schema and Temporal Model

**User Story:** As an engineer, I want the knowledge graph to model ASAM and AUTOSAR domain relationships explicitly with temporal tracking, so that AI agents can perform multi-hop traversals and understand how knowledge evolves over time.

#### Acceptance Criteria

1. THE Loom graph SHALL use Graphiti as the required temporal knowledge graph engine on top of FalkorDB.
2. THE Bitemporal_Model SHALL be implemented using Graphiti-compatible temporal primitives that preserve `validFrom`, `validTo`, `txFrom`, and `txTo` semantics for Loom state relationships.
3. THE Loom graph SHALL separate immutable entity nodes (stable identities: protocol, standard, module) from mutable state nodes (changing attributes: quality grade, version, configuration).
4. THE Loom graph SHALL support hierarchical community detection using the Leiden clustering algorithm, generating Community_Summary nodes at each hierarchy level.
5. THE Loom graph SHALL enforce that every fact node carries a provenance edge linking it to its source document, extraction pipeline, and extraction timestamp.
6. IF a new fact contradicts an existing fact for the same entity, THEN THE Loom graph SHALL invalidate the old state by setting validTo and txTo timestamps rather than deleting the old state node.
7. THE Loom graph SHALL reserve a "practical_notes" node type (Phase 3 placeholder) for experiential knowledge that supplements but is distinct from authoritative spec data.

### Requirement 3: Knowledge Retrieval via GraphRAG

**User Story:** As an engineer, I want to query the knowledge database using natural language and receive accurate, cited responses, so that AI agents retrieve real ASAM/AUTOSAR data instead of hallucinating protocol details.

#### Acceptance Criteria

1. WHEN a query is submitted, THE Loom graph SHALL execute a Global-to-Local retrieval pipeline: first searching Community_Summary nodes to identify relevant clusters, then performing hybrid vector-plus-graph search within those clusters.
2. WHEN performing local search, THE Loom graph SHALL combine vector similarity results with graph traversal results (up to 3 hops) and rerank using MMR or cross-encoder reranking.
3. THE Loom graph SHALL return query results within 2 seconds.
4. THE Loom graph SHALL include an Evidence_Chain with every returned fact: source document name, page or table reference, extraction pipeline identifier, and confidence score.
5. IF a query matches zero results, THEN the system SHALL return an explicit "no results found" response rather than allowing the agent to fall back to parametric knowledge.
6. WHEN a query involves temporal context, THE Loom graph SHALL filter results using the Bitemporal_Model valid time window.

### Requirement 4: Ongoing Ingestion Pipeline

**User Story:** As an admin, I want to ingest new standards documents into Loom without re-indexing the entire graph, so that the knowledge base stays current as new ASAM/AUTOSAR specs are released.

#### Acceptance Criteria

1. THE Loom system SHALL provide an ingestion command that accepts PDF or structured document input and creates new graph nodes with provenance metadata.
2. THE ingestion pipeline SHALL support incremental addition — new documents are added without requiring a full graph rebuild.
3. THE ingestion pipeline SHALL reuse the existing extraction and validation stack (Mistral OCR, Docling, and Kimi-guided validation or fusion where required), adding a new graph-loading stage that creates FalkorDB nodes and edges.
4. WHEN new nodes are added, THE Loom system SHALL regenerate affected Community_Summary nodes to keep global search current.
5. THE Loom system SHALL support versioning — when a standard is updated, old nodes are invalidated via the Bitemporal_Model, new nodes are created, and both remain queryable by time.
6. THE ingestion pipeline SHALL support future ingestion of supplementary AUTOSAR PDFs and other raw source documents that are not yet represented in the current Curated_Source_Systems, without requiring the Phase 1 seed migration to be rerun from scratch.

### Requirement 5: Data Provenance and Citation

**User Story:** As an engineer, I want every piece of knowledge returned by the system to include a traceable citation, so that AI agents never present uncited ASAM/AUTOSAR data.

#### Acceptance Criteria

1. THE Loom graph SHALL store provenance metadata on every fact node: Curated_Source_System name (`ASAMKnowledgeDB` or `autosar-fusion`), upstream extraction pipeline (`mistral_azrouter`, `docling_kimi25`, `virtualECU_text_ingestion`, `cleanup_fix`, or future approved source), source document filename, page number or section identifier, extraction or cleanup date, and confidence score.
2. WHEN a query result is returned, THE result SHALL include the full Evidence_Chain for each fact.
3. IF a fact node lacks provenance metadata, THEN THE system SHALL flag the node as "unverified" and include a warning in the response.
4. THE Loom graph SHALL support provenance-filtered queries where an engineer can restrict results to a specific Curated_Source_System, source pipeline, or confidence threshold.
5. THE Loom graph SHALL preserve fusion audit artifacts (`comparison_report`, `fusion_log`, and cleanup decisions) as linked audit context for migrated knowledge.

---

## Module 2: AMS Solver — Agent Memory (Integrate, Don't Build)

### Requirement 6: AMS Tool Integration

**User Story:** As an engineer, I want a local memory system that automatically captures session state and prevents context rot, so that my AI coding agent maintains fidelity across unlimited chat sessions without me manually saving progress.

#### Acceptance Criteria

1. THE system SHALL integrate an existing open-source AMS tool (primary candidate: Hindsight; fallback: Engram) rather than building session memory from scratch.
2. THE AMS_Solver SHALL run locally on the engineer's machine (Windows primary, macOS secondary) with no mandatory network dependency.
3. THE AMS_Solver SHALL expose its operations (store, retrieve, search) as tools callable by the Orchestrator via MCP.
4. THE AMS_Solver SHALL automatically capture session state at session wrap-up without requiring manual engineer action.
5. THE AMS_Solver SHALL store Steering_Commands as permanent constraints that are never removed by summarization or compression.
6. THE AMS_Solver SHALL retain raw transcripts or transcript references alongside structured memories so engineers can audit decisions and debug session drift.

### Requirement 7: Session Relationship Tracking

**User Story:** As an engineer working on multiple projects across multiple days and chat sessions, I want the AMS to maintain relationships between sessions pursuing the same objective, so that the main goal doesn't get lost across scattered sessions.

#### Acceptance Criteria

1. THE AMS_Solver SHALL assign a unique session_id to each chat session.
2. THE AMS_Solver SHALL link each session to a project_id (the thing being built or fixed).
3. THE AMS_Solver SHALL link each session to an objective_id (the goal being pursued).
4. WHEN an engineer starts a new chat about the same issue, THE AMS_Solver SHALL link it to the existing objective_id, preserving continuity.
5. THE objective record SHALL carry: original intent, active steering commands, key decisions with evidence, and current status.
6. WHEN a new session begins, THE AMS_Solver SHALL retrieve the most recent state for the relevant objective and present it as resumption context.

### Requirement 8: Session Continuity Across Context Clears

**User Story:** As an engineer, I want my AI agent to resume work with 100% accuracy on initial constraints after any number of chat clears, so that context window limitations do not cause architectural drift or forgotten requirements.

#### Acceptance Criteria

1. WHEN an agent session starts after a context clear, THE AMS_Solver SHALL provide the most recent Session_Snapshot containing all active steering commands, open threads, and recent decisions.
2. THE AMS_Solver SHALL preserve all Steering_Commands across unlimited context clears without degradation, summarization, or lossy compression.
3. THE AMS_Solver SHALL limit resumption context to a configurable token budget (default 2,000 tokens) to prevent context window clogging.
4. IF resumption context exceeds the token budget, THEN THE AMS_Solver SHALL prioritize: (1) active steering commands, (2) open threads with next steps, (3) most recent decisions, truncating oldest decisions first.

### Requirement 9: AMS Template and Evolution

**User Story:** As an admin, I want to seed each engineer's AMS with a minimal template of hard coding rules, so that all engineers start with baseline discipline while their AMS evolves organically to reflect their individual patterns.

#### Acceptance Criteria

1. THE system SHALL provide a minimal AMS template containing only hard rules (Zero-Skip Policy, Plan-Implement-Run, Debug-first, DO NOT GUESS on ASAM data, always cite sources).
2. THE AMS template SHALL NOT impose admin-specific coding patterns or style preferences — engineers' AMS instances evolve organically through use.
3. THE AMS_Solver SHALL support a future "knowledge correction dump" export (Phase 3 placeholder) that extracts structured corrections, patterns, and dos/don'ts for admin review.
4. THE AMS_Solver SHALL support a future federation mode (Phase 3 placeholder) where selected facts from local instances can synchronize to a shared team knowledge layer.
5. THE system SHALL support seeding AMS context from project steering files and progress trackers at project onboarding or session startup.

---

## Module 3: LangGraph Orchestrator — Single Entry Point

### Requirement 10: Orchestrator as Single MCP Server

**User Story:** As an engineer, I want to configure a single MCP server in my IDE that routes my queries to the correct module (Loom, AMS, CMM) automatically, so that I don't need to know which tool to call or manage multiple MCP connections.

#### Acceptance Criteria

1. THE Orchestrator SHALL be exposed as a single MCP server using the JSON-RPC 2.0 protocol, callable from any MCP-compatible IDE.
2. THE Orchestrator SHALL internally route queries to Loom (knowledge), AMS_Solver (memory), and CMM (code structure) based on query classification.
3. THE Orchestrator SHALL support both local transport (stdio) for single-machine development and authenticated remote transport (HTTP/SSE) for networked access.
4. THE Orchestrator SHALL log every tool invocation with timestamp, engineer identifier, tool name, and request parameters for audit purposes.
5. WHEN an MCP tool call fails, THE Orchestrator SHALL return a structured error response containing an error code, human-readable message, and the original request parameters.
6. THE Orchestrator SHALL pass `engineer_id`, `session_id`, and `objective_id` to downstream modules when available so memory, audit, and artifact lineage remain connected.

### Requirement 11: Engineering Workflow Enforcement

**User Story:** As an admin, I want the orchestrator to enforce a research-before-output workflow, so that AI agents always consult domain knowledge, session memory, and code structure before generating automotive artifacts or code.

#### Acceptance Criteria

1. THE Orchestrator SHALL implement a LangGraph state machine with the workflow: Research Standards (Loom) → Check Memory (AMS_Solver) → Inspect Code Context (CMM when codebase work is requested) → Draft → Verify Compliance → Output.
2. IF the Research Standards node returns zero results for a domain-specific query, THE Orchestrator SHALL halt and request human input rather than allowing the agent to proceed with parametric knowledge.
3. IF the Verify Compliance node identifies a conflict between generated code and a retrieved standard, THE Orchestrator SHALL pause and request human intervention via the MCP interface (Human-in-the-Loop).
4. THE Orchestrator SHALL pass the Loom Evidence_Chain through to the final output so that every code generation response includes citations to the standards that informed it.
5. WHEN the request involves code implementation or impact analysis, THE Orchestrator SHALL consult CMM before Draft.
6. WHEN the request is a Spec_Session task, THE Orchestrator SHALL ground generated output in Loom citations and active steering or memory context.

### Requirement 12: REST API Interface

**User Story:** As an engineer using a non-MCP client or custom tooling, I want to access the same operations via REST API, so that the system is accessible regardless of IDE.

#### Acceptance Criteria

1. THE Orchestrator SHALL expose all Loom query operations, Spec_Session artifact generation or update operations, and AMS_Solver read or write operations as equivalent HTTP endpoints via FastAPI.
2. THE REST_API SHALL require authentication via API key for all operations.
3. THE REST_API SHALL enforce role-based access control: read-only for engineers on Loom, write access for admin on Loom, full access for each engineer on their own AMS_Solver instance.

---

## Module 4: CMM — Code Structure Awareness (Bolt-On)

### Requirement 13: CMM Integration

**User Story:** As an engineer, I want my AI coding agent to understand the structural relationships in my codebase (call graphs, dependencies, impact analysis), so that it can reason about code changes without reading every file.

#### Acceptance Criteria

1. THE system SHALL integrate codebase-memory-mcp (CMM) as a bolt-on module requiring zero custom build effort — install the pre-built binary and configure as an MCP server.
2. THE CMM SHALL be registered as a tool within the Orchestrator so that code structure queries and coding-task workflows are routed automatically.
3. THE CMM SHALL provide at minimum: code indexing, call graph traversal, impact analysis (git diff → affected symbols), and structural search.
4. THE CMM SHALL operate independently of Loom and AMS_Solver — it has no dependency on the knowledge graph or session memory.

---

## Cross-Cutting Requirements

### Requirement 14: Containerized Deployment

**User Story:** As an admin, I want the system to run in Docker containers, so that it can be developed locally and deployed to Azure Container Services without environment-specific changes.

#### Acceptance Criteria

1. THE system SHALL provide a Docker Compose configuration that starts FalkorDB, Graphiti-enabled Loom services, the Orchestrator, and the REST API with a single command.
2. THE system SHALL configure FalkorDB with a configurable RAM cap (default 4GB) for local development.
3. THE system SHALL use environment variables for all deployment-specific configuration with no hardcoded values.
4. THE system SHALL provide a production Docker Compose override targeting Azure Container Services.
5. WHEN a container crashes, THE system SHALL persist all FalkorDB data via Redis AOF/snapshotting to a mounted volume.
6. THE system SHALL expose health check endpoints for each service container.
7. THE system SHALL be tested on Windows (WSL2) Docker early in Phase 1 to validate cross-platform compatibility.

### Requirement 15: Multi-Engineer Scaling (Phase 2+)

**User Story:** As an admin, I want to support 2-3 engineers initially scaling to 10+, sharing the centralized Loom knowledge graph while maintaining isolated AMS instances.

#### Acceptance Criteria

1. THE Loom graph SHALL support concurrent read access from 10+ simultaneous engineer sessions without query latency exceeding 2 seconds.
2. THE Orchestrator SHALL identify each connected engineer by a unique engineer identifier.
3. THE system SHALL enforce that only the admin role can write to Loom, while all engineers have read access.
4. THE AMS_Solver architecture SHALL support future federation where local instances synchronize selected facts to a shared team layer.

### Requirement 16: Context Cost Reduction

**User Story:** As an engineer, I want the system to reduce context window costs by at least 60% compared to full-context approaches.

#### Acceptance Criteria

1. THE Orchestrator SHALL return only relevant subgraph context rather than loading full documents into the agent's context window.
2. THE AMS_Solver SHALL use structured Session_Snapshots (bounded by token budget) instead of raw transcript replay for session resumption.
3. THE Loom graph SHALL use Community_Summary nodes for global queries, avoiding full graph traversal.
4. WHEN context is returned, THE Orchestrator SHALL report the token count in the response metadata.

### Requirement 17: Knowledge Correction Queue (Phase 3 Placeholder)

**User Story:** As an admin, I want a mechanism for engineers to flag knowledge issues they discover during coding, so that corrections can be reviewed and applied to Loom without contaminating authoritative data.

#### Acceptance Criteria

1. THE system design SHALL reserve a Correction_Queue interface with three correction types: data_quality (wrong fact in source), retrieval_quality (wrong section cited), and practical_knowledge (spec says X but real behavior is Y).
2. THE Correction_Queue SHALL NOT be implemented in Phase 1 or Phase 2 — this is a design placeholder only.
3. WHEN implemented, THE Correction_Queue SHALL require admin approval before any correction enters the Loom graph.
4. WHEN implemented, practical_knowledge corrections SHALL create "practical_notes" nodes in the graph, tagged as experiential and distinct from authoritative spec data.

### Requirement 18: Spec Session Artifact Generation and Traceability

**User Story:** As an engineer starting or refining an automotive project, I want Loom to help create and maintain `requirements.md`, `design.md`, and `tasks.md` artifacts grounded in standards knowledge, steering, and prior decisions, so that spec work stays aligned with implementation across sessions.

#### Acceptance Criteria

1. THE system SHALL support Spec_Session workflows that combine engineer input, Loom retrieval, and AMS steering or memory context to produce or update `requirements.md`, `design.md`, and `tasks.md`.
2. EACH generated artifact section SHALL preserve traceability to the originating `objective_id` and `session_id`, plus applicable Loom Evidence_Chains or engineer-provided references.
3. THE system SHALL store Artifact_Lineage linking prompt or inputs, generated artifacts, subsequent revisions, and key design decisions.
4. WHEN an artifact is revised in a later session, THE AMS_Solver SHALL preserve prior intent, unresolved questions, and key decisions so follow-on sessions do not drift.
5. ENGINEERS SHALL be able to audit why an artifact changed by reviewing linked transcript or transcript-reference, steering context, and cited knowledge sources.

### Requirement 19: Novice Onboarding and Guided Usage

**User Story:** As a first-time user in Cursor, Claude Code, Kiro, VS Code, or a similar IDE, I want Loom to guide me through setup and my first successful workflow, so that I can get value from the system without already understanding MCP internals, traceability jargon, or the underlying module boundaries.

#### Acceptance Criteria

1. THE product SHALL provide a Loom-native onboarding surface that guides a user through IDE selection, authentication setup, API or MCP connectivity checks, and initial request-context setup.
2. THE onboarding flow SHALL include at least one guided example demonstrating knowledge retrieval, memory recall, and code-impact tracing in plain language.
3. THE onboarding surface SHALL explain the meaning of `engineer_id`, `project_id`, `objective_id`, and `session_id` without requiring the user to read implementation documentation first.
4. WHEN a dependency is unavailable or misconfigured, THE onboarding flow SHALL present a plain-language explanation of the failure and the next recommended action.
5. THE onboarding experience SHALL support heterogeneous IDE environments and SHALL NOT assume a single vendor-specific workflow.

### Requirement 20: Unified Traceability UX

**User Story:** As an engineer using Loom output in a real project, I want every answer to expose a single explainable trace view, so that I can trust, verify, and debug what the system did without manually stitching together knowledge citations, memory results, code impact, and orchestrator logs.

#### Acceptance Criteria

1. THE product SHALL provide a normalized `TraceabilityEnvelope` that combines knowledge provenance, AMS trace or recall evidence, CMM code-impact context, orchestrator workflow steps, request context, and audit identifiers.
2. EVERY user-facing answer surfaced through the Loom portal SHALL support an "explain this answer" interaction with answer-first summary text followed by expandable knowledge, memory, code, and workflow sections.
3. IF a subsystem did not contribute to a response, THEN THE traceability view SHALL explicitly mark that subsystem as `not_used` or `unavailable` rather than silently omitting it.
4. THE traceability experience SHALL support both human-readable summaries and machine-readable structured payloads for automation or export.
5. THE traceability surface SHALL preserve stable follow-up identifiers including node IDs, transcript references, audit IDs, artifact revision IDs, `objective_id`, `session_id`, and `project_id` where applicable.

### Requirement 21: Development Journey Dashboard

**User Story:** As an engineer or evaluator during a trial period, I want a dashboard that shows my development journey across sessions, memories, code impact, and artifacts, so that I can quickly understand whether Loom is helping me make progress and where the system influenced the work.

#### Acceptance Criteria

1. THE product SHALL provide a development journey dashboard organized by `project_id` and `objective_id`.
2. THE dashboard SHALL render a timeline of normalized `JourneyEvent` entries including session start or resume, memory retain or recall, knowledge query, code-impact analysis, artifact revision, and human-in-the-loop checkpoint events.
3. EACH journey event SHALL support drill-down into linked provenance, code-impact output, transcript references, artifact lineage, and audit metadata when those details exist.
4. THE dashboard SHALL provide a concise overview of current objective status, open threads, recent decisions, traceability completeness, and recent code-impact findings.
5. THE dashboard SHALL allow a user to understand primary progress without requiring them to inspect raw LangSmith, FalkorDB, Hindsight, or CMM-native UIs.

### Requirement 22: External Tool Integration and Deep Links

**User Story:** As an advanced user or admin, I want Loom to connect me to the native UIs of the underlying systems, so that I can jump from the simple Loom view into deeper inspection tools without losing the context of the answer or workflow I am investigating.

#### Acceptance Criteria

1. THE product SHALL provide context-aware deep links from the Loom portal to FalkorDB UI, LangSmith Studio or Agent Server surfaces, Hindsight raw views, and any available CMM-native interface.
2. WHEN possible, THE deep-link layer SHALL propagate correlation context such as query text, node ID, audit ID, thread ID, `project_id`, `objective_id`, and `session_id`.
3. THE first implementation SHALL prefer deep links over embedded third-party iframes or panels.
4. IF an external integration is unavailable, unconfigured, or blocked by authentication, THEN the Loom portal SHALL degrade gracefully and describe the missing dependency instead of failing the primary UI flow.
5. LangSmith integration SHALL be optional and SHALL NOT be required for core Loom operation, onboarding, or dashboard usage.

### Requirement 23: Portal Architecture and Manual Traceability Operations

**User Story:** As an admin designing Loom for novice and advanced users, I want a dedicated Loom-native portal on top of the existing services, so that product UX can evolve independently from LangGraph runtime internals while still exposing manual traceability operations for users who need direct inspection.

#### Acceptance Criteria

1. THE product SHALL implement a separate Loom portal web application instead of placing the dashboard inside the LangGraph runtime itself.
2. THE portal SHALL consume existing Loom service and orchestrator APIs as sources of truth and SHALL NOT duplicate retrieval, provenance, memory, or code-impact business logic in the UI tier.
3. THE portal SHALL support progressive disclosure, with plain-language defaults for novice users and deeper technical trace views for advanced users.
4. THE portal SHALL expose manual traceability operations that allow a user to search or inspect by query, node ID, audit ID, artifact revision, `objective_id`, `session_id`, or `project_id`.
5. THE portal SHALL use UI language that explains the workflow in user terms such as `Why this answer`, `What memory was used`, `What code is affected`, and `What happened this week` rather than relying on internal agent jargon.
