from __future__ import annotations

from fastmcp import FastMCP

from common.auth import APIRequestContext
from common.settings import load_settings
from orchestrator.app import _require_spec_traceability_context
from orchestrator.audit import OrchestratorAuditLogger
from orchestrator.clients import AMSClient, CMMClient, LoomServiceClient
from orchestrator.workflow import OrchestratorWorkflow
from orchestrator.spec_session import render_artifact, resolve_target_path
from artifacts.lineage import ArtifactLineageStore

settings = load_settings()
audit_logger = OrchestratorAuditLogger()
mcp = FastMCP(
    name='Loom Orchestrator',
    instructions='Single MCP entry point for Loom knowledge, CMM code context, AMS continuity memory, and spec-session workflows.',
    version='0.1.0',
)


def _context(
    engineer_id: str | None = None,
    session_id: str | None = None,
    objective_id: str | None = None,
    project_id: str | None = None,
) -> APIRequestContext:
    return APIRequestContext(
        role='engineer',
        auth_mode='mcp-local',
        engineer_id=engineer_id,
        session_id=session_id,
        objective_id=objective_id,
        project_id=project_id,
    )


def _artifact_store() -> ArtifactLineageStore:
    return ArtifactLineageStore()


def _workflow() -> OrchestratorWorkflow:
    return OrchestratorWorkflow(
        loom_client=LoomServiceClient(settings=settings),
        cmm_client=CMMClient(settings=settings),
        ams_client=AMSClient(settings=settings),
    )


@mcp.tool(description='Main entry point for domain, coding, memory, and spec workflows.')
def ask(query: str, artifact_type: str | None = None, engineer_id: str | None = None, session_id: str | None = None, objective_id: str | None = None, project_id: str | None = None) -> dict:
    context = _context(engineer_id, session_id, objective_id, project_id)
    result = _workflow().run(query=query, context=context, artifact_type=artifact_type)
    audit_id = audit_logger.record(action='ask_mcp', context=context, request={'query': query, 'artifact_type': artifact_type}, result=result.to_dict())
    payload = result.to_dict()
    payload['audit_id'] = audit_id
    return payload


@mcp.tool(description='Direct knowledge search over Loom.')
def search_knowledge(query: str, engineer_id: str | None = None, session_id: str | None = None, objective_id: str | None = None, project_id: str | None = None) -> dict:
    context = _context(engineer_id, session_id, objective_id, project_id)
    result = LoomServiceClient(settings=settings).search(query, context=context)
    result['audit_id'] = audit_logger.record(action='search_knowledge_mcp', context=context, request={'query': query}, result=result)
    return result


@mcp.tool(description='Direct code structure search via codebase-memory-mcp.')
def search_code(query: str, engineer_id: str | None = None, session_id: str | None = None, objective_id: str | None = None, project_id: str | None = None) -> dict:
    context = _context(engineer_id, session_id, objective_id, project_id)
    cmm = CMMClient(settings=settings)
    result = {'ok': True, 'query': query, 'route': 'code', 'cmm': cmm.search_code(query), 'request_context': context.to_dict()}
    result['audit_id'] = audit_logger.record(action='search_code_mcp', context=context, request={'query': query}, result=result)
    return result



@mcp.tool(description='Analyze repository change impact via codebase-memory-mcp.')
def analyze_code_changes(scope: str = 'working_tree', depth: int = 2, since: str | None = None, engineer_id: str | None = None, session_id: str | None = None, objective_id: str | None = None, project_id: str | None = None) -> dict:
    context = _context(engineer_id, session_id, objective_id, project_id)
    cmm = CMMClient(settings=settings)
    result = {'ok': True, 'route': 'code_impact', 'impact': cmm.detect_changes(scope=scope, depth=depth, since=since), 'request_context': context.to_dict()}
    result['audit_id'] = audit_logger.record(action='analyze_code_changes_mcp', context=context, request={'scope': scope, 'depth': depth, 'since': since}, result=result)
    return result


@mcp.tool(description='Return current AMS resume snapshot for an objective or project.')
def resume_session(objective_id: str | None = None, engineer_id: str | None = None, session_id: str | None = None, project_id: str | None = None, token_budget: int = 2000) -> dict:
    context = _context(engineer_id, session_id, objective_id, project_id)
    result = AMSClient(settings=settings).resume(context=context, token_budget=token_budget)
    result['audit_id'] = audit_logger.record(action='resume_session_mcp', context=context, request={'objective_id': objective_id, 'project_id': project_id, 'token_budget': token_budget}, result=result)
    return result


@mcp.tool(description='Generate a standards-grounded spec artifact draft and store lineage.')
def generate_spec_artifact(artifact_type: str, prompt: str, target_path: str | None = None, references: list[str] | None = None, engineer_id: str | None = None, session_id: str | None = None, objective_id: str | None = None, project_id: str | None = None) -> dict:
    context = _context(engineer_id, session_id, objective_id, project_id)
    _require_spec_traceability_context(context)
    workflow = _workflow()
    result = workflow.run(query=prompt, context=context, artifact_type=artifact_type)
    refs = references or []
    if not refs and not result.citations:
        loom_client = LoomServiceClient(settings=settings)
        from orchestrator.spec_session import fallback_queries
        for fallback in fallback_queries(prompt):
            search_payload = loom_client.search(fallback, context=context)
            if search_payload.get('results'):
                result.knowledge = search_payload
                result.citations = [e for item in search_payload.get('results', []) for e in item.get('provenance_preview', [])]
                result.warnings = list(dict.fromkeys(list(result.warnings) + [f'spec_fallback_search:{fallback}']))
                break
    resolved_path = resolve_target_path(artifact_type, target_path)
    rendered = render_artifact(
        artifact_type=artifact_type,
        prompt=prompt,
        knowledge=result.knowledge or {},
        context=context,
        target_path=resolved_path,
        existing_content=None,
        references=refs,
        operation='generate',
    )
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(rendered['content'])
    store = _artifact_store()
    try:
        revision = store.record_revision(
            artifact_type=artifact_type,
            artifact_path=str(resolved_path),
            content=rendered['content'],
            objective_id=context.objective_id,
            session_id=context.session_id,
            engineer_id=context.engineer_id,
            prompt=prompt,
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
    payload = result.to_dict()
    payload.update({'target_path': str(resolved_path), 'operation': 'generate_spec_artifact', 'rendered_content': rendered['content'], 'revision': revision})
    payload['audit_id'] = audit_logger.record(action='generate_spec_artifact_mcp', context=context, request={'artifact_type': artifact_type, 'prompt': prompt, 'target_path': target_path, 'references': refs}, result=payload)
    return payload


@mcp.tool(description='Update an existing grounded spec artifact and preserve revision continuity.')
def update_spec_artifact(artifact_type: str, target_path: str, change_request: str, references: list[str] | None = None, engineer_id: str | None = None, session_id: str | None = None, objective_id: str | None = None, project_id: str | None = None) -> dict:
    context = _context(engineer_id, session_id, objective_id, project_id)
    _require_spec_traceability_context(context)
    workflow = _workflow()
    result = workflow.run(query=change_request, context=context, artifact_type=artifact_type)
    refs = references or []
    if not refs and not result.citations:
        loom_client = LoomServiceClient(settings=settings)
        from orchestrator.spec_session import fallback_queries
        for fallback in fallback_queries(change_request):
            search_payload = loom_client.search(fallback, context=context)
            if search_payload.get('results'):
                result.knowledge = search_payload
                result.citations = [e for item in search_payload.get('results', []) for e in item.get('provenance_preview', [])]
                result.warnings = list(dict.fromkeys(list(result.warnings) + [f'spec_fallback_search:{fallback}']))
                break
    resolved_path = resolve_target_path(artifact_type, target_path)
    if not resolved_path.exists():
        raise FileNotFoundError(f'Artifact not found: {resolved_path}')
    existing_content = resolved_path.read_text()
    rendered = render_artifact(
        artifact_type=artifact_type,
        prompt=change_request,
        knowledge=result.knowledge or {},
        context=context,
        target_path=resolved_path,
        existing_content=existing_content,
        references=refs,
        operation='update',
    )
    resolved_path.write_text(rendered['content'])
    store = _artifact_store()
    try:
        revision = store.record_revision(
            artifact_type=artifact_type,
            artifact_path=str(resolved_path),
            content=rendered['content'],
            objective_id=context.objective_id,
            session_id=context.session_id,
            engineer_id=context.engineer_id,
            prompt=change_request,
            operation='update',
            request_context=context.to_dict(),
            citations=rendered['citations'],
            supporting_node_ids=rendered['supporting_node_ids'],
            steering_paths=rendered['steering_paths'],
            unresolved_items=rendered['unresolved_items'],
            traceability_ok=rendered['traceability_ok'],
            change_request=change_request,
        )
    finally:
        store.client.close()
    payload = result.to_dict()
    payload.update({'target_path': str(resolved_path), 'operation': 'update_spec_artifact', 'rendered_content': rendered['content'], 'revision': revision})
    payload['audit_id'] = audit_logger.record(action='update_spec_artifact_mcp', context=context, request={'artifact_type': artifact_type, 'change_request': change_request, 'target_path': target_path, 'references': refs}, result=payload)
    return payload


@mcp.tool(description='Persist structured session memory into the AMS bank for the active objective or project.')
def save_memory(text: str, tags: list[str] | None = None, transcript_ref: str | None = None, transcript_excerpt: str | None = None, engineer_id: str | None = None, session_id: str | None = None, objective_id: str | None = None, project_id: str | None = None) -> dict:
    context = _context(engineer_id, session_id, objective_id, project_id)
    result = AMSClient(settings=settings).retain(
        text,
        context=context,
        tags=tags or [],
        transcript_ref=transcript_ref,
        transcript_excerpt=transcript_excerpt,
    )
    result['audit_id'] = audit_logger.record(action='save_memory_mcp', context=context, request={'text': text, 'tags': tags or [], 'transcript_ref': transcript_ref, 'transcript_excerpt': transcript_excerpt}, result=result)
    return result


@mcp.tool(description='Reflect over AMS memory for the active objective.')
def reflect_memory(query: str, engineer_id: str | None = None, session_id: str | None = None, objective_id: str | None = None, project_id: str | None = None) -> dict:
    context = _context(engineer_id, session_id, objective_id, project_id)
    result = AMSClient(settings=settings).reflect(query, context=context)
    result['audit_id'] = audit_logger.record(action='reflect_memory_mcp', context=context, request={'query': query}, result=result)
    return result



@mcp.tool(description="Promote AMS recall output into Loom's correction queue for admin review.")
def promote_memory(query: str, correction_type: str = 'practical_knowledge', title: str | None = None, target_node_id: str | None = None, priority: str = 'medium', transcript_ref: str | None = None, engineer_id: str | None = None, session_id: str | None = None, objective_id: str | None = None, project_id: str | None = None) -> dict:
    context = _context(engineer_id, session_id, objective_id, project_id)
    memory = AMSClient(settings=settings).recall(query, context=context)
    result = memory.get('result', {}) if isinstance(memory, dict) else {}
    texts = [str(item.get('text')) for item in result.get('results', [])[:3] if isinstance(item, dict) and item.get('text')]
    if not texts:
        texts = [str(chunk.get('text')) for chunk in list((result.get('chunks') or {}).values())[:3] if isinstance(chunk, dict) and chunk.get('text')]
    if not texts:
        raise ValueError('AMS recall returned no promotable memory content')
    payload = LoomServiceClient(settings=settings).submit_correction(
        {
            'correction_type': correction_type,
            'title': title or query,
            'content': '\n\n'.join(texts),
            'target_node_id': target_node_id,
            'priority': priority,
            'source': 'ams_recall',
            'transcript_ref': transcript_ref,
            'transcript_excerpt': texts[0],
        },
        context=context,
    )
    body = {'ok': True, 'memory': memory, 'correction': payload.get('correction', payload), 'request_context': context.to_dict()}
    body['audit_id'] = audit_logger.record(action='promote_memory_mcp', context=context, request={'query': query, 'correction_type': correction_type, 'title': title, 'target_node_id': target_node_id, 'priority': priority, 'transcript_ref': transcript_ref}, result=body)
    return body


@mcp.tool(description='Seed AMS memory from project steering and progress files.')
def seed_project_memory(steering_paths: list[str], progress_path: str | None = None, engineer_id: str | None = None, session_id: str | None = None, objective_id: str | None = None, project_id: str | None = None) -> dict:
    context = _context(engineer_id, session_id, objective_id, project_id)
    result = AMSClient(settings=settings).seed_from_project(steering_paths=steering_paths, progress_path=progress_path, context=context)
    result['audit_id'] = audit_logger.record(action='seed_project_memory_mcp', context=context, request={'steering_paths': steering_paths, 'progress_path': progress_path}, result=result)
    return result


if __name__ == '__main__':
    mcp.run()
