# Loom Runtime Foundation

This directory contains the first runnable foundation for Loom.

Current scope:

- FalkorDB + Graphiti runtime bootstrap
- Loom services health surface
- Orchestrator health surface
- Graphiti smoke test for the adapter spike

Quick start:

```bash
cp .env.example .env
docker compose up --build falkordb loom-services orchestrator
```

Graphiti smoke test:

```bash
python3.10 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m spikes.graphiti_smoke_test
```

Optional episode ingestion smoke test:

```bash
python -m spikes.graphiti_smoke_test --with-episode
```

The basic smoke test auto-uses a placeholder OpenAI key if no LLM key is set, because index bootstrap does not require a live model call.
The `--with-episode` mode requires either a valid OpenAI-compatible key path or Azure OpenAI settings (`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_LLM_DEPLOYMENT`, `AZURE_OPENAI_LLM_MODEL_NAME`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`).

For GPT-5.4 Azure deployments, use `AZURE_OPENAI_API_VERSION=2025-03-01-preview` or later.
Treat sequential `add_episode` as the supported Graphiti path on Azure GPT-5.4. The benchmarked `add_episode_bulk` path still hits an upstream `max_tokens` incompatibility, so deterministic seed migration plus direct Chroma import remain Loom's seed strategy.

Docker note: the `orchestrator` container does not currently ship a Linux `codebase-memory-mcp` binary or project index state. For Phase 1, use host-native CMM/MCP workflows; container health now reports `cmm_host_native_only` until container packaging is expanded.

Continuity note: the orchestrator now accepts `X-Project-Id` alongside `X-Engineer-Id`, `X-Session-Id`, and `X-Objective-Id`. `/api/v1/memory/retain` can capture `transcript_ref` and `transcript_excerpt`, and `/api/v1/session/resume` returns a budgeted AMS snapshot (default `2000` tokens) with prioritized steering, open-thread, decision, and transcript-reference sections.

Authenticated API usage:

```bash
export LOOM_API_KEY=engineer-local-key
export LOOM_ADMIN_API_KEY=admin-local-key

curl -X POST http://localhost:8090/api/v1/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $LOOM_API_KEY" \
  -d '{"query":"What is XCP?","limit":3}'
```

If both `LOOM_API_KEY` and `LOOM_ADMIN_API_KEY` are unset, the service falls back to a local-development bypass mode.


Deployment runbooks:

- `docs/runbooks/deployment.md`
- `docs/runbooks/operations.md`

Validation scripts:

- `evals/retrieval_eval.py`
- `evals/spec_session_eval.py`
- `evals/ams_eval.py`
- `evals/load_eval.py`

---

## Traceability Tools

Loom provides debuggable retrieval - every query result can be traced back to its source.

### Knowledge Trace CLI

```bash
python loom/tools/trace_knowledge.py "your query here"
```

Example queries:
```bash
python loom/tools/trace_knowledge.py "Eth ARXML spec"
python loom/tools/trace_knowledge.py "CanIf module configuration"
python loom/tools/trace_knowledge.py "XCP DAQ measurement"
```

The tool shows:
1. **Entity Detection** — Query parsed into graph entities
2. **Graph Traversal** — Path through knowledge graph (Hub → Layer → Module)
3. **Evidence Nodes** — Retrieved modules/documents with confidence scores
4. **Provenance Chain** — Full metadata: pipeline, source file, extraction date

Output includes JSON export for programmatic use.

### Provenance API

```bash
# Get node provenance chain
curl http://localhost:8080/api/v1/node/{id}/provenance

# Search with source filters
curl -X POST http://localhost:8080/api/v1/search \
  -d '{"query":"Eth driver", "source_system":"AUTOSAR-fusion"}'
```

### In-Chat Tracing

When using the Loom orchestrator, prefix queries with "trace:" to get provenance:
```
"Trace: What is the EthIf module?"
"Show evidence for: XCP DAQ configuration"
```

---

## Portal and Aggregation APIs

Loom now includes a separate portal app under `../loom-portal` and a new aggregation layer in the orchestrator for novice-friendly traceability and progress views.

### Portal app

```bash
cd ../loom-portal
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

The portal expects the orchestrator at `http://localhost:8080` by default and lets users enter:
- `X-API-Key`
- `X-Engineer-Id`
- `X-Session-Id`
- `X-Objective-Id`
- `X-Project-Id`

### Portal-facing orchestrator endpoints

```bash
# Explain one answer with normalized knowledge + memory + code + workflow traces
curl -X POST http://localhost:8080/api/v1/trace/explain \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $LOOM_API_KEY" \
  -d '{"query":"What are XCP timing constraints?","include_change_impact":true}'

# Objective-level dashboard overview
curl http://localhost:8080/api/v1/dashboard/overview \
  -H "X-API-Key: $LOOM_API_KEY" \
  -H "X-Project-Id: proj-1" \
  -H "X-Objective-Id: obj-1"

# Timeline of normalized journey events
curl http://localhost:8080/api/v1/dashboard/journey \
  -H "X-API-Key: $LOOM_API_KEY" \
  -H "X-Project-Id: proj-1" \
  -H "X-Objective-Id: obj-1"

# Deep links to FalkorDB UI, Hindsight, LangGraph, LangSmith, and CMM UI when configured
curl "http://localhost:8080/api/v1/integrations/links?query=XCP&node_id=node-1" \
  -H "X-API-Key: $LOOM_API_KEY"
```

### Optional UI link environment variables

These power the portal's deep-link launchpad:

- `LOOM_SERVICE_PUBLIC_URL`
- `ORCHESTRATOR_PUBLIC_URL`
- `FALKORDB_UI_URL`
- `HINDSIGHT_UI_URL`
- `LANGGRAPH_UI_URL`
- `LANGSMITH_UI_URL`
- `CMM_UI_URL`

The orchestrator now allows localhost portal origins (`3000` and `3001`) for browser-based development.

### Optional LangSmith tracing

Loom now supports optional LangSmith instrumentation at the orchestrator workflow, portal aggregation, tool-client, and Graphiti Azure/OpenAI wrapper layers.

Enable it with environment variables:

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=replace-with-your-key
export LANGSMITH_PROJECT=loom
# optional but recommended for deep links
export LANGSMITH_UI_URL=https://smith.langchain.com
```

When enabled, traces capture:
- orchestrator workflow execution and verification stages
- Loom service, AMS, and CMM client calls
- portal aggregation calls such as `trace/explain` and dashboard endpoints
- Graphiti Azure/OpenAI client calls when Graphiti is using Azure OpenAI

The integration is optional: if LangSmith is unset, Loom keeps running normally.
