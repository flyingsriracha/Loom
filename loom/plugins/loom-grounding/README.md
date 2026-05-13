# Loom Grounding Plugin

Drop-in grounding pack for an **external AI system** (lead generation, competitive analysis, market research) that needs authoritative ASAM/AUTOSAR automotive knowledge instead of hallucinating from base-model memory.

Three files, read-only scope, works with any LLM framework.

## Contents

| File | Purpose |
|---|---|
| `manifest.json` | Portable tool schemas (OpenAI-function format) + endpoint + auth metadata |
| `system_prompt.md` | The grounding discipline to attach as the AI's system prompt |
| `README.md` | This file |

## Surface Exposed

Only three read-only tools — no memory, spec-session, ingest, or admin surface:

- `loom_ask` — grounded natural-language answer with citations (default)
- `loom_search_knowledge` — raw evidence chunks for per-side retrieval (competitive analysis)
- `loom_get_node_provenance` — full evidence chain for a specific node (defensible citations)

## Integration in under 5 Minutes

### 1. Provision a consumer API key

On the Loom host, set one or more consumer keys as a comma-separated list:

```bash
LEADGEN_KEY="leadgen-$(openssl rand -hex 16)"
export LOOM_CONSUMER_API_KEYS="$LEADGEN_KEY"
docker compose -f loom/docker-compose.yml up -d
```

You can add more consumers later by appending: `LOOM_CONSUMER_API_KEYS="leadgen-...,marketresearch-...,sales-..."`.

Give `$LEADGEN_KEY` (and only that key) to the external AI. Do **not** share your personal engineer key or any admin key. The `consumer` role is enforced server-side — a consumer key that attempts to hit memory, spec-session, ingest, or admin endpoints receives HTTP 403 regardless of what the AI tries to do.

### 2. Attach the system prompt

Load `system_prompt.md` as the external AI's system message. It enforces the grounding rules, confidence floor, and no-hallucination contract that match Loom's Hard Rule #1 (no guessing on ASAM/AUTOSAR).

### 3. Register the tools

**OpenAI / Azure OpenAI function-calling.** The `tools[]` array in `manifest.json` is already in OpenAI function format. Pass it straight into `tools=` on your chat completion call. Wire each `http` block to a small executor that adds the `X-API-Key` and `X-Engineer-Id` headers.

**LangChain / LangGraph.** Wrap each tool as a `StructuredTool` whose `func` issues the HTTP request described in the `http` block of the manifest entry.

**n8n / Zapier / generic HTTP agent.** Point the HTTP node at the URLs in `endpoints`, add headers from `auth`, and expose each tool to the agent node.

**Anthropic tool-use.** Map each `function` entry to an Anthropic `tool` (same JSON schema). Use the `http` block as the executor contract.

### 4. Smoke test

```bash
curl -X POST http://localhost:8080/api/v1/ask \
  -H "X-API-Key: $LEADGEN_KEY" \
  -H "X-Engineer-Id: leadgen-agent" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is XCP and which measurement hardware implements it?","artifact_type":"research"}'
```

Then confirm the scope lock works — this must return HTTP 403:

```bash
curl -i -X POST http://localhost:8080/api/v1/spec/generate \
  -H "X-API-Key: $LEADGEN_KEY" \
  -H "X-Engineer-Id: leadgen-agent" \
  -H "Content-Type: application/json" \
  -d '{"artifact_type":"requirements","prompt":"test"}'
```

You should see a non-empty `answer`, non-empty `citations`, and an `audit_id`. If `citations` is empty, the plugin will surface that as a warning — the external AI must not ship the claim.

## Production Hardening

Before letting this run against customer data:

- Put the orchestrator behind your Azure ingress with mTLS or IP allowlist. The API key is a second factor, not a first.
- Enable fail-closed auth: `LOOM_DEPLOYMENT_ENV=production`, `LOOM_ALLOW_LOCAL_DEV_BYPASS=false`.
- Schedule `/admin/audit/export` to blob storage so every lead-gen query and its evidence chain is retained for dispute resolution.
- Rotate the consumer key on a schedule independent of engineer keys.

## Audit Trail

Every call made through this plugin is recorded with:

- `engineer_id` = the `X-Engineer-Id` you set (recommend `leadgen-agent` or similar)
- `action` = the endpoint invoked
- `request` = full payload
- `result` = full response including `audit_id`

Exportable via `POST /admin/audit/export` with an admin key. This is what makes the external AI's output defensible when a sales claim is challenged.

## Scope Reminder

This plugin is intentionally **read-only knowledge grounding**. The external AI must not:

- Write to the knowledge graph
- Ingest documents
- Touch AMS memory
- Touch spec-session endpoints
- Hit FalkorDB or Graphiti directly

If the external AI needs write capability later, that is a separate plugin with a separate key and a separate review.
