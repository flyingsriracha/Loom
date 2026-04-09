from __future__ import annotations

from typing import Any, Callable, TypeVar, cast

F = TypeVar('F', bound=Callable[..., Any])

try:
    from langsmith import traceable as _traceable
    from langsmith.wrappers import wrap_openai as _wrap_openai
except Exception:  # pragma: no cover - optional dependency
    _traceable = None
    _wrap_openai = None


def traceable(*, name: str | None = None, run_type: str = 'chain', metadata: dict[str, Any] | None = None):
    def decorator(func: F) -> F:
        if _traceable is None:
            return func
        traced = _traceable(name=name or func.__qualname__, run_type=run_type, metadata=metadata)(func)
        return cast(F, traced)

    return decorator


def wrap_openai_client(client: Any) -> Any:
    if _wrap_openai is None:
        return client
    try:
        return _wrap_openai(client)
    except Exception:
        return client
