from __future__ import annotations

import unittest

from migration.deterministic_migration import DeterministicMigrator
from migration.sources import curated_sources


class _FakeResult:
    def __init__(self, rows):
        self.result_set = rows


class _FakeGraph:
    def __init__(self):
        self.calls: list[tuple[str, dict | None]] = []

    def query(self, cypher: str, params: dict | None = None, timeout=None):
        self.calls.append((cypher, params))
        if 'RETURN count(n)' in cypher:
            return _FakeResult([[0]])
        return _FakeResult([])


class _FakeClient:
    def __init__(self):
        self.graph = _FakeGraph()

    def select_graph(self):
        return self.graph


class DeterministicMigrationTests(unittest.TestCase):
    def test_plan_covers_expected_tables(self) -> None:
        migrator = DeterministicMigrator(client=_FakeClient())
        asam, autosar = curated_sources()

        asam_plan = migrator.plan(asam, include_reference=True, include_audit=True)
        autosar_plan = migrator.plan(autosar, include_reference=True, include_audit=True)

        self.assertEqual(asam_plan['source_system'], 'ASAMKnowledgeDB')
        self.assertEqual(autosar_plan['source_system'], 'autosar-fusion')
        self.assertEqual(asam_plan['missing_tables'], [])
        self.assertEqual(autosar_plan['missing_tables'], [])
        self.assertGreaterEqual(len(asam_plan['mapped_tables']), 13)
        self.assertGreaterEqual(len(autosar_plan['mapped_tables']), 19)

    def test_node_properties_keep_stable_graph_id(self) -> None:
        migrator = DeterministicMigrator(client=_FakeClient())
        asam, _ = curated_sources()
        mapping = migrator._select_mappings(asam.name, include_reference=False, include_audit=False)[0]

        props = migrator._node_properties({'id': 42, 'source_system': 'shadow', 'name': 'sample'}, asam.name, mapping)

        self.assertNotIn('id', props)
        self.assertEqual(props['raw_id'], 42)
        self.assertEqual(props['raw_source_system'], 'shadow')

    def test_dry_run_reports_counts_without_writes(self) -> None:
        fake_client = _FakeClient()
        migrator = DeterministicMigrator(client=fake_client)
        asam, _ = curated_sources()

        report = migrator.migrate(asam, dry_run=True, limit_per_table=5)

        self.assertEqual(report.nodes_created, 0)
        self.assertEqual(len(report.records_skipped), 10)
        self.assertEqual(report.run_status, 'dry_run_completed')
        self.assertIsNotNone(report.run_id)
        self.assertEqual(report.audit_events_recorded, 10)
        self.assertTrue(all(item.get('reason') == 'dry_run' for item in report.records_skipped))
        self.assertGreaterEqual(len(fake_client.graph.calls), 1)


if __name__ == '__main__':
    unittest.main()
