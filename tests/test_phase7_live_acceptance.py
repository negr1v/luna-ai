"""
ACCIO LUNA V4.0 — Phase 7 Live Integration Acceptance Suite
Focus: Live Server (Port 7868), Headless Chrome E2E DOM Render,
       Live Automation CRUD, Gaming Mode Telemetry, Queue Drain & 409,
       Persistent Restart Recovery, Zero Production Data Mutation.
"""

import os
import sys
import json
import time
import asyncio
import tempfile
import threading
import urllib.request
import urllib.error
import subprocess
import unittest

import luna_server

PORT = 7868
BASE_URL = f"http://127.0.0.1:{PORT}"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class Phase7LiveAcceptanceRunner:
    def __init__(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="luna_phase7_live_")
        self.test_tasks_file = os.path.join(self.temp_dir.name, "isolated_tasks.json")
        self.test_mem_file = os.path.join(self.temp_dir.name, "isolated_memory.json")
        self.test_cfg_file = os.path.join(self.temp_dir.name, "isolated_cfg.json")
        self.test_tg_file = os.path.join(self.temp_dir.name, "isolated_tg.json")
        self.test_auto_file = os.path.join(self.temp_dir.name, "isolated_automations.json")
        self.test_notif_file = os.path.join(self.temp_dir.name, "isolated_notifications.json")

        with open(self.test_tasks_file, "w", encoding="utf-8") as f:
            json.dump([], f)
        with open(self.test_mem_file, "w", encoding="utf-8") as f:
            json.dump({"schema_version": "4.0", "revision": 1, "entries": []}, f)
        with open(self.test_cfg_file, "w", encoding="utf-8") as f:
            json.dump({"groq_api_key": "mock_groq_key"}, f)
        with open(self.test_tg_file, "w", encoding="utf-8") as f:
            json.dump([], f)
        with open(self.test_auto_file, "w", encoding="utf-8") as f:
            json.dump({"schema_version": "4.0", "revision": 1, "automations": []}, f)
        with open(self.test_notif_file, "w", encoding="utf-8") as f:
            json.dump({"schema_version": "4.0", "overflow_count": 0, "expired_count": 0, "notifications": []}, f)

        self.server_thread = None
        self.loop = None
        self.runner = None
        self.site = None

    def start_server(self):
        luna_server.TASKS_FILE = self.test_tasks_file
        luna_server.MEMORY_FILE = self.test_mem_file
        luna_server.CONFIG_FILE = self.test_cfg_file
        luna_server.TELEGRAM_FILE = self.test_tg_file
        luna_server.AUTOMATIONS_FILE = self.test_auto_file
        luna_server.NOTIFICATIONS_FILE = self.test_notif_file
        luna_server.OVERFLOW_COUNT = 0
        luna_server.EXPIRED_COUNT = 0
        luna_server.DEFERRED_NOTIFICATIONS = []

        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            app = luna_server.create_app()
            self.runner = luna_server.web.AppRunner(app)
            self.loop.run_until_complete(self.runner.setup())
            self.site = luna_server.web.TCPSite(self.runner, "127.0.0.1", PORT)
            self.loop.run_until_complete(self.site.start())
            self.loop.run_forever()

        self.server_thread = threading.Thread(target=run_loop, daemon=True)
        self.server_thread.start()

        for _ in range(40):
            try:
                req = urllib.request.Request(f"{BASE_URL}/")
                with urllib.request.urlopen(req, timeout=1) as resp:
                    if resp.status == 200:
                        return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("Live test server failed to bind to port 7868")

    def stop_server(self):
        if self.loop and self.runner:
            async def shutdown():
                try:
                    if self.site:
                        await self.site.stop()
                    await self.runner.cleanup()
                except Exception:
                    pass
                self.loop.stop()

            asyncio.run_coroutine_threadsafe(shutdown(), self.loop)
            time.sleep(0.2)

    def cleanup(self):
        self.stop_server()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def request(self, method, path, data=None):
        url = f"{BASE_URL}{path}"
        req = urllib.request.Request(url, method=method)
        req.add_header("Content-Type", "application/json")
        body_bytes = json.dumps(data).encode("utf-8") if data is not None else None
        try:
            with urllib.request.urlopen(req, data=body_bytes, timeout=5) as resp:
                resp_body = resp.read().decode("utf-8")
                return resp.status, json.loads(resp_body) if resp_body else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            try:
                return e.code, json.loads(err_body)
            except Exception:
                return e.code, {"error": err_body}


class Phase7LiveAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = Phase7LiveAcceptanceRunner()
        cls.runner.start_server()

    @classmethod
    def tearDownClass(cls):
        cls.runner.cleanup()

    def test_01_live_headless_chrome_renders_command_center_automations(self):
        """Test 1: Real Headless Chrome connects to live server, rendering automation views without errors."""
        if not os.path.exists(CHROME_PATH):
            self.skipTest("Google Chrome executable not found at specified path.")

        cmd = [
            CHROME_PATH,
            "--headless=new",
            "--disable-gpu",
            "--dump-dom",
            BASE_URL
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        self.assertEqual(res.returncode, 0, f"Chrome failed: {res.stderr}")
        dom_output = res.stdout

        self.assertIn('id="navTabAutomations"', dom_output)
        self.assertIn('id="viewAutomations"', dom_output)
        self.assertIn('id="gamingStatusBadge"', dom_output)
        self.assertIn('id="notifQueueCountBadge"', dom_output)
        self.assertIn('id="createAutoForm"', dom_output)
        self.assertIn('id="autoListContainer"', dom_output)
        print("  [Live Test 1 PASSED] Headless Google Chrome loaded live page and rendered Phase 7E DOM.")

    def test_02_live_automations_crud_lifecycle(self):
        """Test 2: Live server executes complete automation CRUD (Create Daily/Weekly/Once, List, Toggle, Delete)."""
        # 1. Create daily automation
        daily_payload = {
            "name": "Live Günlük Pomodoro",
            "schedule": {"kind": "daily", "time": "09:15"},
            "action": {"action_id": "dispatch_study_reminder", "params": {"text": "Sabah YKS Matematik Bloğu"}},
            "enabled": True
        }
        s1, b1 = self.runner.request("POST", "/api/automations", daily_payload)
        self.assertEqual(s1, 201)
        self.assertEqual(b1["status"], "ok")
        id_daily = b1["automation"]["id"]

        # 2. Create weekly automation
        weekly_payload = {
            "name": "Live Hafta Sonu Denemesi",
            "schedule": {"kind": "weekly", "time": "14:00", "days": ["sat", "sun"]},
            "action": {"action_id": "dispatch_proactive_notification", "params": {"text": "Teşhis Denemesi Vakti"}},
            "enabled": True
        }
        s2, b2 = self.runner.request("POST", "/api/automations", weekly_payload)
        self.assertEqual(s2, 201)
        id_weekly = b2["automation"]["id"]

        # 3. Create once automation
        once_payload = {
            "name": "Live Tek Seferlik Hedef",
            "schedule": {"kind": "once", "at": "2026-11-26T12:00:00"},
            "action": {"action_id": "change_ambient_mood", "params": {"mood": "gaming"}},
            "enabled": True
        }
        s3, b3 = self.runner.request("POST", "/api/automations", once_payload)
        self.assertEqual(s3, 201)
        id_once = b3["automation"]["id"]

        # 4. List automations
        s_list, b_list = self.runner.request("GET", "/api/automations")
        self.assertEqual(s_list, 200)
        self.assertEqual(b_list["count"], 3)
        self.assertTrue(b_list["scheduler_running"])

        # 5. Toggle automation
        s_tog, b_tog = self.runner.request("POST", f"/api/automations/{id_daily}/toggle")
        self.assertEqual(s_tog, 200)
        self.assertFalse(b_tog["automation"]["enabled"])

        # 6. Delete automation
        s_del, b_del = self.runner.request("DELETE", f"/api/automations/{id_once}")
        self.assertEqual(s_del, 200)
        self.assertEqual(b_del["deleted_id"], id_once)

        # Verify count is now 2
        s_list2, b_list2 = self.runner.request("GET", "/api/automations")
        self.assertEqual(b_list2["count"], 2)
        print("  [Live Test 2 PASSED] Live HTTP server executed full automation CRUD lifecycle.")

    def test_03_gaming_mode_telemetry_and_deferred_queue_drain(self):
        """Test 3: Live telemetry reflects gaming mode status and notification drain contract."""
        s_sys, b_sys = self.runner.request("GET", "/api/system_metrics")
        self.assertEqual(s_sys, 200)
        self.assertIn("gaming_mode", b_sys)
        self.assertIn("notifications", b_sys)

        s_notif, b_notif = self.runner.request("GET", "/api/notifications/deferred")
        self.assertEqual(s_notif, 200)
        self.assertEqual(b_notif["count"], 0)
        self.assertEqual(b_notif["overflow_count"], 0)

        # Dispatch study alarm
        s_disp, b_disp = self.runner.request("POST", "/api/notifications/dispatch", {
            "text": "Canlı Ders Bildirimi",
            "category": "study_alarm"
        })
        self.assertEqual(s_disp, 200)

        # If gaming mode active, drain must return 409; if inactive, drain returns 200
        s_drain, b_drain = self.runner.request("POST", "/api/notifications/deferred/drain", {"max_count": 3})
        if b_sys["gaming_mode"]["active"]:
            self.assertEqual(s_drain, 409)
            self.assertEqual(b_drain["status"], "blocked")
        else:
            self.assertEqual(s_drain, 200)
            self.assertEqual(b_drain["status"], "ok")
        print("  [Live Test 3 PASSED] Gaming mode telemetry and drain contract verified on live server.")

    def test_04_persistence_and_simulated_server_restart(self):
        """Test 4: Stop live server and restart on same isolated files to verify persistent recovery."""
        # Check current state before restart
        _, b_pre = self.runner.request("GET", "/api/automations")
        pre_count = b_pre["count"]

        # Stop server
        self.runner.stop_server()
        time.sleep(0.3)

        # Restart server on same isolated storage
        self.runner.start_server()

        # Query state after restart
        s_post, b_post = self.runner.request("GET", "/api/automations")
        self.assertEqual(s_post, 200)
        self.assertEqual(b_post["count"], pre_count)
        self.assertTrue(b_post["scheduler_running"])
        print("  [Live Test 4 PASSED] Automations and scheduler state successfully recovered across live restart.")


if __name__ == "__main__":
    unittest.main()
