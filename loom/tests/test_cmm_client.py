from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from orchestrator.clients import CMMClient
from orchestrator.models import OrchestratorError


class CMMClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = SimpleNamespace(
            cmm_binary_path='codebase-memory-mcp',
            cmm_project='Users-chj1ana-AutoBrain',
            cmm_base_branch='main',
        )

    def test_status_reports_host_native_only_when_binary_missing_in_container(self) -> None:
        client = CMMClient(settings=self.settings)
        with patch.object(CMMClient, '_binary', return_value=None), patch('orchestrator.clients._running_in_container', return_value=True):
            status = client.status()
        self.assertFalse(status['available'])
        self.assertEqual(status['reason'], 'cmm_host_native_only')
        self.assertEqual(status['details']['scope'], 'host_native_only')

    def test_search_code_raises_host_native_only_when_binary_missing_in_container(self) -> None:
        client = CMMClient(settings=self.settings)
        with patch.object(CMMClient, '_binary', return_value=None), patch('orchestrator.clients._running_in_container', return_value=True):
            with self.assertRaises(OrchestratorError) as ctx:
                client.search_code('graphiti_search')
        self.assertEqual(ctx.exception.code, 'cmm_host_native_only')

    def test_status_reports_binary_missing_outside_container(self) -> None:
        client = CMMClient(settings=self.settings)
        with patch.object(CMMClient, '_binary', return_value=None), patch('orchestrator.clients._running_in_container', return_value=False):
            status = client.status()
        self.assertFalse(status['available'])
        self.assertEqual(status['reason'], 'cmm_unavailable')
        self.assertNotIn('scope', status['details'])


if __name__ == '__main__':
    unittest.main()
