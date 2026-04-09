# Loom Operations Runbook

## Health and Readiness

- Loom service health: `GET /api/v1/health`
- Orchestrator health: `GET /api/v1/health`
- Metrics: `GET /api/v1/metrics` on both services
- Diagnostics: `GET /api/v1/diagnostics` on the Loom service

## Audit and Federation

- Export orchestrator audit logs: `POST /admin/audit/export`
- Export federated practical notes: `POST /admin/federation/export`

## Recovery Checks

1. Confirm FalkorDB health and graph counts.
2. Confirm orchestrator reports `cmm_host_native_only` if the container image still omits the Linux CMM binary.
3. Confirm AMS continuity routes: retain, recall, resume, seed.
4. Re-run `loom/evals/retrieval_eval.py`, `loom/evals/spec_session_eval.py`, `loom/evals/ams_eval.py`, and `loom/evals/load_eval.py` after significant deployment changes.

## Security Notes

- In production-like runs, use `LOOM_ALLOW_LOCAL_DEV_BYPASS=false`.
- Set both `LOOM_API_KEY` and `LOOM_ADMIN_API_KEY`.
- Treat `.kiro/runtime/ai-runtime.env` as local runtime material, not as a deployment artifact.
