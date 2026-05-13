# Requirements Document — RLM/HALO Integration for Loom

## Introduction

This specification defines a narrow, evidence-first integration of Recursive Language Models (RLM) and the Hierarchical Agent Loop Optimizer (HALO) into Loom. It reflects a ground-truth review of the current codebase and of HALO's actual data contract, which narrows the original proposal in important ways.

Three facts shape this revision:

1. Loom's `loom/retrieval/pipeline.py` already performs multi-stage retrieval — global community search, local hybrid search, MMR rerank, evidence chain assembly. That pipeline IS intelligent decomposition for the common case. RLM is therefore NOT a replacement for standard retrieval. RLM is reserved for specific, measurable long-context gaps the existing pipeline cannot close.
2. The LangGraph orchestrator in `loom/orchestrator/workflow.py` is a coordinator. Its `_draft` node emits pre-written summary strings; the actual artifact text generation happens downstream in `spec_session.render_artifact` or in the calling IDE. RLM therefore belongs INSIDE specific text-producing tools, not at orchestrator classification time. The classifier is keyword/regex based and does not know token counts before retrieval runs.
3. HALO consumes JSONL span lines in inference.net OTLP-shaped export format, not the full OpenTelemetry stack. Loom already writes `loom/artifacts/orchestrator_audit.jsonl`. The integration is therefore a format translator that extends the existing JSONL schema with span-shaped fields, not a full OpenTelemetry pipeline replacement.

The integration addresses three concrete gaps in Loom:

- **Spec-session artifact generation with many references** that would truncate under standard context limits.
- **Long orchestrator trace analysis** where a single debugging session's trace can exceed standard context windows.
- **Deep multi-hop provenance traversal** across large subgraphs whose serialized form does not fit standard context windows.

Per the Loom steering rule "Module-by-module: never integrate multiple complex systems in one shot", the work is sequenced HALO-first, with a standalone RLM value-validation spike gating any production RLM integration. Per "No mock data in migration or integration code", every RLM and HALO integration point in production code paths MUST operate against real traces, real retrieval output, and real provenance data.

This requirements document follows the EARS patterns and INCOSE quality rules. It assumes Phase 1 of Loom is operational with FalkorDB, Graphiti, the LangGraph orchestrator, Hindsight AMS, and baseline CMM integration complete.

## Scope and Non-Goals

### In Scope

- HALO-style trace analysis over Loom's existing orchestrator audit JSONL extended with span-shaped fields.
- RLM inside `spec_session.generate_artifact` when the reference set is large enough to risk context truncation (evidence-based threshold).
- RLM for long-trace analysis when a HALO debugging session's trace exceeds standard context windows.
- RLM for deep provenance traversal inside provenance-explanation tools when the serialized subgraph exceeds standard context windows.
- An RLM value-validation spike that MUST demonstrate measurable quality improvement before RLM is wired into any production tool.

### Out of Scope

- Replacing Loom's `retrieval/pipeline.py` (global community → local hybrid → MMR → evidence chain) with RLM for general retrieval.
- Classifier-level or orchestrator-level "route to RLM" decisions based on pre-retrieval token estimates, since the classifier is keyword/regex and token counts are only known after retrieval.
- Automated harness auto-patching. HALO findings and change manifests are operator-reviewed; nothing is applied without explicit admin approval.
- A full OpenTelemetry collector/exporter stack for Loom. The integration extends the existing JSONL audit format with span-shaped fields consistent with HALO's OTLP-shaped contract.
- RLM recursion depth greater than 1 as a default, per the RLM reproduction study (arxiv 2603.02615) showing quality degradation from deeper recursion.

## Glossary

- **RLM**: Recursive Language Model — an inference paradigm that treats long prompts as external REPL environment variables, enabling an LLM to programmatically examine, decompose, and recursively call itself over input snippets.
- **REPL_Environment**: Read-Eval-Print Loop environment where prompts become Python variables accessible for programmatic manipulation.
- **Sub_LM_Call**: A recursive LLM invocation within an RLM workflow, typically processing a chunk or transformed subset of the original input.
- **HALO**: Hierarchical Agent Loop Optimizer — a methodology for analyzing execution traces to identify recurring failure modes and generate evidence-backed harness improvement suggestions.
- **Trace_Evidence**: Structured, layered evidence extracted from execution traces, including overview summaries, per-failure-mode detail files, and raw span data.
- **Change_Manifest**: An auditable record explaining what harness component changed, which trace evidence motivated it, expected effects, and predicted risks.
- **Harness_Component**: Any editable piece of the agent system — prompts, tool descriptions, middleware, orchestration logic, skills, memory integration, or evaluation criteria — that can be modified in response to HALO findings.
- **Systemic_Failure_Mode**: A recurring pattern of failure across multiple agent executions, indicating a harness-level problem rather than a one-off error.
- **Orchestrator_Workflow**: The LangGraph state machine in `loom/orchestrator/workflow.py` that routes queries through classify, research, memory, code, draft, and verify nodes.
- **Audit_Trail**: The JSONL execution traces currently recorded by `loom/orchestrator/audit.py` into `loom/artifacts/orchestrator_audit.jsonl`.
- **Long_Context_Query**: A query whose materialized context after Loom's retrieval pipeline exceeds the effective context window of the underlying LLM. Loom's existing multi-stage retrieval already handles most context fitting; this term applies only to residual cases (very large reference sets, large trace corpora, or large provenance subgraphs).
- **Evidence_Corpus**: A structured export containing layered trace evidence (overview.md, detail/*.md, raw/*.jsonl) suitable for RLM analysis or coding-agent consumption.
- **Value_Validation_Spike**: A standalone, time-boxed POC comparing RLM output to the current-retrieval-plus-standard-LLM baseline on a concrete use case with measurable quality metrics. Production RLM integration is gated on this spike showing improvement.
- **OTLP_Shaped_JSONL**: JSONL span records whose fields match inference.net's OTLP-shaped export format (span_id, trace_id, parent_span_id, name, start_time, end_time, status, attributes, events). This is lighter than full OpenTelemetry and is HALO's actual input contract.

---

## Module 1: RLM Integration for Targeted Long-Context Gaps

### Requirement 1: RLM Infrastructure Setup

**User Story:** As a Loom admin, I want a bounded RLM runtime inside Loom, so that specific tools with long-context gaps can invoke recursive inference without new orchestrator-level routing.

#### Acceptance Criteria

1. THE RLM_Module SHALL expose a `rlm.completion(prompt, model, depth_limit, cost_limit, latency_limit)` interface callable from individual Loom tools.
2. WHEN an RLM call is initiated, THE RLM_Module SHALL initialize a Python REPL environment with the input prompt bound to a named variable accessible to the root LLM.
3. THE RLM_Module SHALL support sandbox backends (Docker, Modal, E2B) selectable via environment variables, with Docker as the production default.
4. THE RLM_Module SHALL default the recursion depth limit to 1 sub-call level.
5. WHERE an operator configures recursion depth greater than 1, THE RLM_Module SHALL emit a warning that depths above 1 have been shown to degrade answer quality in the RLM reproduction study and SHALL record the configured depth in every call's audit record.
6. THE RLM_Module SHALL log each recursive sub-call with token counts, latency, cost estimate, and the chunk identifier it operated on.

### Requirement 2: RLM for Deep Provenance Traversal

**User Story:** As an engineer, I want to explain the full derivation of a domain fact when the supporting subgraph is too large to fit standard context, so that I can audit provenance chains that span hundreds of nodes without manual graph walking.

#### Acceptance Criteria

1. WHEN a provenance-explanation tool serializes a subgraph containing more than 500 nodes, THE Provenance_Tool SHALL invoke the RLM_Module with the serialized subgraph bound as a REPL variable.
2. THE RLM provenance traversal SHALL expose programmatic filters for source pipeline, confidence threshold, edge type, and temporal validity window over the in-REPL subgraph.
3. THE RLM provenance traversal SHALL produce a human-readable explanation of the evidence chain with explicit source citations (source_system, source_pipeline, source_file, confidence).
4. WHEN the evidence chain contains contradictions (facts with overlapping validity windows and conflicting values), THE RLM provenance traversal SHALL flag each contradiction and name the conflicting sources.
5. IF the subgraph contains 500 nodes or fewer, THE Provenance_Tool SHALL use the existing standard-context explanation path and SHALL NOT invoke RLM.
6. IF the RLM provenance traversal exceeds its configured cost or latency budget, THE Provenance_Tool SHALL return the partial chain produced so far and SHALL append a `rlm_budget_exceeded` warning to the response.

### Requirement 3: Spec-Session Artifact Generation with RLM

**User Story:** As an engineer, I want to generate spec-session artifacts (requirements.md, design.md, tasks.md) when the reference set is large enough that standard generation would truncate citations, so that comprehensive artifacts retain every required source.

#### Acceptance Criteria

1. WHEN a spec-session generation request has either 20 or more reference documents OR a projected output length of at least 50,000 tokens, THE Spec_Session_Tool SHALL invoke the RLM_Module for artifact rendering.
2. THE RLM spec-session workflow SHALL bind the full set of retrieved reference documents to a corpus variable in the REPL environment.
3. THE RLM spec-session workflow SHALL build the artifact incrementally by issuing recursive sub-calls that accumulate citations section-by-section.
4. THE RLM spec-session workflow SHALL preserve artifact lineage metadata (objective_id, session_id, engineer_id, steering references, supporting_node_ids) across all recursive calls.
5. WHEN the rendered artifact exceeds 100,000 tokens, THE RLM_Module SHALL write the artifact to a REPL file variable and return a file handle reference rather than returning the full text in context.
6. THE RLM spec-session workflow SHALL verify that every citation in the rendered artifact resolves to a node in the knowledge corpus and SHALL fail the generation if any citation cannot be resolved.

### Requirement 4: Provenance Trace Analysis with RLM

**User Story:** As an engineer, I want to analyze complex evidence chains and provenance traces across sessions and projects, so that I can understand how a fact was derived over time.

#### Acceptance Criteria

1. WHEN a cross-session provenance analysis request covers traces whose serialized form exceeds 100,000 tokens, THE Provenance_Tool SHALL invoke the RLM_Module.
2. THE RLM provenance analysis SHALL load the combined trace corpus as a traversable structure in the REPL environment.
3. THE RLM provenance analysis SHALL enable programmatic traversal of edges, filtering by source pipeline, and aggregation of confidence scores.
4. THE RLM provenance analysis SHALL produce a human-readable explanation with explicit source citations.
5. WHEN the evidence chain contains contradictions, THE RLM provenance analysis SHALL flag and explain each contradiction.
6. THE RLM provenance analysis SHALL support temporal queries (valid time, transaction time) through programmatic filtering in the REPL environment.

### Requirement 5: RLM Cost and Latency Guardrails

**User Story:** As an admin, I want RLM calls to respect cost and latency budgets, so that recursive calls do not produce unexpected expenses or block user workflows.

#### Acceptance Criteria

1. THE RLM_Module SHALL enforce a configurable maximum cost per RLM call with a default of 5.00 USD per query.
2. THE RLM_Module SHALL enforce a configurable maximum latency per RLM call with a default of 180 seconds.
3. IF an RLM call exceeds its cost or latency budget, THE RLM_Module SHALL terminate the call and return a partial result annotated with a `budget_exceeded` warning.
4. THE RLM_Module SHALL track cumulative sub-call token counts and SHALL terminate when projected total cost exceeds the configured cost budget.
5. THE RLM_Module SHALL compute a cost prediction before execution based on input size and configured model pricing and SHALL refuse to start calls whose predicted cost already exceeds the budget.
6. WHEN an RLM call is terminated due to budget limits, THE partial result SHALL include all work completed up to the termination point and the identifier of the last successfully processed chunk.

---

## Module 2: HALO Integration for Harness Optimization

### Requirement 6: Trace Collection and OTLP-Shaped JSONL Extension

**User Story:** As a Loom admin, I want the existing orchestrator audit JSONL extended with span-shaped fields, so that HALO can consume Loom traces directly without a full OpenTelemetry pipeline.

#### Acceptance Criteria

1. THE Audit_Trail SHALL extend each `orchestrator_audit.jsonl` record with span-shaped fields matching HALO's OTLP-shaped contract: `span_id`, `trace_id`, `parent_span_id`, `name`, `start_time`, `end_time`, `status`, `attributes`, `events`.
2. EACH orchestrator workflow node invocation (classify, research, memory, code, draft, verify) SHALL be written as an OTLP-shaped span sharing a common `trace_id` for the enclosing request.
3. EACH tool invocation (Loom query, AMS recall/resume, CMM search) SHALL be written as a child span referencing the enclosing workflow-node span via `parent_span_id`, with request and response metadata placed in `attributes`.
4. EACH error or warning SHALL be recorded as a span `event` entry with `error_type`, `message`, and stack trace where available.
5. THE Audit_Trail SHALL continue to write the existing JSONL fields for backward compatibility and SHALL add the span-shaped fields additively in the same record.
6. THE Audit_Trail SHALL support a configurable retention period for raw span-shaped records with a default of 30 days.

### Requirement 7: HALO Trace Analysis Engine

**User Story:** As a Loom admin, I want the system to analyze execution traces and identify systemic failure modes, so that I can improve the orchestrator harness without manual log inspection.

#### Acceptance Criteria

1. THE HALO_Module SHALL ingest OTLP-shaped JSONL records from the Audit_Trail.
2. THE HALO_Module SHALL cluster similar failure patterns across multiple traces using a configurable similarity threshold.
3. THE HALO_Module SHALL identify failure modes including hallucinated tool calls, malformed tool arguments, refusal loops, timeout patterns, and zero-result cascades.
4. WHEN a failure mode appears in more than 5 percent of traces within a configured time window, THE HALO_Module SHALL flag the mode as a Systemic_Failure_Mode.
5. THE HALO_Module SHALL produce a structured failure mode report containing failure type, frequency, affected workflow nodes, representative trace examples, and suggested remediation patterns.
6. THE HALO_Module SHALL support incremental analysis, processing new traces without re-analyzing the full historical corpus.

### Requirement 8: Evidence Corpus Generation

**User Story:** As a Loom admin, I want layered trace evidence exported in a structured corpus format, so that I can pass evidence to coding agents for harness improvement or review it manually.

#### Acceptance Criteria

1. THE HALO_Module SHALL provide an `export_evidence_corpus` action that generates a structured evidence bundle.
2. THE Evidence_Corpus SHALL include an `overview.md` file summarizing key findings, failure frequencies, and high-priority remediation opportunities.
3. THE Evidence_Corpus SHALL include a `detail/` directory containing per-failure-mode markdown files with trace excerpts and context.
4. THE Evidence_Corpus SHALL include a `raw/` directory containing the OTLP-shaped JSONL spans for drill-down analysis.
5. THE Evidence_Corpus SHALL include an `index.json` file providing machine-readable metadata about the corpus structure and contents.
6. WHEN exporting an Evidence_Corpus, THE HALO_Module SHALL support filtering by time range, failure type, engineer_id, project_id, and minimum frequency threshold.

### Requirement 9: Change Manifest Generation

**User Story:** As a Loom admin, I want every harness modification recorded with evidence-backed justification, so that I can audit why changes were made and attribute outcomes to specific interventions.

#### Acceptance Criteria

1. THE HALO_Module SHALL support a Change_Manifest schema capturing component changed, description, failure pattern addressed, evidence references, root cause hypothesis, targeted fixes, predicted regressions, and risk notes.
2. WHEN a Harness_Component is modified based on trace evidence, THE Change_Manifest SHALL be written into a versioned `change_manifests/` directory.
3. EACH Change_Manifest SHALL reference specific trace evidence files that motivated the change.
4. THE Change_Manifest SHALL include predicted task-level impacts listing which task types should improve and which might regress.
5. AFTER evaluation of a harness change, THE HALO_Module SHALL produce a change attribution report comparing predictions to actual outcomes.
6. THE change attribution report SHALL classify outcomes as EFFECTIVE, PARTIALLY_EFFECTIVE, MIXED, INEFFECTIVE, or HARMFUL.

### Requirement 10: Operator-Reviewed Harness Improvement Suggestions

**User Story:** As a Loom admin, I want the system to generate evidence-backed harness improvement suggestions for operator review, so that I can apply vetted fixes efficiently without any automated application.

#### Acceptance Criteria

1. WHEN the HALO_Module identifies a Systemic_Failure_Mode, THE HALO_Module SHALL generate at least one remediation suggestion with explicit evidence backing.
2. THE remediation suggestions SHALL specify which Harness_Component to modify, the specific change to make, which failure pattern it addresses, and which evidence supports it.
3. THE remediation suggestions SHALL be classified by effort level (low, medium, high) and expected impact (high, medium, low).
4. THE remediation suggestions SHALL include a confidence score based on evidence frequency and consistency.
5. IF multiple remediation suggestions conflict, THE HALO_Module SHALL flag the conflict and list resolution approaches.
6. THE HALO_Module SHALL require explicit admin approval for every suggested change and SHALL NOT apply any change automatically.

---

## Module 3: RLM-Enhanced HALO Trace Analysis

### Requirement 11: Long-Trace Analysis with RLM

**User Story:** As a Loom admin, I want to analyze execution traces whose serialized size exceeds standard context windows, so that deep debugging sessions are not truncated.

#### Acceptance Criteria

1. WHEN a trace analysis request involves more than 100,000 tokens of trace data, THE HALO_Module SHALL invoke the RLM_Module for that analysis.
2. THE RLM trace analysis SHALL bind the full trace corpus to a variable in the REPL environment.
3. THE RLM trace analysis SHALL expose programmatic filters by span type, error code, time range, and workflow node.
4. THE RLM trace analysis SHALL support recursive sub-queries to examine specific failure clusters in detail, subject to the default depth limit of 1.
5. WHEN analyzing long traces, THE RLM_Module SHALL preserve span lineage across recursive calls so that findings can be traced back to source spans by `span_id`.
6. THE RLM trace analysis SHALL produce Evidence_Corpus output compatible with the standard HALO analysis pipeline.

### Requirement 12: Cross-Run Pattern Detection with RLM

**User Story:** As a Loom admin, I want to identify failure patterns that span multiple execution runs, so that I can detect systemic issues that only appear across sessions.

#### Acceptance Criteria

1. THE RLM-enhanced HALO analysis SHALL support analysis across multiple trace files from different execution runs.
2. WHEN analyzing cross-run patterns, THE RLM_Module SHALL load all selected trace files as a combined corpus in the REPL environment.
3. THE RLM cross-run analysis SHALL detect recurring failure sequences that span multiple runs.
4. THE cross-run analysis SHALL identify patterns including repeated tool-call failures, consistent timeout patterns, systematic mis-routing, and degradation trends.
5. THE cross-run analysis SHALL produce a comparative report showing failure-frequency changes across runs.
6. WHEN a pattern is detected across runs, THE RLM cross-run analysis SHALL estimate a confidence interval for the pattern's significance.

---

## Module 4: Integration and Operational Requirements

### Requirement 13: Per-Tool RLM Activation

**User Story:** As a Loom admin, I want RLM to be activated inside the specific tools that actually generate text, based on measurable input-size signals those tools already compute, so that RLM is used only where its cost is justified and the orchestrator classifier stays unchanged.

#### Acceptance Criteria

1. THE Orchestrator classifier SHALL NOT route requests to RLM and SHALL NOT include a pre-retrieval token estimate, since classification occurs before retrieval and the classifier is keyword/regex based.
2. THE Spec_Session_Tool SHALL decide whether to invoke RLM based on reference count and projected output length known after retrieval, per the thresholds in Requirement 3.
3. THE Provenance_Tool SHALL decide whether to invoke RLM based on node count of the serialized subgraph, per the thresholds in Requirement 2.
4. THE HALO_Module SHALL decide whether to invoke RLM based on serialized trace size, per the thresholds in Requirements 11 and 12.
5. EACH tool SHALL log every RLM activation decision with the measured signal, threshold, tool identifier, and final routing outcome into the Audit_Trail.
6. IF the RLM_Module is unavailable or misconfigured, EACH tool SHALL fall back to its standard non-RLM path and SHALL append an `rlm_unavailable_fallback` warning to the response.

### Requirement 14: RLM Provider Abstraction

**User Story:** As a Loom admin, I want RLM to support multiple LLM providers, so that I can use the best model for each use case without vendor lock-in.

#### Acceptance Criteria

1. THE RLM_Module SHALL support OpenAI, Azure OpenAI, Anthropic, and open-weight models (Qwen, Llama) as underlying LLM providers.
2. THE RLM_Module SHALL support different models for root LLM and sub-LM calls (for example, a larger root model with a smaller sub-call model).
3. THE RLM_Module SHALL provide a unified configuration schema for model selection, pricing, and token limits per provider.
4. WHEN a provider returns a transient error, THE RLM_Module SHALL apply configurable retry logic with exponential backoff.
5. THE RLM_Module SHALL support Azure OpenAI with correct API version handling for the configured deployment.
6. THE RLM_Module SHALL log provider-specific metrics (tokens used, latency, cost) for cost attribution and optimization.

### Requirement 15: HALO Dashboard Integration

**User Story:** As a Loom admin, I want HALO findings visible in the Loom portal dashboard, so that I can monitor harness health and improvement opportunities without CLI access.

#### Acceptance Criteria

1. THE Loom portal SHALL expose a HALO dashboard showing active failure modes, recent Evidence_Corpus exports, and pending remediation suggestions.
2. THE HALO dashboard SHALL display failure-mode frequency trends over time.
3. THE HALO dashboard SHALL provide drill-down from failure-mode summaries to detailed Evidence_Corpus views.
4. THE HALO dashboard SHALL show Change_Manifest history with outcome attribution (EFFECTIVE, PARTIALLY_EFFECTIVE, MIXED, INEFFECTIVE, or HARMFUL).
5. WHERE external observability tools are configured (LangSmith, FalkorDB UI), THE HALO dashboard SHALL provide deep links to those tools.
6. THE HALO dashboard SHALL support filtering by time range, failure type, engineer_id, and project_id.

### Requirement 16: Containerized Deployment

**User Story:** As a Loom admin, I want RLM and HALO components deployable via Docker Compose alongside existing Loom services, so that the integrated system runs consistently across environments.

#### Acceptance Criteria

1. THE RLM_Module SHALL be packaged as a Docker image with the Python REPL environment and required dependencies.
2. THE HALO_Module SHALL be packaged as a Docker image compatible with the existing orchestrator container.
3. THE Docker Compose configuration SHALL include resource limits for RLM containers (memory, CPU) to prevent resource contention.
4. THE Docker Compose configuration SHALL mount persistent volumes for trace data and Evidence_Corpus exports.
5. THE RLM container SHALL support multiple sandbox modes, with Docker-in-Docker for production isolation and local mode only for development.
6. THE deployment documentation SHALL include configuration examples for Modal, E2B, and Prime sandbox environments.

---

## Cross-Cutting Requirements

### Requirement 17: Observability and Debugging

**User Story:** As a Loom admin, I want detailed observability for RLM and HALO operations, so that I can debug issues and optimize performance.

#### Acceptance Criteria

1. THE RLM_Module SHALL emit OTLP-shaped spans for all REPL operations, sub-LM calls, and context transformations into the Audit_Trail.
2. THE HALO_Module SHALL emit OTLP-shaped spans for trace ingestion, analysis iterations, and Evidence_Corpus generation into the Audit_Trail.
3. WHEN LangSmith tracing is enabled, THE RLM and HALO spans SHALL appear in LangSmith Studio with proper parent-child relationships via `parent_span_id`.
4. THE RLM_Module SHALL log each REPL code execution with truncated output for debugging.
5. THE HALO_Module SHALL log failure-mode detection decisions with evidence excerpts.
6. THE system SHALL provide a CLI tool for replaying RLM trajectories and HALO analysis runs for debugging.

### Requirement 18: Security and Access Control

**User Story:** As a Loom admin, I want RLM and HALO operations subject to the same access controls as other Loom operations, with sandbox isolation on RLM-generated code, so that unauthorized users cannot access traces or modify the harness and model-written code cannot escape its sandbox.

#### Acceptance Criteria

1. THE RLM API endpoints SHALL require the same API-key authentication as existing orchestrator endpoints.
2. THE HALO trace analysis endpoints SHALL require an admin role for access.
3. THE Evidence_Corpus export SHALL respect data isolation boundaries (engineer_id, project_id) based on the requester's permissions.
4. THE RLM REPL environment SHALL execute in an isolated sandbox (Docker, Modal, or E2B) with no host filesystem access except explicitly mounted input and output volumes, no outbound network access except approved LLM provider endpoints, and enforced CPU, memory, and wall-clock time limits.
5. THE Change_Manifest application endpoint SHALL require an admin role and SHALL log every application with the admin identity, timestamp, and manifest identifier.

### Requirement 19: Performance and Scalability

**User Story:** As a Loom admin, I want RLM and HALO operations to scale with the existing Loom infrastructure, so that long-context queries and trace analysis do not degrade system performance.

#### Acceptance Criteria

1. THE RLM_Module SHALL support concurrent RLM calls up to a configurable limit with a default of 5.
2. THE RLM_Module SHALL queue requests beyond the concurrency limit and process them in FIFO order.
3. THE HALO trace analysis SHALL process new traces incrementally without blocking live operations.
4. THE Evidence_Corpus export SHALL complete within 60 seconds for corpora containing up to 10,000 traces.
5. THE RLM-based retrieval SHALL return results within 120 seconds for queries whose materialized context is up to 500,000 tokens.
6. THE system SHALL monitor RLM and HALO resource utilization and SHALL emit an alert when utilization approaches configured limits.

### Requirement 20: RLM Value Validation Spike

**User Story:** As a Loom admin, I want a standalone, measurable POC comparing RLM to the existing retrieval-plus-standard-LLM baseline before any production integration, so that RLM is only wired into Loom where it demonstrably improves outcomes.

#### Acceptance Criteria

1. THE Value_Validation_Spike SHALL be implemented as a standalone script outside production code paths, operating against real retrieved references and real provenance subgraphs with no mock data.
2. THE Value_Validation_Spike SHALL target a concrete use case — spec-session artifact generation with a reference set of 20 or more documents.
3. THE Value_Validation_Spike SHALL produce both a baseline output (current Loom retrieval plus standard LLM call) and an RLM output for the same inputs.
4. THE Value_Validation_Spike SHALL measure and report at least citation completeness (fraction of provided references cited in the output), output-quality score from a documented rubric, and total cost and latency per run.
5. IF the Value_Validation_Spike does not demonstrate measurable improvement on citation completeness or output quality at acceptable cost and latency, THEN RLM SHALL NOT be integrated into the targeted production tool.
6. THE Value_Validation_Spike results SHALL be recorded in `loom/artifacts/` with the spike inputs, outputs, metrics, and the go/no-go decision, and SHALL be referenced by any subsequent RLM integration requirement's implementation.

---

## Property-Based Testing Considerations

The following acceptance criteria are well-suited for property-based testing using Hypothesis or similar frameworks. Criteria that test external services, infrastructure, or UI layers are listed separately as integration-test candidates.

### Invariants (State Properties)

| Requirement | Property | Test Strategy |
|---|---|---|
| 1.4, 1.5 | Recursion depth never exceeds the configured limit, and default depth is 1 | Generate random RLM call sequences; assert `recursion_depth <= configured_limit` and assert `configured_limit == 1` unless explicit override is supplied |
| 2.6, 3.5, 11.x | Budget termination returns a partial result with a budget_exceeded warning | Generate RLM scenarios that exhaust budgets; assert `partial_result is not None` AND warnings contain a `budget_exceeded` entry |
| 5.1, 5.2 | Cost and latency never exceed configured limits | Generate random RLM workloads; assert `total_cost <= max_cost` AND `total_latency <= max_latency` |
| 6.1 through 6.4 | All span-shaped records have the required OTLP-shaped fields | Generate random workflow executions; assert every record has `span_id`, `trace_id`, `parent_span_id` (nullable only for root), `name`, `start_time`, `end_time`, `status`, `attributes`, `events` |
| 17.3 | Parent-child span relationships are consistent | Generate traces; assert every non-root span's `parent_span_id` resolves to an existing span in the same `trace_id` |

### Round-Trip Properties

| Requirement | Property | Test Strategy |
|---|---|---|
| 3.6 | Every citation in the generated artifact resolves to a node in the knowledge corpus | Generate spec-session artifacts; parse citations; assert each citation references a node present in the corpus |
| 6.1, 6.5 | Extended span-shaped record round-trips through the ingestion/parse path | Generate records; write JSONL; parse back; assert parsed record equals the original, preserving both legacy and span-shaped fields |
| 8.1 through 8.6 | Evidence_Corpus metadata accurately describes contents | Export a corpus; parse `index.json`; assert every file listed in the index exists on disk and every on-disk file is listed in the index |

### Metamorphic Properties

| Requirement | Property | Test Strategy |
|---|---|---|
| 3.1 | The 20-reference-or-50K-token threshold correctly triggers RLM inside the Spec_Session_Tool | Generate requests with varying reference counts and projected output sizes; assert `refs >= 20 OR projected_tokens >= 50000` iff the tool activates RLM |
| 2.1 | The 500-node threshold correctly triggers RLM inside the Provenance_Tool | Generate subgraphs of varying node counts; assert `node_count > 500` iff the tool activates RLM |
| 7.4 | The 5 percent failure-frequency threshold triggers systemic-mode flagging | Generate trace sets with controlled failure rates; assert frequency above 5 percent iff flagged as systemic |

### Confluence Properties

| Requirement | Property | Test Strategy |
|---|---|---|
| 1.3 | Different sandbox backends produce equivalent results for the same input | Execute identical RLM queries in Docker vs Modal sandboxes with fixed seeds; assert outputs equivalent within documented tolerance |
| 14.1 | Different providers produce equivalent results for the same input | Execute identical queries with different providers using fixed seeds; assert outputs equivalent within documented tolerance |

### Set Membership Invariants

| Requirement | Property | Test Strategy |
|---|---|---|
| 2.4, 4.5 | Contradiction detection flags fact pairs with overlapping validity windows and conflicting values | Generate fact pairs with controlled overlap and value conflicts; assert contradictions flagged exactly when both conditions hold |
| 9.3 | Change_Manifest evidence references point to existing files | Generate Change_Manifests; assert every `evidence_ref` resolves to an actual file on disk |
| 11.5 | RLM trace-analysis findings reference valid source spans | Generate trace analyses; assert every finding's `span_id` reference is valid within the analyzed `trace_id` |

### Security Invariants

| Requirement | Property | Test Strategy |
|---|---|---|
| 18.1 | Unauthenticated requests return 401 | Generate requests without API keys; assert 401 response |
| 18.2 | Non-admin requests to admin endpoints return 403 | Generate non-admin requests to HALO endpoints; assert 403 response |
| 18.4 | Sandbox isolation blocks host filesystem and non-approved egress | Generate RLM-produced code that attempts host filesystem writes and outbound connections to non-approved endpoints; assert attempts blocked by the sandbox configuration |

### Performance Bounds

| Requirement | Property | Test Strategy |
|---|---|---|
| 19.1 | Concurrent active RLM calls never exceed the configured limit | Generate concurrent request bursts; assert `active_calls <= max_concurrent` at every sampled instant |
| 19.4, 19.5 | Response times within configured bounds | Generate workloads; assert documented latency percentiles within SLA |

### Value Validation Invariants

| Requirement | Property | Test Strategy |
|---|---|---|
| 20.1 | Spike operates only on real inputs | Scan the spike script for mock-data imports and fixture stubs; assert none present |
| 20.3, 20.4 | Baseline and RLM outputs are produced for the same inputs with metrics recorded | Run the spike on a fixed input set; assert both outputs exist and the metrics report lists citation completeness, quality score, cost, and latency per run |
| 20.5 | Go/no-go gate is enforced in downstream integration | Simulate a no-go spike result; assert downstream RLM integration code paths refuse to activate and fall back to standard tools |

### Integration Test Candidates (Not Property-Based)

The following require integration tests with representative examples rather than generative property tests:

- Requirement 2.2, 2.3: Deep provenance traversal programmatic filters (complex stateful behavior over a real subgraph).
- Requirement 3.2, 3.3, 3.4: Spec-session artifact generation workflow (complex multi-step, stateful).
- Requirement 6.2, 6.3: End-to-end span emission for a live orchestrator run (best validated against actual `orchestrator_audit.jsonl` output).
- Requirement 15: HALO Dashboard Integration (UI layer).
- Requirement 16: Containerized Deployment (infrastructure).
- Requirement 20.2: Specific use-case selection for the spike (one-off setup).

---

## Implementation Priorities

Per the Loom steering rule "Module-by-module: never integrate multiple complex systems in one shot", and per the observation that HALO offers low-risk, immediately measurable value while RLM carries higher integration and quality risk, work is sequenced HALO-first with RLM gated behind a value-validation spike. Per "No mock data in migration or integration code", every phase below operates against real traces, real retrieval output, and real provenance data.

### Phase 1: HALO Foundation (Priority: High)

- Requirement 6: Trace Collection and OTLP-Shaped JSONL Extension
- Requirement 7: HALO Trace Analysis Engine
- Requirement 8: Evidence Corpus Generation
- Requirement 17: Observability and Debugging

This phase is low-risk. It extends the existing audit JSONL with span-shaped fields and runs HALO analysis against data Loom already produces. No new runtime inference infrastructure is introduced. Value is measurable immediately against existing audit logs.

### Phase 2: RLM Value Validation Spike (Priority: High, Gating)

- Requirement 20: RLM Value Validation Spike

This phase is a standalone POC that compares RLM to the current retrieval-plus-standard-LLM baseline on spec-session artifact generation. If the spike does not demonstrate measurable improvement on citation completeness or output quality at acceptable cost and latency, RLM is NOT integrated into any production tool and Phases 3 and 4 are cancelled.

### Phase 3: RLM Integration in Spec-Session (Priority: Medium, gated by Phase 2)

- Requirement 1: RLM Infrastructure Setup
- Requirement 3: Spec-Session Artifact Generation with RLM
- Requirement 5: RLM Cost and Latency Guardrails
- Requirement 13: Per-Tool RLM Activation
- Requirement 14: RLM Provider Abstraction
- Requirement 18: Security and Access Control

### Phase 4: RLM for Provenance and Long Traces (Priority: Medium, gated by Phase 2)

- Requirement 2: RLM for Deep Provenance Traversal
- Requirement 4: Provenance Trace Analysis with RLM
- Requirement 11: Long-Trace Analysis with RLM
- Requirement 12: Cross-Run Pattern Detection with RLM

### Phase 5: HALO Self-Improvement Loop (Priority: Medium, operator-reviewed)

- Requirement 9: Change Manifest Generation
- Requirement 10: Operator-Reviewed Harness Improvement Suggestions
- Requirement 15: HALO Dashboard Integration

No automated harness application. Every Change_Manifest requires explicit admin approval.

### Phase 6: Operational Hardening (Priority: Lower)

- Requirement 16: Containerized Deployment
- Requirement 19: Performance and Scalability
