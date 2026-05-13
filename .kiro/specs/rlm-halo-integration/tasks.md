# Implementation Plan — RLM/HALO Integration for Loom

Each task is derived from the design document and maps to one or more requirements and properties. The phase order encodes the hard gates: Phase 1 (HALO) is independent and lands first; Phase 2 (RLM spike) must produce an admin-recorded `go` decision before Phases 3 or 4 start.

## Overview

Convert the feature design into a series of prompts for a code-generation LLM that will implement each step with incremental progress. Each prompt builds on the previous prompts and ends with wiring things together. There is no orphan code — every module introduced in one task is consumed by a later task. Tasks focus ONLY on writing, modifying, or testing code.

Conventions:
- Sub-tasks marked with `*` (e.g., `- [ ]* 1.2`) are optional — typically property tests, integration tests, or non-critical tooling. Core implementation tasks are never optional.
- Each task lists exact file paths from the design's anchors, referenced requirements (`_Requirements: N.M_`), and referenced correctness properties (`_Properties: N_`) where applicable.
- Testing is test-first where practical: the property test task appears ahead of the implementation it covers. The test begins failing, then the implementation turns it green.
- The 22 correctness properties are those enumerated in `design.md § Testing Strategy § Correctness Properties`.

## Tasks

- [ ] 1. HALO Foundation: extend audit JSONL and ship out-of-band analyzer
  - Track A of the design. No RLM dependency — starts immediately and delivers value against existing Loom traces.

  - [ ] 1.1 Define `SpanRecord` dataclass and extend `OrchestratorAuditLogger.record_span()` additively
    - Add a `SpanRecord` dataclass in `loom/orchestrator/audit.py` with the fields specified in design.md § Data Models (legacy tuple + `span_id`, `trace_id`, `parent_span_id`, `name`, `start_time`, `end_time`, `status`, `attributes`, `events`).
    - Add a `record_span(...)` method on `OrchestratorAuditLogger` that serializes one JSONL line containing BOTH the legacy fields `{audit_id, timestamp, action, request_context, request, result}` AND the additive span-shaped fields.
    - Leave the existing `record(...)` public surface unchanged; internally route it through `record_span()` with `trace_id = audit_id` and `parent_span_id = None`.
    - _Requirements: 6.1, 6.5_

  - [ ]* 1.2 Write property test for SpanRecord round-trip and parent-child consistency
    - File: `loom/tests/test_span_extension.py`.
    - **Property 8: Every span record has the required OTLP-shaped fields and round-trips through JSONL.**
    - **Property 9: Parent-child span relationships are consistent within a trace.**
    - **Property 14: The classifier carries no `estimated_context_tokens` and no RLM route** (classifier stability co-located here per design's test file map).
    - Use Hypothesis strategies to generate random span trees; assert JSONL round-trip preserves both legacy and span-shaped fields; assert every non-root `parent_span_id` resolves within the same `trace_id`.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 13.1_ _Properties: 8, 9, 14_

  - [ ] 1.3 Wrap each workflow node with a span context manager
    - File: `loom/orchestrator/workflow.py`.
    - Wrap `_classify`, `_research`, `_memory`, `_code`, `_draft`, `_verify` so each emits one span per invocation, child of the request's root span (whose `span_id == trace_id == audit_id`).
    - Capture node name, status, start/end time, and any warnings accumulated during the node in `attributes`.
    - _Requirements: 6.2_ _Properties: 9_

  - [ ] 1.4 Emit child spans for tool calls inside each workflow node
    - Files: `loom/orchestrator/workflow.py`, `loom/orchestrator/clients.py` (thin wrapper), `loom/orchestrator/spec_session.py`.
    - Emit child spans around `LoomServiceClient.query/search/artifact_context`, `AMSClient.recall/resume/reflect`, `CMMClient.search_code/trace_call_path/detect_changes/get_architecture/status`.
    - Set each tool span's `parent_span_id` to the enclosing node span's `span_id`. Place request/response metadata in `attributes`.
    - _Requirements: 6.3_ _Properties: 9_

  - [ ] 1.5 Record errors and warnings as span events
    - File: `loom/orchestrator/audit.py` (helper), applied from both workflow and spec_session paths.
    - Each `OrchestratorError`, each raised exception inside a node, and each appended warning becomes a span `event` entry `{name, timestamp, attributes}` with `error_type`, `message`, and stack trace where available.
    - _Requirements: 6.4_

  - [ ] 1.6 Implement span retention configuration
    - File: `loom/orchestrator/audit.py` (reads `LOOM_AUDIT_RETENTION_DAYS`, default 30).
    - Add a prune-on-read or windowed read helper that filters records older than the retention window. Preserve the JSONL file but drop aged lines via rewrite on admin-triggered retention runs.
    - _Requirements: 6.6_

  - [ ] 1.7 Create JSONL-to-OTLP-shaped trace converter with incremental cursor
    - File: `loom/halo/trace_converter.py` (≤200 lines, single-responsibility).
    - Implement `ConversionReport` dataclass and `jsonl_to_otlp_shaped(audit_path, output_path) -> ConversionReport` per design § Component Interfaces.
    - Persist the byte-offset cursor to `loom/artifacts/halo/.cursor.json` so subsequent calls only process new records.
    - _Requirements: 7.6_

  - [ ] 1.8 Implement HALO analyzer with failure-mode clustering
    - File: `loom/halo/analyzer.py` (≤200 lines).
    - Implement `HALOAnalyzer.analyze(trace_path, *, filters) -> AnalysisReport`.
    - Clusters: `hallucinated_tool_call`, `malformed_tool_args`, `refusal_loop`, `timeout_pattern`, `zero_result_cascade`, `other`.
    - Flags a cluster as `Systemic_Failure_Mode` when frequency > 0.05 within the analysis window.
    - Produces structured failure-mode records containing type, frequency, affected nodes, example `trace_id`s, and remediation-suggestion placeholder slots (filled in Phase 5).
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [ ]* 1.9 Write property test for the 5% systemic-failure threshold
    - File: `loom/tests/test_halo_systemic_threshold.py`.
    - **Property 10: 5 percent threshold triggers systemic-mode flagging.**
    - Generate synthetic trace corpora with controlled failure frequencies; assert systemic flag iff `f > 0.05`.
    - _Requirements: 7.4_ _Properties: 10_

  - [ ] 1.10 Implement Evidence_Corpus exporter
    - File: `loom/halo/evidence.py` (≤200 lines).
    - Implement `export_evidence_corpus(report, out_dir, *, filters) -> EvidenceCorpus`.
    - Writes `loom/artifacts/halo/evidence_corpus/<timestamp>/{overview.md, detail/, raw/, index.json}`.
    - Supports filters: time range, failure type, `engineer_id`, `project_id`, minimum frequency.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 1.11 Write property test for Evidence_Corpus index.json bijection
    - File: `loom/tests/test_evidence_corpus_bijection.py`.
    - **Property 11: Evidence_Corpus index.json is a bijection with its on-disk contents.**
    - Generate random corpus shapes; assert every indexed path exists and every on-disk file is indexed.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_ _Properties: 11_

  - [ ] 1.12 Add HALO admin REST endpoints
    - File: `loom/orchestrator/app.py`.
    - Register three endpoints, all gated by `_read_admin_context`:
      - `POST /admin/halo/analyze` → returns an `AnalysisReport`.
      - `POST /admin/halo/evidence_corpus` → returns the exported corpus metadata.
      - `GET /admin/halo/change_manifests` → lists manifests (read path only; writes added in Phase 5).
    - HALO is NOT exposed via `mcp_server.py` (admin-only review surface).
    - _Requirements: 7.1, 8.1, 18.2_

  - [ ]* 1.13 Write property test for admin-endpoint auth invariants
    - File: `loom/tests/test_admin_auth_invariants.py`.
    - **Property 17: Admin endpoints reject unauthenticated and non-admin requests.**
    - Assert 401 on missing/invalid key, 403 on non-admin keys, and 403 on `LOOM_CONSUMER_API_KEYS` against every `/admin/halo/*` and `/admin/rlm/*` route.
    - _Requirements: 18.1, 18.2_ _Properties: 17_

  - [ ] 1.14 Add `halo-tools` service to Docker Compose
    - File: `loom/docker-compose.yml`.
    - Add a `halo-tools` CLI container: no exposed port, mounts `./artifacts` read-write, runs the HALO CLI entrypoint, depends on `orchestrator` only for volume sharing (no runtime dependency).
    - _Requirements: 16.2_

  - [ ] 1.15 Integration test: analyzer against real orchestrator traces
    - File: `loom/tests/integration/test_halo_end_to_end.py`.
    - Run `HALOAnalyzer` against the JSONL produced by the existing 8 passing orchestrator integration tests; assert a non-empty `AnalysisReport` and a readable `EvidenceCorpus` on disk.
    - Run one `/api/v1/ask` call through the live stack and assert the emitted JSONL line contains both legacy fields AND span-shaped fields with proper parent-child structure for all tool calls.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 8.1_

  - [ ]* 1.16 Add HALO replay CLI
    - File: `loom/tools/halo_replay.py`.
    - Reconstructs the ordered span tree for a given `trace_id` from `orchestrator_audit.jsonl`.
    - _Requirements: 17.6_

- [ ] 2. Checkpoint — Phase 1 HALO foundation landed
  - Ensure all unit, property, and integration tests from Phase 1 pass. Ask the user if questions arise.
  - Confirm `loom/artifacts/orchestrator_audit.jsonl` contains span-shaped lines and that `docker compose run --rm halo-tools analyze` completes against real traces.

- [ ] 3. RLM Value Validation Spike: prove measurable improvement before any RLM integration
  - Track B of the design. This phase produces the go/no-go decision that gates Phases 4 and 5.

  - [ ] 3.1 Gate check — confirm Phase 1 HALO foundation is landed
    - Fail this task unless task 2 (Phase 1 checkpoint) is complete. We do not spike RLM without real orchestrator span data available.
    - _Requirements: 20.1_

  - [ ] 3.2 Evaluate RLM library candidates and record selection
    - Evaluate `alexzhang13/rlm` (reference impl), `rlm-python`, `fast-rlm`, and DSPy's RLM module on: sandbox integration cost, Azure GPT-5 compatibility (reuse existing Graphiti Azure wrapper), depth-limit support, license compatibility.
    - Record the selection rationale in the spike decision template (`loom/spikes/rlm_library_evaluation.md`).
    - _Requirements: 14.1, 14.3, 14.5_

  - [ ] 3.3 Implement the spike script operating only on real inputs
    - File: `loom/spikes/rlm_spec_session_spike.py`.
    - Operates on real retrieved references from the live `/api/v1/artifact/context` path — no mocks, no fixtures.
    - Resolves the target spec-session from `(objective_id, artifact_type)` passed on the command line.
    - Produces a baseline output (current `spec_session.render_artifact()`) AND an RLM output (draft `render_artifact_rlm()`) for the same reference set.
    - _Requirements: 20.1, 20.2, 20.3_

  - [ ]* 3.4 Write property test asserting spike inputs are real
    - File: `loom/tests/test_spike_inputs_real.py`.
    - **Property 20: Spike operates only on real inputs.**
    - Assert the spike module does not import from `unittest.mock` and does not load from known fixture packages.
    - _Requirements: 20.1_ _Properties: 20_

  - [ ] 3.5 Produce spike artifacts and metrics
    - Output layout under `loom/artifacts/rlm_spike/<timestamp>/`:
      - `baseline_output.md`, `rlm_output.md`
      - `metrics.json` with keys `citation_completeness`, `quality_score`, `total_cost_usd`, `wallclock_seconds`
      - `decision.md` (admin-authored after running)
      - `inputs/` — serialized reference set for reproducibility
    - _Requirements: 20.3, 20.4_

  - [ ]* 3.6 Write property test for spike output shape
    - File: `loom/tests/test_spike_artifacts.py`.
    - **Property 21: Spike produces both outputs and required metrics.**
    - Assert after a run that `baseline_output.md`, `rlm_output.md`, and `metrics.json` with the required keys are all present on disk.
    - _Requirements: 20.3, 20.4_ _Properties: 21_

  - [ ] 3.7 Document the go/no-go rubric in the decision.md template
    - File: `loom/spikes/decision_template.md`.
    - Specify the concrete rubric the admin uses to compute `quality_score` (citation coverage, section completeness, lineage preservation) and the acceptance thresholds for `citation_completeness`, cost, and latency.
    - _Requirements: 20.5, 20.6_

  - [ ]* 3.8 Admin runs the spike and records the decision
    - Admin executes the spike against a real objective with ≥20 references, reviews outputs, and writes `decision.md` with either `go` or `no-go` plus rationale.
    - This task is optional from the coding-agent perspective — it is manual and outside agent scope — but it is the real gate.
    - If `no-go`: record the learning in `loom-progress.md`, and tasks 5 and 6 do not start.
    - If `go`: proceed to task 5.
    - _Requirements: 20.5, 20.6_

- [ ] 4. Checkpoint — Phase 2 spike decision recorded
  - Ensure all spike property tests pass. Confirm `loom/artifacts/rlm_spike/<latest>/decision.md` exists and contains either `go` or `no-go`. Ask the user if questions arise.

- [ ] 5. RLM in Spec-Session: render_artifact_rlm with go-gate enforcement
  - Track C of the design. Gated by a `go` decision from Phase 2.

  - [ ] 5.1 Gate check — confirm spike decision is `go`
    - Read the latest `loom/artifacts/rlm_spike/<timestamp>/decision.md`. Fail this task if the file does not exist or does not contain the literal token `go`.
    - This gate is also enforced at runtime inside `RLMClient.gate_is_go()`; encoding it here blocks the implementation phase from starting without a recorded decision.
    - _Requirements: 20.5_

  - [ ] 5.2 Implement RLMClient
    - File: `loom/rlm/client.py` (≤200 lines).
    - Implement `RLMClient` with methods `__init__(settings, sandbox)`, `completion(prompt, *, model, depth_limit=1, cost_limit_usd=5.0, latency_limit_s=180, corpus=None) -> RLMResponse`, `predict_cost(prompt, *, model) -> float`, `gate_is_go() -> bool` (reads most recent `decision.md`).
    - Default recursion depth is 1; override emits a warning recorded in the call's audit record.
    - Return `RLMResponse` and `RLMMetrics` dataclasses per design § Data Models.
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 5.5_

  - [ ]* 5.3 Write property tests for RLM budget enforcement
    - File: `loom/tests/test_rlm_budgets.py`.
    - **Property 1: Default recursion depth is 1.**
    - **Property 2: Budget termination returns a partial result plus a `budget_exceeded` warning.**
    - **Property 3: Cost and latency never exceed configured limits.**
    - **Property 4: Pre-execution cost prediction refuses calls above budget.**
    - Use Hypothesis to generate random RLM workloads against a stubbed sub-LM; assert every invariant.
    - _Requirements: 1.4, 1.5, 5.1, 5.2, 5.3, 5.4, 5.5_ _Properties: 1, 2, 3, 4_

  - [ ] 5.4 Implement sandbox backends with production default Docker-in-Docker
    - File: `loom/rlm/sandbox.py` (≤200 lines).
    - Backends: Docker-in-Docker (production default), Modal, E2B. Local REPL dev-only, gated by `LOOM_DEPLOYMENT_ENV=development`.
    - Enforce: read-only input mount, write-only output mount, no other host-fs mounts, egress allow-list limited to configured LLM provider endpoints, CPU/memory/wallclock limits enforced by the sandbox runtime.
    - _Requirements: 1.3, 16.1, 16.5, 16.6, 18.4_

  - [ ]* 5.5 Write property test for sandbox configuration invariants
    - File: `loom/tests/test_sandbox_config.py`.
    - **Property 18: Sandbox configuration respects isolation invariants.**
    - Generate random sandbox configs; assert the mount list is exactly `{ro_input, wo_output}` and the egress allow-list contains only configured LLM provider endpoints.
    - _Requirements: 18.4_ _Properties: 18_

  - [ ] 5.6 Implement three-layer budget enforcement
    - File: `loom/rlm/client.py` (cost accounting helper module, if size requires, at `loom/rlm/budget.py`).
    - Layer 1: pre-call prediction via `predict_cost`; refuse if predicted cost exceeds `cost_limit_usd`.
    - Layer 2: mid-call cumulative token tracking with early termination on projected overrun.
    - Layer 3: sandbox-enforced wallclock per Req 5.2.
    - On budget termination: return partial `RLMResponse` with `warnings = ['budget_exceeded']` and the last processed chunk id in the span's `attributes`.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ] 5.7 Implement bounded concurrency via asyncio semaphore
    - File: `loom/rlm/client.py` (or co-located concurrency helper).
    - Default concurrency limit 5, configurable. Excess requests queue in FIFO order.
    - _Requirements: 19.1, 19.2_

  - [ ]* 5.8 Write property test for concurrent-call limit
    - File: `loom/tests/test_rlm_concurrency.py`.
    - **Property 19: Concurrent RLM calls never exceed configured limit.**
    - Drive bursts of concurrent calls against an instrumented `RLMClient`; sample active-call count; assert `active <= limit` at every instant and FIFO ordering of queued requests.
    - _Requirements: 19.1, 19.2_ _Properties: 19_

  - [ ] 5.9 Implement `render_artifact_rlm` adapter for spec-session
    - File: `loom/rlm/adapters/spec_session.py` (≤200 lines).
    - Signature mirrors `spec_session.render_artifact(...)` and returns the SAME dict shape (content, citations, supporting_node_ids, steering_paths, unresolved_items, traceability_ok).
    - Binds the retrieved reference set to a REPL corpus variable; issues depth-1 sub-calls accumulating citations section-by-section; preserves lineage metadata across sub-calls.
    - When the rendered artifact exceeds 100K tokens, writes to a REPL file variable and returns a file handle reference.
    - Every citation in the final output MUST resolve to a supporting node; otherwise raise. No silent fallback here — silent fallback happens one layer up in the dispatcher.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 5.10 Write property test for activation thresholds
    - File: `loom/tests/test_rlm_activation_thresholds.py`.
    - **Property 5: Threshold activation is exactly the disjunction `refs ≥ 20 OR projected_tokens ≥ 50_000`.**
    - Generate random `(ref_count, projected_tokens)` pairs and assert the Spec_Session_Tool activates RLM iff the disjunction holds.
    - _Requirements: 3.1_ _Properties: 5_

  - [ ]* 5.11 Write property test for citation resolution
    - File: `loom/tests/test_citation_resolution.py`.
    - **Property 7: Every citation in a rendered artifact resolves to a corpus node.**
    - Generate synthetic corpora and rendered outputs; assert `render_artifact_rlm` raises when any citation does not resolve.
    - _Requirements: 3.6_ _Properties: 7_

  - [ ] 5.12 Wire dispatch in `/api/v1/spec/generate` and `/api/v1/spec/update`
    - File: `loom/orchestrator/app.py`.
    - Route to `render_artifact_rlm(...)` when `(len(references) >= 20 OR projected_tokens >= 50_000) AND rlm_client.gate_is_go()`; otherwise route to `render_artifact(...)`.
    - Log every activation decision (measured signal, threshold, tool id, outcome) into the audit trail as a span event.
    - On `RLMClient` raise/timeout/misconfiguration or `gate_is_go() == False`, fall back to `render_artifact(...)` and append warning `rlm_unavailable_fallback` or `rlm_gate_pending` respectively.
    - _Requirements: 13.2, 13.5, 13.6, 20.5_

  - [ ] 5.13 Wire same dispatch in MCP `generate_spec_artifact`/`update_spec_artifact` tools
    - File: `loom/orchestrator/mcp_server.py`.
    - Mirror the dispatch logic in task 5.12 so MCP callers receive the same behavior as REST callers.
    - _Requirements: 13.2, 13.6_

  - [ ]* 5.14 Write property test for per-tool RLM activation and clean fallback
    - File: `loom/tests/test_per_tool_rlm_activation.py`.
    - **Property 15: Every RLM activation decision is logged with its measured signal.**
    - **Property 16: Tools fall back cleanly when RLM is unavailable.**
    - Drive random tool invocations with and without RLM availability; assert audit-log entries and `rlm_unavailable_fallback` warning surface.
    - _Requirements: 13.5, 13.6_ _Properties: 15, 16_

  - [ ]* 5.15 Write property test for spike-gate enforcement in downstream paths
    - File: `loom/tests/test_spike_gate_enforcement.py`.
    - **Property 22: Go/no-go gate enforced in downstream RLM paths.**
    - Simulate `decision.md` absent or `no-go`; assert dispatcher falls back to `render_artifact(...)` and appends `rlm_gate_pending`.
    - _Requirements: 20.5, 20.6_ _Properties: 22_

  - [ ]* 5.16 Write property test for classifier stability
    - File: part of `loom/tests/test_span_extension.py` (see task 1.2) — or stand-alone `loom/tests/test_classifier_stability.py`.
    - **Property 14: The classifier carries no `estimated_context_tokens` field and no `rlm` route.**
    - _Requirements: 13.1_ _Properties: 14_

  - [ ] 5.17 Add `rlm-runtime` service to Docker Compose
    - File: `loom/docker-compose.yml`.
    - Define `rlm-runtime` with CPU/memory limits, read-only input mount, write-only output mount, egress allow-list to configured LLM provider endpoints, and `LOOM_DEPLOYMENT_ENV=production` default.
    - _Requirements: 16.1, 16.3, 16.4, 16.5_

  - [ ] 5.18 Implement RLM provider abstraction
    - File: `loom/rlm/providers.py` (≤200 lines).
    - Support OpenAI, Azure OpenAI (reusing Loom's existing Graphiti Azure wrapper), Anthropic, and open-weight endpoints. Support different models for root vs sub-LM calls.
    - Unified configuration schema for model selection, pricing, token limits per provider; retry with exponential backoff on transient errors; provider-specific metrics logged per call.
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

  - [ ] 5.19 Integration test: real spec-session request with ≥20 references
    - File: `loom/tests/integration/test_spec_session_rlm_path.py`.
    - Drive `/api/v1/spec/generate` with a real request backed by ≥20 retrieved references; assert the RLM path is taken, the output is citation-complete, and fallback triggers cleanly when `rlm-runtime` is disabled.
    - _Requirements: 3.1, 3.6, 13.2, 13.6_

- [ ] 6. Checkpoint — Phase 3 RLM spec-session landed
  - Ensure all unit, property, and integration tests from Phase 3 pass. Ask the user if questions arise.

- [ ] 7. RLM for Provenance and Long Traces
  - Track D of the design. Gated by a `go` decision from Phase 2.

  - [ ] 7.1 Gate check — confirm spike decision is `go`
    - Same enforcement as task 5.1. Fail this task if the latest `decision.md` does not contain `go`.
    - _Requirements: 20.5_

  - [ ] 7.2 Implement `explain_evidence_chain_rlm` adapter for provenance
    - File: `loom/rlm/adapters/provenance.py` (≤200 lines).
    - Consumes the already-retrieved subgraph JSON from `/api/v1/node/{id}/provenance` — does not re-run retrieval.
    - Binds subgraph to a REPL variable; exposes programmatic filters for source pipeline, confidence threshold, edge type, and temporal validity window; produces a human-readable explanation with explicit citations (`source_system, source_pipeline, source_file, confidence`).
    - On budget overrun, returns the partial chain with `rlm_budget_exceeded` warning.
    - _Requirements: 2.1, 2.2, 2.3, 2.6_

  - [ ] 7.3 Wire provenance dispatch at the explainer consumer of `/api/v1/node/{id}/provenance`
    - File: `loom/orchestrator/app.py` (or the dedicated provenance-explainer path if one exists).
    - Dispatch to `explain_evidence_chain_rlm` when `node_count > 500 AND gate_is_go()`; otherwise use the existing short-path explanation.
    - _Requirements: 2.1, 2.5_

  - [ ]* 7.4 Write property test for the 500-node activation threshold
    - Add cases to `loom/tests/test_rlm_activation_thresholds.py` (or split into `test_provenance_threshold.py`).
    - **Property 6: Provenance 500-node threshold activates RLM exactly when exceeded.**
    - Generate random subgraph sizes; assert RLM invocation iff `node_count > 500`.
    - _Requirements: 2.1, 2.5, 13.3_ _Properties: 6_

  - [ ] 7.5 Contradiction detection across overlapping validity windows
    - File: `loom/rlm/adapters/provenance.py`.
    - Flag each pair of facts with overlapping `validFrom/validTo` windows and conflicting values. Include conflicting source identifiers in the output.
    - _Requirements: 2.4, 4.5_

  - [ ] 7.6 Long-trace HALO analyzer path via RLM
    - File: `loom/halo/analyzer.py` (dispatch) + `loom/rlm/adapters/halo_long_trace.py` (≤200 lines).
    - When the serialized trace corpus exceeds 100K tokens, route to an RLM-backed analyzer that binds the corpus as a REPL variable, exposes filters by span type/error code/time range/workflow node, supports depth-1 sub-queries on failure clusters, and preserves span lineage.
    - Output remains `AnalysisReport` / `EvidenceCorpus`-compatible.
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [ ] 7.7 Cross-run pattern detection across multiple trace files
    - File: `loom/rlm/adapters/halo_long_trace.py`.
    - Combine multiple trace files into one REPL corpus; detect recurring failure sequences across runs; produce comparative frequency report; estimate confidence interval for pattern significance.
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [ ]* 7.8 Write property test for long-trace findings referencing valid source spans
    - File: `loom/tests/test_long_trace_findings.py`.
    - **Property 13: Long-trace findings reference valid source spans.**
    - Generate synthetic long-trace inputs; assert every finding's `span_id` resolves to a span in the analyzed `trace_id`.
    - _Requirements: 11.5_ _Properties: 13_

  - [ ] 7.9 Integration test: provenance subgraph of >500 nodes
    - File: `loom/tests/integration/test_provenance_rlm_path.py`.
    - Drive the provenance explainer with a real subgraph of >500 nodes; assert RLM path is taken, the evidence chain is complete, and contradictions are flagged when present.
    - _Requirements: 2.1, 2.3, 2.4_

- [ ] 8. Checkpoint — Phase 4 provenance and long-trace RLM landed
  - Ensure all unit, property, and integration tests from Phase 4 pass. Ask the user if questions arise.

- [ ] 9. HALO Self-Improvement Loop (operator-reviewed)
  - Track E of the design. Depends on Phase 1 only; not gated by the RLM decision.

  - [ ] 9.1 Implement ChangeManifest writer and outcome attribution
    - File: `loom/halo/manifests.py` (≤200 lines).
    - Implement `write_change_manifest(manifest, out_dir) -> Path` writing versioned `change_manifests/<timestamp>_<slug>.json`.
    - Implement `attribute_outcome(manifest_id, *, before, after) -> ChangeManifest` that classifies the outcome as `EFFECTIVE | PARTIALLY_EFFECTIVE | MIXED | INEFFECTIVE | HARMFUL` per Req 9.6.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 9.2 Write property test for manifest evidence references
    - File: `loom/tests/test_change_manifest_evidence.py`.
    - **Property 12: ChangeManifest evidence references point to existing files.**
    - Generate random manifests with `evidence_refs`; assert every entry resolves to an actual file in the referenced Evidence_Corpus.
    - _Requirements: 9.3_ _Properties: 12_

  - [ ] 9.3 Remediation-suggestion generator
    - File: `loom/halo/analyzer.py` (extend Phase 1 analyzer).
    - For every Systemic_Failure_Mode, emit ≥1 `RemediationSuggestion` with: component to modify, specific change, failure pattern addressed, evidence backing, effort (`low/medium/high`), expected impact (`high/medium/low`), confidence score.
    - On conflicting suggestions, flag the conflict and list resolution approaches.
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ] 9.4 Admin-only apply endpoint
    - File: `loom/orchestrator/app.py`.
    - Implement `POST /admin/rlm/apply_manifest` (admin role; consumer keys rejected). On every apply, log admin identity, timestamp, and manifest_id to the audit trail.
    - No automated apply path exists. Every change is operator-reviewed.
    - _Requirements: 10.6, 18.5_

  - [ ] 9.5 Extend HALO dashboard in `loom-portal/`
    - Files: `loom-portal/` components consuming `/admin/halo/*` endpoints.
    - Show active failure modes, frequency trends over time, Change_Manifest history with outcome attribution, drill-down from summary to Evidence_Corpus views.
    - Reuse `orchestrator/portal_links.py` for deep links to LangSmith and FalkorDB UI.
    - Filters: time range, failure type, `engineer_id`, `project_id`.
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_

  - [ ] 9.6 Integration test: Change_Manifest audit and attribution flow
    - File: `loom/tests/integration/test_change_manifest_flow.py`.
    - Submit a `ChangeManifest` via the admin endpoint; assert the audit log records admin identity, timestamp, and manifest_id. Drive `attribute_outcome` with before/after `AnalysisReport`s; assert correct classification.
    - _Requirements: 9.5, 9.6, 10.6, 18.5_

- [ ] 10. Checkpoint — Phase 5 self-improvement loop landed
  - Ensure all unit, property, and integration tests from Phase 5 pass. Ask the user if questions arise.

- [ ] 11. Operational Hardening
  - Track F of the design. Depends on whichever RLM tracks actually shipped (Phase 3 always; Phase 4 if spike was `go`).

  - [ ] 11.1 Add RLM and HALO concurrency/utilization monitoring
    - Files: `loom/rlm/client.py`, `loom/halo/analyzer.py`, `loom/common/observability.py`.
    - Track active-call count, queue depth, and cost per minute. Emit Prometheus-compatible metrics and alert when utilization approaches configured limits.
    - _Requirements: 19.6_

  - [ ] 11.2 Deployment documentation for sandbox backends
    - File: `loom/docs/runbooks/rlm_sandbox_deployment.md`.
    - Configuration examples for Modal, E2B, and Prime sandbox environments including networking, resource limits, and credential handling.
    - _Requirements: 16.6_

  - [ ]* 11.3 Evidence_Corpus export performance test
    - File: `loom/tests/performance/test_evidence_corpus_sla.py`.
    - Assert `export_evidence_corpus` completes within 60 seconds for corpora containing up to 10,000 traces.
    - _Requirements: 19.4_

  - [ ]* 11.4 RLM retrieval performance test
    - File: `loom/tests/performance/test_rlm_retrieval_sla.py`.
    - Assert RLM-based retrieval returns within 120 seconds for queries whose materialized context is up to 500K tokens.
    - _Requirements: 19.5_

  - [ ]* 11.5 Cross-backend confluence integration test
    - File: `loom/tests/integration/test_sandbox_confluence.py`.
    - Same input executed on Docker-in-Docker and Modal sandboxes with fixed seeds; assert output equivalence within documented tolerance.
    - _Requirements: 1.3_

  - [ ] 11.6 Evidence_Corpus data-isolation enforcement
    - File: `loom/halo/evidence.py`.
    - Filter traces by the requester's `engineer_id` and `project_id` scope BEFORE clustering; clustering operates only over entitled traces.
    - _Requirements: 18.3_

  - [ ]* 11.7 Load test alongside existing `load_eval.py`
    - File: `loom/evals/load_eval_rlm_halo.py`.
    - Extend the existing load-evaluation harness to exercise RLM and HALO paths under concurrent sessions. Record `p95` latency and cost-per-request.
    - _Requirements: 19.1, 19.6_

- [ ] 12. Final checkpoint — all phases green
  - Ensure all unit, property, and integration tests across Phases 1–6 pass. Confirm `loom-progress.md` is refreshed with the current RLM/HALO integration status, and ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional — they are typically property tests, integration tests, or non-critical tooling that can be skipped for a faster MVP. Core implementation tasks are never optional.
- Each task references specific requirements from `requirements.md` and, where applicable, specific correctness properties from `design.md § Testing Strategy`.
- The 22 correctness properties are covered as follows:
  - **Phase 1 (HALO foundation):** Properties 8, 9, 10, 11, 14, 17
  - **Phase 2 (RLM spike):** Properties 20, 21
  - **Phase 3 (RLM spec-session):** Properties 1, 2, 3, 4, 5, 7, 14, 15, 16, 18, 19, 22
  - **Phase 4 (RLM provenance + long trace):** Properties 6, 13
  - **Phase 5 (HALO self-improvement):** Property 12
  - **Phase 6 (operational hardening):** no new properties — performance and isolation are integration-test-scoped per design
- Gate structure:
  - Phase 1 has no RLM dependency — starts immediately.
  - Phase 2 starts after Phase 1 checkpoint so the spike runs against real span data.
  - Phases 3 and 4 begin only if `loom/artifacts/rlm_spike/<latest>/decision.md` contains the literal token `go`.
  - Phase 5 depends on Phase 1 only.
  - Phase 6 depends on whichever RLM tracks shipped.
- Checkpoints are explicit tasks (2, 4, 6, 8, 10, 12). Each says "Ensure all tests pass, ask the user if questions arise."

## Workflow Completion

This workflow produced only design and planning artifacts (`requirements.md`, `design.md`, `tasks.md`). The feature is not implemented here. Execute tasks by opening `tasks.md` and clicking "Start task" next to task items.
