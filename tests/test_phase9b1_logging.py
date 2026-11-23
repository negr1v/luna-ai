"""
Phase 9B.1D — Rotating Logging & Startup Integration Acceptance Tests
ACCIO LUNA V4.0

Validates:
1. Runtime log file configuration and path.
2. Maximum size configuration (2 MB).
3. Backup count configuration (5).
4. UTF-8 encoding.
5. Formatter includes timestamp, level, name and message.
6. setup_logging() idempotency (no duplicate handlers).
7. Single log message is written exactly once.
8. File rotation mechanics.
9. Backup retention limit (does not exceed backupCount).
10. Console output handler functionality.
11. File handler initialization failure fallback.
12. Startup path initializes logging before server execution.
13. Port conflict error logging.
14. Normal startup and shutdown event logging.
15. Secret configuration values are not leaked into log output.
"""

import unittest
from unittest.mock import patch, MagicMock
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import tempfile
import shutil
import errno
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import luna_server

class TestPhase9B1Logging(unittest.TestCase):

    def setUp(self):
        self.original_handlers = list(logging.getLogger("luna").handlers)
        self.test_dir = tempfile.mkdtemp(prefix="luna_log_test_")

    def tearDown(self):
        logger = logging.getLogger("luna")
        for h in list(logger.handlers):
            h.close()
            logger.removeHandler(h)
        for h in self.original_handlers:
            logger.addHandler(h)

        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir, ignore_errors=True)
            except Exception:
                pass

    def test_01_log_file_configuration_and_constants(self):
        """1, 2, 3, 4: Confirms LOG_FILE, 2 MB max size, 5 backups, and UTF-8 encoding."""
        self.assertEqual(luna_server.LOG_MAX_BYTES, 2 * 1024 * 1024)
        self.assertEqual(luna_server.LOG_BACKUP_COUNT, 5)
        self.assertTrue(luna_server.LOG_FILE.endswith("luna_runtime.log"))

        test_log_file = os.path.join(self.test_dir, "test_conf.log")
        with patch.object(luna_server, "LOG_FILE", test_log_file):
            logger = logging.getLogger("luna")
            for h in list(logger.handlers):
                logger.removeHandler(h)

            log = luna_server.setup_logging()
            file_handlers = [h for h in log.handlers if isinstance(h, RotatingFileHandler)]
            self.assertEqual(len(file_handlers), 1)
            fh = file_handlers[0]
            self.assertEqual(fh.maxBytes, 2 * 1024 * 1024)
            self.assertEqual(fh.backupCount, 5)
            self.assertEqual(fh.encoding.lower(), "utf-8")

    def test_05_log_format_contains_timestamp_level_and_message(self):
        """5. Format includes asctime, levelname, name and message."""
        test_log_file = os.path.join(self.test_dir, "format_test.log")
        with patch.object(luna_server, "LOG_FILE", test_log_file):
            logger = logging.getLogger("luna")
            for h in list(logger.handlers):
                logger.removeHandler(h)

            log = luna_server.setup_logging()
            log.info("FORMAT_VERIFICATION_MESSAGE")

            with open(test_log_file, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("[INFO]", content)
            self.assertIn("[luna]", content)
            self.assertIn("FORMAT_VERIFICATION_MESSAGE", content)

    def test_06_idempotent_setup_logging_no_duplicates(self):
        """6, 7: Repeated setup_logging calls do not duplicate handlers or messages."""
        test_log_file = os.path.join(self.test_dir, "idempotent.log")
        with patch.object(luna_server, "LOG_FILE", test_log_file):
            logger = logging.getLogger("luna")
            for h in list(logger.handlers):
                logger.removeHandler(h)

            # Call multiple times
            luna_server.setup_logging()
            luna_server.setup_logging()
            log = luna_server.setup_logging()

            file_handlers = [h for h in log.handlers if isinstance(h, RotatingFileHandler)]
            console_handlers = [h for h in log.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)]

            self.assertEqual(len(file_handlers), 1)
            self.assertEqual(len(console_handlers), 1)

            log.info("SINGLE_DISPATCH_MESSAGE")
            with open(test_log_file, "r", encoding="utf-8") as f:
                lines = [l for l in f.readlines() if "SINGLE_DISPATCH_MESSAGE" in l]

            self.assertEqual(len(lines), 1)

    def test_08_and_09_rotation_and_backup_retention(self):
        """8, 9: File rotation and backup retention limit work as expected."""
        test_log_file = os.path.join(self.test_dir, "rotating.log")
        # Use small maxBytes (100 bytes) and 3 backups for testing rotation mechanics
        with patch.object(luna_server, "LOG_FILE", test_log_file), \
             patch.object(luna_server, "LOG_MAX_BYTES", 120), \
             patch.object(luna_server, "LOG_BACKUP_COUNT", 3):

            logger = logging.getLogger("luna")
            for h in list(logger.handlers):
                logger.removeHandler(h)

            log = luna_server.setup_logging()

            # Write enough lines to force multiple rotations
            for i in range(25):
                log.info(f"Rotation payload message step {i:03d} padding_extra_characters_to_exceed_size")

            created_files = os.listdir(self.test_dir)
            # Should have rotating.log and up to 3 backup files (rotating.log.1, .2, .3)
            self.assertIn("rotating.log", created_files)
            backups = [f for f in created_files if f.startswith("rotating.log.")]
            self.assertGreater(len(backups), 0)
            self.assertLessEqual(len(backups), 3)

    def test_10_console_output_functional(self):
        """10. Console StreamHandler outputs formatted log messages."""
        test_log_file = os.path.join(self.test_dir, "console_test.log")
        with patch.object(luna_server, "LOG_FILE", test_log_file):
            logger = logging.getLogger("luna")
            for h in list(logger.handlers):
                logger.removeHandler(h)

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                log = luna_server.setup_logging()
                log.info("CONSOLE_STREAM_TEST")

            self.assertIn("[INFO]", captured.getvalue())
            self.assertIn("CONSOLE_STREAM_TEST", captured.getvalue())

    def test_11_file_handler_failure_retains_console_fallback(self):
        """11. File handler initialization failure retains console fallback without crashing."""
        logger = logging.getLogger("luna")
        for h in list(logger.handlers):
            logger.removeHandler(h)

        with patch("luna_server.RotatingFileHandler", side_effect=PermissionError("Mock Permission Denied")):
            log = luna_server.setup_logging()
            self.assertIsNotNone(log)
            has_console = any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in log.handlers)
            self.assertTrue(has_console)

    def test_12_and_14_startup_and_shutdown_logged(self):
        """12, 14: safe_start_server logs startup and normal shutdown events."""
        test_log_file = os.path.join(self.test_dir, "startup_shutdown.log")
        with patch.object(luna_server, "LOG_FILE", test_log_file):
            logger = logging.getLogger("luna")
            for h in list(logger.handlers):
                logger.removeHandler(h)

            with patch("aiohttp.web.run_app", return_value=None):
                luna_server.safe_start_server(MagicMock(), host="127.0.0.1", port=7860)

            with open(test_log_file, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("LUNA sunucusu başlatılıyor: http://127.0.0.1:7860", content)
            self.assertIn("LUNA sunucusu normal şekilde durduruldu.", content)

    def test_13_port_conflict_logged(self):
        """13. Port conflict is logged as ERROR before sys.exit(1)."""
        test_log_file = os.path.join(self.test_dir, "conflict.log")
        with patch.object(luna_server, "LOG_FILE", test_log_file):
            logger = logging.getLogger("luna")
            for h in list(logger.handlers):
                logger.removeHandler(h)

            err = OSError(errno.EADDRINUSE, "Address already in use")
            with patch("aiohttp.web.run_app", side_effect=err):
                with self.assertRaises(SystemExit):
                    luna_server.safe_start_server(MagicMock(), host="127.0.0.1", port=7860)

            with open(test_log_file, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("[ERROR]", content)
            self.assertIn("[BAŞLATMA HATASI]", content)
            self.assertIn("netstat -ano | findstr :7860", content)

    def test_15_secrets_never_exposed_in_operational_logs(self):
        """15. Secret credentials are not leaked into runtime logs."""
        test_log_file = os.path.join(self.test_dir, "secrets.log")
        with patch.object(luna_server, "LOG_FILE", test_log_file):
            logger = logging.getLogger("luna")
            for h in list(logger.handlers):
                logger.removeHandler(h)

            log = luna_server.setup_logging()

            fake_groq = "gsk_testSECRET1234567890"
            fake_tg_token = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_12345678"

            # Use mask_secrets on operational messages
            safe_msg = luna_server.mask_secrets(f"Worker report key={fake_groq} token={fake_tg_token}")
            log.info(safe_msg)

            with open(test_log_file, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertNotIn("gsk_testSECRET1234567890", content)
            self.assertNotIn("123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_12345678", content)
            self.assertIn("gsk_***REDACTED***", content)
            self.assertIn("***TELEGRAM_TOKEN_REDACTED***", content)

if __name__ == "__main__":
    unittest.main(verbosity=2)
