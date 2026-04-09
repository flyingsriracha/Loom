from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

OUTPUT = Path(__file__).resolve().parents[1] / 'artifacts' / 'retrieval_eval_results.json'
BASE_URL = 'http://localhost:8090'

CASES = [
    {
        'name': 'autosar_e2e_library',
        'path': '/api/v1/query',
        'payload': {'query': 'E2E Library', 'source_system': 'autosar-fusion', 'limit': 3},
        'expect_results': True,
    },
    {
        'name': 'asam_xcp_connect',
        'path': '/api/v1/query',
        'payload': {'query': 'XCP CONNECT', 'source_system': 'ASAMKnowledgeDB', 'limit': 3},
        'expect_results': True,
    },
    {
        'name': 'no_results_guard',
        'path': '/api/v1/query',
        'payload': {'query': 'nonexistent foobarbaz protocol 9999', 'limit': 3},
        'expect_results': False,
    },
]


def call(path: str, payload: dict) -> dict:
    req = Request(BASE_URL + path, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode('utf-8'))


def main() -> None:
    results = []
    for case in CASES:
        body = call(case['path'], case['payload'])
        result_count = len(body.get('results', []))
        passed = (result_count > 0) if case['expect_results'] else bool(body.get('no_results'))
        results.append({'name': case['name'], 'passed': passed, 'result_count': result_count, 'warnings': body.get('warnings', [])})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({'cases': results}, indent=2))
    print(json.dumps({'cases': results}, indent=2))


if __name__ == '__main__':
    main()
