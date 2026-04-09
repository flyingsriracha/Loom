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


def build_api_auth_dependency(settings: Settings, *, admin_only: bool = False) -> Callable:
    async def dependency(
        x_api_key: str | None = Header(default=None, alias='X-API-Key'),
        x_engineer_id: str | None = Header(default=None, alias='X-Engineer-Id'),
        x_session_id: str | None = Header(default=None, alias='X-Session-Id'),
        x_objective_id: str | None = Header(default=None, alias='X-Objective-Id'),
        x_project_id: str | None = Header(default=None, alias='X-Project-Id'),
    ) -> APIRequestContext:
        allow_local_dev_bypass = getattr(settings, 'allow_local_dev_bypass', True)
        if not settings.loom_api_key and not settings.loom_admin_api_key:
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

        role: str | None = None
        if settings.loom_admin_api_key and x_api_key == settings.loom_admin_api_key:
            role = 'admin'
        elif settings.loom_api_key and x_api_key == settings.loom_api_key:
            role = 'engineer'

        if role is None:
            raise HTTPException(status_code=401, detail='invalid API key')
        if admin_only and role != 'admin':
            raise HTTPException(status_code=403, detail='admin API key required')

        return APIRequestContext(
            role=role,
            auth_mode='api-key',
            engineer_id=x_engineer_id,
            session_id=x_session_id,
            objective_id=x_objective_id,
            project_id=x_project_id,
        )

    return dependency
