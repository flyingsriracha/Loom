# Loom Deployment Runbook

## Local Production-Like Boot

1. Copy `loom/.env.azure.example` to a private env file and fill in real secrets.
2. Ensure `LOOM_ALLOW_LOCAL_DEV_BYPASS=false`.
3. Start the stack with:

```bash
docker compose -f loom/docker-compose.yml -f loom/docker-compose.azure.yml --env-file loom/.env.azure.example up -d --build
```

4. Verify health:

```bash
curl http://localhost:8090/api/v1/health
curl http://localhost:8080/api/v1/health
```

5. Verify metrics and audit export:

```bash
curl http://localhost:8090/api/v1/metrics
curl http://localhost:8080/api/v1/metrics
curl -X POST http://localhost:8080/admin/audit/export -H "X-API-Key: $LOOM_ADMIN_API_KEY" -H "Content-Type: application/json" -d '{"limit":1000}'
```

## Azure Method

Use `docker-compose.azure.yml` as the production override source of truth.

1. Build and push the `loom-services` and `loom-orchestrator` images to your Azure Container Registry.
2. Provision FalkorDB persistence and an artifacts volume for `/app/artifacts`.
3. Configure Container Apps or another Azure container service with the env keys from `.env.azure.example`.
4. Route public traffic only to the orchestrator and Loom service health endpoints as needed.
5. Keep secrets out of source control and store them in the Azure secret store for the deployment target.
