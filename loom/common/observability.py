from __future__ import annotations

from collections import defaultdict
from threading import Lock
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import PlainTextResponse


class MetricsRegistry:
    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self._lock = Lock()
        self._totals: dict[str, float] = defaultdict(float)
        self._durations_ms: dict[tuple[str, str], float] = defaultdict(float)
        self._counts: dict[tuple[str, str], int] = defaultdict(int)

    def record(self, *, method: str, path: str, status_code: int, duration_ms: float) -> None:
        key = (method, path)
        with self._lock:
            self._totals['requests_total'] += 1
            if status_code >= 400:
                self._totals['errors_total'] += 1
            self._durations_ms[key] += duration_ms
            self._counts[key] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            by_route = []
            for (method, path), count in sorted(self._counts.items()):
                total_ms = self._durations_ms[(method, path)]
                by_route.append(
                    {
                        'method': method,
                        'path': path,
                        'requests': count,
                        'avg_latency_ms': round(total_ms / max(count, 1), 2),
                    }
                )
            return {
                'service': self.service_name,
                'requests_total': int(self._totals['requests_total']),
                'errors_total': int(self._totals['errors_total']),
                'routes': by_route,
            }

    def render_prometheus(self) -> str:
        lines = [
            '# HELP loom_requests_total Total HTTP requests observed.',
            '# TYPE loom_requests_total counter',
            f'loom_requests_total{{service="{self.service_name}"}} {int(self._totals["requests_total"])}',
            '# HELP loom_errors_total Total HTTP responses with status >= 400.',
            '# TYPE loom_errors_total counter',
            f'loom_errors_total{{service="{self.service_name}"}} {int(self._totals["errors_total"])}',
            '# HELP loom_route_avg_latency_ms Average latency in milliseconds by route.',
            '# TYPE loom_route_avg_latency_ms gauge',
        ]
        for route in self.snapshot()['routes']:
            lines.append(
                'loom_route_avg_latency_ms{service="%s",method="%s",path="%s"} %.2f'
                % (self.service_name, route['method'], route['path'], route['avg_latency_ms'])
            )
        return '\n'.join(lines) + '\n'


def metrics_response(registry: MetricsRegistry) -> PlainTextResponse:
    return PlainTextResponse(registry.render_prometheus(), media_type='text/plain; version=0.0.4')


async def instrument_request(request: Request, call_next, *, registry: MetricsRegistry):
    request_id = request.headers.get('X-Request-Id') or uuid4().hex
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        registry.record(method=request.method, path=request.url.path, status_code=500, duration_ms=(perf_counter() - started) * 1000)
        raise
    duration_ms = (perf_counter() - started) * 1000
    registry.record(method=request.method, path=request.url.path, status_code=response.status_code, duration_ms=duration_ms)
    response.headers['X-Request-Id'] = request_id
    return response
