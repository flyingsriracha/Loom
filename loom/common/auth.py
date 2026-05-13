from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import Header, HTTPException

from common.settings import Settings


@dataclass(frozen=True)
class APIRequestContext:
    role: str
    auth_mode: str
    engineer_id: str | None
    session_id: str | None
    objective_id: str | None
    project_id: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            'role': self.role,
            'auth_mode': self.auth_mode,
            'engineer_id': self.engineer_id,
            'session_id': self.session_id,
            'objective_id': self.objective_id,
            'project_id': self.project_id,
        }


def _resolve_role(settings: Settings, x_api_key: str) -> str | None:
    if settings.loom_admin_api_key and x_api_key == settings.loom_admin_api_key:
        return 'admin'
    if settings.loom_api_key and x_api_key == settings.loom_api_key:
        return 'engineer'
    consumer_keys = getattr(settings, 'loom_consumer_api_keys', ()) or ()
    if x_api_key in consumer_keys:
        return 'consumer'
    return None


def _any_key_configured(settings: Settings) -> bool:
    consumer_keys = getattr(settings, 'loom_consumer_api_keys', ()) or ()
    return bool(settings.loom_api_key or settings.loom_admin_api_key or consumer_keys)


def build_api_auth_dependency(
    settings: Settings,
    *,
    admin_only: bool = False,
    allow_consumer: bool = False,
) -> Callable:
    """Build a FastAPI dependency that resolves the request role and enforces scope.

    Role hierarchy (highest to lowest): admin > engineer > consumer.

    - `admin_only=True` requires the admin key.
    - `allow_consumer=True` accepts consumer/engineer/admin. Use this for the
      read-only external-grounding surface (loom_ask, loom_search_knowledge,
      loom_get_node_provenance).
    - Default (neither flag set) accepts engineer/admin only. Consumer keys are
      rejected server-side on any endpoint that does not opt in.
    """

    if admin_only and allow_consumer:
        raise ValueError('admin_only and allow_consumer are mutually exclusive')

    async def dependency(
        x_api_key: str | None = Header(default=None, alias='X-API-Key'),
        x_engineer_id: str | None = Header(default=None, alias='X-Engineer-Id'),
        x_session_id: str | None = Header(default=None, alias='X-Session-Id'),
        x_objective_id: str | None = Header(default=None, alias='X-Objective-Id'),
        x_project_id: str | None = Header(default=None, alias='X-Project-Id'),
    ) -> APIRequestContext:
        allow_local_dev_bypass = getattr(settings, 'allow_local_dev_bypass', True)
        if not _any_key_configured(settings):
            if not allow_local_dev_bypass:
                raise HTTPException(status_code=503, detail='authentication is not configured for this deployment')
            return APIRequestContext(
                role='admin',
                auth_mode='local-dev-bypass',
                engineer_id=x_engineer_id,
                session_id=x_session_id,
                objective_id=x_objective_id,
                project_id=x_project_id,
            )

        if x_api_key is None:
            raise HTTPException(status_code=401, detail='missing X-API-Key header')

        role = _resolve_role(settings, x_api_key)
        if role is None:
            raise HTTPException(status_code=401, detail='invalid API key')
        if admin_only and role != 'admin':
            raise HTTPException(status_code=403, detail='admin API key required')
        if not admin_only and not allow_consumer and role == 'consumer':
            raise HTTPException(status_code=403, detail='consumer API key is limited to read-only grounding endpoints')

        return APIRequestContext(
            role=role,
            auth_mode='api-key',
            engineer_id=x_engineer_id,
            session_id=x_session_id,
            objective_id=x_objective_id,
            project_id=x_project_id,
        )

    return dependency
