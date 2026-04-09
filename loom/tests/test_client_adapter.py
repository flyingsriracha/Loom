from __future__ import annotations

import asyncio
import unittest
from unittest.mock import Mock

from graph.client import FalkorDBClient, FalkorDBHealth
from graph.graphiti_adapter import graphiti_search


class _GraphWithLatestSearch:
    async def search(self, *, query: str, group_ids: list[str], num_results: int):
        return {'path': 'search', 'query': query, 'group_ids': group_ids, 'num_results': num_results}


class _GraphWithLegacySearch:
    async def search(self, *, query: str, group_id: str, num_results: int):
        return {'path': 'search', 'query': query, 'group_id': group_id, 'num_results': num_results}


class _GraphWithSearchUnderscore:
    async def search_(self, *, query: str, group_ids: list[str], num_results: int):
        return {'path': 'search_', 'query': query, 'group_ids': group_ids, 'num_results': num_results}


class ClientAdapterTests(unittest.TestCase):
    def test_falkordb_health_to_dict(self) -> None:
        health = FalkorDBHealth(ok=True, detail='ok', database='loom_knowledge', graphs=['g1'])
        self.assertEqual(health.to_dict()['database'], 'loom_knowledge')

    def test_select_graph_uses_default_database(self) -> None:
        client = FalkorDBClient()
        fake_graph = object()
        fake_conn = Mock()
        fake_conn.select_graph.return_value = fake_graph
        client.connect = Mock(return_value=fake_conn)  # type: ignore[method-assign]

        out = client.select_graph()

        self.assertIs(out, fake_graph)
        fake_conn.select_graph.assert_called_once_with(client.settings.falkordb_database)

    def test_graphiti_search_prefers_latest_search_signature(self) -> None:
        result = asyncio.run(graphiti_search(_GraphWithLatestSearch(), 'xcp command', group_id='loom', num_results=5))
        self.assertEqual(result['path'], 'search')
        self.assertEqual(result['group_ids'], ['loom'])

    def test_graphiti_search_supports_legacy_search_signature(self) -> None:
        result = asyncio.run(graphiti_search(_GraphWithLegacySearch(), 'xcp command', group_id='loom', num_results=5))
        self.assertEqual(result['path'], 'search')
        self.assertEqual(result['group_id'], 'loom')

    def test_graphiti_search_falls_back_to_search_underscore(self) -> None:
        result = asyncio.run(graphiti_search(_GraphWithSearchUnderscore(), 'xcp command', group_id='loom', num_results=5))
        self.assertEqual(result['path'], 'search_')
        self.assertEqual(result['group_ids'], ['loom'])


if __name__ == '__main__':
    unittest.main()
