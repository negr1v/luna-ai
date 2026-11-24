import subprocess
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from openjarvis_bridge import handle_openjarvis_execute


class TestOpenJarvisExecutionDisabled(AioHTTPTestCase):
    async def get_application(self):
        app = web.Application()
        app.router.add_post("/api/openjarvis/execute", handle_openjarvis_execute)
        return app

    @unittest_run_loop
    async def test_python_code_is_rejected_without_starting_subprocess(self):
        with patch.object(subprocess, "run") as subprocess_run:
            response = await self.client.post(
                "/api/openjarvis/execute",
                json={"code": "print('must not execute')"},
            )
            payload = await response.json()

        self.assertEqual(response.status, 501)
        self.assertEqual(payload["error_code"], "PYTHON_EXECUTION_DISABLED")
        self.assertFalse(payload["success"])
        subprocess_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
