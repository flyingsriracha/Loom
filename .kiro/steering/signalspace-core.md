---
inclusion: manual
---

# SignalSpace / AutoBrain — Core Steering (ARCHIVED — superseded by loom-core.md)

## Identity
Automotive signal analysis platform built on ASAM standards (XCP, MDF, ODX, UDS).
Hybrid RAG knowledge base (SQLite + ChromaDB) for protocol lookups.

## Current Phase
Fusion v1 complete. Two-pipeline architecture (A + B → Fusion) finalized.
Pipeline C explored but abandoned (Azure free-tier rate limits impractical).
Pipeline A grade: B–C (7–15% claim-level hallucination). Known facts: 6/6.

## Architecture
- Pipeline A: Mistral OCR → azrouter distillation → `tools/asam-db/` (570 rows, 3,194 vectors, 64 files)
- Pipeline B: Docling + Apple MLX VLM → `tools/docling/` (2,009 tables, 70,892 vectors, 39 PDFs)
- Fusion AB: Kimi-K2.5 compare + merge → `tools/ASAMKnowledgeDB/` (659 rows, 74,086 vectors, Docker API on :8400)
- Virtual ECU: Text ingestion → `tools/virtualECU/` (86 structured rows, 9,240 docs, 17,390 vectors)
- All use SQLite + ChromaDB (all-MiniLM-L6-v2 embeddings)
- CLI: `tools/asam-db/lookup.py`, `tools/docling/lookup.py`, `tools/ASAMKnowledgeDB/lookup.py`, `tools/virtualECU/lookup.py`
- REST API: `http://localhost:8400` (Docker) — see `tools/ASAMKnowledgeDB/AGENT_API_GUIDE.md`
- Steering: Core (always) + Domain skills (fileMatch) + Progress tracker (manual)

## Hard Rules
1. DO NOT GUESS on ASAM protocol data. Use the lookup tool.
2. DO NOT read files from `archived/` directly.
3. DO NOT embed large docs, file paths, or "must read" in steering files.
4. Keep this file under 800 tokens. Domain details go in skill files.
5. NO personas in steering. Use concrete context, constraints, and examples.

## Tool Commands
- Fused DB (CLI): `tools/docling/.venv/bin/python3 tools/ASAMKnowledgeDB/lookup.py <cmd> "<arg>"`
- Fused DB (API): `curl http://localhost:8400/<endpoint>` — see AGENT_API_GUIDE.md
  Commands: glossary, query, fts, sql, tables, stats, quality, provenance, search-tables, add-knowledge, promote
- Virtual ECU DB: `tools/docling/.venv/bin/python3 tools/virtualECU/lookup.py <cmd> "<arg>"`
  Commands: glossary, query, fts, sql, tables, stats, search-tables
- Start here (zero knowledge): `lookup.py glossary ""` then `lookup.py stats`
- Pipeline A: `python tools/asam-db/lookup.py query|sql|tables|stats "<arg>"`
- Pipeline B: `tools/docling/.venv/bin/python3 tools/docling/lookup.py query|stats "<arg>"`
- Agent guides: `tools/ASAMKnowledgeDB/AGENT_API_GUIDE.md`, `tools/virtualECU/AGENT_INSTRUCTIONS.md`

## Coding Discipline
- Zero-Skip Policy: no placeholders, no TODOs, no `// ... rest of code`
- Plan-Implement-Run: plan it, build it, verify it runs. Never skip Run.
- Debug-first: add logs, read output, then fix. No speculative patches.
- Rebuild over patching: 3+ patches same component? Scrap and rebuild.

## Data Quality Warning
XCP tables (commands, errors, events) are high quality. MDF/ODX tables solid.
`protocol_parameters` excluded from spot-check (loosely structured, high false-positive rate).
`uds_nrc_codes` empty — source corpus lacks ISO 14229 UDS NRC data.
`odx_file_types` has some hallucinated entries (.xml, cdfx). Cross-reference with semantic search.

## Session Recovery
Load `#progress-tracker` for session continuity.
