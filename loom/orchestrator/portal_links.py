from __future__ import annotations

import os
from urllib.parse import urlencode, urlsplit, urlunsplit

from common.auth import APIRequestContext
from common.settings import Settings

LOCAL_HOSTS = {'0.0.0.0', '127.0.0.1', 'localhost', 'loom-services', 'orchestrator', 'hindsight'}


def _browser_base(url: str | None, fallback_port: int) -> str:
    if not url:
        return f'http://localhost:{fallback_port}'
    parts = urlsplit(url)
    host = parts.hostname or 'localhost'
    port = parts.port or fallback_port
    if host in LOCAL_HOSTS:
        host = 'localhost'
    netloc = f'{host}:{port}'
    return urlunsplit((parts.scheme or 'http', netloc, parts.path or '', parts.query, parts.fragment))


def _append_params(url: str, params: dict[str, str | None]) -> str:
    query = urlencode({key: value for key, value in params.items() if value})
    if not query:
        return url
    separator = '&' if urlsplit(url).query else '?'
    return f'{url}{separator}{query}'


def build_integration_links(
    settings: Settings,
    *,
    context: APIRequestContext,
    query: str | None = None,
    node_id: str | None = None,
    audit_id: str | None = None,
    transcript_ref: str | None = None,
    orchestrator_base_url: str | None = None,
) -> list[dict[str, object]]:
    params = {
        'query': query,
        'node_id': node_id,
        'audit_id': audit_id,
        'project_id': context.project_id,
        'objective_id': context.objective_id,
        'session_id': context.session_id,
        'engineer_id': context.engineer_id,
    }
    loom_base = _browser_base(
        getattr(settings, 'loom_service_public_url', None)
        or os.getenv('LOOM_SERVICE_PUBLIC_URL')
        or settings.loom_service_url,
        settings.loom_service_port,
    )
    orchestrator_base = orchestrator_base_url or _browser_base(
        getattr(settings, 'orchestrator_public_url', None) or os.getenv('ORCHESTRATOR_PUBLIC_URL'),
        settings.orchestrator_port,
    )
    links: list[dict[str, object]] = [
        {
            'name': 'loom_portal_trace_api',
            'label': 'Trace Explain API',
            'kind': 'api',
            'url': f'{orchestrator_base}/api/v1/trace/explain',
            'available': True,
        },
        {
            'name': 'loom_services_api',
            'label': 'Knowledge Service API',
            'kind': 'api',
            'url': loom_base,
            'available': True,
        },
        {
            'name': 'langgraph_orchestrator',
            'label': 'LangGraph Orchestrator API',
            'kind': 'api',
            'url': orchestrator_base,
            'available': True,
        },
    ]
    if node_id:
        links.append(
            {
                'name': 'knowledge_provenance',
                'label': 'Selected Node Provenance',
                'kind': 'api',
                'url': f'{loom_base}/api/v1/node/{node_id}/provenance',
                'available': True,
            }
        )

    optional_urls = [
        ('falkordb_ui', 'Knowledge Foundation UI', getattr(settings, 'falkordb_ui_url', None) or os.getenv('FALKORDB_UI_URL') or 'http://localhost:3000/graph'),
        ('hindsight_ui', 'AMS / Hindsight UI', getattr(settings, 'hindsight_ui_url', None) or os.getenv('HINDSIGHT_UI_URL') or settings.hindsight_api_url),
        ('langgraph_ui', 'LangGraph UI', getattr(settings, 'langgraph_ui_url', None) or os.getenv('LANGGRAPH_UI_URL')),
        ('langsmith_ui', 'LangSmith Studio', getattr(settings, 'langsmith_ui_url', None) or os.getenv('LANGSMITH_UI_URL')),
        ('cmm_ui', 'CMM UI', getattr(settings, 'cmm_ui_url', None) or os.getenv('CMM_UI_URL')),
    ]
    for name, label, url in optional_urls:
        if not url:
            continue
        links.append(
            {
                'name': name,
                'label': label,
                'kind': 'ui',
                'url': _append_params(url, params),
                'available': True,
            }
        )
    if transcript_ref:
        links.append(
            {
                'name': 'transcript_reference',
                'label': 'Transcript Reference',
                'kind': 'reference',
                'url': transcript_ref,
                'available': True,
            }
        )
    return links
