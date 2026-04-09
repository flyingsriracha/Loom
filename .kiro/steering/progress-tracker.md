---
inclusion: manual
---

# Progress Tracker — AutoBrain / SignalSpace (ARCHIVED — superseded by loom-progress.md)

Last updated: 2026-04-08

## Latest Loom Snapshot
- This file remains archived for the old SignalSpace / AutoBrain phase.
- Current active tracker is `loom-progress.md`.
- As of 2026-04-08, all non-WSL Loom work is complete locally: Docker integration (`8/8`), retrieval eval (`3/3`), spec-session eval, AMS eval, and load validation all pass on the rebuilt stack.
- Phase 2 continuity is live locally: `project_id` propagates through HTTP/MCP and downstream services, transcript references are retained alongside memory writes, and `resume` returns a token-budgeted prioritized session snapshot.
- Phase 3 is live locally: correction queue, admin review, practical notes, AMS-to-Loom promotion, and federation export are implemented.
- Phase 4 non-WSL delivery is live locally: Azure-oriented deployment packaging, production auth controls, metrics, audit export, runbooks, and load validation are implemented.
- Bundled AMS seeding of `loom-core.md` + `loom-progress.md` completes in about `67s` under a `120s` client timeout and is recallable afterward.
- Sequential `Graphiti.add_episode` is the accepted Azure GPT-5.4 path; `add_episode_bulk` still hits an upstream `max_tokens` incompatibility and is no longer treated as the preferred Loom ingestion path.
- Dockerized CMM remains host-native-only for Phase 1+, but container health reports explicit `cmm_host_native_only` guidance instead of a vague missing-binary state.
- Current live graph target state after restore: `39411` mapped nodes, `384763` vector nodes, `744` temporal state edges, and `26` community nodes.
- Remaining deferred item: Windows WSL2 validation.

## Current Task
Virtual ECU knowledge base text ingestion COMPLETE. PDF ingestion pending.
Fusion v1 complete (Kimi-K2.5). Two-pipeline architecture finalized.
Database optimization complete: FTS5, glossary, extensibility, agent instructions updated.
Pipeline C explored and abandoned (Azure free-tier 1 req/60s impractical for 39 PDFs).

## Status
- Steering system v2.1 established (three-layer + passive dev journey)
- Pipeline A (Mistral/azrouter): v4 complete, grade B–C, 570 rows, 3,194 vectors
- Pipeline B (Docling/MLX): v1 complete, 39 PDFs, 2,009 tables, 70,892 vectors
- Fusion AB (Kimi-K2.5): v1 COMPLETE — all 5 phases done, 659 rows, 74,086 vectors
- Virtual ECU Pipeline: ALL PHASES COMPLETE — 9,477 docs, 310,686 chunks/vectors, 127 structured rows, 32,648 extracted tables, 17 standards
- Virtual ECU PDF ingestion: COMPLETE — 237 PDFs (235 VLM + 2 CPU fallback), 279.3 MB SQLite, 1,268.3 MB ChromaDB
- Self-healing wrapper built: `tools/fusion/run_fusion.sh` (auto-restart, progress tracking)
- Database optimization COMPLETE: FTS5 indexes, domain glossary, extensibility tables, PRAGMA tuning
- Agent instructions v2 COMPLETE: 11 commands documented, zero-knowledge onboarding flow, anti-laziness prompt updated
- Virtual ECU agent instructions COMPLETE: `tools/virtualECU/AGENT_INSTRUCTIONS.md`
- Documentation updated: all docs current
- Pipeline C: explored and abandoned (Azure free-tier rate limits impractical)

## Disk Size Breakdown
| Component | SQLite | Vectors | Other | Total |
|---|---|---|---|---|
| Pipeline A (`tools/asam-db/`) | 13 MB | 103 MB | — | 116 MB |
| Pipeline B (`tools/docling/`) | 25 MB | 243 MB | 1.7 GB venv | ~2 GB |
| Fusion (`tools/fusion/`) | 12.5 MB | 309 MB | — | 322 MB |

Bulk of storage is ChromaDB vector stores (384-dim float arrays + text + HNSW index).
The 1.7 GB in docling is Python packages (PyTorch, MLX), not data.

## Key Decisions
- Core steering budget: <800 tokens (always loaded)
- Domain skills: fileMatch conditional inclusion, <1500 tokens each
- Dev journey (DEV_JOURNEY.md): passive, never loaded by agent
- Milestone sanity checks at every phase boundary
- NO personas in steering or prompts
- Zero-Skip Policy: no placeholders accepted in any implementation
- Plan-Implement-Run: mandatory cycle for all non-trivial tasks
- Rebuild over patching: 3+ patches = scrap and rebuild in fresh session
- Kimi-K2.5 needs high max_tokens (32000) for reasoning before content output
- Elaborate ASAM domain prompts for Kimi (hex codes, block types, reference data)

## Pipeline A — Mistral/azrouter (tools/asam-db/)
- SQLite: 570 rows, 10 structured tables (xcp_commands: 112, xcp_errors: 68, xcp_events: 28, mdf_block_types: 34, protocol_parameters: 291)
- ChromaDB: 3,194 chunks from 64 ingested files (2,596 OCR-fused)
- Claim-level hallucination: 7–15% (varies by random sample; was 94% in v3)
- Known facts: 6/6 (100%)
- Chunk-ID orphans: 0/570 (0%)
- Ingestion: Mistral OCR → page-aligned fusion → structure-aware chunking → azrouter distillation

## Pipeline B — Docling/MLX (tools/docling/)
- 39 PDFs processed, 0 failures, ~8–9 hours on Apple Silicon
- 2,009 tables extracted (markdown + JSON), 70,892 text chunks, 20,431 table rows
- ChromaDB: 70,892 vectors (all-MiniLM-L6-v2)
- Uses GraniteDocling 258M VLM with Apple MLX (MPS device)
- Python venv: `tools/docling/.venv/`

## Fusion Pipeline — Kimi-K2.5 (tools/fusion/)
- Phase 1 (Compare): DONE — 10 tables compared
- Phase 2 (Seed): DONE — 570 rows from Pipeline A as baseline
- Phase 3 (Enrich): DONE — 192 batches, 89 new rows from Docling tables
- Phase 4 (Copy Docling tables): DONE — 1,956 tables copied
- Phase 5 (Merge vectors): DONE — 74,086 fused vectors
- Total: 659 structured rows (570 mistral_azrouter + 89 docling_kimi25)
- Self-healing wrapper: `tools/fusion/run_fusion.sh` (auto-restart on crash)
- Retry logic: 12 attempts, 10s→300s exponential backoff, all errors treated as transient
- Per-batch error handling: failed batches skip and continue, retried on next --resume

### Fused DB Row Breakdown
| Table | Total | From A | From Docling/Kimi |
|---|---|---|---|
| xcp_commands | 144 | 112 | 32 |
| xcp_errors | 68 | 68 | 0 |
| xcp_events | 30 | 28 | 2 |
| mdf_block_types | 66 | 34 | 32 |
| mdf_channel_types | 8 | 7 | 1 |
| mdf_conversion_types | 19 | 7 | 12 |
| uds_nrc_codes | 0 | 0 | 0 |
| odx_file_types | 20 | 12 | 8 |
| odx_compu_categories | 11 | 11 | 0 |
| protocol_parameters | 293 | 291 | 2 |

### Phase 1 Comparison Results
| Table | A quality | B quality | Verdict |
|---|---|---|---|
| xcp_commands | medium | empty | neither (hex conflicts) |
| xcp_errors | low | medium | neither |
| xcp_events | low | empty | neither (bogus hex codes) |
| mdf_block_types | high | low | prefer_a |
| mdf_channel_types | low | empty | neither |
| mdf_conversion_types | low | empty | neither |
| uds_nrc_codes | empty | low | neither |
| odx_file_types | medium | empty | prefer_a (flagged .xml/.cdfx) |
| odx_compu_categories | medium | empty | prefer_a |
| protocol_parameters | high | low | prefer_a |

## Pipeline C — Abandoned
- Scaffolding at `tools/pipeline-c/` (db_setup.py, extract.py, run_extract.sh)
- Tested DeepSeek-V3-0324, Grok-3, Llama-3.3-70B on Azure AI Foundry
- All on free tier: 1 request per 60 seconds — impractical for 39 PDFs
- Would need a paid deployment for production speed
- User decided: "forget it, I'll take what we have"

## Deliverables Created
- `steeringSkill/02_STEERING_SYSTEM_FRAMEWORK.md` — universal framework v2.1
- `steeringSkill/01_RESEARCH_CONTEXT_MANAGEMENT.md` — research compilation
- `steeringSkill/DEV_JOURNEY.md` — passive development history
- `VIBE_CODING_LESSONS_LEARNED.md` — 11 lessons with prompts
- `.kiro/steering/signalspace-core.md` — core steering
- `.kiro/steering/progress-tracker.md` — this file
- `tools/asam-db/GEMINI_ARCHITECT_PROMPT.md` — architect review prompt
- `tools/asam-db/VALIDATION_REPORT.md` — v4 validation report (grade B–C)
- `tools/docling/convert.py` — Docling PDF converter with MLX
- `tools/docling/db_setup.py` — Docling DB schema
- `tools/docling/lookup.py` — Docling CLI lookup
- `tools/fusion/fuse.py` — Kimi-K2.5 fusion pipeline
- `tools/fusion/db_setup.py` — Fusion DB schema
- `tools/fusion/run_fusion.sh` — Self-healing wrapper (auto-restart, progress tracking)
- `tools/fusion/lookup.py` — Unified fused DB lookup CLI (11 commands: glossary, query, fts, sql, tables, stats, quality, provenance, search-tables, add-knowledge, promote)
- `tools/fusion/AGENT_INSTRUCTIONS.md` — AI agent operating manual v2 (zero-knowledge onboarding, 11 commands, extensibility workflow, anti-laziness prompt, 11 lessons)
- `tools/fusion/optimize_db.py` — Database optimization script (FTS5, glossary, indexes, PRAGMAs, extensibility tables)
- `tools/asam-db/INGESTION_RUNBOOK.md` — updated with all 3 pipelines + fusion results
- `tools/asam-db/ASAM_KNOWLEDGE_BASE_ACCESS.md` — updated with architecture diagram
- `tools/virtualECU/db_setup.py` — Virtual ECU DB schema (20+ tables, FTS5, ChromaDB)
- `tools/virtualECU/ingest.py` — Virtual ECU ingestion pipeline (text + PDF + seed, 46 file extensions)
- `tools/virtualECU/lookup.py` — Virtual ECU CLI lookup (7 commands: glossary, query, fts, sql, tables, stats, search-tables)
- `tools/virtualECU/AGENT_INSTRUCTIONS.md` — Virtual ECU agent operating manual
- `virtualECU/KNOWLEDGE_VIRTUAL_ECU.md` — Research & sources documentation for 9 standards
- `tools/pipeline-c/extract.py` — Pipeline C extraction code (abandoned, scaffolding only)
- `tools/pipeline-c/db_setup.py` — Pipeline C DB schema (abandoned)
- `tools/pipeline-c/run_extract.sh` — Pipeline C wrapper (abandoned)

## Blockers
- Engineering RAG tests fail (0/4) — source corpus lacks byte-level protocol detail
- odx_file_types has hallucinated entries (.xml, cdfx)
- XCP tables have quality issues (hex conflicts, bogus event codes) per Kimi-K2.5 analysis
- No domain skill files created yet (XCP, MDF, ODX, UDS)

## Virtual ECU Pipeline (tools/virtualECU/)
- Schema: 20+ tables covering FMI, SSP, DCP, ASAM OSI, XIL, FIBEX, MCD-3 MC, AUTOSAR CP, vECU levels, co-sim concepts
- db_setup.py: COMPLETE, TESTED
- ingest.py: COMPLETE, text ingestion TESTED (9,240 docs, 17,390 chunks, ~7 files/sec)
- lookup.py: COMPLETE, TESTED (tables, stats, glossary, query all verified)
- AGENT_INSTRUCTIONS.md: COMPLETE
- Text ingestion: 9,240 files across 15 standards, 46 file extensions, 77.5 MB SQLite, 322.4 MB ChromaDB
- Structured seed: 86 rows across 16 domain tables (confidence=1.0, from official specs)
- PDF ingestion: PENDING — 237 PDFs (run `--pdf-only` to process via Docling MLX VLM)
- AUTOSAR mode: key specs only by default (15 folders), use `--all-autosar` for full R24files/

### Virtual ECU Source Coverage
| Standard | Documents | Chunks |
|---|---|---|
| ASAM MCD-3 MC | 3,097 | 3,156 |
| ASAM XIL | 2,801 | 3,647 |
| AUTOSAR CP (open-source) | 1,867 | 6,005 |
| OMSimulator | 821 | 1,834 |
| FMPy | 186 | 664 |
| ASAM FIBEX | 98 | 628 |
| ASAM OSI | 88 | 390 |
| PyFMI | 77 | 373 |
| FMI | 71 | 255 |
| AUTOSAR CP (specs) | 50 | 75 |
| SSP | 42 | 195 |
| FMI Guides | 22 | 58 |
| DCP | 15 | 103 |
| Reference | 5 | 7 |

## Database Optimization (COMPLETE)
- SQLite PRAGMAs: WAL, synchronous=NORMAL, mmap_size=256MB, cache_size=64MB, temp_store=MEMORY
- 34 secondary indexes on all searchable columns
- FTS5 full-text search: fts_structured (659), fts_docling_tables (1,956), fts_glossary (14)
- domain_glossary table: 14 ASAM terms (XCP, MDF, ODX, UDS, ECU, DAQ, A2L, CTO, DTO, ASAP3, COMPU-METHOD, CCBLOCK, NRC, ASAM)
- user_additions table + pending_additions view for extensibility
- lookup.py upgraded: 11 commands (glossary, query, fts, sql, tables, stats, quality, provenance, search-tables, add-knowledge, promote)
- AGENT_INSTRUCTIONS.md v2: zero-knowledge onboarding flow, all 11 commands documented, search strategy table, extensibility workflow, updated anti-laziness prompt
- DB grew from 6.9MB → 12.5MB (FTS indexes + glossary)

## Next Steps
1. Create domain skill files for XCP, MDF, ODX, UDS (conditional inclusion)
2. Clean up hallucinated rows based on fusion comparison reports
3. Consider adding ISO 14229 UDS source material via add-knowledge workflow
4. Optionally revisit Pipeline C if a paid Azure model deployment becomes available
5. ChromaDB optimization: metadata filter performance is slow (~30s on 74K vectors), consider where_document $contains for hybrid search
