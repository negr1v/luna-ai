"""
Phase 9B.1B — Safe Port & Startup Management Tests
ACCIO LUNA V4.0

Validates:
1. Default host (127.0.0.1) and port (7860) configuration.
2. Address-in-use errors (EADDRINUSE / WinError 10048) are cleanly intercepted with exit code 1.
3. Windows WinError 10048 attribute / code is properly handled.
4. Unrelated OSError exceptions (e.g. EACCES, ENOENT) are not swallowed and re-raised.
5. create_app() signature and returned aiohttp web.Application remain compatible.
6. No process termination (psutil.Process.terminate/kill) is attempted.
7. No automatic alternative port is silently chosen.
"""

import unittest
from unittest.mock import patch, MagicMock
import io
import sys
import os
import errno

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import luna_server
from aiohttp import web

class TestPhase9B1Startup(unittest.TestCase):

    def test_01_default_host_and_port(self):
        """1. Normal startup defaults to port 7860 and host 127.0.0.1."""
        self.assertEqual(luna_server.PORT, 7860)

        with patch("aiohttp.web.run_app") as mock_run:
            app = MagicMock()
            luna_server.safe_start_server(app)
            mock_run.assert_called_once_with(app, host="127.0.0.1", port=7860)

    def test_02_address_in_use_error_handled_cleanly(self):
        """2. Address-in-use error is caught and terminates cleanly with exit code 1."""
        err = OSError(errno.EADDRINUSE, "Address already in use")
        with patch("aiohttp.web.run_app", side_effect=err):
            captured_out = io.StringIO()
            with patch("sys.stdout", captured_out):
                with self.assertRaises(SystemExit) as cm:
                    luna_server.safe_start_server(MagicMock(), host="127.0.0.1", port=7860)
                self.assertEqual(cm.exception.code, 1)

            output = captured_out.getvalue()
            self.assertIn("BAŞLATMA HATASI", output)
            self.assertIn("netstat -ano | findstr :7860", output)

    def test_03_windows_winerror_10048_recognized(self):
        """3. Windows WinError 10048 is recognized specifically."""
        err = OSError()
        err.winerror = 10048
        err.strerror = "Only one usage of each socket address (protocol/network address/port) is normally permitted"

        with patch("aiohttp.web.run_app", side_effect=err):
            captured_out = io.StringIO()
            with patch("sys.stdout", captured_out):
                with self.assertRaises(SystemExit) as cm:
                    luna_server.safe_start_server(MagicMock(), host="127.0.0.1", port=7860)
                self.assertEqual(cm.exception.code, 1)

            output = captured_out.getvalue()
            self.assertIn("Port 7860 şu anda başka bir süreç tarafından kullanılıyor", output)

    def test_04_unrelated_oserror_not_swallowed(self):
        """4. Unrelated OSError exceptions (e.g. EACCES, ENOMEM) are re-raised."""
        err = OSError(errno.EACCES, "Permission denied")
        err.winerror = 10013

        with patch("aiohttp.web.run_app", side_effect=err):
            with self.assertRaises(OSError) as cm:
                luna_server.safe_start_server(MagicMock(), host="127.0.0.1", port=7860)
            self.assertEqual(cm.exception.errno, errno.EACCES)

    def test_05_create_app_remains_compatible(self):
        """5. create_app() returns valid aiohttp web.Application with all existing routes."""
        app = luna_server.create_app()
        self.assertIsInstance(app, web.Application)
        route_paths = [r.resource.canonical for r in app.router.routes() if r.resource is not None]
        self.assertIn("/", route_paths)
        self.assertIn("/api/config", route_paths)
        self.assertIn("/api/tasks", route_paths)
        self.assertIn("/api/telegram/messages", route_paths)

    def test_06_no_process_termination_attempted(self):
        """6. No process termination (kill/terminate) is attempted when port is occupied."""
        err = OSError(errno.EADDRINUSE, "Address already in use")
        with patch("aiohttp.web.run_app", side_effect=err):
            with patch("psutil.Process.terminate") as mock_terminate, \
                 patch("psutil.Process.kill") as mock_kill, \
                 patch("os.kill") as mock_os_kill:
                with self.assertRaises(SystemExit):
                    luna_server.safe_start_server(MagicMock(), host="127.0.0.1", port=7860)

                mock_terminate.assert_not_called()
                mock_kill.assert_not_called()
                mock_os_kill.assert_not_called()

    def test_07_no_automatic_alternative_port_selected(self):
        """7. Port conflict never silently switches to port 7861 or another port."""
        err = OSError(errno.EADDRINUSE, "Address already in use")
        recorded_calls = []

        def track_run_app(app, host, port):
            recorded_calls.append((host, port))
            raise err

        with patch("aiohttp.web.run_app", side_effect=track_run_app):
            with self.assertRaises(SystemExit):
                luna_server.safe_start_server(MagicMock(), host="127.0.0.1", port=7860)

        self.assertEqual(len(recorded_calls), 1)
        self.assertEqual(recorded_calls[0], ("127.0.0.1", 7860))

if __name__ == "__main__":
    unittest.main(verbosity=2)
