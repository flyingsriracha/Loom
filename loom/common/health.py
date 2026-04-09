from __future__ import annotations

import socket
from urllib.error import URLError
from urllib.request import urlopen


def tcp_check(host: str, port: int, timeout: float = 1.5) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, 'ok'
    except OSError as exc:
        return False, str(exc)


def http_check(url: str, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 400, f'http {response.status}'
    except URLError as exc:
        return False, str(exc.reason)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return False, str(exc)
