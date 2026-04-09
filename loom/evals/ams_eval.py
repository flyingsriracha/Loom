from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

OUTPUT = Path(__file__).resolve().parents[1] / 'artifacts' / 'ams_eval_results.json'
BASE_URL = 'http://localhost:8080'
HEADERS = {
    'Content-Type': 'application/json',
    'X-Engineer-Id': 'ams-eval-eng',
    'X-Session-Id': 'ams-eval-sess',
    'X-Objective-Id': 'ams-eval-obj',
    'X-Project-Id': 'ams-eval-project',
}


def call(path: str, payload: dict) -> dict:
    req = Request(BASE_URL + path, data=json.dumps(payload).encode('utf-8'), headers=HEADERS, method='POST')
    with urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode('utf-8'))


def main() -> None:
    retain = call('/api/v1/memory/retain', {
        'text': 'AMS eval note: transcript references and budgeted resume context are active.',
        'tags': ['decision', 'status'],
        'transcript_ref': 'cursor://ams-eval/session/1',
        'transcript_excerpt': 'Transcript reference capture should remain available for debugging drift.',
    })
    resume = call('/api/v1/session/resume', {'token_budget': 900})
    seed = call('/api/v1/memory/seed', {
        'steering_paths': ['.kiro/steering/loom-core.md'],
        'progress_path': '.kiro/steering/loom-progress.md',
    })
    recall = call('/api/v1/memory/recall', {'query': 'What transcript references or steering context exist for this objective?'})

    payload = {
        'retain_ok': retain.get('ok') is True,
        'project_id_propagated': retain.get('request_context', {}).get('project_id') == 'ams-eval-project',
        'resume_ok': resume.get('ok') is True,
        'resume_has_sections': sorted((resume.get('result') or {}).get('sections', {}).keys()) == ['open_threads', 'recent_decisions', 'steering', 'transcript_refs'],
        'seed_ok': seed.get('ok') is True,
        'seed_mode': seed.get('seed_mode'),
        'seed_bundle_chars': seed.get('bundle_chars'),
        'seed_compact': (seed.get('bundle_chars') or 10_000) < 900,
        'recall_ok': recall.get('ok') is True,
        'recall_result_count': len((recall.get('result') or {}).get('results', [])),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == '__main__':
    main()
