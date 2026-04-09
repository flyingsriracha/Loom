from __future__ import annotations

import unittest

from graph.schema import GraphSchemaBootstrap


class FakeGraph:
    def __init__(self, *, fail_messages: dict[str, str] | None = None):
        self.fail_messages = fail_messages or {}
        self.operations: list[str] = []

    def _maybe_fail(self, op: str) -> None:
        self.operations.append(op)
        if op in self.fail_messages:
            raise RuntimeError(self.fail_messages[op])

    def create_node_range_index(self, label: str, prop: str):
        self._maybe_fail(f'range:{label}.{prop}')

    def create_node_unique_constraint(self, label: str, prop: str):
        self._maybe_fail(f'unique:{label}.{prop}')

    def create_node_vector_index(self, label: str, prop: str, *, dim: int, similarity_function: str):
        self._maybe_fail(f'vector:{label}.{prop}:{dim}:{similarity_function}')


class FakeClient:
    def __init__(self, graph: FakeGraph):
        self.graph = graph

    def select_graph(self):
        return self.graph


class SchemaBootstrapTests(unittest.TestCase):
    def test_schema_bootstrap_runs_all_operations(self) -> None:
        graph = FakeGraph()
        client = FakeClient(graph)
        bootstrap = GraphSchemaBootstrap(client=client)

        result = bootstrap.run(embedding_dimensions=3072)

        self.assertEqual(len(graph.operations), 55)
        self.assertEqual(result.statements_applied, 55)
        self.assertEqual(result.statements_skipped, 0)

    def test_schema_bootstrap_skips_known_compatibility_errors(self) -> None:
        graph = FakeGraph(fail_messages={'range:Standard.id': "Attribute 'id' is already indexed"})
        client = FakeClient(graph)
        bootstrap = GraphSchemaBootstrap(client=client)

        result = bootstrap.run()

        self.assertGreaterEqual(result.statements_skipped, 1)
        self.assertTrue(any('already indexed' in warning for warning in result.warnings))


if __name__ == '__main__':
    unittest.main()
