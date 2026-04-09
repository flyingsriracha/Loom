---
inclusion: manual
---

# Progress Tracker — Loom

Last updated: 2026-04-08

## Current Task
All non-WSL Loom runtime work remains complete locally. Parallel demo work under `demo/` is still a validated static marketing prototype with 3 interactive slides, benchmark-backed KPI claims, and defensible comparison cards.
The first novice-facing Loom portal slice is now implemented. The orchestrator exposes normalized traceability and dashboard aggregation endpoints, and `loom-portal/` provides a working Next.js shell for onboarding, explain-this-answer traces, and development-journey views.
Next focus: refine the portal UX, add optional LangSmith instrumentation, run live browser validation against the local Loom stack, then return to broader deployment polish and Windows WSL2 validation.

## Status
- Research: COMPLETE — `research/agentic_memory_architecture_2026.md`
- Design decisions doc: ACTIVE source of why — `research/loom_system_design_decisions.md`
- Steering: `loom-core.md` ACTIVE, `loom-progress.md` ACTIVE
- Requirements: UPDATED — now includes novice onboarding, unified traceability UX, development journey dashboard, external integrations, and a separate Loom portal surface
- Design doc: UPDATED — now adds Loom portal architecture, portal-first UX principles, aggregation API direction, and traceability/journey read models alongside the existing runtime design
- Tasks doc: UPDATED — phased full-development plan now includes a new workstream for portal onboarding, explain-this-answer UX, journey dashboard, deep links, and optional LangSmith instrumentation
- Runtime foundation: LIVE — `falkordb`, `loom-services`, and `orchestrator` containers are up and healthy
- Python environment: READY — `loom/.venv` created and dependencies installed, including `graphiti-core[falkordb]`
- Graphiti smoke script: PASSING — bootstrap and live JSON episode ingestion both work against FalkorDB
- Azure OpenAI path: WORKING — GPT-5.4 requires `AZURE_OPENAI_API_VERSION=2025-03-01-preview` or later, plus a local wrapper to handle deployment-name reasoning detection and Azure structured-response token accounting
- FalkorDB client layer: IMPLEMENTED — connection management, retries, graph selection, query helper, and health checks are now in `loom/graph/client.py`
- Graphiti adapter layer: IMPLEMENTED — production adapter now includes Azure compatibility wrapper plus latest-API search compatibility (`group_ids` on Graphiti 0.28.2, legacy fallback retained)
- Graph schema bootstrap: IMPLEMENTED — idempotent schema bootstrap routines now enforce unique `id` constraints across domain/audit labels and align `TextChunk.embedding` to 384-d imported vectors
- Curated-source scanner foundation: IMPLEMENTED — SQLite scan/profiling and seed report scaffolding now exist for `ASAMKnowledgeDB` and `autosar-fusion` in `loom/migration/`
- Schema blocker: RESOLVED — switched bootstrap from Cypher-only constraint syntax to native FalkorDB graph APIs (`create_node_unique_constraint`, vector index helpers), validated live
- Deterministic migration foundation: IMPLEMENTED — `loom/migration/deterministic_migration.py` now provides complete curated-table coverage, canonical field normalization, semantic anchor edges, and provenance links through source document and source pipeline
- Loom admin migration APIs: IMPLEMENTED — added `/admin/migration/structured/plan` and `/admin/migration/structured/run` endpoints
- MigrationRun + AuditEvent model: IMPLEMENTED — each structured migration now writes run metadata and per-table audit events to FalkorDB
- Live structured migration execution: UPDATED — clean full-table runs now cover expanded mappings (ASAM structured: 673 nodes; AUTOSAR structured: 1783 nodes) with reconciliation support
- ASAM reference migration: COMPLETE — `docling_tables` imported as reference-layer nodes (`1956`)
- ASAM audit migration: COMPLETE — `fusion_log` + `comparison_report` imported as audit-layer nodes (`223`)
- ASAM vector migration: COMPLETE — direct Chroma collection import created `74086` `TextChunk` nodes with real 384-d embeddings and provenance links
- AUTOSAR structured migration: COMPLETE — expanded structured deterministic mappings are live (`1783` nodes)
- AUTOSAR reference migration: COMPLETE — `docling_tables` plus `research_papers` imported as reference-layer context (`31619` total rows)
- AUTOSAR audit migration: COMPLETE — `fusion_log` + `comparison_report` imported as audit-layer nodes (`3157`)
- AUTOSAR vector migration: COMPLETE — full Chroma collection import created `310686` `TextChunk` nodes with real 384-d embeddings and provenance links
- AUTOSAR reconciliation: COMPLETE — zero non-zero deltas across structured/reference/audit mappings
- Phase 1 seed checkpoint validation: COMPLETE — live reruns verified reconciliation, embeddings, uniqueness constraints, and provenance coverage for ASAM and AUTOSAR
- Reconciliation reporting: IMPLEMENTED — per-table source-vs-graph delta output is now returned in migration reports
- Provenance resolution services: IMPLEMENTED — `/api/v1/node/{id}` and `/api/v1/node/{id}/provenance` resolve evidence chains through source document, source pipeline, source system, and migration runs
- Provenance-filtered search: IMPLEMENTED — `/api/v1/search` and `/api/v1/query` now support source-system, source-pipeline, and confidence filters
- Service auth boundary: IMPLEMENTED — engineer/admin API-key roles plus request-context propagation are now live for service operations, with local-dev bypass when keys are unset
- Artifact context route: IMPLEMENTED — `/api/v1/artifact/context` now returns artifact-scoped guidance for requirements/design/tasks workflows
- Service diagnostics: IMPLEMENTED — `/api/v1/diagnostics` exposes graph counts, cache state, auth status, and provider configuration hints
- Incremental ingestion baseline: IMPLEMENTED — `ingestion/loader.py`, `validation.py`, `graph_loader.py`, and `/api/v1/ingest` / `/api/v1/ingest/validate` now accept supplementary PDFs/text/structured files and load them into Loom with provenance
- Supplementary AUTOSAR ingest flow: IMPLEMENTED — live smoke test verified supplementary AUTOSAR JSON ingest, retrieval visibility, and cleanup
- Orchestrator foundation: IMPLEMENTED — request classification, LangGraph workflow routing, structured errors, and JSONL audit logging are now live in `loom/orchestrator/`
- Orchestrator REST API: IMPLEMENTED — `/api/v1/ask`, direct knowledge/code proxy routes, memory placeholders, and spec-session entry routes are now exposed with API-key auth
- Baseline CMM integration: IMPLEMENTED — orchestrator can invoke `codebase-memory-mcp` via CLI bridge, expose direct code-query flows, and surface CMM availability/index warnings; Dockerized orchestrator now reports explicit `cmm_host_native_only` guidance because container packaging still does not include a Linux-ready binary/index state
- FastMCP entrypoint: IMPLEMENTED — `loom/orchestrator/mcp_server.py` now exposes the orchestrator over stdio/MCP with direct ask, knowledge, code, resume, and spec-session tools
- Graphiti live benchmark: IMPLEMENTED — Azure GPT-5.4 mini with `2025-03-01-preview` plus local MiniLM embedder fallback now runs sequential `add_episode` benchmarks (~52s total latest run) and focused temporal smoke checks; Loom now accepts sequential provider-backed ingestion as the supported Azure path while full `add_episode_bulk` remains upstream-incompatible
- Graphiti temporal smoke: IMPLEMENTED — provider-backed `retrieve_episodes` and `graphiti_search` were validated on a fresh temporal benchmark group
- Docker persistence: IMPLEMENTED — append-only FalkorDB persistence is now enabled locally and survives container restart for new writes
- Spec-session artifact lineage: IMPLEMENTED — graph-backed `Artifact` / `ArtifactRevision` storage plus `SUPPORTED_BY` and `REVISED_FROM` links are now live
- Spec-session generation/update/audit: IMPLEMENTED — live REST and MCP flows now render grounded artifact drafts, persist revisions, and expose audit retrieval
- Temporal state layer: IMPLEMENTED — `graph/temporal.py` now manages `HAS_STATE` edges plus `validFrom`/`validTo` and `txFrom`/`txTo`, with `744` live state edges bootstrapped
- Time-sliced query API: IMPLEMENTED — `/api/v1/temporal/query` resolves active state by valid/transaction time
- GraphRAG baseline: IMPLEMENTED — retrieval pipeline now combines cached community search, local graph matches, vector `TextChunk` retrieval, MMR reranking, and evidence-chain assembly
- Community summaries: IMPLEMENTED — Leiden communities now persist to Graphiti-native `:Community` nodes in FalkorDB, with `loom/artifacts/community_cache.json` retained as backup/export artifact
- Source-pipeline provenance layer: COMPLETE — `SourcePipeline`, `EXTRACTED_BY`, `BELONGS_TO`, and `PROVENANCE` edges are now populated live
- Section 3 (ASAM migration): COMPLETE — structured + reference + audit + vector imports are now live, with reconciliation validated at zero delta for mapped tables
- Foundational test coverage: EXPANDED — client, adapter, schema/bootstrap, deterministic migration, provenance, temporal, retrieval, service API, orchestrator, MCP entrypoint, artifact lineage, ingestion, scanner, identity, and vector-import helpers are covered by unit tests (`52` passing)
- Property-based test baseline: IMPLEMENTED — Hypothesis coverage now validates stable IDs, chunking bounds, routing, and reranker invariants (`4` property tests passing)
- Docker integration coverage: IMPLEMENTED — live container tests now validate service/orchestrator health, metrics, audit export, AMS memory routes, AMS promotion/correction review, bundled project seeding, and spec-session flows (`8` integration tests passing on the latest rerun)
- Retrieval evaluation suite: IMPLEMENTED — `loom/evals/retrieval_eval.py` records AUTOSAR/ASAM hit behavior and zero-result guarding; the latest rerun passed all `3/3` cases
- Spec-session evaluation suite: IMPLEMENTED — `loom/evals/spec_session_eval.py` records generate/update/audit revision behavior; the latest rerun passed with `12` revisions recorded
- Hindsight Phase 2 baseline: IMPLEMENTED — live Hindsight container runs with Azure router for LLMs plus local BAAI embeddings; AMS `retain`, `recall`, `reflect`, `resume`, `memory/promote`, and bundled `memory/seed` are revalidated on the live stack
- Phase 2 continuity layer: COMPLETE — `project_id` propagates through HTTP/MCP and downstream services, transcript references are retained alongside structured memories, and `resume` returns a token-budgeted prioritized session snapshot
- AMS evaluation suite: IMPLEMENTED — `loom/evals/ams_eval.py` validates project-id propagation, transcript-reference capture, budgeted resume sections, compact seeding, and continuity recall (`all checks passed`)
- Correction queue and practical notes: IMPLEMENTED — graph-backed `CorrectionItem` review flows, `PracticalNote` creation/retrieval, federation export, and provenance wiring are now live
- AMS-to-Loom promotion: IMPLEMENTED — orchestrator HTTP/MCP promotion flows now convert AMS recall output into correction-queue submissions for admin review
- Expanded CMM workflows: IMPLEMENTED — `detect_changes` is now exposed through orchestrator HTTP/MCP and included in coding-task workflows when repo-change impact is relevant
- Deployment packaging: IMPLEMENTED — `.env.azure.example`, `docker-compose.azure.yml`, and deployment/operations runbooks now define the Azure-oriented handoff path
- Production auth hardening: IMPLEMENTED — `LOOM_DEPLOYMENT_ENV`, `LOOM_ALLOW_LOCAL_DEV_BYPASS`, and fail-closed auth behavior now support production-style runs without local bypass
- Observability and audit export: IMPLEMENTED — Prometheus-style `/api/v1/metrics`, request IDs, `/admin/audit/export`, and `/admin/federation/export` are now live
- Concurrent load validation: COMPLETE — `loom/evals/load_eval.py` now validates `10` concurrent engineer sessions; the final warm-start run passed with `p95` latency about `21.69 ms`
- Phase 1 local validation rerun: COMPLETE — the full non-WSL stack now passes Docker integration, retrieval/spec-session/AMS evals, and load validation; checkpoint `14.5` remains open only for Windows WSL2
- Central AI runtime config: IMPLEMENTED — `.kiro/runtime/ai-runtime.env` now centralizes Azure GPT, Azure embeddings, Azure router, and Hindsight runtime settings
- Demo prototype: UPDATED — `demo/` now contains a validated static Loom marketing/demo page with a 3-slide carousel (4th slide hidden), animated Knowledge Foundation graph scene, rebuilt IDE demos for ETAS ETK / XCP / A2L and AUTOSAR Classic workflows. Product naming: "FalkorDB" -> "Knowledge Foundation", "Hindsight" -> "AMS System". Problem/solution carousel with 7 engineer pain points. Comparison section added with 3 USP cards validated against real benchmarks
- Demo KPIs: VALIDATED — `loom/evals/kpi_eval.py` benchmarks retrieval speed (5.7x vs SQLite, 1.8x vs Chroma) and token efficiency (81% reduction vs raw chunks); results exported to `loom/artifacts/kpi_eval_results.json`
- Traceability tooling: IMPLEMENTED — `loom/tools/trace_knowledge.py` CLI provides debuggable retrieval with full provenance chain visualization
- Portal UX direction: IMPLEMENTED (initial slice) — Loom now has a separate `loom-portal/` app on top of the orchestrator and knowledge services, with deep-link-first integrations for FalkorDB UI, Hindsight, LangSmith, LangGraph, and any future CMM-native UI
- Portal aggregation API: IMPLEMENTED — orchestrator now exposes `/api/v1/trace/explain`, `/api/v1/dashboard/overview`, `/api/v1/dashboard/journey`, and `/api/v1/integrations/links`
- Portal validation: COMPLETE (initial) — orchestrator unit tests pass with the new routes, and `loom-portal` passes `npm run lint` plus `npm run build`
- LangSmith instrumentation: IMPLEMENTED (optional) — orchestrator workflows, portal aggregation, client/tool boundaries, and Graphiti Azure/OpenAI wrappers now emit LangSmith traces when `LANGSMITH_TRACING` and `LANGSMITH_API_KEY` are configured
- Portal live smoke: COMPLETE (initial) — local orchestrator on `127.0.0.1:8081` and portal dev server on `127.0.0.1:3001` were exercised successfully; trace and overview endpoints returned live data from the current code
- Portal browser validation: COMPLETE — guided examples, explicit connect/apply flow, trace rendering, metric refresh, and timeline updates were validated in a live browser session; remaining hydration warning is a dev-only browser-tool artifact
- Demo release gate: UPDATED — slide 4 (CMM + AMS) is intentionally hidden from carousel controls for Vercel deployment until narrative/design is finalized
- Graph restore on corrected volume: COMPLETE — full curated graph was restored after fixing the FalkorDB data mount and currently reports `39411` mapped nodes, `384763` vector nodes, `744` state edges, and `26` community nodes
- Local persistence root-cause fixed: COMPLETE — FalkorDB volume now mounts to `/var/lib/falkordb/data`, and append-only persistence survives restart for new writes
- Foundational tests: IMPLEMENTED — unit tests for schema bootstrap skip behavior and curated-source scanner profile loading now exist in `loom/tests/`
- CMM evaluation: COMPLETE — complementary tool, not a replacement
- AMS landscape scan: COMPLETE — Hindsight top candidate

## Architecture (Decided)
- Loom is an internal product for standards research, spec-session authoring, and development execution.
- Core modules:
  1. Loom (FalkorDB + Graphiti) — centralized ASAM/AUTOSAR knowledge graph
  2. AMS Solver (Hindsight or alt) — local per-engineer session memory
  3. LangGraph Orchestrator — single MCP entry point and workflow enforcement
  4. CMM (codebase-memory-mcp) — code structure awareness bolt-on
- Phase 1 seed migration uses two curated fused source systems:
  - `tools/ASAMKnowledgeDB`
  - `tools/autosar-fusion`
- Preserve upstream provenance from `mistral_azrouter`, `docling_kimi25`, `virtualECU_text_ingestion`, and `cleanup_fix`
- Supplementary raw docs remain future ingestion scope, not part of the seed migration
- Spec-session artifact generation and lineage are first-class design requirements
- Seed migration remains deterministic for curated structured data; bulk vector stores stay separate from Graphiti episode extraction

## Build Phases
- Phase 1: foundation, FalkorDB + Graphiti migration, retrieval, orchestrator, baseline CMM, spec-session workflows
- Phase 2: AMS integration (Hindsight) + session/objective/transcript continuity
- Phase 3: correction queue + practical notes + AMS→Loom promotion + expanded CMM workflows
- Phase 4: Azure deployment + federation + scaling + operational hardening

## Key Decisions
- Creator: Jerry Chen (chj1ana)
- FalkorDB over Neo4j
- Graphiti is required, not optional
- LangGraph is Phase 1, not Phase 3
- AMS uses existing open-source (Hindsight preferred), not built from scratch
- Engineers primarily on Windows; Docker/WSL2 must be tested early
- Loom is the internal product going forward, not just a bootstrap project
- Spec-session support is first-class: Loom should help produce and maintain `requirements.md`, `design.md`, and `tasks.md`
- Correction queue and practical-notes layer are now implemented for shared operational knowledge capture and admin-reviewed promotion
- Offline mode: DEFERRED
- Local development auth for FalkorDB is still intentionally disabled; credential hardening remains a later task

## Existing Data (Phase 1 Seed Sources)
- `tools/ASAMKnowledgeDB` — final ASAM fused SQLite + vector source
- `tools/autosar-fusion` — final AUTOSAR fused SQLite + vector source
- Raw supplementary AUTOSAR and other source files can be ingested later through the incremental pipeline

## Blockers
- Windows Docker (WSL2) validation is still pending, so checkpoint `14.5` is only locally satisfied today

## Next Steps
1. Refine the `loom-portal/` UX so onboarding, trace details, and journey summaries feel production-ready rather than scaffold-level
2. Add richer portal-level explanations and friendlier deep-link labels for novice users before external demos
3. Rebuild or redeploy the containerized orchestrator so the new portal endpoints are available on the primary runtime port, not only the local dev instance
4. Polish `demo/` copy, branding, and presentation details before public presentation or Vercel preview handoff
5. Decide whether checkpoint `14.5` is acceptable as local-complete pending WSL2, or leave Phase 1 formally open until Windows validation is run
6. If containerized CMM becomes a requirement, package a Linux binary plus repo/index state instead of relying on the host-native CLI

## Technical Corrections

### ETK Communication Architecture Fix (2026-04-09)
**Issue**: Demo incorrectly stated "XCP over CAN" as an option for ETK communication.
**Root Cause**: AI hallucination — no ETK entries existed in the knowledge foundation. The claim was fabricated without verification.
**Correction**:
- ETK connects via **debug interfaces** (DAP/JTAG/proprietary), NOT CAN
- ETK provides **XCP-over-Ethernet** to measurement tools (INCA)
- XCP-over-CAN is a separate architecture requiring XCP driver in ECU code
**Files Updated**: `demo/script.js`, `demo/DEMO_SCENARIOS_BACKGROUND.md`
**Source**: ASAM MCD-1 XCP documentation, Vector VX1000 product pages

### ETK Knowledge Added to Loom FalkorDB (2026-04-09)
**Added Nodes**:
- `ETK` (Protocol) — ETAS Emulator Test Kit
- `FETK` (Protocol) — ETAS Fast Emulator Test Kit  
- `VX1000` (Protocol) — Vector measurement hardware

**Status**: Nodes created directly in FalkorDB graph. Semantic search requires embedding generation (happens during standard ingestion). Direct Cypher queries work.

**Verification**:
```cypher
MATCH (p:Protocol) WHERE p.id IN ['ETK', 'FETK', 'VX1000'] RETURN p.id, p.name, p.tool_interface
```

**Note**: Legacy SQLite entry in `/tools/ASAMKnowledgeDB/fused_knowledge.db` should be considered deprecated.
