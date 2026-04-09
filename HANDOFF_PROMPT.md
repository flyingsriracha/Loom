# Fused ASAM Knowledge Base — Handoff Package

## WHAT TO COPY TO YOUR DEV FOLDER

### Primary: Fused Database (this is the main deliverable)
```
tools/fusion/                           # The whole folder (~322 MB)
├── fused_knowledge.db                  # 12.5 MB SQLite (659 rows, 10 structured tables + metadata)
├── fused_vector_store/                 # 309 MB ChromaDB (74,086 vectors)
├── db_setup.py                         # Schema definitions (structured + docling_tables + fusion_log + comparison_report)
├── lookup.py                           # CLI query tool (11 commands)
├── optimize_db.py                      # FTS5 indexes, glossary, PRAGMA tuning
├── AGENT_INSTRUCTIONS.md               # Comprehensive agent operating manual
└── .gitignore
```

### Also Copy: Pipeline A (the source that fed into fusion)
```
tools/asam-db/                          # ~120 MB
├── asam_structured.db                  # 13 MB SQLite (570 rows — Pipeline A's raw output)
├── asam_vector_store/                  # 103 MB ChromaDB (3,194 vectors)
├── db_setup.py                         # Pipeline A schema
├── ingest.py                           # Mistral OCR → azrouter distillation pipeline
├── lookup.py                           # Pipeline A query tool (4 commands)
├── requirements.txt                    # Python deps
├── INGESTION_RUNBOOK.md                # Full pipeline runbook
└── ASAM_KNOWLEDGE_BASE_ACCESS.md       # Architecture + access guide
```

### Required: Steering & Agent Behavior Docs
```
.kiro/steering/signalspace-core.md      # Core rules & architecture
.kiro/steering/progress-tracker.md      # Full project history, decisions, stats
```

### Required: Agent Discipline & Anti-Laziness Framework
```
archived/VIBE_CODING_LESSONS_LEARNED.md                           # 11 lessons with prompts
archived/steeringSkill/02_STEERING_SYSTEM_FRAMEWORK.md            # 3-layer steering framework v2.1
archived/steeringSkill/01_RESEARCH_CONTEXT_MANAGEMENT.md          # Research: context rot, budgets
archived/Mastering Vibe Coding_ A Framework for AI Development Optimization.md  # Gemini framework
```

### Required: Historical Context
```
archived/steeringSkill/DEV_JOURNEY.md                             # Development journey log
archived/tools-asam-db-historical/GEMINI_ARCHITECT_PROMPT.md       # 7-change architect prompt (D → C)
archived/tools-asam-db-historical/VALIDATION_REPORT.md             # v4 validation report (Grade C)
archived/tools-asam-db-historical/validate_report.py               # The validation script
```

### Note on Python Environment
The fusion lookup.py requires chromadb and sentence-transformers (all-MiniLM-L6-v2).
In our workspace it runs via: `tools/docling/.venv/bin/python3 tools/fusion/lookup.py`
The other agent will need their own venv with: `pip install chromadb openai tiktoken`

---

## PROMPT — PASTE THIS INTO THE OTHER AGENT'S FIRST MESSAGE

```
You are receiving the Fused ASAM Knowledge Base from the AutoBrain/SignalSpace project.
This is an automotive signal analysis platform built on ASAM standards (XCP, MDF, ODX, UDS)
with a hybrid RAG knowledge base (SQLite + ChromaDB).

The fused database is the MERGED result of two independent extraction pipelines:
- Pipeline A: Mistral OCR → azrouter LLM distillation (570 rows, 3,194 vectors)
- Pipeline B: Docling (IBM) + Apple MLX VLM table extraction (2,009 tables, 70,892 vectors)
- Fusion: Kimi-K2.5 reasoning model compared both, resolved conflicts, merged best data

The fused DB at tools/fusion/ is your primary working database.
Pipeline A at tools/asam-db/ is a reference — the raw input before fusion.

=============================================================================
PART 1: WHAT YOU HAVE — THE FUSED DATABASE
=============================================================================

Location: tools/fusion/
- SQLite: fused_knowledge.db (12.5 MB)
  - 659 structured rows across 10 domain tables
  - 1,956 raw Docling tables (markdown + JSON from original PDFs)
  - 10 comparison reports (Kimi-K2.5 per-table quality assessment)
  - 213 fusion log entries (audit trail)
  - 14 domain glossary terms
  - FTS5 full-text search indexes (BM25 ranked, porter stemming)
- ChromaDB: fused_vector_store/ (309 MB, 74,086 vectors, all-MiniLM-L6-v2)

Every structured row has provenance:
- source_pipeline: "mistral_azrouter" (from Pipeline A) or "docling_kimi25" (from Pipeline B + Kimi)
- confidence: float 0.0–1.0
- source_file: original PDF/document

THE 10 STRUCTURED TABLES (FUSED):

| Table | Total | From A | From Docling/Kimi | Quality | Known Issues |
|---|---|---|---|---|---|
| xcp_commands | 144 | 112 | 32 | medium | Hex conflicts (0xFB collision), wrong categories |
| xcp_errors | 68 | 68 | 0 | low | Non-standard entries |
| xcp_events | 30 | 28 | 2 | low | Bogus hex codes (0xFFFF, 0xAAAA, 0xEEEE) — fabricated |
| mdf_block_types | 66 | 34 | 32 | HIGH | Complete MDF4 block coverage — best table |
| mdf_channel_types | 8 | 7 | 1 | low | Wrong cn_type mappings (cn_type=2 should be Master) |
| mdf_conversion_types | 19 | 7 | 12 | low | Conflates A2L names with MDF cc_type enum |
| uds_nrc_codes | 0 | 0 | 0 | EMPTY | No ISO 14229 UDS NRC data in source corpus |
| odx_file_types | 20 | 12 | 8 | medium | Hallucinated .xml and .cdfx entries |
| odx_compu_categories | 11 | 11 | 0 | medium | Reasonable coverage |
| protocol_parameters | 293 | 291 | 2 | HIGH | Covers XCP, MDF, ASAP3 — best data |

ADDITIONAL TABLES:
- docling_tables: 1,956 raw tables extracted from PDFs (markdown + JSON)
- comparison_report: 10 Kimi-K2.5 per-table quality assessments
- fusion_log: 213 audit trail entries
- domain_glossary: 14 ASAM domain terms with definitions
- user_additions: staging table for new knowledge (extensibility)
- FTS5 indexes: fts_structured (659), fts_docling_tables (1,956), fts_glossary (14)

=============================================================================
PART 2: YOUR MISSION
=============================================================================

Improve the data quality of this fused database.
Target: move from Grade C (15.2% claim hallucination) to Grade A-B (under 5%).

1. AUDIT each table against ASAM standards. Use the quality and provenance commands
   to understand what Kimi-K2.5 already flagged.

2. CLEAN hallucinated rows:
   - xcp_events with hex codes 0xFFFF, 0xAAAA, 0xEEEE (real XCP events: 0x00–0x03)
   - odx_file_types with .xml and .cdfx (valid ODX: .odx, .pdx, .odx-d, .odx-c, .odx-f, .odx-v, .odx-cs, .odx-e)
   - xcp_commands with conflicting hex codes (resolve the 0xFB conflict)
   - mdf_channel_types with wrong cn_type mappings
   - mdf_conversion_types entries that are A2L names, not MDF cc_type values
   - mdf_block_types: "IDBLOCK" flagged as hallucinated
   - mdf_channel_types: "classification result" entry is fabricated

3. ENRICH gaps:
   - uds_nrc_codes is completely empty — populate with ISO 14229-1 NRC codes
   - mdf_conversion_types: MDF4 spec defines cc_type values 0–11
   - xcp_commands may be missing some optional/service commands

4. VALIDATE after changes:
   - All hex codes in valid ranges for their protocol
   - No duplicate command/hex_code pairs
   - Confidence scores reflect actual reliability
   - Known facts still pass: XCP CONNECT=0xFF, ERR_CMD_BUSY=0x10, ##CN block exists
   - Rebuild FTS5 indexes after changes: python3 tools/fusion/optimize_db.py

=============================================================================
PART 3: HOW TO USE THE FUSED DATABASE (11 Commands)
=============================================================================

All commands use this pattern (adjust python path for your env):
  python3 tools/fusion/lookup.py <command> "<argument>"

ZERO-KNOWLEDGE ONBOARDING (start here if unfamiliar with ASAM):
  python3 tools/fusion/lookup.py glossary ""        # List all 14 domain terms
  python3 tools/fusion/lookup.py stats              # Database overview

QUERYING:
  python3 tools/fusion/lookup.py query "XCP CONNECT command"   # Hybrid: structured + FTS + semantic
  python3 tools/fusion/lookup.py fts "connect command"         # Fast BM25 keyword search
  python3 tools/fusion/lookup.py sql "SELECT * FROM xcp_commands WHERE hex_code='0xFF'"

INSPECTION:
  python3 tools/fusion/lookup.py tables             # List all tables and columns
  python3 tools/fusion/lookup.py quality xcp_commands    # Kimi-K2.5 quality assessment
  python3 tools/fusion/lookup.py provenance xcp_commands # Which pipeline contributed what
  python3 tools/fusion/lookup.py search-tables "CONNECT" # Search 1,956 raw Docling tables

EXTENSIBILITY:
  python3 tools/fusion/lookup.py add-knowledge 'uds_nrc_codes {"nrc_name":"subFunctionNotSupported","hex_code":"0x12","description":"Sub-function not supported"} "ISO 14229-1"'
  python3 tools/fusion/lookup.py promote list        # Review staged additions
  python3 tools/fusion/lookup.py promote 1           # Promote to main table

PIPELINE A (reference, raw input before fusion):
  python3 tools/asam-db/lookup.py query "XCP CONNECT"
  python3 tools/asam-db/lookup.py sql "SELECT * FROM xcp_commands LIMIT 5"
  python3 tools/asam-db/lookup.py tables
  python3 tools/asam-db/lookup.py stats

IMPORTANT: Always query BEFORE modifying. Understand current state first.

=============================================================================
PART 4: HARD RULES — DO NOT VIOLATE
=============================================================================

1. DO NOT GUESS on ASAM protocol data. If you don't know a hex code, say "unknown."
   You have 74,086 vectors and 1,956 raw tables to search. Use them.

2. DO NOT read files from archived/ directly. Use the lookup tool.

3. ZERO-SKIP POLICY: No placeholders, no TODOs, no "// ... rest of code".
   Every change must be complete. Debt accrues infinitely faster in AI-assisted
   coding because the agent builds on top of placeholders as if they were real.

4. PLAN-IMPLEMENT-RUN: Plan changes. Make changes. Verify by querying the database.
   Never skip verification. Code that "looks right" but hasn't been executed is
   an assumption, not a deliverable.

5. DEBUG-FIRST: Query data first, understand the issue, then fix. No speculative
   patches. Add logs, read output, fix based on evidence.

6. REBUILD OVER PATCHING: If a table needs 3+ fixes, drop and rebuild with clean
   data. Micro-patches create Jenga towers.

7. PRESERVE PROVENANCE: Every row has source_pipeline, source_file, confidence.
   When you add/modify data:
   - confidence=1.0: verified against actual ASAM specification
   - confidence=0.7: high confidence from training knowledge
   - confidence=0.5: reasonable but needs human verification
   - source_pipeline: use "user_cleanup" for your changes
   Use INSERT OR IGNORE, not INSERT OR REPLACE.

8. DO NOT modify lookup.py, db_setup.py, or optimize_db.py unless there is a bug.
   Your job is to improve the DATA, not the tooling.

9. NO PERSONAS: Don't "act as a Senior Architect." Research shows personas waste
   tokens without improving correctness. Use concrete context and constraints.

10. USE THE QUALITY COMMAND: Before citing or modifying any table, run:
    python3 tools/fusion/lookup.py quality <table_name>
    This shows Kimi-K2.5's assessment of that table's reliability.

=============================================================================
PART 5: CODING DISCIPLINE (Battle-Tested Lessons)
=============================================================================

These are from building this exact system across 10+ sessions. Not theoretical.

CONTEXT ROT: If you start looping or hallucinating, save state and start fresh.
Don't keep working in a degraded session.

MOCKUP SHELL TRAP: Don't build perfect shells with placeholder logic. Every
function must have real implementation.

SHALLOW INTEGRATION: Do a Gap Analysis first. List what needs to change, get
approval, implement module by module. Never integrate multiple complex changes
in a single pass.

CONTEXT SUMMARY COMPRESSION: In a new context window, don't trust summaries
for technical details. Re-read actual files and data.

LAZY LLM SYNDROME: When processing bulk data, LLMs skip tedious extraction
and act as pass-through filters. Verify every extraction with concrete queries.

REBUILD OVER PATCHING: 3+ patches and still broken? Document what it should do,
rebuild from scratch.

STEERING FILE BLOAT: Never embed large docs or "must read" instructions in
steering files. This caused our system to produce output in Korean after 10+
sessions of cascading context overflow.

THE KOREAN INCIDENT: An LLM put entire ASAM document paths as "must read"
instructions inside a steering file. This caused the agent to load massive
documents into context on every session, burning through the window in minutes
and causing cascading summarization that eventually produced output in Korean.
Lesson: steering files are control surfaces, not documentation.

=============================================================================
PART 6: DATA QUALITY CONTEXT
=============================================================================

HOW WE GOT FROM GRADE D (94%) TO GRADE C (15.2%):
1. Structure-aware chunking — tables no longer split mid-row
2. Page-aligned OCR fusion — plain text page N fuses with OCR page N
3. Pre-extraction content gate — narrative chunks produce zero structured rows
4. Chunk-ID integrity validation — every chunk_id resolves to real ChromaDB doc
5. Claim-level decomposition — spot-checks verify individual fields
6. INSERT OR IGNORE — high-quality rows no longer silently overwritten
7. Adversarial validator prompt — partial matches flagged as hallucinated

Full details: archived/tools-asam-db-historical/GEMINI_ARCHITECT_PROMPT.md

KIMI-K2.5 FUSION COMPARISON RESULTS (Phase 1):
| Table | Pipeline A quality | Pipeline B quality | Verdict |
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

CURRENT VALIDATION (v4, Grade C):
- 92 claims checked, 78 verified, 14 hallucinated (15.2%)
- Known facts: 6/6 (100%), Chunk-ID orphans: 0/570 (0%)
- Worst: odx_file_types (3/5 hallucinated), xcp_events (1/5 hallucinated)
- Best: xcp_errors (5/5), mdf_conversion_types (5/5), odx_compu_categories (5/5)

KNOWN HALLUCINATED ENTRIES TO REMOVE:
- odx_file_types: .xml, .cdfx, cdfx
- xcp_events: "Success" event with fabricated hex code
- mdf_block_types: "IDBLOCK" flagged as hallucinated
- mdf_channel_types: "classification result" entry is fabricated

=============================================================================
PART 7: DOMAIN CONTEXT (ASAM Standards)
=============================================================================

XCP (ASAM MCD-1 XCP V1.5.0):
- Universal Measurement and Calibration Protocol for ECU development
- Master-slave: tool (master) ↔ ECU (slave)
- CTO (Command Transfer Object) and DTO (Data Transfer Object)
- Command hex range: 0xC0–0xFF (standard), 0x00–0xBF (reserved/user)
- Key errors: ERR_CMD_SYNCH=0x00, ERR_CMD_BUSY=0x10, ERR_CMD_UNKNOWN=0x20

MDF (ASAM MDF V4.x):
- Block-based binary: each block starts with 4-char ID (##HD, ##DG, ##CG, ##CN, etc.)
- cn_type: 0=Fixed Length, 1=VLSD, 2=Master, 3=Virtual Master, 4=Sync, 5=MLSD, 6=Virtual Data
- cc_type: 0=1:1, 1=Linear, 2=Rational, 3=Text Formula, 4=Tab Interp, 5=Tab NoInterp,
  6=Range Table, 7=Text Table, 8=Text Range, 9=Bitfield Text, 10=Algebraic, 11=Tab Verb Range

ODX (ISO 22901 / ASAM MCD-2D):
- Valid extensions: .odx, .pdx, .odx-d, .odx-c, .odx-f, .odx-v, .odx-cs, .odx-e
- NOT valid: .xml, .cdfx (hallucinated entries in current DB)
- COMPU-METHOD: IDENTICAL, LINEAR, SCALE-LINEAR, TAB-INTP, TAB-NOINTP, TEXTTABLE, COMPUCODE, COMPUCONST

UDS (ISO 14229) — Core NRC codes to populate the empty table:
- 0x10 generalReject, 0x11 serviceNotSupported, 0x12 subFunctionNotSupported,
  0x13 incorrectMessageLengthOrInvalidFormat, 0x14 responseTooLong,
  0x22 conditionsNotCorrect, 0x24 requestSequenceError,
  0x25 noResponseFromSubnetComponent, 0x26 failurePreventsExecution,
  0x31 requestOutOfRange, 0x33 securityAccessDenied, 0x35 invalidKey,
  0x36 exceededNumberOfAttempts, 0x37 requiredTimeDelayNotExpired,
  0x70 uploadDownloadNotAccepted, 0x71 transferDataSuspended,
  0x72 generalProgrammingFailure, 0x73 wrongBlockSequenceCounter,
  0x78 requestCorrectlyReceivedResponsePending,
  0x7E subFunctionNotSupportedInActiveSession,
  0x7F serviceNotSupportedInActiveSession

=============================================================================
PART 8: CONTEXT FILES TO READ (in this order)
=============================================================================

1. tools/fusion/AGENT_INSTRUCTIONS.md — THE primary doc. Agent manual with all 11
   commands, data quality map, search strategies, domain context, example workflows,
   anti-laziness prompt, extensibility workflow
2. tools/asam-db/ASAM_KNOWLEDGE_BASE_ACCESS.md — Architecture diagram, all tables
3. tools/asam-db/INGESTION_RUNBOOK.md — How the data was built (all pipelines)
4. archived/tools-asam-db-historical/VALIDATION_REPORT.md — Current v4 results
5. archived/tools-asam-db-historical/GEMINI_ARCHITECT_PROMPT.md — 7 changes (D→C)
6. archived/VIBE_CODING_LESSONS_LEARNED.md — 11 battle-tested lessons with prompts
7. archived/steeringSkill/02_STEERING_SYSTEM_FRAMEWORK.md — Steering framework v2.1
8. archived/steeringSkill/01_RESEARCH_CONTEXT_MANAGEMENT.md — Context management research
9. .kiro/steering/signalspace-core.md — Core steering rules
10. .kiro/steering/progress-tracker.md — Full project history and current state

=============================================================================
PART 9: WHAT SUCCESS LOOKS LIKE
=============================================================================

- Claim-level hallucination: 15.2% → under 5%
- Known facts: still 6/6 (100%)
- No bogus hex codes in any table
- uds_nrc_codes: 0 → 20+ core NRC codes from ISO 14229-1
- odx_file_types: only valid ODX extensions (no .xml, .cdfx)
- mdf_channel_types: correct cn_type mappings per MDF4 spec
- mdf_conversion_types: all cc_type values 0–11 covered
- Every modified row has appropriate confidence score and source_pipeline="user_cleanup"
- FTS5 indexes rebuilt after changes (python3 tools/fusion/optimize_db.py)
- Summary of all changes with before/after counts per table
```
