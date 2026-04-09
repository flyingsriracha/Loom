---
inclusion: always
---

# Loom — Core Steering

## Identity
Modular AI-assisted automotive development system. Four modules:
1. Loom (FalkorDB graph) — centralized ASAM/AUTOSAR knowledge
2. AMS Solver (Hindsight or alt) — per-engineer session memory
3. LangGraph Orchestrator — single MCP entry point
4. CMM (codebase-memory-mcp) — code structure awareness
Creator: Jerry Chen (chj1ana).

## Current Phase
Phase 1: Spec alignment → build planning.
Requirements doc refreshed (18 requirements).
Next: align `design.md`, rebuild `tasks.md`, then run the FalkorDB + Graphiti migration spike.

## Hard Rules
1. DO NOT GUESS on ASAM/AUTOSAR data. Query the knowledge DB.
2. DO NOT build AMS from scratch. Integrate Hindsight or Engram.
3. Every fact must carry provenance (source, page, pipeline, confidence).
4. Steering commands are PERMANENT. Never summarize away.
5. NO mock data in migration or integration code. Real connections only.
6. Before starting any session: re-read `#loom-progress` and this file. Do not rely on chat summaries for architectural decisions.

## Progress Update Protocol
- At session start, read `loom-progress.md` before doing substantive work.
- Update `loom-progress.md` whenever a milestone completes, a design decision changes, a blocker changes, or the next steps change.
- Always update `loom-progress.md` before summarizing, handing off, clearing context, or ending a long session.
- Keep `loom-progress.md` concise. Replace stale status and next steps instead of appending noisy chat summaries.
- Record decisions, status, blockers, and next steps. Do not use the progress file as a raw transcript dump.
- If chat state and `loom-progress.md` disagree, refresh the progress file and treat it as the handoff source of truth.

## Coding Discipline (from Vibe Coding Lessons)
- Zero-Skip Policy: no placeholders, no TODOs, no `// ... rest of code`
- Plan-Implement-Run: plan it, build it, verify it runs. Never skip Run.
- Debug-first: add logs, read output, then fix. No speculative patches.
- Rebuild over patching: 3+ patches same component? Scrap and rebuild.
- Module-by-module: never integrate multiple complex systems in one shot. Gap analysis first, then implement one module at a time.
- Integration tasks are mandatory: every phase must end with a task that wires components together and verifies the system runs end-to-end.
- Keep files under 200 lines. Break large modules into single-purpose files.
- Use CMM (`loom/plugins/codebase-memory-mcp/codebase-memory-mcp cli`) to check call chains and impact before modifying shared code.

## Anti-Patterns to Block
- Mockup Shell: if you see a function returning hardcoded/mock data where a real DB call should be, stop and fix immediately.
- Context Rot: if the agent starts forgetting prior decisions or re-introducing fixed bugs, save state to progress tracker, clear chat, start fresh.
- Lazy Ingestion: when processing bulk data (migration), verify counts match source. Report total rows migrated vs source rows. No silent skips.
- Isolated Components: do not build Loom MCP, LangGraph orchestrator, and AMS integration as disconnected pieces. Each phase must include integration verification.

## Key References
- Design decisions: `research/loom_system_design_decisions.md`
- Requirements: `.kiro/specs/aaems-system-architecture/requirements.md`
- Research: `research/agentic_memory_architecture_2026.md`

## Session Recovery
Load `#loom-progress` for session continuity.
Before handoff or context clear, refresh `#loom-progress`.
