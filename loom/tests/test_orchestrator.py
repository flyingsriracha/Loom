from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import orchestrator.app as orch_app
from common.auth import APIRequestContext
from orchestrator.classifier import classify_request
from orchestrator.models import OrchestratorError


class _FakeLoomClient:
    def __init__(self, *args, **kwargs):
        pass

    def query(self, query: str, *, context: APIRequestContext):
        return {
            'ok': True,
            'query_mode': 'graphrag_baseline',
            'query': query,
            'results': [{'id': 'k1', 'snippet': 'XCP CONNECT', 'evidence_chain': [{'source_file': 'asam.pdf'}]}],
            'warnings': [],
            'no_results': False,
        }

    def search(self, query: str, *, context: APIRequestContext):
        return {'ok': True, 'query': query, 'results': [{'id': 'k1'}], 'no_results': False}

    def artifact_context(self, query: str, artifact_type: str, *, context: APIRequestContext):
        return {
            'ok': True,
            'query_mode': 'graphrag_baseline',
            'query': query,
            'artifact_type': artifact_type,
            'results': [{'id': 'ctx1', 'snippet': 'artifact context', 'evidence_chain': [{'source_file': 'design.pdf'}]}],
            'warnings': [],
            'no_results': False,
        }

    def diagnostics(self, *, context: APIRequestContext):
        return {'ok': True, 'counts': {'mapped_nodes': 1}}

    def submit_correction(self, payload: dict, *, context: APIRequestContext):
        return {'ok': True, 'correction': {'id': 'corr-1', 'title': payload['title'], 'project_id': context.project_id}}


class _FakeCMMClient:
    def __init__(self, *args, **kwargs):
        pass

    def status(self):
        return {'available': True, 'project': 'Users-chj1ana-AutoBrain'}

    def search_code(self, query: str):
        return {'results': [{'kind': 'code', 'query': query}]}

    def trace_call_path(self, function_name: str):
        return {'results': [{'kind': 'trace', 'function_name': function_name}]}

    def get_architecture(self):
        return {'summary': 'repo architecture'}

    def detect_changes(self, *, scope: str = 'working_tree', depth: int = 2, since: str | None = None):
        return {'scope': scope, 'depth': depth, 'since': since, 'changed_symbols': ['foo', 'bar']}


class _FakeAMSClient:
    resume_calls = 0
    recall_calls = 0
    retain_calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    def status(self):
        return {'available': True, 'detail': 'ok'}

    def retain(self, text: str, *, context: APIRequestContext, tags=None, metadata=None, document_id=None, transcript_ref=None, transcript_excerpt=None):
        type(self).retain_calls.append({
            'text': text,
            'context': context.to_dict(),
            'tags': tags or [],
            'metadata': metadata or {},
            'document_id': document_id,
            'transcript_ref': transcript_ref,
            'transcript_excerpt': transcript_excerpt,
        })
        return {
            'ok': True,
            'bank_id': 'loom::objective::obj-1',
            'request_context': context.to_dict(),
            'text': text,
            'tags': tags or [],
            'metadata': metadata or {},
            'document_id': document_id,
            'transcript_ref': transcript_ref,
            'transcript_excerpt': transcript_excerpt,
        }

    def recall(self, query: str, *, context: APIRequestContext, max_tokens: int = 4096, tags=None, tags_match='any'):
        type(self).recall_calls += 1
        return {
            'ok': True,
            'available': True,
            'detail': 'ok',
            'query': query,
            'request_context': context.to_dict(),
            'result': {
                'summary': 'memory',
                'results': [
                    {
                        'text': 'Approved local knowledge: keep sequential Graphiti ingestion on Azure and capture transcript refs.',
                        'metadata': {'transcript_ref': 'cursor://chat/123'},
                    }
                ],
                'chunks': {'c1': {'text': 'fallback chunk'}},
            },
            'max_tokens': max_tokens,
            'tags': tags or [],
        }

    def reflect(self, query: str, *, context: APIRequestContext):
        return {'ok': True, 'available': True, 'detail': 'ok', 'query': query, 'request_context': context.to_dict(), 'result': {'answer': 'reflection'}}

    def resume(self, *, context: APIRequestContext, token_budget: int = 2000):
        type(self).resume_calls += 1
        return {'ok': True, 'available': True, 'detail': 'ok', 'request_context': context.to_dict(), 'token_budget': token_budget, 'result': {'summary': 'resume', 'sections': {'steering': ['rule']}}}

    def seed_from_project(self, *, steering_paths, progress_path, context: APIRequestContext):
        return {'ok': True, 'retained': [{'source_path': 'a.md', 'ok': True}], 'seed_mode': 'bundled_summary', 'request_context': context.to_dict()}


class _FakeAuditLogger:
    def __init__(self):
        self.records = [
            {
                'audit_id': 'audit-search_knowledge-old',
                'timestamp': '2026-04-08T10:00:00+00:00',
                'action': 'search_knowledge',
                'request_context': {'engineer_id': 'eng-1', 'session_id': 'sess-1', 'objective_id': 'obj-1', 'project_id': 'proj-1'},
                'request': {'query': 'XCP'},
                'result': {'summary': 'Knowledge query completed'},
            },
            {
                'audit_id': 'audit-memory_retain-old',
                'timestamp': '2026-04-08T10:05:00+00:00',
                'action': 'memory_retain',
                'request_context': {'engineer_id': 'eng-1', 'session_id': 'sess-1', 'objective_id': 'obj-1', 'project_id': 'proj-1'},
                'request': {'text': 'remember this'},
                'result': {'summary': 'Stored memory'},
            },
            {
                'audit_id': 'audit-search_code_impact-old',
                'timestamp': '2026-04-08T10:10:00+00:00',
                'action': 'search_code_impact',
                'request_context': {'engineer_id': 'eng-1', 'session_id': 'sess-1', 'objective_id': 'obj-1', 'project_id': 'proj-1'},
                'request': {'scope': 'working_tree'},
                'result': {'summary': 'Code impact analyzed'},
            },
            {
                'audit_id': 'audit-generate_spec_artifact-old',
                'timestamp': '2026-04-08T10:15:00+00:00',
                'action': 'generate_spec_artifact',
                'request_context': {'engineer_id': 'eng-1', 'session_id': 'sess-1', 'objective_id': 'obj-1', 'project_id': 'proj-1'},
                'request': {'artifact_type': 'design'},
                'result': {'summary': 'Spec generated', 'revision': {'revision_id': 'rev-1'}},
            },
        ]

    def record(self, *, action: str, context: APIRequestContext, request: dict, result: dict) -> str:
        audit_id = f'audit-{action}'
        self.records.append({
            'audit_id': audit_id,
            'timestamp': '2026-04-08T10:20:00+00:00',
            'action': action,
            'request_context': context.to_dict(),
            'request': request,
            'result': result,
        })
        return audit_id

    def list_records(self, *, limit: int | None = None, engineer_id: str | None = None, project_id: str | None = None, objective_id: str | None = None, session_id: str | None = None, actions=None):
        filtered = []
        for record in self.records:
            ctx = record.get('request_context') or {}
            if engineer_id and ctx.get('engineer_id') != engineer_id:
                continue
            if project_id and ctx.get('project_id') != project_id:
                continue
            if objective_id and ctx.get('objective_id') != objective_id:
                continue
            if session_id and ctx.get('session_id') != session_id:
                continue
            if actions and record.get('action') not in actions:
                continue
            filtered.append(record)
        if limit is not None:
            filtered = filtered[-limit:]
        return list(reversed(filtered))

    def export(self, *, output_dir: str, limit: int | None = None):
        return {'ok': True, 'path': f'{output_dir}/audit-export.json', 'count': 1}


class _FakeArtifactStore:
    def __init__(self, *args, **kwargs):
        self.client = SimpleNamespace(close=lambda: None)

    def record_revision(self, **kwargs):
        return {'revision_id': 'rev-1', 'revision_number': 1, 'traceability_ok': True}

    def get_audit(self, **kwargs):
        return {'found': True, 'artifact': {'id': 'artifact-1'}, 'revisions': [{'id': 'rev-1'}]}


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeAMSClient.resume_calls = 0
        _FakeAMSClient.recall_calls = 0
        _FakeAMSClient.retain_calls = []
        self.tempdir = TemporaryDirectory()
        self.target_path = str(Path(self.tempdir.name) / 'design.md')
        fake_settings = SimpleNamespace(
            loom_api_key='engineer-key',
            loom_admin_api_key='admin-key',
            allow_local_dev_bypass=True,
            deployment_environment='test',
            audit_export_dir=self.tempdir.name,
            loom_service_url='http://loom-services:8090',
            loom_service_port=8090,
            orchestrator_port=8080,
            hindsight_host='hindsight',
            hindsight_api_port=8888,
            hindsight_api_url='http://localhost:8888',
            cmm_binary_path='codebase-memory-mcp',
            cmm_project='Users-chj1ana-AutoBrain',
            cmm_base_branch='main',
            falkordb_ui_url='http://localhost:3000/graph',
            langgraph_ui_url='http://localhost:2024/studio',
            langsmith_ui_url='https://smith.langchain.com',
            cmm_ui_url='http://localhost:3030',
        )
        self.patchers = [
            patch.object(orch_app, 'settings', fake_settings),
            patch.object(orch_app, 'LoomServiceClient', _FakeLoomClient),
            patch.object(orch_app, 'CMMClient', _FakeCMMClient),
            patch.object(orch_app, 'AMSClient', _FakeAMSClient),
            patch.object(orch_app, 'ArtifactLineageStore', _FakeArtifactStore),
            patch.object(orch_app, 'audit_logger', _FakeAuditLogger()),
            patch.object(orch_app, 'http_check', lambda url: (True, 'http 200')),
            patch.object(orch_app, 'falkordb_health', lambda settings: SimpleNamespace(ok=True, to_dict=lambda: {'ok': True, 'database': 'loom_knowledge'})),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.client = TestClient(orch_app.app)

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tempdir.cleanup()

    def spec_headers(self):
        return {
            'X-API-Key': 'engineer-key',
            'X-Engineer-Id': 'eng-1',
            'X-Session-Id': 'sess-1',
            'X-Objective-Id': 'obj-1',
            'X-Project-Id': 'proj-1',
        }

    def test_classifier_routes(self) -> None:
        self.assertEqual(classify_request('What are XCP timing constraints?').route, 'domain')
        self.assertEqual(classify_request('What calls graphiti_search?').route, 'code')
        self.assertEqual(classify_request('Implement XCP CONNECT handler').route, 'coding_task')
        self.assertEqual(classify_request('Update the design doc for AUTOSAR migration').route, 'spec_session')
        self.assertEqual(classify_request('Where did we leave off on this objective?').route, 'memory')

    def test_ask_requires_api_key(self) -> None:
        response = self.client.post('/api/v1/ask', json={'query': 'What are XCP timing constraints?'})
        self.assertEqual(response.status_code, 401)


    def test_metrics_endpoint_returns_prometheus_text(self) -> None:
        response = self.client.get('/api/v1/metrics')
        self.assertEqual(response.status_code, 200)
        self.assertIn('loom_requests_total', response.text)

    def test_ask_domain_route_returns_audited_workflow_output(self) -> None:
        response = self.client.post('/api/v1/ask', json={'query': 'What are XCP timing constraints?'}, headers={'X-API-Key': 'engineer-key'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['route'], 'domain')
        self.assertEqual(body['audit_id'], 'audit-ask')
        self.assertGreaterEqual(len(body['citations']), 1)

    def test_ask_coding_task_includes_change_impact(self) -> None:
        response = self.client.post('/api/v1/ask', json={'query': 'Fix XCP CONNECT handler'}, headers=self.spec_headers())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['route'], 'coding_task')
        self.assertIn('change_impact', body['code'])

    def test_ask_spec_session_prefers_resume_context(self) -> None:
        response = self.client.post('/api/v1/ask', json={'query': 'Update the design doc for AUTOSAR migration'}, headers=self.spec_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['route'], 'spec_session')
        self.assertEqual(_FakeAMSClient.resume_calls, 1)
        self.assertEqual(_FakeAMSClient.recall_calls, 0)

    def test_search_knowledge_proxy(self) -> None:
        response = self.client.post('/api/v1/search/knowledge', json={'query': 'XCP'}, headers={'X-API-Key': 'engineer-key'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['audit_id'], 'audit-search_knowledge')

    def test_search_code_proxy(self) -> None:
        response = self.client.post('/api/v1/search/code', json={'query': 'graphiti_search'}, headers={'X-API-Key': 'engineer-key'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['cmm']['results'][0]['kind'], 'code')

    def test_search_code_impact_proxy(self) -> None:
        response = self.client.post('/api/v1/search/code/impact', json={'scope': 'working_tree', 'depth': 3}, headers=self.spec_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['impact']['changed_symbols'][0], 'foo')

    def test_trace_explain_returns_envelope(self) -> None:
        response = self.client.post(
            '/api/v1/trace/explain',
            json={'query': 'What are XCP timing constraints?', 'include_change_impact': True},
            headers=self.spec_headers(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['audit_id'], 'audit-trace_explain')
        self.assertEqual(body['availability']['knowledge'], 'used')
        self.assertGreaterEqual(len(body['knowledge_trace']), 1)
        self.assertTrue(any(item['kind'] == 'change_impact' for item in body['code_trace']))
        self.assertTrue(any(link['name'] == 'knowledge_provenance' for link in body['deep_links']))

    def test_dashboard_overview_combines_resume_progress_and_change_impact(self) -> None:
        response = self.client.get('/api/v1/dashboard/overview', headers=self.spec_headers())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['objective']['summary'], 'resume')
        self.assertEqual(body['change_impact']['impact']['changed_symbols'][0], 'foo')
        self.assertGreaterEqual(body['progress']['recent_event_count'], 1)
        self.assertEqual(body['services']['loom']['counts']['mapped_nodes'], 1)

    def test_dashboard_journey_returns_normalized_events(self) -> None:
        response = self.client.get('/api/v1/dashboard/journey?limit=10', headers=self.spec_headers())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        event_types = {event['event_type'] for event in body['events']}
        self.assertIn('knowledge_query', event_types)
        self.assertIn('artifact_revision', event_types)
        self.assertIn('code_impact', event_types)

    def test_integration_links_returns_contextual_links(self) -> None:
        response = self.client.get('/api/v1/integrations/links?query=XCP&node_id=k1&audit_id=audit-1', headers=self.spec_headers())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        link_names = {link['name'] for link in body['links']}
        self.assertIn('falkordb_ui', link_names)
        self.assertIn('knowledge_provenance', link_names)
        self.assertIn('langsmith_ui', link_names)

    def test_spec_generate_requires_traceability_context(self) -> None:
        response = self.client.post('/api/v1/spec/generate', json={'artifact_type': 'design', 'prompt': 'Update AUTOSAR design'})
        self.assertEqual(response.status_code, 401)

    def test_spec_generate_writes_revision(self) -> None:
        response = self.client.post(
            '/api/v1/spec/generate',
            json={'artifact_type': 'design', 'prompt': 'Update AUTOSAR design', 'target_path': self.target_path},
            headers=self.spec_headers(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['route'], 'spec_session')
        self.assertEqual(body['revision']['revision_number'], 1)
        self.assertTrue(Path(self.target_path).exists())

    def test_spec_update_requires_existing_file(self) -> None:
        response = self.client.post(
            '/api/v1/spec/update',
            json={'artifact_type': 'design', 'prompt': 'Update AUTOSAR design', 'target_path': self.target_path},
            headers=self.spec_headers(),
        )
        self.assertEqual(response.status_code, 404)

    def test_spec_audit_returns_revision_chain(self) -> None:
        Path(self.target_path).write_text('content')
        response = self.client.post(
            '/api/v1/spec/audit',
            json={'artifact_type': 'design', 'target_path': self.target_path},
            headers=self.spec_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['found'])
        self.assertEqual(response.json()['audit_id'], 'audit-audit_spec_artifact')

    def test_memory_retain_route_accepts_transcript_reference(self) -> None:
        response = self.client.post(
            '/api/v1/memory/retain',
            json={
                'text': 'remember this',
                'tags': ['steering'],
                'transcript_ref': 'cursor://chat/123',
                'transcript_excerpt': 'Wrap-up summary',
            },
            headers=self.spec_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(_FakeAMSClient.retain_calls[0]['transcript_ref'], 'cursor://chat/123')
        self.assertEqual(_FakeAMSClient.retain_calls[0]['context']['project_id'], 'proj-1')

    def test_resume_route_accepts_project_and_budget(self) -> None:
        response = self.client.post('/api/v1/session/resume', json={'token_budget': 900}, headers=self.spec_headers())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['token_budget'], 900)
        self.assertEqual(body['request_context']['project_id'], 'proj-1')
        self.assertEqual(_FakeAMSClient.resume_calls, 1)

    def test_memory_seed_route(self) -> None:
        response = self.client.post('/api/v1/memory/seed', json={'steering_paths': ['.kiro/steering/loom-progress.md']}, headers={'X-API-Key': 'engineer-key'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])

    def test_memory_promote_route(self) -> None:
        response = self.client.post(
            '/api/v1/memory/promote',
            json={'query': 'Promote the latest continuity decision', 'title': 'Continuity decision'},
            headers=self.spec_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['correction']['id'], 'corr-1')
        self.assertEqual(response.json()['correction']['project_id'], 'proj-1')

    def test_structured_error_handler(self) -> None:
        with patch.object(orch_app, 'LoomServiceClient', side_effect=OrchestratorError('boom', 'fail', 502)):
            response = self.client.post('/api/v1/ask', json={'query': 'What are XCP timing constraints?'}, headers={'X-API-Key': 'engineer-key'})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['error']['code'], 'boom')


    def test_admin_audit_export_route(self) -> None:
        response = self.client.post('/admin/audit/export', json={'limit': 25}, headers={'X-API-Key': 'admin-key', 'X-Engineer-Id': 'admin-1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)


if __name__ == '__main__':
    unittest.main()
