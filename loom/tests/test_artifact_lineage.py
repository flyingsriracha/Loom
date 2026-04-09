from __future__ import annotations

import unittest

from artifacts.lineage import ArtifactLineageStore


class _FakeResult:
    def __init__(self, rows):
        self.result_set = rows


class _FakeGraph:
    def __init__(self):
        self.calls = []

    def query(self, cypher: str, params: dict | None = None, timeout=None):
        params = params or {}
        self.calls.append((cypher, params))
        if 'RETURN coalesce(max(r.revision_number), 0)' in cypher:
            return _FakeResult([[0, None]])
        if 'MATCH (a:Artifact {id: $artifact_id}) RETURN properties(a) LIMIT 1' in cypher:
            return _FakeResult([[{'id': 'artifact-1', 'artifact_type': 'design', 'path': '/tmp/design.md'}]])
        if 'RETURN properties(r), prev.id' in cypher:
            return _FakeResult([[{'id': 'rev-1', 'revision_number': 1, 'content_preview': 'preview'}, None]])
        if 'MATCH (r:ArtifactRevision {id: $revision_id})-[:SUPPORTED_BY]->(n)' in cypher:
            return _FakeResult([['node-1', ['TextChunk'], {'name': 'chunk'}]])
        return _FakeResult([])


class _FakeClient:
    def __init__(self):
        self.graph = _FakeGraph()

    def select_graph(self):
        return self.graph


class ArtifactLineageTests(unittest.TestCase):
    def test_record_revision_returns_revision_metadata(self) -> None:
        client = _FakeClient()
        store = ArtifactLineageStore(client=client)

        result = store.record_revision(
            artifact_type='design',
            artifact_path='/tmp/design.md',
            content='hello',
            objective_id='obj-1',
            session_id='sess-1',
            engineer_id='eng-1',
            prompt='update design',
            operation='update',
            request_context={'objective_id': 'obj-1'},
            citations=[{'source_file': 'design.pdf'}],
            supporting_node_ids=['node-1'],
            steering_paths=['.kiro/steering/loom-core.md'],
            unresolved_items=['- [ ] open item'],
            traceability_ok=True,
        )

        self.assertEqual(result['revision_number'], 1)
        self.assertTrue(result['traceability_ok'])
        self.assertGreaterEqual(len(client.graph.calls), 4)

    def test_get_audit_returns_revisions(self) -> None:
        client = _FakeClient()
        store = ArtifactLineageStore(client=client)

        audit = store.get_audit(artifact_type='design', artifact_path='/tmp/design.md')

        self.assertTrue(audit['found'])
        self.assertEqual(audit['artifact']['artifact_type'], 'design')
        self.assertEqual(audit['revisions'][0]['supported_by'][0]['id'], 'node-1')


if __name__ == '__main__':
    unittest.main()
