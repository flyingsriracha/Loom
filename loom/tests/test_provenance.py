from __future__ import annotations

import unittest

from graph.provenance import ProvenanceResolver


class FakeResult:
    def __init__(self, rows):
        self.result_set = rows


class FakeClient:
    def query(self, cypher: str, params: dict | None = None, timeout=None):
        params = params or {}
        if cypher == 'MATCH (n {id: $id}) RETURN n.id, labels(n), properties(n) LIMIT 1':
            if params['id'] == 'cmd1':
                return FakeResult([['cmd1', ['Command'], {'id': 'cmd1', 'name': 'XCP CONNECT', 'source_system': 'ASAMKnowledgeDB'}]])
            return FakeResult([])

        if 'RETURN properties(prov), properties(d), properties(p), properties(s), node_runs, collect(DISTINCT dr.run_id)' in cypher:
            if params['id'] == 'cmd1':
                return FakeResult([
                    [
                        {'confidence': 0.95, 'extraction_date': '2026-04-07T00:00:00Z', 'page_number': 12},
                        {'source_file': 'asam.pdf', 'source_system': 'ASAMKnowledgeDB'},
                        {'name': 'mistral_azrouter'},
                        {'name': 'ASAMKnowledgeDB'},
                        ['run-a'],
                        ['run-b'],
                    ]
                ])
            if params['id'] == 'cmd2':
                return FakeResult([
                    [
                        {'confidence': 0.5, 'extraction_date': '2026-04-07T00:00:00Z', 'page_number': 2},
                        {'source_file': 'autosar.pdf', 'source_system': 'autosar-fusion'},
                        {'name': 'virtualECU_text_ingestion'},
                        {'name': 'autosar-fusion'},
                        ['run-c'],
                        ['run-d'],
                    ]
                ])
            return FakeResult([])

        if cypher.startswith('MATCH (n) WHERE') and 'RETURN n.id, labels(n), properties(n) LIMIT $candidate_limit' in cypher:
            return FakeResult([
                ['cmd1', ['Command'], {'id': 'cmd1', 'name': 'XCP CONNECT', 'source_system': 'ASAMKnowledgeDB'}],
                ['cmd2', ['Module'], {'id': 'cmd2', 'name': 'E2E Library', 'source_system': 'autosar-fusion'}],
            ])

        raise AssertionError(f'unexpected query: {cypher}')


class ProvenanceResolverTests(unittest.TestCase):
    def test_get_node_returns_node_projection(self) -> None:
        resolver = ProvenanceResolver(client=FakeClient())

        node = resolver.get_node('cmd1')

        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node['id'], 'cmd1')
        self.assertEqual(node['labels'], ['Command'])
        self.assertEqual(node['properties']['name'], 'XCP CONNECT')

    def test_resolve_applies_filters(self) -> None:
        resolver = ProvenanceResolver(client=FakeClient())

        allowed = resolver.resolve('cmd1', source_pipeline='mistral_azrouter', min_confidence=0.9)
        blocked = resolver.resolve('cmd1', source_pipeline='virtualECU_text_ingestion')

        self.assertEqual(len(allowed), 1)
        self.assertEqual(allowed[0]['source_system'], 'ASAMKnowledgeDB')
        self.assertEqual(blocked, [])

    def test_search_nodes_attaches_filtered_provenance_preview(self) -> None:
        resolver = ProvenanceResolver(client=FakeClient())

        results = resolver.search_nodes('xcp', source_system='ASAMKnowledgeDB', min_confidence=0.9, limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], 'cmd1')
        self.assertEqual(results[0]['provenance_preview'][0]['source_pipeline'], 'mistral_azrouter')


if __name__ == '__main__':
    unittest.main()
