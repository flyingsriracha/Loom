from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

OUTPUT = Path(__file__).resolve().parents[1] / 'artifacts' / 'spec_session_eval_results.json'
BASE_URL = 'http://localhost:8080'
HEADERS = {
    'Content-Type': 'application/json',
    'X-Engineer-Id': 'eval-eng',
    'X-Session-Id': 'eval-sess',
    'X-Objective-Id': 'eval-obj',
}
TARGET = '.kiro/specs/aaems-system-architecture/design.eval-test.md'


def call(path: str, payload: dict) -> dict:
    req = Request(BASE_URL + path, data=json.dumps(payload).encode('utf-8'), headers=HEADERS, method='POST')
    with urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode('utf-8'))


def main() -> None:
    generate = call('/api/v1/spec/generate', {'artifact_type': 'design', 'prompt': 'Update AUTOSAR design around E2E Library and provenance flow', 'target_path': TARGET})
    update = call('/api/v1/spec/update', {'artifact_type': 'design', 'prompt': 'Preserve unresolved items and add revision note for E2E Library follow-up', 'target_path': TARGET})
    audit = call('/api/v1/spec/audit', {'artifact_type': 'design', 'target_path': TARGET})
    payload = {
        'generate_ok': generate.get('status') == 'ok',
        'update_ok': update.get('status') == 'ok',
        'audit_found': audit.get('found') is True,
        'revision_count': len(audit.get('revisions', [])),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == '__main__':
    main()
