from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean
from time import perf_counter
from urllib.request import Request, urlopen

OUTPUT = Path(__file__).resolve().parents[1] / 'artifacts' / 'load_eval_results.json'
BASE_URL = os.getenv('LOOM_LOAD_EVAL_BASE_URL', 'http://localhost:8090')
CONCURRENCY = int(os.getenv('LOOM_LOAD_EVAL_CONCURRENCY', '10'))
QUERY = os.getenv('LOOM_LOAD_EVAL_QUERY', 'XCP CONNECT')
API_KEY = os.getenv('LOOM_API_KEY')


def call_once(idx: int) -> dict:
    headers = {'Content-Type': 'application/json', 'X-Engineer-Id': f'load-eng-{idx}', 'X-Session-Id': f'load-sess-{idx}', 'X-Objective-Id': 'load-eval-obj', 'X-Project-Id': 'load-eval-project'}
    if API_KEY:
        headers['X-API-Key'] = API_KEY
    req = Request(BASE_URL + '/api/v1/query', data=json.dumps({'query': QUERY, 'limit': 3}).encode(), headers=headers, method='POST')
    started = perf_counter()
    with urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode())
    elapsed_ms = (perf_counter() - started) * 1000
    return {'elapsed_ms': elapsed_ms, 'ok': body.get('ok') is True, 'result_count': len(body.get('results', []))}


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def main() -> None:
    results = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(call_once, idx) for idx in range(CONCURRENCY)]
        for future in as_completed(futures):
            results.append(future.result())
    latencies = [item['elapsed_ms'] for item in results]
    payload = {
        'base_url': BASE_URL,
        'concurrency': CONCURRENCY,
        'query': QUERY,
        'successful_requests': sum(1 for item in results if item['ok']),
        'avg_latency_ms': round(mean(latencies), 2) if latencies else 0.0,
        'p95_latency_ms': round(percentile(latencies, 0.95), 2),
        'max_latency_ms': round(max(latencies), 2) if latencies else 0.0,
        'target_pass': percentile(latencies, 0.95) <= 2000.0 and all(item['ok'] for item in results),
        'results': [{**item, 'elapsed_ms': round(item['elapsed_ms'], 2)} for item in sorted(results, key=lambda item: item['elapsed_ms'])],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == '__main__':
    main()
