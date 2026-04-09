# FalkorDB — Loom Knowledge Graph Backend

FalkorDB is a Docker-based Redis module, not a downloadable binary.

## Quick Start (Docker — one command)

```bash
docker run -p 6379:6379 -it --rm -v ./data:/data falkordb/falkordb:latest
```

With memory limit (recommended for local dev):
```bash
docker run -p 6379:6379 -it --rm \
  -v ./data:/data \
  --memory=4g \
  falkordb/falkordb:latest
```

## Verify

```bash
# Connect via redis-cli
redis-cli
> GRAPH.QUERY test "CREATE (n:Test {name: 'hello'}) RETURN n"
```

## Python Client

```bash
pip install falkordb
```

```python
from falkordb import FalkorDB
db = FalkorDB()
graph = db.select_graph("loom")
result = graph.query("CREATE (s:Standard {name: 'ASAM XCP'}) RETURN s")
```

## Links

- GitHub: https://github.com/FalkorDB/FalkorDB
- Docs: https://docs.falkordb.com/
- Docker Hub: https://hub.docker.com/r/falkordb/falkordb
- Python client: https://pypi.org/project/falkordb/
- Graphiti integration: https://docs.falkordb.com/agentic-memory/graphiti.html
