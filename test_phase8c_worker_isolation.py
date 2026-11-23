"""
ACCIO JARVIS V4.0 — Phase 8C Automated Test Suite
Focus: Automation & Worker Thread Isolation, Strict Timeout Enforcement,
       Akakçe Price Validator Worker Integration & /api/automations/test_action Endpoint.
"""

import unittest
import asyncio
import os
import sys
import json
import time
from unittest.mock import patch, MagicMock

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

import jarvis_server


class Phase8CWorkerIsolationTest(AioHTTPTestCase):

    async def get_application(self):
        app = web.Application()
        app.router.add_get("/api/automations", jarvis_server.handle_get_automations)
        app.router.add_post("/api/automations", jarvis_server.handle_create_automation)
        app.router.add_post("/api/automations/test_action", jarvis_server.handle_test_automation_action)
        return app

    def setUp(self):
        super().setUp()
        self.orig_automations_file = jarvis_server.AUTOMATIONS_FILE
        self.test_automations_file = os.path.join(jarvis_server.BASE_DIR, "test_automations_phase8c.json")
        jarvis_server.AUTOMATIONS_FILE = self.test_automations_file
        with open(self.test_automations_file, "w", encoding="utf-8") as f:
            json.dump({"schema_version": "4.0", "revision": 1, "automations": []}, f)

    def tearDown(self):
        super().tearDown()
        jarvis_server.AUTOMATIONS_FILE = self.orig_automations_file
        if os.path.exists(self.test_automations_file):
            try:
                os.remove(self.test_automations_file)
            except Exception:
                pass

    async def test_01_worker_thread_isolation_non_blocking(self):
        """Test 01: Synchronous function runs in worker thread without blocking event loop."""
        def blocking_io_func(x, y):
            time.sleep(0.05)
            return x * y

        res = await jarvis_server.run_in_worker_thread(blocking_io_func, 6, 7, timeout=2.0)
        self.assertEqual(res, 42)

    async def test_02_worker_thread_timeout_enforcement(self):
        """Test 02: run_in_worker_thread raises TimeoutError when execution exceeds timeout."""
        def hanging_func():
            time.sleep(0.3)
            return "never"

        with self.assertRaises(TimeoutError):
            await jarvis_server.run_in_worker_thread(hanging_func, timeout=0.1)

    async def test_03_execute_automation_action_timeout_handling(self):
        """Test 03: execute_automation_action returns graceful TIMEOUT error when action times out."""
        async def slow_action_func(*args, **kwargs):
            await asyncio.sleep(0.3)
            return {"status": "ok"}

        with patch("jarvis_server.dispatch_notification", side_effect=slow_action_func):
            res = await jarvis_server.execute_automation_action({
                "action_id": "dispatch_study_reminder",
                "params": {"text": "Ders Çalışma Saati", "timeout": 0.1}
            })
            self.assertEqual(res.get("status"), "error")
            self.assertEqual(res.get("error_code"), "TIMEOUT")
            self.assertIn("timed out", res.get("message", ""))

    async def test_04_run_isolated_worker_akakce_success(self):
        """Test 04: run_isolated_worker executes allowlisted akakce task cleanly."""
        res = await jarvis_server.execute_automation_action({
            "action_id": "run_isolated_worker",
            "params": {
                "task_name": "akakce_price_validator",
                "timeout": 5.0
            }
        })
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("action_id"), "run_isolated_worker")
        self.assertEqual(res.get("task_name"), "akakce_price_validator")
        self.assertIn("7500f", res.get("result", {}))

    async def test_05_disallowed_worker_task_rejected(self):
        """Test 05: run_isolated_worker rejects unapproved task names."""
        res = await jarvis_server.execute_automation_action({
            "action_id": "run_isolated_worker",
            "params": {"task_name": "unauthorized_malicious_script"}
        })
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("error_code"), "DISALLOWED_TASK")

    async def test_06_validate_automation_definition_worker_specs(self):
        """Test 06: validate_automation_definition strictly validates worker specs and timeouts."""
        # Valid worker definition
        valid_spec = {
            "name": "Gece Donanım Fiyat Taraması",
            "schedule": {"kind": "daily", "time": "03:00"},
            "action": {
                "action_id": "run_isolated_worker",
                "params": {"task_name": "hardware_price_check", "timeout": 10.0}
            }
        }
        ok, msg, cleaned = jarvis_server.validate_automation_definition(valid_spec)
        self.assertTrue(ok, msg)
        self.assertEqual(cleaned["action"]["action_id"], "run_isolated_worker")

        # Invalid worker task
        bad_task_spec = {
            "name": "Kötü İşlem",
            "schedule": {"kind": "daily", "time": "03:00"},
            "action": {
                "action_id": "run_isolated_worker",
                "params": {"task_name": "rm_rf_script"}
            }
        }
        ok2, msg2, _ = jarvis_server.validate_automation_definition(bad_task_spec)
        self.assertFalse(ok2)
        self.assertIn("invalid", msg2.lower())

        # Invalid timeout
        bad_timeout_spec = {
            "name": "Aşırı Timeout",
            "schedule": {"kind": "daily", "time": "03:00"},
            "action": {
                "action_id": "run_isolated_worker",
                "params": {"task_name": "hardware_price_check", "timeout": 999.0}
            }
        }
        ok3, msg3, _ = jarvis_server.validate_automation_definition(bad_timeout_spec)
        self.assertFalse(ok3)
        self.assertIn("between 1.0 and 30.0", msg3)

    async def test_07_allowed_action_ids_includes_worker(self):
        """Test 07: ALLOWED_ACTION_IDS contains run_isolated_worker."""
        self.assertIn("run_isolated_worker", jarvis_server.ALLOWED_ACTION_IDS)
        self.assertIn("dispatch_study_reminder", jarvis_server.ALLOWED_ACTION_IDS)

    async def test_08_test_action_endpoint_success(self):
        """Test 08: POST /api/automations/test_action triggers allowlisted action directly."""
        resp = await self.client.post("/api/automations/test_action", json={
            "action_id": "change_ambient_mood",
            "params": {"mood": "focus"}
        })
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("mood"), "focus")

    async def test_09_test_action_endpoint_invalid_payload(self):
        """Test 09: POST /api/automations/test_action rejects invalid requests."""
        resp1 = await self.client.post(
            "/api/automations/test_action",
            data="not-a-json",
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(resp1.status, 400)

        resp2 = await self.client.post("/api/automations/test_action", json={
            "action_id": "unapproved_action"
        })
        self.assertEqual(resp2.status, 400)
        data2 = await resp2.json()
        self.assertEqual(data2.get("status"), "error")

    async def test_10_scheduler_tick_resilience_on_action_timeout(self):
        """Test 10: Scheduler tick gracefully records timeout without hanging or crashing."""
        import datetime
        now = datetime.datetime(2026, 11, 8, 14, 0, 0)

        auto_item = {
            "id": "auto_timeout_test",
            "name": "Timeout Test",
            "schedule": {"kind": "daily", "time": "14:00"},
            "action": {
                "action_id": "run_isolated_worker",
                "params": {"task_name": "akakce_price_validator", "timeout": 0.1}
            },
            "enabled": True,
            "execution_count": 0
        }
        with open(self.test_automations_file, "w", encoding="utf-8") as f:
            json.dump({"schema_version": "4.0", "revision": 1, "automations": [auto_item]}, f)

        # Mock worker to take longer than timeout
        def hanging_worker(*args, **kwargs):
            time.sleep(0.3)
            return {}

        with patch("jarvis_server.run_in_worker_thread", side_effect=TimeoutError("Worker task timed out after 0.1s")):
            executed = await jarvis_server.scheduler_tick(now_dt=now)
            self.assertEqual(len(executed), 1)
            action_res = executed[0].get("action_result", {})
            self.assertEqual(action_res.get("status"), "error")
            self.assertEqual(action_res.get("error_code"), "TIMEOUT")


if __name__ == "__main__":
    unittest.main()
