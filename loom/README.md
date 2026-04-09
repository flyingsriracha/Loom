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
