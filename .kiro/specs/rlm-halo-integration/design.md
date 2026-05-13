# Design Document — RLM/HALO Integration for Loom

## Overview

Loom today has a working multi-stage retrieval pipeline (`loom/retrieval/pipeline.py`: global community search → local hybrid search → MMR rerank → evidence chain assembly) and a LangGraph orchestrator (`loom/orchestrator/workflow.py`) that coordinates classify → research → memory → code → draft → verify. Two concrete gaps remain: (1) text-producing tools — spec-session artifact rendering and provenance explanation — can hit long-context limits when reference sets or serialized subgraphs are very large, and (2) systemic harness failure modes in orchestrator traces are not surfaced, because `loom/artifacts/orchestrator_audit.jsonl` is only consulted in the dashboard aggregator, not analyzed for failure patterns.

This design addresses both gaps with a two-track approach sequenced HALO-first. Track A extends `orchestrator_audit.jsonl` additively with OTLP-shaped span fields and runs a HALO analyzer out-of-band, with zero risk to the production request path. Track B is a hard-gating value-validation spike for RLM: only if the spike shows measurable improvement on a real spec-session workload does RLM get wired into specific tools (`render_artifact`, the provenance explainer, and long-trace HALO analysis). Tracks C–F are explicitly gated by Track B. This ordering reflects the Loom steering rule: "Module-by-module — never integrate multiple complex systems in one shot."

## Design Goals and Constraints

Loom steering rules that shape this design (from `.kiro/steering/loom-core.md`):

- **Zero-Skip Policy** — no placeholder adapters, no TODO shims. If RLM is integrated into a tool, it is integrated end-to-end with a working sandbox and a working fallback.
- **No mock data in migration or integration code** — every RLM and HALO call in production code paths runs against real traces, real retrieved references, and real provenance subgraphs. Mocks exist only in unit/property tests.
- **Module-by-module** — HALO ships before RLM. RLM spike ships before any RLM tool integration. Tracks C/D/E/F do not start until their gate is satisfied.
- **Keep files under 200 lines** — every new module introduced by this design is scoped to one responsibility and sized accordingly (client, adapter per tool, converter, analyzer, evidence exporter, manifest writer).

Requirements-derived constraints:

- **Default recursion depth is 1** (Req 1.4). Depths above 1 require explicit override plus an audit-recorded warning (Req 1.5) per the RLM reproduction study.
- **Sandbox isolation, not source-code sanitization** (Req 18.4). The correct control for RLM-generated code is an isolated runtime (Docker-in-Docker / Modal / E2B), not string filtering of model output.
- **The value-validation spike (Req 20) is a hard gate** for Phase 3/4. Phase 3/4 code refuses to activate until a recorded "go" decision exists.
- **Fields are additive** (Req 6.5). Legacy `audit_id`, `timestamp`, `action`, `request_context`, `request`, `result` remain unchanged; new span-shaped fields are appended in the same record.
- **Classifier stays keyword/regex** (Req 13.1). No RLM routing at classification time and no `estimated_context_tokens` field in `ClassificationResult`.

## System Context Diagram

```mermaid
flowchart LR
  subgraph Request_Path[Production Request Path]
    Client[Engineer / Consumer Client]
    Orchestrator[orchestrator/workflow.py<br/>classify → research → memory → code → draft → verify]
    SpecTool[orchestrator/spec_session.py<br/>render_artifact]
    ProvTool[loom-services<br/>/api/v1/node/{id}/provenance]
    Retrieval[retrieval/pipeline.py<br/>unchanged]
    Audit[(orchestrator_audit.jsonl<br/>+ span fields)]
  end

  subgraph RLM_Runtime[RLM Runtime — gated by spike]
    RLMClient[rlm/client.py<br/>RLMClient]
    Sandbox[rlm-runtime container<br/>Docker-in-Docker / Modal / E2B]
    SpecAdapter[rlm/adapters/spec_session.py]
    ProvAdapter[rlm/adapters/provenance.py]
  end

  subgraph HALO_Out_of_Band[HALO — admin, out of hot path]
    Converter[halo/trace_converter.py]
    Analyzer[halo/analyzer.py]
    Evidence[halo/evidence.py]
    Manifests[halo/manifests.py]
    EvidenceDir[(loom/artifacts/halo/<br/>evidence_corpus + change_manifests)]
  end

  Client -->|/api/v1/ask, /spec/generate| Orchestrator
  Orchestrator --> Retrieval
  Orchestrator --> SpecTool
  Orchestrator --> Audit
  SpecTool -- large ref set --> SpecAdapter
  SpecAdapter --> RLMClient --> Sandbox
  ProvTool -- >500 nodes --> ProvAdapter
  ProvAdapter --> RLMClient
  SpecTool --> Audit
  ProvTool --> Audit

  Audit --> Converter --> Analyzer --> Evidence --> EvidenceDir
  Analyzer --> Manifests --> EvidenceDir
```

Key properties of this topology:
- The classifier (`loom/orchestrator/classifier.py`) and workflow nodes (`_classify/_research/_memory/_code/_draft/_verify`) are unchanged — they remain coordinator-only. RLM is invoked **inside** `render_artifact` and the provenance explainer, not from the workflow graph.
- HALO never blocks a production request. The analyzer reads `orchestrator_audit.jsonl` on an admin trigger or a cron, writing outputs under `loom/artifacts/halo/`.
- RLM does **not** re-run retrieval. It consumes an already-retrieved reference set (spec-session) or the already-retrieved provenance subgraph from `loom-services`.


## Track A: HALO Integration (Phase 1) — no RLM dependency

Track A is the cheapest, lowest-risk improvement available and ships first. It extends the existing audit JSONL additively and introduces an out-of-band analyzer.

### A.1 Additive span extension in `OrchestratorAuditLogger`

`loom/orchestrator/audit.py` currently writes `{audit_id, timestamp, action, request_context, request, result}`. Track A extends this with OTLP-shaped fields produced by a new `record_span()` method on the same class. The existing `record()` call sites stay; internally they now call `record_span()` with the action as `name`, a fresh `span_id`, `trace_id = audit_id` for root actions, and `parent_span_id = None`.

New signature (additive):

```
class OrchestratorAuditLogger:
    def record(self, *, action, context, request, result) -> str: ...  # unchanged public surface
    def record_span(
        self,
        *,
        trace_id: str | None,
        parent_span_id: str | None,
        name: str,
        context: APIRequestContext,
        attributes: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
        start_time: str,
        end_time: str,
        status: Literal['ok', 'error', 'needs_human'] = 'ok',
        request: dict | None = None,
        result: dict | None = None,
        action: str | None = None,
    ) -> SpanRecord: ...
```

Each record emitted by `record_span()` serializes to a single JSONL line containing both the legacy tuple and the span fields. Backward compatibility: any consumer reading only the legacy fields continues to work.

### A.2 Workflow-node and tool spans

`OrchestratorWorkflow._classify / _research / _memory / _code / _draft / _verify` each wrap their body in a context-managed span. The workflow node span is a child of the root request span (whose `span_id == trace_id`). Each downstream tool call inside a node (`LoomServiceClient.query/search`, `AMSClient.recall/resume`, `CMMClient.search_code/detect_changes`) emits its own child span with `parent_span_id = <node_span_id>`. Error and warning events become span `events`.

This gives HALO the trace shape it expects without requiring a full OpenTelemetry collector.

### A.3 HALO out-of-band pipeline

Three modules, single responsibility each (under 200 lines):

- `loom/halo/trace_converter.py` — reads the extended JSONL and produces a normalized trace corpus keyed by `trace_id`.
- `loom/halo/analyzer.py` — clusters failure patterns (hallucinated tool calls, malformed tool args, refusal loops, timeout patterns, zero-result cascades) and flags any cluster appearing in >5% of traces in the window as a `Systemic_Failure_Mode` (Req 7.4). Supports incremental analysis by persisting a cursor over the JSONL byte offset.
- `loom/halo/evidence.py` — writes `loom/artifacts/halo/evidence_corpus/<timestamp>/{overview.md, detail/, raw/, index.json}`.

### A.4 REST surface for HALO (admin-only)

Added to `loom/orchestrator/app.py` via `_read_admin_context`:

- `POST /admin/halo/analyze` — run analysis over a time window; returns an `AnalysisReport`.
- `POST /admin/halo/evidence_corpus` — export an `Evidence_Corpus` with filters (time range, failure type, engineer_id, project_id, min frequency).
- `GET /admin/halo/change_manifests` — list and read manifests.

HALO is **not** exposed through `mcp_server.py`. MCP tools are engineer-facing; HALO is admin-only review.

### A.5 `halo-tools` compose service

A new `halo-tools` service is added to `loom/docker-compose.yml`. It has no runtime port. It mounts `./artifacts` read-write and ships the HALO CLI so an admin can run:

```
docker compose run --rm halo-tools analyze --since 7d
docker compose run --rm halo-tools export_evidence_corpus --since 7d
```

Because HALO reads the JSONL that the 8 existing passing orchestrator integration tests already produce, no synthetic trace seeding is required.

## Track B: RLM Value Validation Spike (Phase 2, gating)

Track B is a standalone spike that blocks Tracks C and D. Its output is an admin-recorded go/no-go decision.

### B.1 Spike script

`loom/spikes/rlm_spec_session_spike.py` — a single script, not production code. Responsibilities:

1. Pick a real spec-session target with ≥20 retrieved references (Req 20.2). The script resolves the target from a named objective_id/artifact_type pair passed on the command line; no synthetic fixtures.
2. Produce two outputs for the same inputs: a **baseline** (current path through `spec_session.render_artifact()`) and an **RLM** output (same inputs, but rendered via a draft `render_artifact_rlm()`). Both outputs operate on the same already-retrieved reference set.
3. Compute metrics and write them.

Output layout under `loom/artifacts/rlm_spike/<timestamp>/`:

```
baseline_output.md
rlm_output.md
metrics.json        # {citation_completeness, quality_score, total_cost_usd, wallclock_seconds}
decision.md         # admin-recorded "go" | "no-go" with rationale
inputs/             # serialized reference set for reproducibility
```

### B.2 RLM library candidates

The spike is responsible for picking one, documenting the choice, and recording evidence. Candidates considered (final selection deferred to the spike task):

| Candidate | Sandbox support | Azure compatibility | Maintenance | License notes |
|---|---|---|---|---|
| `alexzhang13/rlm` (reference impl from the RLM paper) | Local Python REPL; bring-your-own sandbox | Direct Azure OpenAI via `openai` | Research repo; low release cadence | Check repo LICENSE before taking a hard dependency |
| `rlm-python` | Pluggable executors; Docker backend available | Through standard `openai`/`litellm` shim | Community | Check before commit |
| `fast-rlm` | Focused on throughput; sandboxing left to caller | Relies on `litellm` | Community | Check before commit |
| DSPy's RLM module | Integrates with DSPy programs; no built-in sandbox | Works with DSPy's LM abstractions (Azure supported via DSPy) | Actively maintained | Apache-2.0 per DSPy |

Selection criteria the spike SHALL record: sandbox integration cost, Azure GPT-5 wrapper compatibility (Loom's existing Graphiti Azure wrapper should be reusable), depth-limit support, and license compatibility.

### B.3 Gate enforcement

A prior "go" decision is a **precondition** for Phase 3 and Phase 4 tasks. The enforcement is a two-layer check:

1. At the tool level: `SpecSessionTool` and the provenance tool each call `rlm.gate.is_go()` which reads the most recent `decision.md`. If no `go` decision exists, the tool path short-circuits to its baseline (existing) rendering and appends the warning `rlm_gate_pending`.
2. At the tasks.md level: tasks in Phase 3/4 explicitly check for `loom/artifacts/rlm_spike/<...>/decision.md` containing `go` before they are allowed to begin. This is encoded in the spec's `tasks.md` preconditions (next workflow step).


## Track C: RLM in Spec-Session (Phase 3, gated by Track B)

### C.1 Activation decision lives in `render_artifact` (or sibling)

`loom/orchestrator/spec_session.py:render_artifact()` is the only text-producing step in the spec-session path. The activation gate (Req 3.1) is: `len(references) >= 20 OR projected_output_tokens >= 50_000`. Both signals are computable after retrieval; neither requires a change to `classifier.py`.

Implementation choice: add a sibling `render_artifact_rlm()` in a new layer (`loom/rlm/adapters/spec_session.py`) that returns the **same shape** as the existing `render_artifact()` dict. Callers in `app.py` and `mcp_server.py` dispatch:

```
if should_use_rlm(references, projected_tokens) and rlm.gate.is_go():
    rendered = render_artifact_rlm(..., budget=...)
else:
    rendered = render_artifact(...)
```

The existing `render_artifact()` is unchanged. That preserves the traceability/citation logic already covered by integration tests and makes the RLM path easy to remove if it regresses.

### C.2 Reference binding and iterative rendering

The adapter binds the full retrieved reference set to a REPL corpus variable. It issues recursive sub-calls (depth ≤ 1 default) that accumulate citations section-by-section (Req 3.3). Lineage metadata (objective_id, session_id, engineer_id, steering_paths, supporting_node_ids) is threaded through every sub-call so the final assembled dict keeps the same traceability guarantees as the baseline (Req 3.4).

When the rendered artifact exceeds 100K tokens, the adapter writes to a REPL file variable and returns a file handle reference instead of the full text in context (Req 3.5).

Citation resolution (Req 3.6) is a post-condition: every citation in the rendered output MUST resolve to a supporting node id in the knowledge corpus. If not, the adapter raises — it does not silently fall back.

### C.3 Fallback semantics

If `RLMClient` raises, times out, is misconfigured, or `gate.is_go()` is false, the caller falls back to `render_artifact()` and appends `rlm_unavailable_fallback` (Req 13.6). No 500 response is emitted to the client for an RLM availability issue. This is consistent with Loom's existing pattern of degrading gracefully on `CMMClient` unavailability.

## Track D: RLM for Provenance and Long Traces (Phase 4, gated by Track B)

### D.1 Deep provenance traversal

The provenance traversal tool is exposed by `loom-services` via `/api/v1/node/{id}/provenance`. The RLM adapter (`loom/rlm/adapters/provenance.py`) consumes the already-retrieved subgraph JSON — **RLM does not re-run retrieval**. The activation gate is `node_count > 500` (Req 2.1). Under the threshold, the existing short-path explanation is used (Req 2.5).

Features of the adapter:

- Binds the serialized subgraph to a REPL variable.
- Exposes programmatic filters for source_pipeline, confidence threshold, edge type, and temporal validity window (Req 2.2).
- Produces a human-readable explanation with explicit citations (source_system, source_pipeline, source_file, confidence) (Req 2.3).
- Flags contradictions across overlapping validity windows (Req 2.4).
- On budget overrun, returns the partial chain with `rlm_budget_exceeded` warning (Req 2.6).

### D.2 Long-trace HALO analysis

When a HALO analysis request's serialized trace corpus exceeds 100K tokens (Req 11.1), the analyzer invokes RLM rather than attempting a direct LLM call. The RLM trace analyzer loads the full corpus as a REPL variable, exposes filters by span type/error code/time range/workflow node (Req 11.3), and supports depth-1 sub-queries to drill into failure clusters (Req 11.4). Output remains Evidence_Corpus-compatible (Req 11.6).

Cross-run pattern detection (Req 12) follows the same structure: multiple trace files combined into a single REPL corpus, comparative frequency reporting, confidence-interval estimation on detected patterns.

## Track E: HALO Self-Improvement Loop (Phase 5, operator-reviewed)

### E.1 Change manifest generation

`loom/halo/manifests.py` writes versioned `ChangeManifest` entries to `loom/artifacts/halo/change_manifests/<timestamp>_<slug>.json`. Each manifest references specific files in the Evidence_Corpus that motivated the change (Req 9.3), lists predicted task-level impacts (Req 9.4), and records risk notes.

After an operator applies a change and a measurement window passes, `attribute_outcome()` compares predicted to actual outcomes and writes an attribution report classifying the outcome as `EFFECTIVE | PARTIALLY_EFFECTIVE | MIXED | INEFFECTIVE | HARMFUL` (Req 9.6).

### E.2 Remediation suggestions

On detecting a systemic mode, the analyzer emits at least one remediation suggestion (Req 10.1) with evidence backing, effort level, expected impact, and confidence score. Conflicts between suggestions are flagged with resolution approaches (Req 10.5). **No automated application.** Every apply requires admin approval through a separate endpoint (Req 10.6, 18.5) that logs admin identity, timestamp, and manifest id.

### E.3 Portal dashboard

The Loom portal consumes the HALO outputs through a set of read endpoints under `/admin/halo/*`. Visualization is a portal concern; this design specifies the data contract only:

- Active failure modes list (from the latest AnalysisReport).
- Failure-mode frequency over time (aggregated across AnalysisReports).
- Drill-down from summary to Evidence_Corpus views (by `evidence_corpus_path`).
- Change_Manifest history with outcome attribution.
- Deep links to LangSmith and FalkorDB UI reuse the existing `orchestrator/portal_links.py` builder.

## Track F: Operational Hardening (Phase 6)

### F.1 Container layout

- `halo-tools` (Track A): CLI container, mounts `./artifacts`, no exposed port.
- `rlm-runtime` (Track C/D, only after spike "go"): runs the RLM REPL in isolation. Production default is Docker-in-Docker with CPU/memory/wallclock limits in the compose service definition; alternatives are Modal (remote) and E2B (remote). Local REPL mode is dev-only and is gated by `LOOM_DEPLOYMENT_ENV=development`.
- Volumes: `rlm-runtime` mounts input corpora read-only and writes outputs to a dedicated volume. No `./artifacts` read-write mount for rlm-runtime (writes go through the orchestrator, not directly).

### F.2 Resource limits and concurrency

- RLMClient enforces a configurable concurrency limit (default 5, Req 19.1) through a bounded asyncio semaphore.
- Queued requests process FIFO (Req 19.2).
- Per-call wallclock enforced by the sandbox runtime, not Python.
- HALO analyzer processes incrementally (cursor over the JSONL) to avoid blocking live operations (Req 19.3).

### F.3 Observability

- All workflow nodes and tool calls emit spans through `OrchestratorAuditLogger.record_span()` (Track A).
- RLM sub-calls emit child spans whose `parent_span_id` is the enclosing tool span (Req 17.1).
- `common/langsmith_support.traceable` decorators continue to work unchanged; LangSmith Studio sees the same parent-child structure (Req 17.3).
- Two CLIs under `loom/tools/`: `halo_replay.py` reconstructs a trace from JSONL for debugging; `rlm_replay.py` replays an RLM trajectory including REPL variable state transitions (Req 17.6).


## Data Models and Schemas

All additions are additive to existing Loom schemas. Existing consumers of `orchestrator_audit.jsonl` continue to work without change.

### SpanRecord (written by `OrchestratorAuditLogger.record_span`)

```
@dataclass
class SpanRecord:
    # Legacy audit fields — unchanged
    audit_id: str
    timestamp: str
    action: str
    request_context: dict[str, Any]
    request: dict[str, Any] | None
    result: dict[str, Any] | None

    # Additive OTLP-shaped fields
    span_id: str
    trace_id: str               # == audit_id on root spans
    parent_span_id: str | None  # None iff root
    name: str                    # typically == action for root, node name for workflow spans, tool name for tool spans
    start_time: str              # ISO 8601 UTC
    end_time: str                # ISO 8601 UTC
    status: Literal['ok', 'error', 'needs_human']
    attributes: dict[str, Any]   # structured metadata, must be JSON-serializable
    events: list[dict[str, Any]] # error/warning events with {name, timestamp, attributes}
```

### RLMResponse (returned by `RLMClient.completion`)

```
@dataclass
class RLMResponse:
    output: str
    citations: list[dict[str, Any]]
    metrics: RLMMetrics          # {tokens_in, tokens_out, subcalls, wallclock_s, cost_usd}
    warnings: list[str]          # may contain 'budget_exceeded', 'depth_above_default', etc.
    depth_used: int              # actual recursion depth (0 if no sub-call was made)

@dataclass
class RLMMetrics:
    tokens_in: int
    tokens_out: int
    subcalls: int
    wallclock_s: float
    cost_usd: float
```

Partial results are valid: on budget overrun, `output` contains whatever was accumulated and `warnings` contains `budget_exceeded` with the last successfully processed chunk id in `attributes`.

### FailureMode (from HALO analyzer)

```
@dataclass
class FailureMode:
    type: Literal['hallucinated_tool_call', 'malformed_tool_args', 'refusal_loop',
                  'timeout_pattern', 'zero_result_cascade', 'other']
    frequency: float              # fraction of traces in the window
    affected_nodes: list[str]     # workflow node names (e.g. 'research', 'code')
    example_trace_ids: list[str]  # up to N representative trace_ids
    remediation_suggestions: list[RemediationSuggestion]
```

### ChangeManifest (matching Req 9.1 schema)

```
@dataclass
class ChangeManifest:
    manifest_id: str
    component_changed: Literal['prompt', 'tool_description', 'middleware',
                               'orchestration_logic', 'skill', 'memory_integration',
                               'evaluation_criteria']
    description: str
    failure_pattern_addressed: str
    evidence_refs: list[str]      # paths to Evidence_Corpus files (validated)
    root_cause_hypothesis: str
    targeted_fixes: list[str]
    predicted_task_impacts: dict[str, Literal['improve', 'regress', 'neutral']]
    risk_notes: str
    created_at: str
    applied_at: str | None
    applied_by: str | None
    attribution: Literal['EFFECTIVE', 'PARTIALLY_EFFECTIVE', 'MIXED',
                         'INEFFECTIVE', 'HARMFUL'] | None
```

### SpikeMetrics (matching Req 20.4)

```
@dataclass
class SpikeMetrics:
    citation_completeness: float  # fraction of provided references cited in output
    quality_score: float           # rubric-driven, documented in decision.md
    total_cost_usd: float
    wallclock_seconds: float
    baseline_output_path: str
    rlm_output_path: str
    inputs_path: str
```

### EvidenceCorpus layout

On-disk structure under `loom/artifacts/halo/evidence_corpus/<timestamp>/`:

```
overview.md               # high-level summary + remediation priorities
detail/<mode>_<slug>.md    # per-failure-mode analysis
raw/<trace_id>.jsonl       # OTLP-shaped spans for drill-down
index.json                 # machine-readable manifest of every file above
```

`index.json` is a bijection with the on-disk contents (asserted by a property test, see Testing Strategy).

## Component Interfaces

File sizing target: every module listed is single-responsibility and ≤ 200 lines.

### `loom/rlm/client.py` — RLMClient

```
class RLMClient:
    def __init__(self, *, settings: Settings, sandbox: SandboxBackend) -> None: ...
    def completion(
        self,
        prompt: str | dict,
        *,
        model: str,
        depth_limit: int = 1,
        cost_limit_usd: float = 5.0,
        latency_limit_s: int = 180,
        corpus: dict[str, Any] | None = None,   # named REPL variables
    ) -> RLMResponse: ...
    def predict_cost(self, prompt: str | dict, *, model: str) -> float: ...
    def gate_is_go(self) -> bool: ...            # reads latest decision.md
```

`completion()` returns partial results + warnings on budget overrun; does not raise on budget. Raises only on configuration or sandbox-startup errors.

### `loom/rlm/adapters/spec_session.py`

```
def render_artifact_rlm(
    *,
    artifact_type: str,
    prompt: str,
    knowledge: dict[str, Any],
    context: APIRequestContext,
    target_path: Path,
    existing_content: str | None,
    references: list[str],
    operation: str,
    budget: RLMBudget,
) -> dict[str, Any]: ...   # same return shape as spec_session.render_artifact
```

Same return shape guarantees swap-in compatibility.

### `loom/rlm/adapters/provenance.py`

```
def explain_evidence_chain_rlm(
    subgraph_json: dict[str, Any],
    *,
    budget: RLMBudget,
) -> dict[str, Any]: ...   # {explanation, citations, contradictions, warnings}
```

### `loom/halo/trace_converter.py`

```
@dataclass
class ConversionReport:
    input_path: Path
    output_path: Path
    spans_written: int
    traces_written: int
    cursor_byte_offset: int    # for incremental analysis
    warnings: list[str]

def jsonl_to_otlp_shaped(audit_path: Path, output_path: Path) -> ConversionReport: ...
```

### `loom/halo/analyzer.py`

```
class HALOAnalyzer:
    def __init__(self, *, systemic_threshold: float = 0.05) -> None: ...
    def analyze(
        self,
        trace_path: Path,
        *,
        filters: TraceFilters,
    ) -> AnalysisReport: ...
```

### `loom/halo/evidence.py`

```
def export_evidence_corpus(
    report: AnalysisReport,
    out_dir: Path,
    *,
    filters: CorpusFilters,
) -> EvidenceCorpus: ...
```

### `loom/halo/manifests.py`

```
def write_change_manifest(manifest: ChangeManifest, out_dir: Path) -> Path: ...

def attribute_outcome(
    manifest_id: str,
    *,
    before: AnalysisReport,
    after: AnalysisReport,
) -> ChangeManifest: ...   # returns updated manifest with attribution field set
```


## Observability and Audit Strategy

### Span emission path

Every entry and exit from a workflow node in `OrchestratorWorkflow` opens/closes a span through `OrchestratorAuditLogger.record_span()`. Every tool call inside a node emits a child span. The root span's `span_id` is the existing `audit_id` of the request, so `trace_id == audit_id` preserves traceability into the existing audit export endpoint (`/admin/audit/export`).

### RLM sub-call spans

When `RLMClient.completion()` runs, it emits a root RLM span whose `parent_span_id` is the enclosing tool's span (`render_artifact_rlm`, `explain_evidence_chain_rlm`, or the HALO long-trace analyzer). Each sub-LM call emits a child span recording model, tokens_in, tokens_out, cost_usd, wallclock_s, and the chunk identifier it operated on (Req 1.6).

### LangSmith

The existing `common/langsmith_support.traceable` decorators are opt-in and continue to work without changes (Req 17.3). When `LANGSMITH_TRACING=true`, LangSmith Studio sees the same parent-child relationships via `parent_span_id`.

### Retention

Raw span-shaped records are retained per Req 6.6 (default 30 days, configurable). `halo/trace_converter.py` supports reading a windowed slice and persisting a cursor to avoid re-analyzing historical records.

### Replay CLIs

- `loom/tools/halo_replay.py <trace_id>` — reconstructs the ordered span tree for a trace.
- `loom/tools/rlm_replay.py <rlm_span_id>` — prints the RLM trajectory: root prompt, each sub-call input/output, final warnings, and REPL variable state transitions if recorded.

## Security and Sandbox Model

### RLM code-execution controls

RLM's root LLM generates Python expressions that run inside the REPL. The **only** control against malicious or accidental damage is sandbox isolation — not string filtering of the model's output. Any earlier proposal to "sanitize REPL code" is explicitly rejected here because string filters cannot safely constrain arbitrary Python. The sandbox is the trust boundary.

### Sandbox guarantees (Req 18.4)

- **Filesystem:** read-only mount of the input corpus; write-only mount of the output directory. No other host filesystem access.
- **Network egress:** allow-list limited to configured LLM provider endpoints (OpenAI, Azure OpenAI, Anthropic, or the specific open-weight inference endpoint). All other egress denied at the sandbox-network layer.
- **Resource limits:** CPU, memory, and wall-clock limits enforced by the **sandbox runtime** (Docker-in-Docker resource constraints, Modal's per-function limits, or E2B's sandbox config). Python-level timeouts are not load-bearing.
- **Backend default:** Docker-in-Docker in production, with Modal and E2B documented as alternatives (Req 1.3, 16.5, 16.6). Local REPL mode is dev-only and gated by `LOOM_DEPLOYMENT_ENV=development`.

### Auth scopes

- `/admin/halo/*` — admin role via `_read_admin_context` (Req 18.2).
- `/admin/rlm/spike/run` — admin role.
- `/admin/rlm/apply_manifest` — admin role, with admin identity and timestamp logged per application (Req 18.5).
- Consumer keys (`LOOM_CONSUMER_API_KEYS` in `common/auth.py`) MUST NOT reach any HALO or RLM admin endpoint. These endpoints are registered with `admin_only=True`; `allow_consumer=False` semantics are enforced by the existing `build_api_auth_dependency` with the `admin_only` flag set.

### Data isolation (Req 18.3)

Evidence_Corpus exports respect `engineer_id` and `project_id` scoping: the filter step drops traces the requester is not entitled to see before clustering runs. Clustering operates only over traces the requester can access.

## Testing Strategy

The strategy follows Loom's dual-testing principle: unit/property tests for pure logic, integration tests for cross-system behavior.

### When PBT applies

PBT applies to:

- Budget enforcement (pure accounting logic).
- Threshold activation functions (pure predicates).
- Span schema extension (pure serialization).
- Configuration shape (sandbox config, audit shape).
- Auth gate invariants (401/403 rules over random inputs).

PBT does **not** apply to:

- The HALO dashboard (UI).
- Docker Compose bringup (infrastructure smoke).
- Actual sandbox escape prevention (requires a real sandbox; integration test).
- Cross-provider/cross-backend confluence on real LLM outputs (integration test).

### Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

#### Property 1: Default recursion depth is 1

*For any* RLM call made through `RLMClient.completion` without an explicit `depth_limit` override, the call's recorded `depth_used` SHALL be ≤ 1 and the effective `depth_limit` SHALL be 1.

**Validates: Requirements 1.4, 1.5**

#### Property 2: Budget termination returns a partial result plus a `budget_exceeded` warning

*For any* RLM workload whose cumulative cost or latency would exceed the configured budget, the returned `RLMResponse.output` SHALL be non-None, `RLMResponse.warnings` SHALL contain `budget_exceeded`, and the last successfully processed chunk identifier SHALL be present in the associated span's `attributes`.

**Validates: Requirements 2.6, 5.3, 5.4, 11.x**

#### Property 3: Cost and latency never exceed configured limits

*For any* random RLM workload executed against a stubbed sub-LM, the final `metrics.cost_usd` SHALL be ≤ `cost_limit_usd` and `metrics.wallclock_s` SHALL be ≤ `latency_limit_s`.

**Validates: Requirements 5.1, 5.2**

#### Property 4: Pre-execution cost prediction refuses calls above budget

*For any* input prompt whose `predict_cost(...)` result exceeds the configured `cost_limit_usd`, `RLMClient.completion` SHALL refuse to start the call and SHALL return an `RLMResponse` with `warnings` containing `predicted_cost_exceeds_budget` and `metrics.subcalls == 0`.

**Validates: Requirements 5.5**

#### Property 5: Threshold activation is exactly the disjunction `refs ≥ 20 OR projected_tokens ≥ 50_000`

*For any* generated spec-session request with varying reference counts and projected output sizes, the Spec_Session_Tool SHALL invoke `render_artifact_rlm` if and only if `len(references) >= 20 OR projected_tokens >= 50_000`.

**Validates: Requirements 3.1, 13.2**

#### Property 6: Provenance 500-node threshold activates RLM exactly when exceeded

*For any* provenance subgraph of size `n`, the Provenance_Tool SHALL invoke `explain_evidence_chain_rlm` if and only if `n > 500`.

**Validates: Requirements 2.1, 2.5, 13.3**

#### Property 7: Every citation in a rendered artifact resolves to a corpus node

*For any* artifact returned by `render_artifact_rlm`, every citation in the output SHALL reference a node present in the supporting knowledge corpus; otherwise the generation SHALL fail.

**Validates: Requirements 3.6**

#### Property 8: Every span record has the required OTLP-shaped fields and round-trips through JSONL

*For any* span record emitted by `OrchestratorAuditLogger.record_span`, the written JSONL line SHALL parse back into a `SpanRecord` with all of `{span_id, trace_id, parent_span_id (nullable only on root), name, start_time, end_time, status, attributes, events}` present AND all legacy fields `{audit_id, timestamp, action, request_context, request, result}` preserved unchanged.

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

#### Property 9: Parent-child span relationships are consistent within a trace

*For any* span emitted with a non-None `parent_span_id`, that `parent_span_id` SHALL resolve to an existing span whose `trace_id` matches the child's `trace_id`.

**Validates: Requirements 6.2, 6.3, 17.3**

#### Property 10: 5 percent threshold triggers systemic-mode flagging

*For any* trace corpus where a failure mode appears with frequency `f` in a configured window, the HALOAnalyzer SHALL flag the mode as systemic if and only if `f > 0.05`.

**Validates: Requirements 7.4**

#### Property 11: Evidence_Corpus index.json is a bijection with its on-disk contents

*For any* call to `export_evidence_corpus`, the resulting `index.json` SHALL enumerate exactly the set of files that exist under the corpus directory (every indexed path exists; every on-disk file is indexed).

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6**

#### Property 12: ChangeManifest evidence references point to existing files

*For any* `ChangeManifest` produced by `write_change_manifest`, every `evidence_refs` entry SHALL resolve to an actual file in the referenced Evidence_Corpus.

**Validates: Requirements 9.1, 9.3**

#### Property 13: Long-trace findings reference valid source spans

*For any* finding produced by the RLM long-trace analyzer, the finding's `span_id` SHALL resolve to a span in the analyzed `trace_id`.

**Validates: Requirements 11.5**

#### Property 14: The classifier carries no `estimated_context_tokens` and no RLM route

*For any* query string passed to `classify_request`, the returned `ClassificationResult` SHALL NOT contain an `estimated_context_tokens` field and SHALL NOT have `route == 'rlm'`.

**Validates: Requirements 13.1**

#### Property 15: Every RLM activation decision is logged with its measured signal

*For any* tool call reaching the RLM activation check, the audit trail SHALL record the measured signal, the configured threshold, the tool identifier, and the final activation outcome.

**Validates: Requirements 13.5**

#### Property 16: Tools fall back cleanly when RLM is unavailable

*For any* tool invocation where `RLMClient` raises, times out, or `gate.is_go()` is false, the tool SHALL return a non-error result using its baseline non-RLM path and SHALL append the warning `rlm_unavailable_fallback`.

**Validates: Requirements 13.6**

#### Property 17: Admin endpoints reject unauthenticated and non-admin requests

*For any* request to `/admin/halo/*`, `/admin/rlm/spike/run`, or `/admin/rlm/apply_manifest` without a valid admin API key, the response SHALL be 401 (missing/invalid key) or 403 (valid non-admin key). Consumer keys SHALL never satisfy these endpoints.

**Validates: Requirements 18.1, 18.2**

#### Property 18: Sandbox configuration respects isolation invariants

*For any* generated sandbox configuration, the mount list SHALL contain exactly the read-only input mount and the write-only output mount with no additional host-fs mounts, and the egress allow-list SHALL contain only configured LLM provider endpoints.

**Validates: Requirements 18.4**

#### Property 19: Concurrent RLM calls never exceed configured limit

*For any* burst of concurrent RLM requests, the number of simultaneously active calls sampled at any instant SHALL be ≤ the configured concurrency limit; excess requests SHALL queue in FIFO order.

**Validates: Requirements 19.1, 19.2**

#### Property 20: Spike operates only on real inputs

*For any* execution of `loom/spikes/rlm_spec_session_spike.py`, the spike module SHALL NOT import from `unittest.mock` and SHALL NOT load from known fixture packages; all inputs SHALL be loaded from live services or persisted real retrieved reference sets.

**Validates: Requirements 20.1**

#### Property 21: Spike produces both outputs and required metrics

*For any* spike run, the output directory SHALL contain `baseline_output.md`, `rlm_output.md`, and a `metrics.json` whose keys include `citation_completeness`, `quality_score`, `total_cost_usd`, and `wallclock_seconds`.

**Validates: Requirements 20.3, 20.4**

#### Property 22: Go/no-go gate enforced in downstream RLM paths

*For any* tool invocation that would route to RLM, if the most recent `decision.md` does not record `go`, the tool SHALL fall back to its baseline non-RLM path and SHALL append `rlm_gate_pending`.

**Validates: Requirements 20.5, 20.6**

### Property test file map

| Test file (under `loom/tests/`) | Properties covered |
|---|---|
| `test_span_extension.py` | 8, 9, 14 |
| `test_rlm_budgets.py` | 1, 2, 3, 4 |
| `test_rlm_activation_thresholds.py` | 5, 6 |
| `test_per_tool_rlm_activation.py` | 15, 16 |
| `test_citation_resolution.py` | 7 |
| `test_halo_systemic_threshold.py` | 10 |
| `test_evidence_corpus_bijection.py` | 11 |
| `test_change_manifest_evidence.py` | 12 |
| `test_long_trace_findings.py` | 13 |
| `test_admin_auth_invariants.py` | 17 |
| `test_sandbox_config.py` | 18 |
| `test_rlm_concurrency.py` | 19 |
| `test_spike_inputs_real.py` | 20 |
| `test_spike_artifacts.py` | 21 |
| `test_spike_gate_enforcement.py` | 22 |

Each file uses Hypothesis, minimum 100 iterations, and tags each property test with `Feature: rlm-halo-integration, Property N: <text>`.

### Integration tests

Run against real services via Docker Compose (the existing `falkordb`, `loom-services`, `orchestrator`, `hindsight` stack plus the new `halo-tools` service). No synthetic trace seeding is required — the existing **8 passing orchestrator integration tests** produce enough real `orchestrator_audit.jsonl` content to exercise HALO end-to-end.

Integration test coverage:

- **HALO end-to-end:** run Track A analyzer over the JSONL produced by the existing integration-test suite; assert a non-empty AnalysisReport and a readable EvidenceCorpus.
- **Extended span emission:** run one workflow request and assert the emitted JSONL line contains both legacy and span-shaped fields and that child spans exist for each tool call.
- **Spec-session RLM path (Phase 3 only):** drive `/api/v1/spec/generate` with a real ≥20-reference request and assert the RLM adapter is invoked, the output is citation-complete, and fallback triggers when the sandbox is disabled.
- **Provenance RLM path (Phase 4 only):** drive `/api/v1/node/<id>/provenance` on a real subgraph of >500 nodes.
- **Docker Compose bringup smoke (Track F):** `docker compose up halo-tools rlm-runtime` completes successfully with health checks green.
- **Cross-backend confluence (Phase 6):** one-shot integration test exercising the same input on Docker vs Modal sandboxes; equivalence within documented tolerance.

### The spike is a gate, not a test

The value-validation spike (`loom/spikes/rlm_spec_session_spike.py`) is not part of CI. It is a manual, admin-triggered run whose output (`metrics.json` plus admin-signed `decision.md`) is a precondition for Phase 3 and Phase 4 work beginning.


## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| RLM fails to show measurable improvement on the spike | Medium | High on RLM track; zero on HALO track | Req 20 is a hard gate. Phase 3 and 4 do not begin without a recorded "go" decision. HALO (Track A) ships independently and delivers value regardless of the spike outcome. |
| Sandbox escape on RLM-generated code | Low | Critical | Docker-in-Docker / Modal / E2B enforced sandbox; no local REPL in production; network egress allow-list limited to approved LLM endpoints; read-only input mount and write-only output mount; CPU/memory/wallclock enforced by the sandbox runtime, not Python. No string-based "sanitization" of model output — the sandbox is the trust boundary. |
| Trace volume overwhelms HALO analysis | Medium | Medium | Incremental analysis with persisted byte-offset cursor (Req 7.6); configurable retention (Req 6.6); filters on time range, failure type, engineer_id, project_id in both analyze and export. |
| Azure GPT-5 compatibility issues in RLM library | Medium | Medium | Reuse the existing Azure wrapper already in use by Graphiti; spike task evaluates the chosen RLM library specifically against Azure before committing. |
| Adding span fields breaks existing audit consumers | Low | Medium | Additive schema only. Legacy fields `{audit_id, timestamp, action, request_context, request, result}` are unchanged. Property 8 enforces this invariant in tests. |
| Cost runaway inside a deep RLM call | Low | Medium | Three-layer budget: pre-call prediction (Req 5.5), mid-call cumulative token tracking (Req 5.4), post-timeout wallclock (Req 5.2). Property tests on budget enforcement. |
| HALO suggestions applied without operator review | Low | High | No automated apply path exists. `apply_manifest` is admin-only and logs admin identity/timestamp per application (Req 18.5). Operator-reviewed loop is explicit in Track E. |
| Consumer API keys reach HALO or RLM admin endpoints | Low | High | All HALO/RLM admin endpoints registered with `admin_only=True`; `build_api_auth_dependency` rejects consumer keys. Property 17 asserts this. |
| Large rendered spec-session artifacts blow out orchestrator memory | Low | Medium | When rendered artifact exceeds 100K tokens, the RLM adapter writes to a REPL file variable and returns a handle (Req 3.5). Orchestrator receives only a reference, not the full body. |
| RLM spike recursion depth > 1 silently degrades quality | Low | Medium | Default depth is 1 (Req 1.4). Overrides emit a warning recorded in every call's audit record (Req 1.5). Property 1 asserts the default. |
