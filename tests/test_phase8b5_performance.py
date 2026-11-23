"""
ACCIO JARVIS V4.0 — Phase 8B.5 Automated Test Suite
Focus: Performance, I/O Caching, CPU & Resource Management, Background Polling Optimization.
"""

import unittest
import asyncio
import os
import sys
import json
import tempfile
import shutil
import time

import jarvis_server


class Phase8B5PerformanceTest(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="phase8b5_test_")
        self.test_auto_file = os.path.join(self.test_dir, "jarvis_automations.json")
        self.test_config_file = os.path.join(self.test_dir, "jarvis_config.json")

        self.initial_auto_data = {
            "schema_version": "4.0",
            "revision": 1,
            "automations": [
                {
                    "id": "auto_test_1",
                    "title": "Hourly Focus Reminder",
                    "enabled": True,
                    "schedule": {"kind": "daily", "time": "14:00"},
                    "action": {"type": "voice_notification", "message": "Test"}
                }
            ]
        }

        with open(self.test_auto_file, "w", encoding="utf-8") as f:
            json.dump(self.initial_auto_data, f)

        self.orig_auto_file = jarvis_server.AUTOMATIONS_FILE
        self.orig_config_file = jarvis_server.CONFIG_FILE
        jarvis_server.AUTOMATIONS_FILE = self.test_auto_file
        jarvis_server.CONFIG_FILE = self.test_config_file

        jarvis_server._AUTOMATIONS_CACHE = None
        jarvis_server._AUTOMATIONS_MTIME = 0.0

    def tearDown(self):
        jarvis_server.AUTOMATIONS_FILE = self.orig_auto_file
        jarvis_server.CONFIG_FILE = self.orig_config_file
        jarvis_server._AUTOMATIONS_CACHE = None
        jarvis_server._AUTOMATIONS_MTIME = 0.0

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_automations_mtime_caching_avoids_redundant_disk_reads(self):
        """Test 01: load_automations_data reuses cached memory object when mtime unchanged."""
        d1 = jarvis_server.load_automations_data()
        self.assertEqual(len(d1["automations"]), 1)
        self.assertIsNotNone(jarvis_server._AUTOMATIONS_CACHE)
        cached_mtime = jarvis_server._AUTOMATIONS_MTIME

        # Second load should reuse cache directly
        d2 = jarvis_server.load_automations_data()
        self.assertEqual(d2, d1)
        self.assertEqual(jarvis_server._AUTOMATIONS_MTIME, cached_mtime)

    def test_02_automations_cache_invalidates_on_mtime_change(self):
        """Test 02: External modification to file updates mtime and invalidates cache."""
        jarvis_server.load_automations_data()

        # Update disk file with second automation and new mtime
        new_data = {
            "schema_version": "4.0",
            "revision": 2,
            "automations": [
                {"id": "auto_1", "title": "A1"},
                {"id": "auto_2", "title": "A2"}
            ]
        }
        time.sleep(0.05)  # Ensure filesystem timestamp increments
        with open(self.test_auto_file, "w", encoding="utf-8") as f:
            json.dump(new_data, f)

        reloaded = jarvis_server.load_automations_data()
        self.assertEqual(len(reloaded["automations"]), 2)
        self.assertEqual(reloaded["revision"], 2)

    def test_03_save_automations_updates_cache_synchronously(self):
        """Test 03: save_automations_data writes to disk and refreshes memory cache."""
        updated = {
            "schema_version": "4.0",
            "revision": 10,
            "automations": [{"id": "auto_fresh", "title": "Fresh"}]
        }
        jarvis_server.save_automations_data(updated)
        self.assertIsNotNone(jarvis_server._AUTOMATIONS_CACHE)
        self.assertEqual(jarvis_server._AUTOMATIONS_CACHE["automations"][0]["id"], "auto_fresh")

        # Immediate load returns fresh data without cache miss
        loaded = jarvis_server.load_automations_data()
        self.assertEqual(loaded["automations"][0]["id"], "auto_fresh")

    def test_04_frontend_document_hidden_guards_present_in_index_html(self):
        """Test 04: index.html contains document.hidden guards for telemetry and telegram polling."""
        index_path = os.path.join(jarvis_server.BASE_DIR, "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()

        # Verify telemetry polling guards
        self.assertIn("if (!document.hidden)", html)
        self.assertIn("loadTelegramFeed();", html)

    def test_05_async_lock_acquisition_latency(self):
        """Test 05: Core synchronization locks acquire in sub-millisecond range under sequential load."""
        async def measure_locks():
            t0 = time.perf_counter()
            for _ in range(100):
                async with jarvis_server.AUTOMATIONS_LOCK:
                    pass
                async with jarvis_server.TELEGRAM_ASYNC_LOCK:
                    pass
                async with jarvis_server.TELEGRAM_POLL_LOCK:
                    pass
            duration = time.perf_counter() - t0
            return duration

        elapsed = asyncio.run(measure_locks())
        # 100 iterations of 3 locks (300 acquisitions) should complete well under 0.1s
        self.assertLess(elapsed, 0.1, f"Lock acquisition took too long: {elapsed:.4f}s")


if __name__ == "__main__":
    unittest.main()
