from __future__ import annotations

import unittest

from graph.temporal import TemporalStateManager


class FakeResult:
    def __init__(self, rows):
        self.result_set = rows


class FakeClient:
    def __init__(self):
        self.queries: list[tuple[str, dict]] = []

    def select_graph(self):
        return self

    def query(self, cypher: str, params: dict | None = None, timeout=None):
        params = params or {}
        self.queries.append((cypher, params))
        if cypher.startswith('MATCH (e:Module) WHERE'):
            return FakeResult([['mod1', {'id': 'mod1', 'name': 'E2E', 'description': 'old desc', 'source_system': 'autosar-fusion', 'module_type': 'swc'}]])
        if cypher.startswith('MATCH (e:Module {id: $entity_id})-[r:HAS_STATE]'):
            return FakeResult([])
        if cypher.startswith('MATCH (e)-[r:HAS_STATE]->(s)'):
            return FakeResult([
                ['mod1', ['Module'], {'id': 'mod1', 'name': 'E2E', 'source_system': 'autosar-fusion'}, ['ModuleState'], {'description': 'current desc', 'status': 'current'}, '2026-01-01T00:00:00+00:00', None, '2026-01-01T00:00:00+00:00', None],
                ['proto1', ['Protocol'], {'id': 'proto1', 'name': 'XCP', 'source_system': 'ASAMKnowledgeDB'}, ['ProtocolState'], {'description': 'transport', 'status': 'current'}, '2026-01-01T00:00:00+00:00', None, '2026-01-01T00:00:00+00:00', None],
            ])
        if cypher.startswith('MATCH (e:Module {id: $entity_id}) RETURN properties(e) LIMIT 1'):
            return FakeResult([[{'id': 'mod1', 'name': 'E2E'}]])
        return FakeResult([])


class TemporalStateTests(unittest.TestCase):
    def test_seed_from_existing_creates_initial_states(self) -> None:
        client = FakeClient()
        manager = TemporalStateManager(client=client)

        result = manager.seed_from_existing(source_system='autosar-fusion')

        self.assertEqual(result['created'], 1)
        self.assertEqual(result['per_label']['Module'], 1)

    def test_query_as_of_filters_by_label_and_text(self) -> None:
        client = FakeClient()
        manager = TemporalStateManager(client=client)

        rows = manager.query_as_of(valid_at='2026-04-07T00:00:00+00:00', entity_label='Module', query_text='e2e')

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['entity_id'], 'mod1')


if __name__ == '__main__':
    unittest.main()
