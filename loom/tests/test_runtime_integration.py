from __future__ import annotations

import json
import os
from pathlib import Path
import unittest
from urllib.request import Request, urlopen

RUN = os.getenv('RUN_DOCKER_INTEGRATION') == '1'
ADMIN_KEY = os.getenv('LOOM_ADMIN_API_KEY')


@unittest.skipUnless(RUN, 'set RUN_DOCKER_INTEGRATION=1 to execute live Docker integration tests')
class RuntimeIntegrationTests(unittest.TestCase):
    def call_json(self, url: str, payload: dict | None = None, *, headers: dict | None = None, method: str | None = None) -> dict:
        if payload is None and method is None:
            with urlopen(url, timeout=180) as resp:
                return json.loads(resp.read().decode('utf-8'))
        merged_headers = {'Content-Type': 'application/json'}
        if headers:
            merged_headers.update(headers)
        req = Request(url, data=None if payload is None else json.dumps(payload).encode('utf-8'), headers=merged_headers, method=method or 'POST')
        with urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def call_text(self, url: str) -> str:
        with urlopen(url, timeout=180) as resp:
            return resp.read().decode('utf-8')

    def admin_headers(self) -> dict[str, str]:
        headers = {'X-Engineer-Id': 'integration-admin'}
        if ADMIN_KEY:
            headers['X-API-Key'] = ADMIN_KEY
        return headers

    def test_service_and_orchestrator_health(self) -> None:
        loom = self.call_json('http://localhost:8090/api/v1/health')
        orch = self.call_json('http://localhost:8080/api/v1/health')
        self.assertEqual(loom['service'], 'loom-services')
        self.assertEqual(orch['service'], 'orchestrator')
        self.assertEqual(orch['services']['cmm']['reason'], 'cmm_host_native_only')
        self.assertEqual(orch['services']['cmm']['details']['scope'], 'host_native_only')

    def test_metrics_endpoints_publish_prometheus_text(self) -> None:
        loom_metrics = self.call_text('http://localhost:8090/api/v1/metrics')
        orch_metrics = self.call_text('http://localhost:8080/api/v1/metrics')
        self.assertIn('loom_requests_total', loom_metrics)
        self.assertIn('loom_requests_total', orch_metrics)

    def test_orchestrator_domain_query(self) -> None:
        body = self.call_json('http://localhost:8080/api/v1/ask', {'query': 'What are XCP timing constraints?'})
        self.assertEqual(body['route'], 'domain')
        self.assertGreaterEqual(len(body['citations']), 1)

    def test_hindsight_memory_routes(self) -> None:
        headers = {
            'X-Engineer-Id': 'integration-eng',
            'X-Session-Id': 'integration-sess',
            'X-Objective-Id': 'integration-obj',
            'X-Project-Id': 'integration-project',
        }
        retain = self.call_json(
            'http://localhost:8080/api/v1/memory/retain',
            {
                'text': 'We decided to use the Azure model router for Hindsight.',
                'tags': ['decision'],
                'transcript_ref': 'cursor://integration/session/1',
                'transcript_excerpt': 'Wrap-up: use Azure router, keep sequential Graphiti path, defer WSL validation.',
            },
            headers=headers,
        )
        recall = self.call_json('http://localhost:8080/api/v1/memory/recall', {'query': 'What did we decide about Hindsight?'}, headers=headers)
        reflect = self.call_json('http://localhost:8080/api/v1/memory/reflect', {'query': 'Summarize the Hindsight routing decision.'}, headers=headers)
        resume = self.call_json('http://localhost:8080/api/v1/session/resume', {'token_budget': 900}, headers=headers)
        self.assertTrue(retain['ok'])
        self.assertTrue(recall['ok'])
        self.assertTrue(reflect['ok'])
        self.assertTrue(resume['ok'])
        self.assertEqual(retain['request_context']['project_id'], 'integration-project')
        self.assertEqual(resume['token_budget'], 900)
        self.assertIn('sections', resume['result'])

    def test_hindsight_project_seed_routes(self) -> None:
        headers = {
            'X-Engineer-Id': 'integration-eng',
            'X-Session-Id': 'integration-seed-sess',
            'X-Objective-Id': 'integration-seed-obj',
            'X-Project-Id': 'integration-project',
        }
        seed = self.call_json(
            'http://localhost:8080/api/v1/memory/seed',
            {
                'steering_paths': ['.kiro/steering/loom-core.md'],
                'progress_path': '.kiro/steering/loom-progress.md',
            },
            headers=headers,
        )
        recall = self.call_json(
            'http://localhost:8080/api/v1/memory/recall',
            {'query': 'What steering or progress files were seeded for this objective?'},
            headers=headers,
        )
        self.assertTrue(seed['ok'])
        self.assertEqual(seed['seed_mode'], 'bundled_summary')
        self.assertEqual(len(seed['retained']), 2)
        self.assertLess(seed['bundle_chars'], 900)
        chunks = ''.join(chunk.get('text', '') for chunk in recall.get('result', {}).get('chunks', {}).values())
        self.assertIn('loom-core.md', chunks)
        self.assertIn('loom-progress.md', chunks)

    def test_memory_promote_and_correction_review_flow(self) -> None:
        memory_headers = {
            'X-Engineer-Id': 'integration-eng',
            'X-Session-Id': 'integration-promote-sess',
            'X-Objective-Id': 'integration-promote-obj',
            'X-Project-Id': 'integration-project',
        }
        self.call_json(
            'http://localhost:8080/api/v1/memory/retain',
            {
                'text': 'Promotion candidate: approved practical note about preserving transcript references and sequential Graphiti ingestion.',
                'tags': ['decision', 'status'],
                'transcript_ref': 'cursor://integration/promote/1',
                'transcript_excerpt': 'Capture this as shared team knowledge once reviewed.',
            },
            headers=memory_headers,
        )
        promote = self.call_json(
            'http://localhost:8080/api/v1/memory/promote',
            {'query': 'What practical note should we promote for this objective?', 'title': 'Integration promotion'},
            headers=memory_headers,
        )
        correction_id = promote['correction']['id']
        review = self.call_json(
            f'http://localhost:8090/admin/corrections/{correction_id}/review',
            {'decision': 'approved', 'publish_practical_note': True, 'federate': True},
            headers=self.admin_headers(),
        )
        notes = self.call_json('http://localhost:8090/api/v1/practical-notes', None, headers={'X-API-Key': os.getenv('LOOM_API_KEY', '')} if os.getenv('LOOM_API_KEY') else None, method='GET')
        export = self.call_json('http://localhost:8090/admin/federation/export', {'limit': 20}, headers=self.admin_headers())
        self.assertTrue(promote['ok'])
        self.assertEqual(review['correction']['status'], 'approved')
        self.assertGreaterEqual(notes['count'], 1)
        self.assertTrue(export['ok'])

    def test_spec_session_generate_update_audit(self) -> None:
        target = '.kiro/specs/aaems-system-architecture/design.integration-test.md'
        headers = {
            'X-Engineer-Id': 'integration-eng',
            'X-Session-Id': 'integration-sess',
            'X-Objective-Id': 'integration-obj',
            'X-Project-Id': 'integration-project',
        }
        generate = self.call_json('http://localhost:8080/api/v1/spec/generate', {
            'artifact_type': 'design',
            'prompt': 'Update AUTOSAR design around E2E Library and provenance flow',
            'target_path': target,
        }, headers=headers)
        update = self.call_json('http://localhost:8080/api/v1/spec/update', {
            'artifact_type': 'design',
            'prompt': 'Preserve unresolved items and add revision note for E2E Library follow-up',
            'target_path': target,
        }, headers=headers)
        audit = self.call_json('http://localhost:8080/api/v1/spec/audit', {
            'artifact_type': 'design',
            'target_path': target,
        }, headers=headers)
        self.assertEqual(generate['status'], 'ok')
        self.assertEqual(update['status'], 'ok')
        self.assertTrue(audit['found'])
        self.assertGreaterEqual(len(audit['revisions']), 2)
        host_path = Path('/Users/chj1ana/AutoBrain/.kiro/specs/aaems-system-architecture/design.integration-test.md')
        self.assertTrue(host_path.exists())

    def test_admin_audit_export_route(self) -> None:
        export = self.call_json('http://localhost:8080/admin/audit/export', {'limit': 100}, headers=self.admin_headers())
        self.assertTrue(export['ok'])
        self.assertGreaterEqual(export['count'], 1)


if __name__ == '__main__':
    unittest.main()
