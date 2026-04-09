from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from common.auth import APIRequestContext
from orchestrator.clients import AMSClient
from orchestrator.seed_context import build_seed_bundle


class _FakeHindsightResult:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return self._payload


class _FakeHindsight:
    retain_calls: list[dict] = []
    recall_calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        self.closed = False

    async def aretain(self, **kwargs):
        type(self).retain_calls.append(kwargs)
        return _FakeHindsightResult({'ok': True, 'kind': 'retain', 'kwargs': kwargs})

    async def arecall(self, **kwargs):
        type(self).recall_calls.append(kwargs)
        tag_key = tuple(kwargs.get('tags') or [])
        if 'transcript-reference' in tag_key:
            results = [{'text': 'Transcript reference captured for session wrap-up.', 'metadata': {'transcript_ref': 'cursor://chat/123'}}]
        elif 'steering' in tag_key or 'project-seed' in tag_key:
            results = [{'text': 'Zero-Skip Policy remains active; project seed says Phase 1 local validation is complete.', 'metadata': {}}]
        elif 'open-thread' in tag_key or 'next-step' in tag_key or 'question' in tag_key:
            results = [{'text': 'Open thread: phase2 continuity hardening and transcript capture remain in progress.', 'metadata': {}}]
        elif 'decision' in tag_key or 'status' in tag_key:
            results = [{'text': 'Decision: accept sequential Graphiti ingestion on Azure GPT-5.4.', 'metadata': {}}]
        else:
            results = [{'text': 'General recall result for objective context.', 'metadata': {}}]
        return _FakeHindsightResult({'ok': True, 'kind': 'recall', 'kwargs': kwargs, 'results': results, 'chunks': {}})

    async def areflect(self, **kwargs):
        return _FakeHindsightResult({'ok': True, 'kind': 'reflect', 'kwargs': kwargs})

    async def aclose(self):
        self.closed = True


class AMSClientTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeHindsight.retain_calls = []
        _FakeHindsight.recall_calls = []
        self.context = APIRequestContext(role='engineer', auth_mode='test', engineer_id='eng-1', session_id='sess-1', objective_id='obj-1', project_id='proj-1')
        self.settings = SimpleNamespace(hindsight_api_url='http://localhost:8888', hindsight_api_key=None, hindsight_bank_prefix='loom', hindsight_host='localhost', hindsight_api_port=8888)
        self.repo_root = Path('/Users/chj1ana/AutoBrain')

    def test_retain_uses_objective_bank_and_project_metadata(self) -> None:
        with patch('orchestrator.clients.Hindsight', _FakeHindsight), patch('orchestrator.clients.http_check', lambda url, timeout=3.0: (True, 'http 200')):
            client = AMSClient(settings=self.settings)
            result = client.retain('hello', context=self.context, tags=['decision'])
        self.assertTrue(result['ok'])
        self.assertEqual(result['bank_id'], 'loom::objective::obj-1')
        self.assertEqual(_FakeHindsight.retain_calls[0]['metadata']['project_id'], 'proj-1')

    def test_retain_captures_transcript_reference(self) -> None:
        with patch('orchestrator.clients.Hindsight', _FakeHindsight), patch('orchestrator.clients.http_check', lambda url, timeout=3.0: (True, 'http 200')):
            client = AMSClient(settings=self.settings)
            result = client.retain(
                'Session wrap-up decision.',
                context=self.context,
                tags=['decision'],
                transcript_ref='cursor://chat/123',
                transcript_excerpt='We accepted sequential Graphiti ingestion and deferred Windows validation.',
            )
        self.assertTrue(result['ok'])
        call = _FakeHindsight.retain_calls[0]
        self.assertIn('Transcript reference: cursor://chat/123', call['content'])
        self.assertIn('Transcript excerpt:', call['content'])
        self.assertEqual(call['metadata']['transcript_ref'], 'cursor://chat/123')
        self.assertIn('transcript-reference', call['tags'])

    def test_recall_and_reflect_return_serialized_payloads(self) -> None:
        with patch('orchestrator.clients.Hindsight', _FakeHindsight), patch('orchestrator.clients.http_check', lambda url, timeout=3.0: (True, 'http 200')):
            client = AMSClient(settings=self.settings)
            recall = client.recall('what happened?', context=self.context, tags=['decision'])
            reflect = client.reflect('summarize', context=self.context)
        self.assertTrue(recall['ok'])
        self.assertEqual(recall['result']['kind'], 'recall')
        self.assertEqual(_FakeHindsight.recall_calls[0]['tags'], ['decision'])
        self.assertTrue(reflect['ok'])
        self.assertEqual(reflect['result']['kind'], 'reflect')

    def test_resume_builds_budgeted_snapshot(self) -> None:
        with patch('orchestrator.clients.Hindsight', _FakeHindsight), patch('orchestrator.clients.http_check', lambda url, timeout=3.0: (True, 'http 200')):
            client = AMSClient(settings=self.settings)
            result = client.resume(context=self.context, token_budget=800)
        self.assertTrue(result['ok'])
        self.assertEqual(result['token_budget'], 800)
        self.assertIn('sections', result['result'])
        self.assertIn('steering', result['result']['sections'])
        self.assertIn('recent_decisions', result['result']['sections'])
        self.assertEqual(len(_FakeHindsight.recall_calls), 4)
        self.assertTrue(any(call.get('tags') == ['transcript-reference'] for call in _FakeHindsight.recall_calls))

    def test_build_seed_bundle_prioritizes_relevant_sections(self) -> None:
        bundle = build_seed_bundle([
            self.repo_root / '.kiro/steering/loom-core.md',
            self.repo_root / '.kiro/steering/loom-progress.md',
        ])
        self.assertEqual(len(bundle.sources), 2)
        self.assertTrue(any(source.summary.startswith('Identity:') for source in bundle.sources))
        self.assertTrue(any(source.summary.startswith('Current task:') for source in bundle.sources))
        self.assertLess(len(bundle.text), 900)
        self.assertTrue(all(source.summary_chars < 400 for source in bundle.sources))

    def test_seed_from_project_bundles_unique_paths_into_single_retain(self) -> None:
        with patch('orchestrator.clients.Hindsight', _FakeHindsight), patch('orchestrator.clients.http_check', lambda url, timeout=3.0: (True, 'http 200')):
            client = AMSClient(settings=self.settings)
            result = client.seed_from_project(
                steering_paths=['.kiro/steering/loom-core.md', '.kiro/steering/loom-progress.md'],
                progress_path='.kiro/steering/loom-progress.md',
                context=self.context,
            )
        self.assertTrue(result['ok'])
        self.assertEqual(result['seed_mode'], 'bundled_summary')
        self.assertEqual(len(result['retained']), 2)
        self.assertEqual(len(_FakeHindsight.retain_calls), 1)
        call = _FakeHindsight.retain_calls[0]
        self.assertEqual(call['document_id'], 'project-seed::obj-1')
        self.assertEqual(call['metadata']['seed_mode'], 'bundled_summary')
        self.assertEqual(call['metadata']['project_id'], 'proj-1')
        self.assertIn('loom-core.md', call['content'])
        self.assertIn('loom-progress.md', call['content'])
        self.assertLess(len(call['content']), 900)

    def test_seed_from_project_reports_missing_paths_without_failing_valid_sources(self) -> None:
        with patch('orchestrator.clients.Hindsight', _FakeHindsight), patch('orchestrator.clients.http_check', lambda url, timeout=3.0: (True, 'http 200')):
            client = AMSClient(settings=self.settings)
            result = client.seed_from_project(
                steering_paths=['.kiro/steering/loom-core.md', '.kiro/steering/missing.md'],
                progress_path=None,
                context=self.context,
            )
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['retained']), 1)
        self.assertTrue(any(warning.startswith('missing:') for warning in result['warnings']))
        self.assertEqual(len(_FakeHindsight.retain_calls), 1)


if __name__ == '__main__':
    unittest.main()
