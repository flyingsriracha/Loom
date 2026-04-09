from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from common.auth import APIRequestContext, build_api_auth_dependency
from common.health import http_check, tcp_check
from common.observability import MetricsRegistry, instrument_request, metrics_response
from common.settings import load_settings
from graph.client import FalkorDBClient, falkordb_health
from artifacts.lineage import ArtifactLineageStore
from orchestrator.audit import OrchestratorAuditLogger
from orchestrator.clients import AMSClient, CMMClient, LoomServiceClient
from orchestrator.models import OrchestratorError
from orchestrator.spec_session import fallback_queries, render_artifact, resolve_target_path
from orchestrator.workflow import OrchestratorWorkflow

app = FastAPI(title='Loom Orchestrator', version='0.1.0')
settings = load_settings()
audit_logger = OrchestratorAuditLogger()
metrics_registry = MetricsRegistry('orchestrator')


@app.middleware('http')
async def metrics_middleware(request: Request, call_next):
    return await instrument_request(request, call_next, registry=metrics_registry)


class AskPayload(BaseModel):
    query: str = Field(min_length=1)
    artifact_type: str | None = None


class SearchKnowledgePayload(BaseModel):
    query: str = Field(min_length=1)


class SearchCodePayload(BaseModel):
    query: str = Field(min_length=1)


class ChangeImpactPayload(BaseModel):
    scope: str = Field(default='working_tree')
    depth: int = Field(default=2, ge=1, le=8)
    since: str | None = None


class ResumePayload(BaseModel):
    objective_id: str | None = None
    project_id: str | None = None
    token_budget: int = Field(default=2000, ge=400, le=8000)


class MemoryRetainPayload(BaseModel):
    text: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    transcript_ref: str | None = None
    transcript_excerpt: str | None = None


class MemoryReflectPayload(BaseModel):
    query: str = Field(min_length=1)


class MemoryPromotePayload(BaseModel):
    query: str = Field(min_length=1)
    correction_type: str = Field(default='practical_knowledge')
    title: str | None = None
    target_node_id: str | None = None
    priority: str = Field(default='medium')
    transcript_ref: str | None = None


class MemorySeedPayload(BaseModel):
    steering_paths: list[str] = Field(default_factory=list)
    progress_path: str | None = None


class SpecPayload(BaseModel):
    artifact_type: str = Field(description='requirements, design, or tasks')
    prompt: str = Field(min_length=1)
    target_path: str | None = None
    references: list[str] = Field(default_factory=list, description='Optional engineer-provided references when direct citations are unavailable')


class SpecAuditPayload(BaseModel):
    artifact_type: str = Field(description='requirements, design, or tasks')
    target_path: str


class AuditExportPayload(BaseModel):
    limit: int | None = Field(default=1000, ge=1, le=50000)


async def _read_context(
    x_api_key: str | None = Header(default=None, alias='X-API-Key'),
    x_engineer_id: str | None = Header(default=None, alias='X-Engineer-Id'),
    x_session_id: str | None = Header(default=None, alias='X-Session-Id'),
    x_objective_id: str | None = Header(default=None, alias='X-Objective-Id'),
    x_project_id: str | None = Header(default=None, alias='X-Project-Id'),
) -> APIRequestContext:
    dependency = build_api_auth_dependency(settings, admin_only=False)
    return await dependency(
        x_api_key=x_api_key,
        x_engineer_id=x_engineer_id,
        x_session_id=x_session_id,
        x_objective_id=x_objective_id,
        x_project_id=x_project_id,
    )



async def _read_admin_context(
    x_api_key: str | None = Header(default=None, alias='X-API-Key'),
    x_engineer_id: str | None = Header(default=None, alias='X-Engineer-Id'),
    x_session_id: str | None = Header(default=None, alias='X-Session-Id'),
    x_objective_id: str | None = Header(default=None, alias='X-Objective-Id'),
    x_project_id: str | None = Header(default=None, alias='X-Project-Id'),
) -> APIRequestContext:
    dependency = build_api_auth_dependency(settings, admin_only=True)
    return await dependency(
        x_api_key=x_api_key,
        x_engineer_id=x_engineer_id,
        x_session_id=x_session_id,
        x_objective_id=x_objective_id,
        x_project_id=x_project_id,
    )


def _require_spec_traceability_context(context: APIRequestContext) -> None:
    missing = []
    if not context.session_id:
        missing.append('session_id')
    if not context.objective_id:
        missing.append('objective_id')
    if missing:
        raise OrchestratorError(
            'missing_traceability_context',
            'Spec-session operations require session and objective context.',
            409,
            {'missing': missing},
        )


def _require_memory_scope_context(context: APIRequestContext) -> None:
    if not context.objective_id and not context.project_id:
        raise OrchestratorError(
            'missing_memory_scope',
            'Memory promotion requires either objective_id or project_id context.',
            409,
            {'required': ['objective_id or project_id']},
        )


def _memory_result_texts(memory_payload: dict) -> list[str]:
    result = memory_payload.get('result', {}) if isinstance(memory_payload, dict) else {}
    texts = []
    for record in result.get('results', [])[:3]:
        if isinstance(record, dict) and record.get('text'):
            texts.append(str(record['text']))
    if texts:
        return texts
    for chunk in list((result.get('chunks') or {}).values())[:3]:
        if isinstance(chunk, dict) and chunk.get('text'):
            texts.append(str(chunk['text']))
    return texts


def _memory_transcript_ref(memory_payload: dict) -> str | None:
    result = memory_payload.get('result', {}) if isinstance(memory_payload, dict) else {}
    for record in result.get('results', []):
        if isinstance(record, dict):
            metadata = record.get('metadata') or {}
            if metadata.get('transcript_ref'):
                return str(metadata['transcript_ref'])
    return None


def _artifact_store() -> ArtifactLineageStore:
    return ArtifactLineageStore(client=FalkorDBClient())


@app.exception_handler(OrchestratorError)
async def orchestrator_error_handler(request: Request, exc: OrchestratorError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            'error': {
                'code': 'internal_error',
                'message': str(exc),
                'details': {'path': str(request.url.path)},
            }
        },
    )


@app.get('/metrics')
@app.get('/api/v1/metrics')
async def metrics():
    return metrics_response(metrics_registry)


@app.get('/api/v1/health')
async def health() -> dict:
    loom_ok, loom_detail = http_check(f"{settings.loom_service_url}/health")
    falkordb = falkordb_health(settings)
    cmm = CMMClient(settings=settings).status()
    hindsight_ok, hindsight_detail = tcp_check(settings.hindsight_host, settings.hindsight_api_port)
    return {
        'service': 'orchestrator',
        'status': 'ok' if loom_ok and falkordb.ok else 'degraded',
        'services': {
            'loom-services': {'ok': loom_ok, 'detail': loom_detail},
            'falkordb': falkordb.to_dict(),
            'hindsight': {'ok': hindsight_ok, 'detail': hindsight_detail},
            'cmm': cmm,
        },
    }


@app.get('/api/v1/health/{service_name}')
async def health_service(service_name: str) -> dict:
    if service_name == 'loom-services':
        ok, detail = http_check(f"{settings.loom_service_url}/health")
        return {'ok': ok, 'detail': detail}
    if service_name == 'falkordb':
        return falkordb_health(settings).to_dict()
    if service_name == 'hindsight':
        ok, detail = tcp_check(settings.hindsight_host, settings.hindsight_api_port)
        return {'ok': ok, 'detail': detail}
    if service_name == 'cmm':
        return CMMClient(settings=settings).status()
    raise HTTPException(status_code=404, detail=f'unknown service: {service_name}')


@app.post('/api/v1/ask')
async def ask(payload: AskPayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    workflow = OrchestratorWorkflow(
        loom_client=LoomServiceClient(settings=settings),
        cmm_client=CMMClient(settings=settings),
        ams_client=AMSClient(settings=settings),
    )
    result = workflow.run(query=payload.query, context=context, artifact_type=payload.artifact_type)
    audit_id = audit_logger.record(action='ask', context=context, request=payload.model_dump(), result=result.to_dict())
    result.audit_id = audit_id
    return result.to_dict()


@app.post('/api/v1/search/knowledge')
async def search_knowledge(payload: SearchKnowledgePayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    client = LoomServiceClient(settings=settings)
    result = client.search(payload.query, context=context)
    audit_id = audit_logger.record(action='search_knowledge', context=context, request=payload.model_dump(), result=result)
    result['audit_id'] = audit_id
    return result


@app.post('/api/v1/search/code')
async def search_code(payload: SearchCodePayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    client = CMMClient(settings=settings)
    result = client.search_code(payload.query)
    result = {
        'ok': True,
        'query': payload.query,
        'route': 'code',
        'cmm': result,
        'request_context': context.to_dict(),
    }
    audit_id = audit_logger.record(action='search_code', context=context, request=payload.model_dump(), result=result)
    result['audit_id'] = audit_id
    return result


@app.post('/api/v1/search/code/impact')
async def search_code_impact(payload: ChangeImpactPayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    client = CMMClient(settings=settings)
    impact = client.detect_changes(scope=payload.scope, depth=payload.depth, since=payload.since)
    result = {
        'ok': True,
        'route': 'code_impact',
        'impact': impact,
        'request_context': context.to_dict(),
    }
    audit_id = audit_logger.record(action='search_code_impact', context=context, request=payload.model_dump(), result=result)
    result['audit_id'] = audit_id
    return result


@app.post('/api/v1/memory/recall')
async def memory_recall(payload: SearchKnowledgePayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    result = AMSClient(settings=settings).recall(payload.query, context=context)
    audit_id = audit_logger.record(action='memory_recall', context=context, request=payload.model_dump(), result=result)
    result['audit_id'] = audit_id
    return result


@app.post('/api/v1/session/resume')
async def resume_session(payload: ResumePayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    if payload.objective_id and context.objective_id is None:
        context = APIRequestContext(
            role=context.role,
            auth_mode=context.auth_mode,
            engineer_id=context.engineer_id,
            session_id=context.session_id,
            objective_id=payload.objective_id,
            project_id=context.project_id,
        )
    if payload.project_id and context.project_id is None:
        context = APIRequestContext(
            role=context.role,
            auth_mode=context.auth_mode,
            engineer_id=context.engineer_id,
            session_id=context.session_id,
            objective_id=context.objective_id,
            project_id=payload.project_id,
        )
    result = AMSClient(settings=settings).resume(context=context, token_budget=payload.token_budget)
    audit_id = audit_logger.record(action='resume_session', context=context, request=payload.model_dump(), result=result)
    result['audit_id'] = audit_id
    return result


@app.post('/api/v1/memory/retain')
async def memory_retain(payload: MemoryRetainPayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    result = AMSClient(settings=settings).retain(
        payload.text,
        context=context,
        tags=payload.tags,
        metadata=payload.metadata,
        transcript_ref=payload.transcript_ref,
        transcript_excerpt=payload.transcript_excerpt,
    )
    audit_id = audit_logger.record(action='memory_retain', context=context, request=payload.model_dump(), result=result)
    result['audit_id'] = audit_id
    return result


@app.post('/api/v1/memory/reflect')
async def memory_reflect(payload: MemoryReflectPayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    result = AMSClient(settings=settings).reflect(payload.query, context=context)
    audit_id = audit_logger.record(action='memory_reflect', context=context, request=payload.model_dump(), result=result)
    result['audit_id'] = audit_id
    return result


@app.post('/api/v1/memory/seed')
async def memory_seed(payload: MemorySeedPayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    result = AMSClient(settings=settings).seed_from_project(steering_paths=payload.steering_paths, progress_path=payload.progress_path, context=context)
    audit_id = audit_logger.record(action='memory_seed', context=context, request=payload.model_dump(), result=result)
    result['audit_id'] = audit_id
    return result


@app.post('/api/v1/memory/promote')
async def memory_promote(payload: MemoryPromotePayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    _require_memory_scope_context(context)
    memory = AMSClient(settings=settings).recall(payload.query, context=context)
    texts = _memory_result_texts(memory)
    if not texts:
        raise OrchestratorError('memory_promotion_empty', 'AMS recall returned no promotable memory content.', 404, {'query': payload.query})
    correction_payload = {
        'correction_type': payload.correction_type,
        'title': payload.title or payload.query,
        'content': '\n\n'.join(texts),
        'target_node_id': payload.target_node_id,
        'priority': payload.priority,
        'source': 'ams_recall',
        'transcript_ref': payload.transcript_ref or _memory_transcript_ref(memory),
        'transcript_excerpt': texts[0],
    }
    correction = LoomServiceClient(settings=settings).submit_correction(correction_payload, context=context)
    body = {
        'ok': True,
        'promotion_source': 'ams_recall',
        'memory': memory,
        'correction': correction.get('correction', correction),
        'request_context': context.to_dict(),
    }
    audit_id = audit_logger.record(action='memory_promote', context=context, request=payload.model_dump(), result=body)
    body['audit_id'] = audit_id
    return body


@app.post('/api/v1/spec/generate')
async def generate_spec_artifact(payload: SpecPayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    _require_spec_traceability_context(context)
    workflow = OrchestratorWorkflow(
        loom_client=LoomServiceClient(settings=settings),
        cmm_client=CMMClient(settings=settings),
        ams_client=AMSClient(settings=settings),
    )
    result = workflow.run(query=payload.prompt, context=context, artifact_type=payload.artifact_type)
    if payload.references == [] and (not result.citations):
        loom_client = LoomServiceClient(settings=settings)
        for fallback in fallback_queries(payload.prompt):
            search_payload = loom_client.search(fallback, context=context)
            if search_payload.get('results'):
                result.knowledge = search_payload
                result.citations = [evidence for item in search_payload.get('results', []) for evidence in item.get('provenance_preview', [])]
                result.warnings = list(dict.fromkeys(list(result.warnings) + [f'spec_fallback_search:{fallback}']))
                break
    target_path = resolve_target_path(payload.artifact_type, payload.target_path)
    rendered = render_artifact(
        artifact_type=payload.artifact_type,
        prompt=payload.prompt,
        knowledge=result.knowledge or {},
        context=context,
        target_path=target_path,
        existing_content=None,
        references=payload.references,
        operation='generate',
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(rendered['content'])
    store = _artifact_store()
    try:
        revision = store.record_revision(
            artifact_type=payload.artifact_type,
            artifact_path=str(target_path),
            content=rendered['content'],
            objective_id=context.objective_id,
            session_id=context.session_id,
            engineer_id=context.engineer_id,
            prompt=payload.prompt,
            operation='generate',
            request_context=context.to_dict(),
            citations=rendered['citations'],
            supporting_node_ids=rendered['supporting_node_ids'],
            steering_paths=rendered['steering_paths'],
            unresolved_items=rendered['unresolved_items'],
            traceability_ok=rendered['traceability_ok'],
        )
    finally:
        store.client.close()
    if rendered['traceability_ok'] and result.citations:
        result.status = 'ok'
        result.warnings = [warning for warning in result.warnings if warning != 'needs_human:research_zero_results']
    body = result.to_dict()
    body.update({
        'target_path': str(target_path),
        'operation': 'generate_spec_artifact',
        'rendered_content': rendered['content'],
        'revision': revision,
    })
    audit_id = audit_logger.record(action='generate_spec_artifact', context=context, request=payload.model_dump(), result=body)
    body['audit_id'] = audit_id
    return body


@app.post('/api/v1/spec/update')
async def update_spec_artifact(payload: SpecPayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    _require_spec_traceability_context(context)
    target_path = resolve_target_path(payload.artifact_type, payload.target_path)
    if not target_path.exists():
        raise OrchestratorError('artifact_not_found', 'Target artifact does not exist for update.', 404, {'target_path': str(target_path)})
    existing_content = target_path.read_text()
    workflow = OrchestratorWorkflow(
        loom_client=LoomServiceClient(settings=settings),
        cmm_client=CMMClient(settings=settings),
        ams_client=AMSClient(settings=settings),
    )
    result = workflow.run(query=payload.prompt, context=context, artifact_type=payload.artifact_type)
    if payload.references == [] and (not result.citations):
        loom_client = LoomServiceClient(settings=settings)
        for fallback in fallback_queries(payload.prompt):
            search_payload = loom_client.search(fallback, context=context)
            if search_payload.get('results'):
                result.knowledge = search_payload
                result.citations = [evidence for item in search_payload.get('results', []) for evidence in item.get('provenance_preview', [])]
                result.warnings = list(dict.fromkeys(list(result.warnings) + [f'spec_fallback_search:{fallback}']))
                break
    rendered = render_artifact(
        artifact_type=payload.artifact_type,
        prompt=payload.prompt,
        knowledge=result.knowledge or {},
        context=context,
        target_path=target_path,
        existing_content=existing_content,
        references=payload.references,
        operation='update',
    )
    target_path.write_text(rendered['content'])
    store = _artifact_store()
    try:
        revision = store.record_revision(
            artifact_type=payload.artifact_type,
            artifact_path=str(target_path),
            content=rendered['content'],
            objective_id=context.objective_id,
            session_id=context.session_id,
            engineer_id=context.engineer_id,
            prompt=payload.prompt,
            operation='update',
            request_context=context.to_dict(),
            citations=rendered['citations'],
            supporting_node_ids=rendered['supporting_node_ids'],
            steering_paths=rendered['steering_paths'],
            unresolved_items=rendered['unresolved_items'],
            traceability_ok=rendered['traceability_ok'],
            change_request=payload.prompt,
        )
    finally:
        store.client.close()
    if rendered['traceability_ok'] and result.citations:
        result.status = 'ok'
        result.warnings = [warning for warning in result.warnings if warning != 'needs_human:research_zero_results']
    body = result.to_dict()
    body.update({
        'target_path': str(target_path),
        'operation': 'update_spec_artifact',
        'rendered_content': rendered['content'],
        'revision': revision,
    })
    audit_id = audit_logger.record(action='update_spec_artifact', context=context, request=payload.model_dump(), result=body)
    body['audit_id'] = audit_id
    return body


@app.post('/api/v1/spec/audit')
async def audit_spec_artifact(payload: SpecAuditPayload, context: APIRequestContext = Depends(_read_context)) -> dict:
    target_path = resolve_target_path(payload.artifact_type, payload.target_path)
    store = _artifact_store()
    try:
        audit = store.get_audit(artifact_type=payload.artifact_type, artifact_path=str(target_path))
    finally:
        store.client.close()
    body = {
        'ok': True,
        'artifact_type': payload.artifact_type,
        'target_path': str(target_path),
        'artifact': audit.get('artifact'),
        'revisions': audit.get('revisions', []),
        'found': audit.get('found', False),
        'current_content': target_path.read_text() if target_path.exists() else None,
        'request_context': context.to_dict(),
    }
    audit_id = audit_logger.record(action='audit_spec_artifact', context=context, request=payload.model_dump(), result=body)
    body['audit_id'] = audit_id
    return body



@app.post('/admin/audit/export')
async def export_audit_log(payload: AuditExportPayload, context: APIRequestContext = Depends(_read_admin_context)) -> dict:
    result = audit_logger.export(output_dir=settings.audit_export_dir, limit=payload.limit)
    return {**result, 'request_context': context.to_dict()}
