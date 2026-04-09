from __future__ import annotations

import unittest

from graph.identities import (
    id_artifact_revision,
    id_audit_event,
    id_migration_run,
    id_module,
    id_protocol,
    id_source_document,
    id_source_pipeline,
    id_source_row,
    id_source_system,
    id_standard,
)


class IdentityTests(unittest.TestCase):
    def test_identity_helpers_are_deterministic(self) -> None:
        self.assertEqual(id_standard('AUTOSAR'), id_standard('AUTOSAR'))
        self.assertEqual(id_protocol('XCP'), id_protocol('XCP'))
        self.assertEqual(id_module('ComM'), id_module('ComM'))
        self.assertEqual(id_source_system('ASAMKnowledgeDB'), id_source_system('ASAMKnowledgeDB'))
        self.assertEqual(id_source_pipeline('ASAMKnowledgeDB', 'mistral_azrouter'), id_source_pipeline('ASAMKnowledgeDB', 'mistral_azrouter'))

    def test_source_row_compatibility_format(self) -> None:
        # Must stay compatible with existing migrated IDs.
        self.assertEqual(
            id_source_row('ASAMKnowledgeDB', 'xcp_commands', '12'),
            id_source_row('ASAMKnowledgeDB', 'xcp_commands', '12'),
        )

    def test_auxiliary_id_helpers(self) -> None:
        self.assertTrue(id_source_document('ASAMKnowledgeDB', 'foo.pdf'))
        self.assertTrue(id_source_pipeline('ASAMKnowledgeDB', 'docling_kimi25'))
        self.assertTrue(id_artifact_revision('requirements', 'r1'))
        self.assertTrue(id_migration_run('ASAMKnowledgeDB', '2026-01-01T00:00:00Z'))
        self.assertTrue(id_audit_event('run1', 'xcp_commands', 'completed', 10))


if __name__ == '__main__':
    unittest.main()
