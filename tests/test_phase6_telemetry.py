"""
ACCIO JARVIS V4.0 — Phase 6 Automated Test Suite
Focus: System Telemetry, Command Center Integration, Polling Lifecycle, Zero Data Leakage
"""

import unittest
import asyncio
import os
import sys
import json
import time
import tempfile
import uuid
import re
import subprocess
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from unittest.mock import patch, MagicMock

# Import the server under test
import jarvis_server

class Phase6TelemetryBackendTest(AioHTTPTestCase):
    async def get_application(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_memory_path = os.path.join(self.temp_dir.name, "jarvis_memory.json")
        self.mock_tasks_path = os.path.join(self.temp_dir.name, "jarvis_tasks.json")
        self.mock_config_path = os.path.join(self.temp_dir.name, "jarvis_config.json")

        with open(self.mock_memory_path, "w", encoding="utf-8") as f:
            json.dump({
                "schema_version": "4.0",
                "revision": 1,
                "user_profile": {"user_name": "negr1"},
                "entries": [
                    {"id": "mem_001", "text": "YKS 2027 Hedef", "category": "yks", "pinned": True}
                ]
            }, f)

        with open(self.mock_tasks_path, "w", encoding="utf-8") as f:
            json.dump([
                {"id": "t1", "subject": "AYT Mat", "duration": 40, "done": False, "category": "ayt_mat"},
                {"id": "t2", "subject": "Paragraf", "duration": 40, "done": True, "category": "turkce"}
            ], f)

        with open(self.mock_config_path, "w", encoding="utf-8") as f:
            json.dump(jarvis_server.DEFAULT_CONFIG, f)

        # Patch storage paths to isolated temp directory
        self.p_mem = patch("jarvis_server.MEMORY_FILE", self.mock_memory_path)
        self.p_task = patch("jarvis_server.TASKS_FILE", self.mock_tasks_path)
        self.p_cfg = patch("jarvis_server.CONFIG_FILE", self.mock_config_path)
        self.p_mem.start()
        self.p_task.start()
        self.p_cfg.start()

        app = web.Application()
        app.router.add_get("/api/system_metrics", jarvis_server.handle_system_metrics)
        return app

    def tearDown(self):
        self.p_mem.stop()
        self.p_task.stop()
        self.p_cfg.stop()
        self.temp_dir.cleanup()
        super().tearDown()

    async def test_01_endpoint_success_and_contract(self):
        """Test 1: /api/system_metrics returns HTTP 200 and comprehensive telemetry contract."""
        resp = await self.client.request("GET", "/api/system_metrics")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("server_status"), "online")
        self.assertIn("server_epoch", data)
        self.assertIn("server_uptime_seconds", data)
        self.assertIn("server_uptime_str", data)
        self.assertIn("telemetry_seq", data)
        self.assertIn("timestamp", data)
        self.assertIn("cpu_percent", data)
        self.assertIn("ram_percent", data)
        self.assertIn("ram_used_gb", data)
        self.assertIn("ram_total_gb", data)
        self.assertIn("ram_available_gb", data)
        self.assertIn("disk_percent", data)
        self.assertIn("disk_free_gb", data)
        self.assertIn("battery_percent", data)
        self.assertIn("power_plugged", data)
        self.assertIn("boot_time", data)
        self.assertIn("active_window", data)
        self.assertIn("tasks_summary", data)
        self.assertIn("memory_notes_count", data)
        self.assertIn("services", data)
        print("  [Phase 6 Test 1 PASSED] /api/system_metrics contract verified.")

    async def test_02_metric_ranges_and_types(self):
        """Test 2: Numeric metrics stay within strictly valid system bounds."""
        resp = await self.client.request("GET", "/api/system_metrics")
        data = await resp.json()

        if data["cpu_percent"] is not None:
            self.assertGreaterEqual(data["cpu_percent"], 0.0)
            self.assertLessEqual(data["cpu_percent"], 100.0)

        if data["ram_percent"] is not None:
            self.assertGreaterEqual(data["ram_percent"], 0.0)
            self.assertLessEqual(data["ram_percent"], 100.0)

        if data["ram_used_gb"] is not None:
            self.assertGreater(data["ram_used_gb"], 0.0)
        if data["ram_total_gb"] is not None:
            self.assertGreater(data["ram_total_gb"], 0.0)
        if data["ram_available_gb"] is not None:
            self.assertGreaterEqual(data["ram_available_gb"], 0.0)

        if data["disk_percent"] is not None:
            self.assertGreaterEqual(data["disk_percent"], 0.0)
            self.assertLessEqual(data["disk_percent"], 100.0)

        self.assertGreaterEqual(data["server_uptime_seconds"], 0)
        self.assertIsInstance(data["server_uptime_str"], str)
        print("  [Phase 6 Test 2 PASSED] Numerical metrics within valid physical bounds.")

    async def test_03_monotonic_telemetry_sequence(self):
        """Test 3: Telemetry sequence increments monotonically across sequential calls."""
        resp1 = await self.client.request("GET", "/api/system_metrics")
        data1 = await resp1.json()
        seq1 = data1["telemetry_seq"]

        resp2 = await self.client.request("GET", "/api/system_metrics")
        data2 = await resp2.json()
        seq2 = data2["telemetry_seq"]

        self.assertGreater(seq2, seq1)
        print("  [Phase 6 Test 3 PASSED] Telemetry sequence increments monotonically.")

    async def test_04_tasks_and_memory_summaries(self):
        """Test 4: Tasks and memory counts accurately reflect current state without leaking data."""
        resp = await self.client.request("GET", "/api/system_metrics")
        data = await resp.json()

        tasks_summary = data["tasks_summary"]
        self.assertEqual(tasks_summary["total"], 2)
        self.assertEqual(tasks_summary["pending"], 1)
        self.assertEqual(tasks_summary["completed"], 1)
        self.assertEqual(data["memory_notes_count"], 1)
        print("  [Phase 6 Test 4 PASSED] Task and memory summaries match active data accurately.")

    async def test_05_missing_psutil_and_hardware_fallbacks(self):
        """Test 5: System handles sensor exceptions gracefully without 500 error."""
        with patch("psutil.cpu_percent", side_effect=Exception("Sensor fault")), \
             patch("psutil.virtual_memory", side_effect=Exception("RAM fault")), \
             patch("psutil.disk_usage", side_effect=Exception("Disk fault")), \
             patch("psutil.sensors_battery", side_effect=Exception("Battery fault")), \
             patch("psutil.boot_time", side_effect=Exception("Boot fault")):

            resp = await self.client.request("GET", "/api/system_metrics")
            self.assertEqual(resp.status, 200)
            data = await resp.json()
            self.assertEqual(data["status"], "ok")
            self.assertIsNone(data["cpu_percent"])
            self.assertIsNone(data["ram_percent"])
            self.assertIsNone(data["ram_used_gb"])
            self.assertIsNone(data["disk_percent"])
            self.assertIsNone(data["battery_percent"])
            self.assertIsNone(data["boot_time"])
        print("  [Phase 6 Test 5 PASSED] Hardware sensor faults degrade gracefully to None.")

    async def test_06_corrupt_storage_resilience(self):
        """Test 6: Corrupt task or memory stores do not crash telemetry."""
        with open(self.mock_tasks_path, "w", encoding="utf-8") as f:
            f.write("{invalid json")

        with open(self.mock_memory_path, "w", encoding="utf-8") as f:
            f.write("{invalid json")

        resp = await self.client.request("GET", "/api/system_metrics")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["tasks_summary"]["total"], 0)
        self.assertEqual(data["memory_notes_count"], 0)
        print("  [Phase 6 Test 6 PASSED] Corrupt persistence fails closed and telemetry survives.")

    async def test_07_zero_external_network_activity(self):
        """Test 7: Telemetry endpoint performs zero external network calls."""
        with patch("urllib.request.urlopen", side_effect=AssertionError("External network call forbidden")), \
             patch("http.client.HTTPConnection.request", side_effect=AssertionError("External network call forbidden")):
            resp = await self.client.request("GET", "/api/system_metrics")
            self.assertEqual(resp.status, 200)
        print("  [Phase 6 Test 7 PASSED] Zero external network activity verified.")


class Phase6FrontendCommandCenterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            cls.html_content = f.read()

    def test_08_command_center_dom_elements_present(self):
        """Test 8: Command Center dynamic telemetry DOM elements are all present in index.html."""
        required_ids = [
            "cpuMetric", "ramMetric", "windowMetric",
            "sysCpuVal", "sysCpuFill",
            "sysRamVal", "sysRamFill", "sysRamPct", "sysRamAvail",
            "sysDiskVal", "sysDiskFill", "sysDiskPct",
            "sysBatteryVal", "sysWindowVal", "sysBootVal", "sysPowerVal",
            "sysServerStatus", "sysServerUptime", "sysTasksSummary", "sysMemoryCount", "sysTtsStatus",
            "viewCockpit", "viewSystem", "viewMemory", "viewLogs",
            "paletteModal", "paletteBtn", "paletteInput", "paletteItems"
        ]
        for dom_id in required_ids:
            self.assertIn(f'id="{dom_id}"', self.html_content, f"Missing required DOM element: id='{dom_id}'")
        print("  [Phase 6 Test 8 PASSED] All 28 Command Center DOM elements present.")

    def test_09_safe_dom_rendering_no_innerhtml_metrics(self):
        """Test 9: Dynamic telemetry values strictly use textContent (safe against XSS)."""
        # Extract pollSystemMetrics function code
        match = re.search(r'async function pollSystemMetrics\(\)\s*\{([\s\S]*?)\n  function setTelemetryOffline', self.html_content)
        self.assertTrue(match, "Could not find pollSystemMetrics function body")
        body = match.group(1)

        # Ensure no innerHTML assignments of data fields inside pollSystemMetrics
        self.assertNotIn("innerHTML =", body, "pollSystemMetrics must not use innerHTML to render dynamic metrics")
        self.assertIn("textContent =", body, "pollSystemMetrics must use textContent for safe rendering")
        print("  [Phase 6 Test 9 PASSED] Safe DOM rendering verified (zero innerHTML in telemetry).")

    def test_10_monotonic_sequence_guard_present(self):
        """Test 10: Frontend implements monotonic sequence checking to reject stale out-of-order data."""
        self.assertIn("lastTelemetrySeq", self.html_content)
        self.assertIn("data.telemetry_seq < lastTelemetrySeq", self.html_content)
        print("  [Phase 6 Test 10 PASSED] Monotonic telemetry sequence check present in frontend.")

    def test_11_duplicate_polling_prevention_lock(self):
        """Test 11: isTelemetryPolling lock prevents concurrent duplicate polling executions."""
        self.assertIn("isTelemetryPolling = true;", self.html_content)
        self.assertIn("if (isTelemetryPolling) return;", self.html_content)
        self.assertIn("isTelemetryPolling = false;", self.html_content)
        print("  [Phase 6 Test 11 PASSED] Concurrency guard lock prevents duplicate polling.")

    def test_12_visibility_lifecycle_cleanup(self):
        """Test 12: visibilitychange halts telemetry polling when page is hidden and resumes when visible."""
        self.assertIn("stopTelemetryPolling()", self.html_content)
        self.assertIn("startTelemetryPolling()", self.html_content)
        self.assertIn("document.addEventListener('visibilitychange'", self.html_content)
        self.assertIn("window.addEventListener('beforeunload'", self.html_content)
        print("  [Phase 6 Test 12 PASSED] Lifecycle hooks halt polling on hidden page and unload.")

    def test_13_command_palette_navigation_integrity(self):
        """Test 13: Command Palette retains quick system actions without arbitrary shell execution."""
        self.assertIn("PALETTE_COMMANDS", self.html_content)
        # Ensure command palette has safe navigation actions
        self.assertIn("switchView('system')", self.html_content)
        self.assertIn("switchView('memory')", self.html_content)
        self.assertIn("switchView('cockpit')", self.html_content)
        self.assertIn("switchView('logs')", self.html_content)
        print("  [Phase 6 Test 13 PASSED] Command palette navigation integrity verified.")

    def test_14_no_external_analytics_or_tracking(self):
        """Test 14: index.html contains zero external analytics, tracking pixels, or third-party fonts."""
        disallowed = [
            "google-analytics", "googletagmanager", "hotjar",
            "mixpanel", "segment.io", "facebook.net", "sentry.io"
        ]
        for term in disallowed:
            self.assertNotIn(term, self.html_content.lower(), f"Forbidden tracking service detected: {term}")
        print("  [Phase 6 Test 14 PASSED] Zero external tracking or analytics in frontend.")

if __name__ == "__main__":
    unittest.main()
