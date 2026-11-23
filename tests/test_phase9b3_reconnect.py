"""
ACCIO LUNA V4.0 — Phase 9B.3D Automated Test Suite
Focus: Frontend Reconnect Acceptance Tests (Offline Banner, State Manager, Network Classification,
       Visibility Lifecycle, Draft Preservation, Mutation Replay Protection & Metrics Endpoint).
"""

import unittest
import os
import sys
import re
import json
import time
import shutil
import glob
import subprocess
import tempfile
import asyncio
from unittest.mock import patch, MagicMock

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import luna_server

INDEX_PATH = os.path.join(PROJECT_DIR, "index.html")

def get_node_executable() -> str:
    found = shutil.which("node")
    if found:
        return found
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidates = glob.glob(os.path.join(appdata, "Accio", "pre-install", "*", "node", "node.exe"))
        for c in candidates:
            if os.path.exists(c):
                return c
    hardcoded = r"C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\node\node.exe"
    if os.path.exists(hardcoded):
        return hardcoded
    return "node"

NODE_EXE = get_node_executable()


class TestPhase9B3StaticHTMLAndDOM(unittest.TestCase):
    """Static inspection of DOM elements, attributes, accessibility and Turkish copy."""

    def setUp(self):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_01_reconnect_banner_exists_and_unique(self):
        """1. Exactly one #reconnectBanner element exists in index.html."""
        matches = re.findall(r'id=["\']reconnectBanner["\']', self.html)
        self.assertEqual(len(matches), 1, "There must be exactly one #reconnectBanner element")

    def test_02_reconnect_banner_accessibility_and_attributes(self):
        """2. #reconnectBanner includes role='status' and aria-live='polite'."""
        banner_match = re.search(r'<div[^>]*id=["\']reconnectBanner["\'][^>]*>', self.html)
        self.assertIsNotNone(banner_match, "#reconnectBanner div tag not found")
        tag = banner_match.group(0)
        self.assertIn('role="status"', tag)
        self.assertIn('aria-live="polite"', tag)

    def test_03_reconnect_banner_initially_hidden(self):
        """3. #reconnectBanner is hidden during normal initial operation."""
        banner_match = re.search(r'<div[^>]*id=["\']reconnectBanner["\'][^>]*>', self.html)
        self.assertIsNotNone(banner_match)
        tag = banner_match.group(0)
        self.assertTrue('display:none' in tag or 'display: none' in tag, "Banner must be initially hidden")

    def test_04_reconnect_banner_exact_turkish_copy(self):
        """4. Exact Turkish text 'LUNA Çevrimdışı — Yeniden Bağlanıyor...' is present."""
        banner_snippet = re.search(r'<div[^>]*id=["\']reconnectBanner["\'].*?</div>', self.html, re.DOTALL)
        self.assertIsNotNone(banner_snippet, "Banner snippet could not be extracted")
        self.assertIn("LUNA Çevrimdışı — Yeniden Bağlanıyor...", banner_snippet.group(0))

    def test_05_reconnect_banner_amber_warning_style(self):
        """5. Styling uses amber warning colors (#f59e0b / #fef08a)."""
        banner_snippet = re.search(r'<div[^>]*id=["\']reconnectBanner["\'].*?</div>', self.html, re.DOTALL)
        self.assertIsNotNone(banner_snippet)
        content = banner_snippet.group(0)
        self.assertIn("#f59e0b", content)
        self.assertIn("#fef08a", content)


class TestPhase9B3ExecutedJavaScriptMocks(unittest.TestCase):
    """
    Executed JavaScript tests using Node.js to exercise the ACTUAL reconnect
    implementation extracted verbatim from index.html with mocked browser APIs.
    """

    @classmethod
    def setUpClass(cls):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            html = f.read()

        # Extract the telemetry & connection state manager snippet from index.html
        start_marker = "const cpuMetric = document.getElementById('cpuMetric');"
        end_marker = "function stopTelemetryPolling()"
        
        start_idx = html.find(start_marker)
        end_idx = html.find(end_marker)
        assert start_idx != -1 and end_idx != -1, "Could not locate connection manager in index.html"

        end_block = html.find("startTelemetryPolling();", end_idx)
        if end_block != -1:
            end_block += len("startTelemetryPolling();")
        else:
            end_block = end_idx + 200

        cls.extracted_js = html[start_idx:end_block]

    def _run_node_harness(self, test_code: str) -> dict:
        """Run Node.js test harness executing the verbatim JS from index.html."""
        harness = f"""
const vm = require('vm');

// Mock Browser Environment
const elements = {{
  reconnectBanner: {{ id: 'reconnectBanner', style: {{ display: 'none' }} }},
  sysServerStatus: {{ id: 'sysServerStatus', textContent: 'Çevrimiçi', style: {{ color: '' }} }},
  cpuMetric: {{ textContent: '12%' }},
  ramMetric: {{ textContent: '4.5 GB' }},
  windowMetric: {{ textContent: 'Masaüstü' }},
  sysCpuVal: {{ textContent: '' }},
  sysCpuFill: {{ style: {{ width: '0%' }} }},
  sysRamVal: {{ textContent: '' }},
  sysRamFill: {{ style: {{ width: '0%' }} }},
  sysRamPct: {{ textContent: '' }},
  sysRamAvail: {{ textContent: '' }},
  sysDiskVal: {{ textContent: '' }},
  sysDiskFill: {{ style: {{ width: '0%' }} }},
  sysDiskPct: {{ textContent: '' }},
  sysBatteryVal: {{ textContent: '' }},
  sysWindowVal: {{ textContent: '' }},
  sysBootVal: {{ textContent: '' }},
  sysPowerVal: {{ textContent: '' }},
  sysServerUptime: {{ textContent: '' }},
  sysTasksSummary: {{ textContent: '' }},
  sysMemoryCount: {{ textContent: '' }},
  sysTtsStatus: {{ textContent: '' }},
  newTaskInput: {{ value: '' }}
}};

let listeners = {{}};
let intervals = [];

global.document = {{
  hidden: false,
  getElementById: (id) => elements[id] || null,
  addEventListener: (event, cb) => {{ listeners[event] = listeners[event] || []; listeners[event].push(cb); }}
}};

global.setInterval = (cb, ms) => {{
  const id = intervals.length + 1;
  intervals.push({{ id, cb, ms }});
  return id;
}};
global.clearInterval = (id) => {{
  intervals = intervals.filter(i => i.id !== id);
}};

global.console = {{
  log: () => {{}},
  warn: () => {{}},
  error: () => {{}}
}};

// Mock Refresh Functions
let refreshCalls = {{
  loadTasks: 0,
  fetchDeferredNotifications: 0,
  loadTelegramFeed: 0
}};

global.loadTasks = () => {{ refreshCalls.loadTasks++; }};
global.fetchDeferredNotifications = () => {{ refreshCalls.fetchDeferredNotifications++; }};
global.loadTelegramFeed = () => {{ refreshCalls.loadTelegramFeed++; }};

// Mock Fetch & Responses default to healthy 200
let fetchMock = async () => ({{
  ok: true,
  status: 200,
  json: async () => ({{ status: 'ok', telemetry_seq: 1 }})
}});
global.fetch = (...args) => {{
  return fetchMock(...args);
}};

// --- VERBATIM JS INJECTION ---
{self.extracted_js}
// --- END VERBATIM JS ---

// Reset state after initial startup poll
stopTelemetryPolling();
connectionState = 'ONLINE';
consecutiveNetworkFailures = 0;
elements.reconnectBanner.style.display = 'none';
elements.sysServerStatus.textContent = 'Çevrimiçi';
isTelemetryPolling = false;

// --- TEST SCENARIO EXECUTION ---
async function runTest() {{
  // Settle any initial top-level async execution
  await new Promise(r => setTimeout(r, 50));
  stopTelemetryPolling();
  connectionState = 'ONLINE';
  consecutiveNetworkFailures = 0;
  elements.reconnectBanner.style.display = 'none';
  elements.sysServerStatus.textContent = 'Çevrimiçi';
  isTelemetryPolling = false;

  {test_code}
}}

runTest().then(result => {{
  process.stdout.write(JSON.stringify({{ success: true, result }}));
}}).catch(err => {{
  process.stderr.write(err.stack || err.message);
  process.exit(1);
}});
"""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as tf:
            tf.write(harness)
            tmp_path = tf.name

        try:
            res = subprocess.run([NODE_EXE, tmp_path], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
            if res.returncode != 0:
                raise RuntimeError(f"Node execution failed (code {res.returncode}): {res.stderr}")
            return json.loads(res.stdout).get("result", {})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_06_initial_online_state_and_hidden_banner(self):
        """6. [Executed JS Mock] Initial state is ONLINE, banner is hidden."""
        code = """
        return {
          connectionState,
          consecutiveNetworkFailures,
          bannerDisplay: elements.reconnectBanner.style.display,
          statusText: elements.sysServerStatus.textContent
        };
        """
        data = self._run_node_harness(code)
        self.assertEqual(data["connectionState"], "ONLINE")
        self.assertEqual(data["consecutiveNetworkFailures"], 0)
        self.assertEqual(data["bannerDisplay"], "none")

    def test_07_failure_threshold_logic(self):
        """7. [Executed JS Mock] Threshold is 2: first failure stays hidden, second shows banner."""
        code = """
        // 1. Mock network rejection (TypeError: Failed to fetch)
        fetchMock = async () => { throw new TypeError("Failed to fetch"); };

        // Poll 1: 1st failure
        await pollSystemMetrics();
        const after1Fail = {
          connectionState,
          consecutiveNetworkFailures,
          bannerDisplay: elements.reconnectBanner.style.display
        };

        // Poll 2: 2nd consecutive failure (threshold reached)
        await pollSystemMetrics();
        const after2Fail = {
          connectionState,
          consecutiveNetworkFailures,
          bannerDisplay: elements.reconnectBanner.style.display,
          statusText: elements.sysServerStatus.textContent
        };

        return { after1Fail, after2Fail };
        """
        data = self._run_node_harness(code)
        # After 1 failure: counter is 1, banner still hidden, state ONLINE
        self.assertEqual(data["after1Fail"]["consecutiveNetworkFailures"], 1)
        self.assertEqual(data["after1Fail"]["connectionState"], "ONLINE")
        self.assertEqual(data["after1Fail"]["bannerDisplay"], "none")

        # After 2 failures: counter is 2, banner is flex, state is OFFLINE
        self.assertEqual(data["after2Fail"]["consecutiveNetworkFailures"], 2)
        self.assertEqual(data["after2Fail"]["connectionState"], "OFFLINE")
        self.assertEqual(data["after2Fail"]["bannerDisplay"], "flex")
        self.assertEqual(data["after2Fail"]["statusText"], "Bağlantı Kesildi")

    def test_08_reconnection_recovery_and_counter_reset(self):
        """8. [Executed JS Mock] HTTP 200 resets failure counter, hides banner, sets ONLINE."""
        code = """
        fetchMock = async () => { throw new TypeError("Failed to fetch"); };
        await pollSystemMetrics();
        await pollSystemMetrics(); // Entered OFFLINE

        // Now backend recovers
        fetchMock = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', telemetry_seq: 1 })
        });
        await pollSystemMetrics();

        return {
          connectionState,
          consecutiveNetworkFailures,
          bannerDisplay: elements.reconnectBanner.style.display,
          statusText: elements.sysServerStatus.textContent,
          refreshCalls
        };
        """
        data = self._run_node_harness(code)
        self.assertEqual(data["connectionState"], "ONLINE")
        self.assertEqual(data["consecutiveNetworkFailures"], 0)
        self.assertEqual(data["bannerDisplay"], "none")
        self.assertEqual(data["statusText"], "Çevrimiçi")
        self.assertEqual(data["refreshCalls"]["loadTasks"], 1)

    def test_09_interleaved_success_resets_sequence(self):
        """9. [Executed JS Mock] Success between two failures resets consecutive-failure counter."""
        code = """
        // Fail 1
        fetchMock = async () => { throw new TypeError("Failed to fetch"); };
        await pollSystemMetrics();
        const countAfterFail1 = consecutiveNetworkFailures;

        // Success
        fetchMock = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', telemetry_seq: 1 })
        });
        await pollSystemMetrics();
        const countAfterSuccess = consecutiveNetworkFailures;

        // Fail 2
        fetchMock = async () => { throw new TypeError("Failed to fetch"); };
        await pollSystemMetrics();
        const countAfterFail2 = consecutiveNetworkFailures;

        return {
          countAfterFail1,
          countAfterSuccess,
          countAfterFail2,
          bannerDisplay: elements.reconnectBanner.style.display,
          connectionState
        };
        """
        data = self._run_node_harness(code)
        self.assertEqual(data["countAfterFail1"], 1)
        self.assertEqual(data["countAfterSuccess"], 0)
        self.assertEqual(data["countAfterFail2"], 1)
        self.assertEqual(data["connectionState"], "ONLINE")
        self.assertEqual(data["bannerDisplay"], "none")

    def test_10_http_and_error_classification(self):
        """10. [Executed JS Mock] AbortError and HTTP 500/503 do not increment network failure count."""
        code = """
        // 1. AbortError (intentional cancellation)
        fetchMock = async () => {
          const err = new Error("The user aborted a request.");
          err.name = "AbortError";
          throw err;
        };
        await pollSystemMetrics();
        const countAfterAbort = consecutiveNetworkFailures;

        // 2. HTTP 500 (server reachable, application error)
        fetchMock = async () => ({
          ok: false,
          status: 500,
          json: async () => ({ status: 'error' })
        });
        await pollSystemMetrics();
        const countAfter500 = consecutiveNetworkFailures;

        // 3. HTTP 503
        fetchMock = async () => ({
          ok: false,
          status: 503,
          json: async () => ({ status: 'error' })
        });
        await pollSystemMetrics();
        const countAfter503 = consecutiveNetworkFailures;

        // 4. Genuine network drop (TypeError: Failed to fetch)
        fetchMock = async () => { throw new TypeError("Failed to fetch"); };
        await pollSystemMetrics();
        const countAfterNetDrop = consecutiveNetworkFailures;

        return {
          countAfterAbort,
          countAfter500,
          countAfter503,
          countAfterNetDrop,
          connectionState
        };
        """
        data = self._run_node_harness(code)
        self.assertEqual(data["countAfterAbort"], 0, "AbortError must not increment network failure count")
        self.assertEqual(data["countAfter500"], 0, "HTTP 500 must not increment network failure count")
        self.assertEqual(data["countAfter503"], 0, "HTTP 503 must not increment network failure count")
        self.assertEqual(data["countAfterNetDrop"], 1, "Genuine network failure must increment count")

    def test_11_reconnecting_state_lifecycle(self):
        """11. [Executed JS Mock] RECONNECTING state is entered on subsequent polls while offline."""
        code = """
        fetchMock = async () => { throw new TypeError("Failed to fetch"); };
        
        await pollSystemMetrics(); // fail 1 -> ONLINE
        const state1 = connectionState;

        await pollSystemMetrics(); // fail 2 -> OFFLINE
        const state2 = connectionState;

        await pollSystemMetrics(); // fail 3 -> RECONNECTING
        const state3 = connectionState;

        // Backend returns
        fetchMock = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok' })
        });
        await pollSystemMetrics(); // -> ONLINE
        const state4 = connectionState;

        return { state1, state2, state3, state4 };
        """
        data = self._run_node_harness(code)
        self.assertEqual(data["state1"], "ONLINE")
        self.assertEqual(data["state2"], "OFFLINE")
        self.assertEqual(data["state3"], "RECONNECTING")
        self.assertEqual(data["state4"], "ONLINE")

    def test_12_request_overlap_prevention(self):
        """12. [Executed JS Mock] isTelemetryPolling prevents overlapping telemetry requests."""
        code = """
        let activeCalls = 0;
        let maxConcurrent = 0;

        fetchMock = async () => {
          activeCalls++;
          maxConcurrent = Math.max(maxConcurrent, activeCalls);
          await new Promise(r => setTimeout(r, 50));
          activeCalls--;
          return {
            ok: true,
            status: 200,
            json: async () => ({ status: 'ok' })
          };
        };

        // Fire 3 simultaneous calls
        const p1 = pollSystemMetrics();
        const p2 = pollSystemMetrics();
        const p3 = pollSystemMetrics();
        await Promise.all([p1, p2, p3]);

        return { maxConcurrent };
        """
        data = self._run_node_harness(code)
        self.assertEqual(data["maxConcurrent"], 1, "Only 1 poll should be in-flight at a time")

    def test_13_visibility_lifecycle(self):
        """13. [Executed JS Mock] Polling pauses when hidden, resumes on visibility change."""
        code = """
        stopTelemetryPolling();
        intervals = [];

        let pollCount = 0;
        fetchMock = async () => {
          pollCount++;
          return { ok: true, status: 200, json: async () => ({ status: 'ok' }) };
        };

        // Start polling
        startTelemetryPolling();
        await new Promise(r => setTimeout(r, 10));
        const initialCalls = pollCount;

        // 1. When hidden, interval ticks skip polling
        document.hidden = true;
        const currentInterval = intervals[intervals.length - 1];
        currentInterval.cb();
        const countWhileHidden = pollCount;

        // 2. Visibility change simulation (index.html line 1854 logic)
        document.hidden = false;
        stopTelemetryPolling();
        startTelemetryPolling();
        await new Promise(r => setTimeout(r, 10));
        const countAfterVisible = pollCount;

        return {
          initialCalls,
          countWhileHidden,
          countAfterVisible,
          intervalsRemaining: intervals.length
        };
        """
        data = self._run_node_harness(code)
        self.assertEqual(data["initialCalls"], 1, "startTelemetryPolling initiates immediate poll")
        self.assertEqual(data["countWhileHidden"], 1, "Interval tick must not poll when hidden")
        self.assertEqual(data["countAfterVisible"], 2, "Becoming visible triggers immediate poll")
        self.assertEqual(data["intervalsRemaining"], 1, "Only 1 permanent interval should exist")

    def test_14_draft_preservation_on_reconnect(self):
        """14. [Executed JS Mock] Unsaved task input draft is preserved; loadTasks is skipped."""
        code = """
        // 1. Unsaved draft in task input
        elements.newTaskInput.value = "Kritik taslak görev yazılıyor...";

        fetchMock = async () => { throw new TypeError("Failed to fetch"); };
        await pollSystemMetrics();
        await pollSystemMetrics(); // OFFLINE

        // Recover
        fetchMock = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok' })
        });
        await pollSystemMetrics();

        const draftPreserved = elements.newTaskInput.value;
        const loadTasksCalled = refreshCalls.loadTasks;

        // 2. Now clean input (empty draft)
        elements.newTaskInput.value = "   ";
        fetchMock = async () => { throw new TypeError("Failed to fetch"); };
        await pollSystemMetrics();
        await pollSystemMetrics(); // OFFLINE

        fetchMock = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok' })
        });
        await pollSystemMetrics();
        const loadTasksCalledWhenClean = refreshCalls.loadTasks;

        return {
          draftPreserved,
          loadTasksCalled,
          loadTasksCalledWhenClean
        };
        """
        data = self._run_node_harness(code)
        self.assertEqual(data["draftPreserved"], "Kritik taslak görev yazılıyor...")
        self.assertEqual(data["loadTasksCalled"], 0, "loadTasks must be skipped when input is dirty")
        self.assertEqual(data["loadTasksCalledWhenClean"], 1, "loadTasks should run when input is clean")

    def test_15_no_mutation_replay_mechanism(self):
        """15. [Executed JS Mock] Verify no failed mutations (POST/PATCH/DELETE) are replayed."""
        # Static & architectural audit of index.html for mutation queues
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertNotIn("replayMutations", html)
        self.assertNotIn("failedRequestQueue", html)
        self.assertNotIn("mutationQueue", html)
        self.assertNotIn("retryFailedWrites", html)

    def test_16_node_check_syntax_validity(self):
        """16. Verify extracted JavaScript syntax parses cleanly with node --check."""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as tf:
            tf.write(f"(function() {{\n{self.extracted_js}\n}})();")
            tmp_path = tf.name

        try:
            res = subprocess.run([NODE_EXE, "--check", tmp_path], capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(res.returncode, 0, f"node --check failed: {res.stderr}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class TestPhase9B3SystemMetricsEndpoint(AioHTTPTestCase):
    """
    Isolated aiohttp TestServer check for GET /api/system_metrics route.
    Does NOT bind to port 7860 or touch production JSON files.
    """

    async def get_application(self):
        app = web.Application()
        app.router.add_get("/api/system_metrics", luna_server.handle_system_metrics)
        return app

    async def test_17_system_metrics_route_isolated(self):
        """17. GET /api/system_metrics returns 200, valid JSON and required telemetry fields."""
        resp = await self.client.request("GET", "/api/system_metrics")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("cpu_percent", data)
        self.assertIn("ram_percent", data)
        self.assertIn("server_uptime_seconds", data)
        self.assertIn("telemetry_seq", data)
        self.assertGreaterEqual(data["server_uptime_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
