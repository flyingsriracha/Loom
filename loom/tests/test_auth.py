from __future__ import annotations

import unittest

from fastapi import HTTPException

from common.auth import build_api_auth_dependency


class AuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_dev_bypass_still_works_when_enabled(self) -> None:
        settings = type('Settings', (), {'loom_api_key': None, 'loom_admin_api_key': None, 'allow_local_dev_bypass': True})()
        dependency = build_api_auth_dependency(settings, admin_only=False)
        context = await dependency(x_api_key=None, x_engineer_id='eng', x_session_id='sess', x_objective_id='obj', x_project_id='proj')
        self.assertEqual(context.auth_mode, 'local-dev-bypass')
        self.assertEqual(context.project_id, 'proj')

    async def test_missing_keys_fail_closed_when_bypass_disabled(self) -> None:
        settings = type('Settings', (), {'loom_api_key': None, 'loom_admin_api_key': None, 'allow_local_dev_bypass': False})()
        dependency = build_api_auth_dependency(settings, admin_only=False)
        with self.assertRaises(HTTPException) as ctx:
            await dependency(x_api_key=None, x_engineer_id='eng', x_session_id='sess', x_objective_id='obj', x_project_id='proj')
        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == '__main__':
    unittest.main()
