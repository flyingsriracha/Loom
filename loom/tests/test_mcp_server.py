from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

import orchestrator.mcp_server as mcp_server


class _FakeResult:
    def __init__(self):
        self.audit_id = None
        self.citations = [{'source_file': 'a.pdf'}]
        self.knowledge = {'results': [{'id': 'n1', 'provenance_preview': [{'source_file': 'a.pdf'}]}]}
        self.warnings = []
        self.status = 'ok'

    def to_dict(self):
        return {'ok': True, 'route': 'spec_session', 'warnings': [], 'citations': self.citations}


class _FakeWorkflow:
    def run(self, **kwargs):
        return _FakeResult()


class _FakeStore:
    def __init__(self, *args, **kwargs):
        self.client = type('C', (), {'close': lambda self: None})()

    def record_revision(self, **kwargs):
        return {'revision_id': 'rev-1', 'revision_number': 1}


class MCPServerTests(unittest.TestCase):
    def test_mcp_ask_returns_payload(self) -> None:
        with patch.object(mcp_server, '_workflow', return_value=_FakeWorkflow()):
            payload = mcp_server.ask('What is XCP?', engineer_id='eng', session_id='sess', objective_id='obj', project_id='proj')
        self.assertTrue(payload['ok'])

    def test_save_memory_returns_payload(self) -> None:
        with patch.object(mcp_server, 'AMSClient') as ams_cls:
            ams = ams_cls.return_value
            ams.retain.return_value = {'ok': True}
            payload = mcp_server.save_memory('remember this', engineer_id='eng', session_id='sess', objective_id='obj', project_id='proj', transcript_ref='cursor://chat/1')
        self.assertTrue(payload['ok'])
        ams.retain.assert_called_once()
        self.assertEqual(ams.retain.call_args.kwargs['transcript_ref'], 'cursor://chat/1')

    def test_resume_session_passes_token_budget(self) -> None:
        with patch.object(mcp_server, 'AMSClient') as ams_cls:
            ams = ams_cls.return_value
            ams.resume.return_value = {'ok': True, 'token_budget': 900}
            payload = mcp_server.resume_session(objective_id='obj', engineer_id='eng', session_id='sess', project_id='proj', token_budget=900)
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['token_budget'], 900)
        self.assertEqual(ams.resume.call_args.kwargs['token_budget'], 900)

    def test_analyze_code_changes_passes_parameters(self) -> None:
        with patch.object(mcp_server, 'CMMClient') as cmm_cls:
            cmm = cmm_cls.return_value
            cmm.detect_changes.return_value = {'changed_symbols': ['foo']}
            payload = mcp_server.analyze_code_changes(scope='working_tree', depth=3, engineer_id='eng', session_id='sess', objective_id='obj', project_id='proj')
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['impact']['changed_symbols'][0], 'foo')
        cmm.detect_changes.assert_called_once()

    def test_promote_memory_uses_ams_and_loom(self) -> None:
        with patch.object(mcp_server, 'AMSClient') as ams_cls, patch.object(mcp_server, 'LoomServiceClient') as loom_cls:
            ams = ams_cls.return_value
            loom = loom_cls.return_value
            ams.recall.return_value = {'ok': True, 'result': {'results': [{'text': 'Promote this memory.'}], 'chunks': {}}}
            loom.submit_correction.return_value = {'ok': True, 'correction': {'id': 'corr-1'}}
            payload = mcp_server.promote_memory('Promote this memory', engineer_id='eng', session_id='sess', objective_id='obj', project_id='proj')
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['correction']['id'], 'corr-1')
        loom.submit_correction.assert_called_once()

    def test_generate_spec_artifact_returns_revision(self) -> None:
        with patch.object(mcp_server, '_workflow', return_value=_FakeWorkflow()), patch.object(mcp_server, '_artifact_store', return_value=_FakeStore()), patch.object(mcp_server, 'resolve_target_path', return_value=Path('/tmp/test-design.md')), patch.object(mcp_server, 'render_artifact', return_value={'content': 'hello', 'citations': [{'source_file': 'a.pdf'}], 'supporting_node_ids': ['n1'], 'steering_paths': ['.kiro/steering/loom-progress.md'], 'unresolved_items': [], 'traceability_ok': True}):
            payload = mcp_server.generate_spec_artifact('design', 'prompt', engineer_id='eng', session_id='sess', objective_id='obj', project_id='proj')
        self.assertEqual(payload['revision']['revision_number'], 1)


if __name__ == '__main__':
    unittest.main()
