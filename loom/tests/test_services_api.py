from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import services.app as service_app
from graph.client import FalkorDBHealth


class _FakeResult:
    def __init__(self, rows):
        self.result_set = rows


class _FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def query(self, cypher: str, params: dict | None = None, timeout=None, read_only: bool = False):
        if 'MATCH (n) WHERE n.mapping_category IN ["structured","reference","audit"] RETURN count(n)' in cypher:
            return _FakeResult([[123]])
        if 'MATCH (n:TextChunk {mapping_category:"vector"}) RETURN count(n)' in cypher:
            return _FakeResult([[456]])
        if 'MATCH ()-[r:HAS_STATE]->() RETURN count(r)' in cypher:
            return _FakeResult([[12]])
        if 'MATCH ()-[r:PROVENANCE]->() RETURN count(r)' in cypher:
            return _FakeResult([[78]])
        if 'MATCH (n:SourcePipeline) RETURN count(n)' in cypher:
            return _FakeResult([[3]])
        if 'MATCH (n:Community) RETURN count(n)' in cypher:
            return _FakeResult([[5]])
        if 'MATCH (n:PracticalNote) RETURN count(n)' in cypher:
            return _FakeResult([[2]])
        if 'MATCH (n:CorrectionItem) RETURN count(n)' in cypher:
            return _FakeResult([[4]])
        return _FakeResult([[0]])

    def close(self):
        return None


class _FakeRetrievalPipeline:
    def __init__(self, *args, **kwargs):
        pass

    def search(self, *args, **kwargs):
        return {
            'ok': True,
            'query': kwargs.get('query') if 'query' in kwargs else args[0],
            'communities': [],
            'community_status': {'communities_created': 0},
            'results': [{'id': 'chunk1', 'labels': ['TextChunk'], 'candidate_type': 'vector'}],
            'no_results': False,
        }

    def query(self, *args, **kwargs):
        return {
            'ok': True,
            'query_mode': 'graphrag_baseline',
            'query': kwargs.get('query') if 'query' in kwargs else args[0],
            'valid_at': kwargs.get('valid_at'),
            'communities': [],
            'results': [{'id': 'chunk1', 'labels': ['TextChunk'], 'candidate_type': 'vector', 'snippet': 'hello', 'warnings': [], 'properties': {}, 'evidence_chain': []}],
            'warnings': [],
            'no_results': False,
        }

    def ensure_communities(self, refresh=False):
        return {'communities_created': 5, 'persist_mode': 'file_cache'}


class _FakeProvenanceResolver:
    def __init__(self, *args, **kwargs):
        pass

    def get_node(self, node_id: str):
        return {'id': node_id, 'labels': ['Module'], 'properties': {'name': 'E2E'}}

    def resolve(self, node_id: str, **kwargs):
        return [{'source_system': 'autosar-fusion', 'source_pipeline': 'docling_kimi25', 'source_file': 'foo.pdf', 'confidence': 0.9, 'migration_runs': ['run-1']}]


class _FakeTemporalStateManager:
    def __init__(self, *args, **kwargs):
        pass

    def query_as_of(self, **kwargs):
        return [{'entity_id': 'mod1', 'entity_labels': ['Module'], 'state_label': 'ModuleState', 'state_properties': {'status': 'current'}}]

    def seed_from_existing(self, source_system=None):
        return {'created': 4, 'skipped': 0, 'source_system': source_system, 'per_label': {'Module': 4}}

    def upsert_state(self, **kwargs):
        return {'created': True, 'entity_id': kwargs['entity_id'], 'entity_label': kwargs['entity_label']}


class _FakeBootstrapResult:
    def to_dict(self):
        return {'statements_applied': 1, 'statements_skipped': 0, 'warnings': []}


class _FakeLoadedDoc:
    def __init__(self, path: str):
        self.source_path = Path(path)
        self.source_kind = 'json'
        self.source_system = 'autosar-supplementary'
        self.source_pipeline = 'incremental_structured_loader'
        self.source_file = 'tmp/autosar.json'
        self.title = 'autosar'
        self.checksum = 'abc123'
        self.chunks = [object(), object()]
        self.tables = [SimpleNamespace(row_count=1, col_count=2)]
        self.metadata = {'structured_kind': 'json'}
        self.warnings = []


class _FakeIngestionLoader:
    def load(self, **kwargs):
        return _FakeLoadedDoc(kwargs['source_path'])


class _FakeValidationResult:
    def __init__(self, accepted: bool = True):
        self.accepted = accepted
        self.errors = [] if accepted else ['bad_input']
        self.warnings = ['warning-a'] if accepted else []
        self.recommended_stack = ['native-structured-parser']
        self.notes = ['supplementary_AUTOSAR_flow_enabled']

    def to_dict(self):
        return {
            'accepted': self.accepted,
            'errors': self.errors,
            'warnings': self.warnings,
            'recommended_stack': self.recommended_stack,
            'notes': self.notes,
        }


class _FakeIngestionValidator:
    def __init__(self, accepted: bool = True):
        self.accepted = accepted

    def validate(self, doc):
        return _FakeValidationResult(accepted=self.accepted)


class _FakeGraphLoader:
    def __init__(self, *args, **kwargs):
        pass

    def ingest(self, doc):
        return {'run_id': 'ingest-1', 'text_chunks_created': 2, 'table_nodes_created': 1, 'superseded_nodes': 0}


class _FakeCommunityRefresher:
    def __init__(self, *args, **kwargs):
        pass

    def refresh(self):
        return {'communities_created': 5, 'persist_mode': 'file_cache'}


class _FakeCorrectionStore:
    def __init__(self, *args, **kwargs):
        pass

    def submit_correction(self, **kwargs):
        return {
            'id': 'corr-1',
            'title': kwargs['title'],
            'correction_type': kwargs['correction_type'],
            'content': kwargs['content'],
            'status': 'submitted',
            'project_id': kwargs['context'].project_id,
        }

    def list_corrections(self, **kwargs):
        return [{'id': 'corr-1', 'status': 'submitted', 'correction_type': 'practical_knowledge'}]

    def review_correction(self, correction_id, **kwargs):
        return {
            'correction': {'id': correction_id, 'status': kwargs['decision'], 'federated': kwargs['federate']},
            'practical_note': {'id': 'note-1', 'title': 'Practical note'} if kwargs.get('publish_practical_note') else None,
        }

    def list_practical_notes(self, **kwargs):
        return [{'id': 'note-1', 'title': 'Practical note', 'note_type': 'practical_knowledge'}]

    def create_practical_note(self, **kwargs):
        return {'id': 'note-1', 'title': kwargs['title'], 'project_id': kwargs['context'].project_id}

    def export_federated_notes(self, **kwargs):
        return {'ok': True, 'count': 1, 'path': '/tmp/federation_export.json'}


class ServicesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.sample_path = str(Path(self.tempdir.name) / 'autosar.json')
        Path(self.sample_path).write_text('{"name":"E2E Library"}')
        fake_settings = SimpleNamespace(
            graphiti_group_id='loom_knowledge',
            falkordb_database='loom_knowledge',
            loom_api_key='engineer-key',
            loom_admin_api_key='admin-key',
            allow_local_dev_bypass=True,
            deployment_environment='test',
            audit_export_dir='/tmp',
            azure_openai_api_key=None,
            azure_openai_endpoint=None,
        )
        self.patchers = [
            patch.object(service_app, 'settings', fake_settings),
            patch.object(service_app, 'FalkorDBClient', _FakeClient),
            patch.object(service_app, 'RetrievalPipeline', _FakeRetrievalPipeline),
            patch.object(service_app, 'ProvenanceResolver', _FakeProvenanceResolver),
            patch.object(service_app, 'TemporalStateManager', _FakeTemporalStateManager),
            patch.object(service_app, 'IngestionLoader', _FakeIngestionLoader),
            patch.object(service_app, 'IncrementalGraphLoader', _FakeGraphLoader),
            patch.object(service_app, 'IngestionCommunityRefresher', _FakeCommunityRefresher),
            patch.object(service_app, 'CorrectionStore', _FakeCorrectionStore),
            patch.object(service_app, 'falkordb_health', lambda settings: FalkorDBHealth(ok=True, detail='ok', database='loom_knowledge', graphs=['loom_knowledge'])),
            patch.object(service_app, 'bootstrap_schema', lambda client=None: _FakeBootstrapResult()),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.client = TestClient(service_app.app)

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tempdir.cleanup()

    def test_health_is_open(self) -> None:
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['service'], 'loom-services')


    def test_metrics_endpoint_returns_prometheus_text(self) -> None:
        response = self.client.get('/api/v1/metrics')
        self.assertEqual(response.status_code, 200)
        self.assertIn('loom_requests_total', response.text)

    def test_query_requires_api_key_when_configured(self) -> None:
        response = self.client.post('/api/v1/query', json={'query': 'XCP'})
        self.assertEqual(response.status_code, 401)

    def test_query_with_engineer_key_returns_request_context(self) -> None:
        response = self.client.post(
            '/api/v1/query',
            json={'query': 'XCP'},
            headers={
                'X-API-Key': 'engineer-key',
                'X-Engineer-Id': 'eng-1',
                'X-Session-Id': 'sess-1',
                'X-Objective-Id': 'obj-1',
                'X-Project-Id': 'proj-1',
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['request_context']['role'], 'engineer')
        self.assertEqual(body['request_context']['engineer_id'], 'eng-1')
        self.assertEqual(body['request_context']['project_id'], 'proj-1')

    def test_artifact_context_returns_guidance(self) -> None:
        response = self.client.post(
            '/api/v1/artifact/context',
            json={'query': 'XCP timing', 'artifact_type': 'design'},
            headers={'X-API-Key': 'engineer-key'},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['artifact_type'], 'design')
        self.assertIn('preferred_labels', body['artifact_guidance'])

    def test_diagnostics_is_read_only_for_engineer_key(self) -> None:
        response = self.client.get('/api/v1/diagnostics', headers={'X-API-Key': 'engineer-key'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['counts']['mapped_nodes'], 123)
        self.assertEqual(response.json()['counts']['practical_notes'], 2)
        self.assertEqual(response.json()['counts']['corrections'], 4)

    def test_admin_route_rejects_engineer_key(self) -> None:
        response = self.client.post('/admin/temporal/bootstrap', headers={'X-API-Key': 'engineer-key'})
        self.assertEqual(response.status_code, 403)

    def test_admin_route_accepts_admin_key(self) -> None:
        response = self.client.post('/admin/temporal/bootstrap', headers={'X-API-Key': 'admin-key'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['request_context']['role'], 'admin')

    def test_ingest_validate_requires_admin(self) -> None:
        response = self.client.post('/api/v1/ingest/validate', json={'source_path': self.sample_path}, headers={'X-API-Key': 'engineer-key'})
        self.assertEqual(response.status_code, 403)

    def test_ingest_validate_returns_document_and_validation(self) -> None:
        response = self.client.post('/api/v1/ingest/validate', json={'source_path': self.sample_path}, headers={'X-API-Key': 'admin-key'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['validation']['accepted'])
        self.assertEqual(body['document']['source_system'], 'autosar-supplementary')

    def test_ingest_runs_graph_loader_and_refresh(self) -> None:
        response = self.client.post('/api/v1/ingest', json={'source_path': self.sample_path}, headers={'X-API-Key': 'admin-key'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['ingest_result']['run_id'], 'ingest-1')
        self.assertEqual(body['community_refresh']['communities_created'], 5)

    def test_submit_and_list_corrections(self) -> None:
        headers = {
            'X-API-Key': 'engineer-key',
            'X-Engineer-Id': 'eng-1',
            'X-Session-Id': 'sess-1',
            'X-Objective-Id': 'obj-1',
            'X-Project-Id': 'proj-1',
        }
        submit = self.client.post(
            '/api/v1/corrections',
            json={
                'correction_type': 'practical_knowledge',
                'title': 'Remember this practical note',
                'content': 'Always verify the current objective before drafting.',
                'transcript_ref': 'cursor://chat/1',
            },
            headers=headers,
        )
        listed = self.client.get('/api/v1/corrections', headers=headers)
        self.assertEqual(submit.status_code, 200)
        self.assertEqual(submit.json()['correction']['project_id'], 'proj-1')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()['count'], 1)

    def test_review_correction_and_list_practical_notes(self) -> None:
        review = self.client.post(
            '/admin/corrections/corr-1/review',
            json={'decision': 'approved', 'publish_practical_note': True, 'federate': True},
            headers={'X-API-Key': 'admin-key', 'X-Engineer-Id': 'admin-1'},
        )
        notes = self.client.get('/api/v1/practical-notes', headers={'X-API-Key': 'engineer-key'})
        export = self.client.post('/admin/federation/export', json={'limit': 10}, headers={'X-API-Key': 'admin-key'})
        self.assertEqual(review.status_code, 200)
        self.assertTrue(review.json()['correction']['federated'])
        self.assertEqual(notes.status_code, 200)
        self.assertEqual(notes.json()['count'], 1)
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export.json()['count'], 1)


if __name__ == '__main__':
    unittest.main()
