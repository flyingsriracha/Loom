from __future__ import annotations

from pathlib import Path


RUNTIME_ENV_RELATIVE = Path('.kiro/runtime/ai-runtime.env')


def discover_runtime_env_path(start: Path | None = None) -> Path | None:
    candidates = []
    if start is not None:
        candidates.append(start)
    candidates.append(Path(__file__).resolve())
    for base in candidates:
        for parent in [base, *base.parents]:
            probe = parent / RUNTIME_ENV_RELATIVE
            if probe.exists():
                return probe
    direct = Path('/app/.kiro/runtime/ai-runtime.env')
    if direct.exists():
        return direct
    return None


def load_runtime_env() -> dict[str, str]:
    path = discover_runtime_env_path()
    if path is None:
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip()
    return values
