from __future__ import annotations

import unittest

from fastapi import HTTPException

from common.auth import build_api_auth_dependency


def _settings(**overrides):
    base = {
        'loom_api_key': None,
        'loom_admin_api_key': None,
        'loom_consumer_api_keys': (),
        'allow_local_dev_bypass': True,
    }
    base.update(overrides)
    return type('Settings', (), base)()


class AuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_dev_bypass_still_works_when_enabled(self) -> None:
        settings = _settings()
        dependency = build_api_auth_dependency(settings, admin_only=False)
        context = await dependency(x_api_key=None, x_engineer_id='eng', x_session_id='sess', x_objective_id='obj', x_project_id='proj')
        self.assertEqual(context.auth_mode, 'local-dev-bypass')
        self.assertEqual(context.project_id, 'proj')

    async def test_missing_keys_fail_closed_when_bypass_disabled(self) -> None:
        settings = _settings(allow_local_dev_bypass=False)
        dependency = build_api_auth_dependency(settings, admin_only=False)
        with self.assertRaises(HTTPException) as ctx:
            await dependency(x_api_key=None, x_engineer_id='eng', x_session_id='sess', x_objective_id='obj', x_project_id='proj')
        self.assertEqual(ctx.exception.status_code, 503)


class ConsumerRoleTests(unittest.IsolatedAsyncioTestCase):
    async def test_consumer_key_resolves_to_consumer_role_when_allowed(self) -> None:
        settings = _settings(
            loom_api_key='eng-key',
            loom_consumer_api_keys=('leadgen-key',),
            allow_local_dev_bypass=False,
        )
        dependency = build_api_auth_dependency(settings, allow_consumer=True)
        context = await dependency(x_api_key='leadgen-key', x_engineer_id='leadgen-agent', x_session_id=None, x_objective_id=None, x_project_id=None)
        self.assertEqual(context.role, 'consumer')
        self.assertEqual(context.engineer_id, 'leadgen-agent')
        self.assertEqual(context.auth_mode, 'api-key')

    async def test_consumer_key_rejected_on_engineer_only_endpoint(self) -> None:
        settings = _settings(
            loom_api_key='eng-key',
            loom_consumer_api_keys=('leadgen-key',),
            allow_local_dev_bypass=False,
        )
        dependency = build_api_auth_dependency(settings)
        with self.assertRaises(HTTPException) as ctx:
            await dependency(x_api_key='leadgen-key', x_engineer_id='leadgen-agent', x_session_id=None, x_objective_id=None, x_project_id=None)
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_consumer_key_rejected_on_admin_endpoint(self) -> None:
        settings = _settings(
            loom_admin_api_key='admin-key',
            loom_consumer_api_keys=('leadgen-key',),
            allow_local_dev_bypass=False,
        )
        dependency = build_api_auth_dependency(settings, admin_only=True)
        with self.assertRaises(HTTPException) as ctx:
            await dependency(x_api_key='leadgen-key', x_engineer_id=None, x_session_id=None, x_objective_id=None, x_project_id=None)
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_engineer_key_still_accepted_on_consumer_endpoint(self) -> None:
        settings = _settings(
            loom_api_key='eng-key',
            loom_consumer_api_keys=('leadgen-key',),
            allow_local_dev_bypass=False,
        )
        dependency = build_api_auth_dependency(settings, allow_consumer=True)
        context = await dependency(x_api_key='eng-key', x_engineer_id='alice', x_session_id=None, x_objective_id=None, x_project_id=None)
        self.assertEqual(context.role, 'engineer')

    async def test_admin_key_still_accepted_on_consumer_endpoint(self) -> None:
        settings = _settings(
            loom_admin_api_key='admin-key',
            loom_consumer_api_keys=('leadgen-key',),
            allow_local_dev_bypass=False,
        )
        dependency = build_api_auth_dependency(settings, allow_consumer=True)
        context = await dependency(x_api_key='admin-key', x_engineer_id=None, x_session_id=None, x_objective_id=None, x_project_id=None)
        self.assertEqual(context.role, 'admin')

    async def test_admin_only_and_allow_consumer_are_mutually_exclusive(self) -> None:
        settings = _settings()
        with self.assertRaises(ValueError):
            build_api_auth_dependency(settings, admin_only=True, allow_consumer=True)

    async def test_unknown_key_rejected_when_consumer_keys_configured(self) -> None:
        settings = _settings(
            loom_consumer_api_keys=('leadgen-key',),
            allow_local_dev_bypass=False,
        )
        dependency = build_api_auth_dependency(settings, allow_consumer=True)
        with self.assertRaises(HTTPException) as ctx:
            await dependency(x_api_key='wrong-key', x_engineer_id=None, x_session_id=None, x_objective_id=None, x_project_id=None)
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == '__main__':
    unittest.main()
