# Hindsight — AMS Solver Plugin

Hindsight is a Docker-based service, not a downloadable binary.
It runs as a container with embedded PostgreSQL + pgvector.

## Quick Start (Docker — one command)

```bash
export OPENAI_API_KEY=sk-xxx

docker run --rm -it --pull always \
  -p 8888:8888 -p 9999:9999 \
  -e HINDSIGHT_API_LLM_API_KEY=$OPENAI_API_KEY \
  -v $HOME/.hindsight-docker:/home/hindsight/.pg0 \
  ghcr.io/vectorize-io/hindsight:latest
```

Port 8888 = API server, Port 9999 = MCP server.

## Alternative: pip install (API only)

```bash
pip install hindsight-server
```

## Core Operations

- `retain(text)` — store a memory (extracts facts, entities, relationships)
- `recall(query)` — search memories (4 parallel strategies + reranking)
- `reflect(question)` — LLM synthesizes across all relevant memories

## Links

- GitHub: https://github.com/vectorize-io/hindsight
- Docs: https://hindsight.vectorize.io/0.3/developer/installation
- Docker image: ghcr.io/vectorize-io/hindsight:latest
- Python SDK: `pip install hindsight-client`
- TypeScript SDK: `npm install @vectorize-io/hindsight-client`

## LLM Providers Supported

- Groq (recommended — fast inference with gpt-oss-20b)
- OpenAI (GPT-4o, GPT-4o-mini)
- Ollama (local models)
