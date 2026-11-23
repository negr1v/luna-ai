"""
ACCIO LUNA V4.0 — Phase 7D Automated Test Suite
Focus: Persistent Automation Scheduler, Safe Action Registry, Atomic Persistence,
       Europe/Istanbul Scheduling, Persistent Deferred Notifications, Lifecycle Cleanup.
"""

import unittest
import asyncio
import os
import sys
import json
import time
import datetime
import tempfile
import shutil
import uuid
from unittest.mock import patch, MagicMock

import luna_server


class Phase7DAutomationEngineTest(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="phase7d_test_")
        self.test_automations_file = os.path.join(self.test_dir, "test_automations.json")
        self.test_notifications_file = os.path.join(self.test_dir, "test_notifications.json")

        # Configure isolated paths in luna_server
        luna_server.AUTOMATIONS_FILE = self.test_automations_file
        luna_server.NOTIFICATIONS_FILE = self.test_notifications_file
        luna_server.OVERFLOW_COUNT = 0
        luna_server.EXPIRED_COUNT = 0

        # Reset in-memory deferred notifications
        async with luna_server.NOTIFICATIONS_LOCK:
            luna_server.DEFERRED_NOTIFICATIONS.clear()

        # Seed clean automations file
        luna_server.save_automations_data({
            "schema_version": "4.0",
            "revision": 1,
            "automations": []
        })

    async def asyncTearDown(self):
        if hasattr(self, "test_dir") and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_01_one_time_schedule_execution_and_duplicate_prevention(self):
        """Test 1: One-time schedule executes when time arrives, disables itself, and never runs again."""
        sched_time = datetime.datetime(2026, 11, 8, 14, 0, 0, tzinfo=luna_server.ISTANBUL_TZ)
        auto_spec = {
            "name": "Tek Seferlik YKS Deneme Hatırlatıcısı",
            "schedule": {
                "kind": "once",
                "at": sched_time.isoformat()
            },
            "action": {
                "action_id": "dispatch_study_reminder",
                "params": {"text": "İlk Seviye Teşhis Denemesi başlıyor!"}
            },
            "enabled": True
        }

        valid, err, cleaned = luna_server.validate_automation_definition(auto_spec)
        self.assertTrue(valid, f"Validation error: {err}")

        data = luna_server.load_automations_data()
        data["automations"].append(cleaned)
        luna_server.save_automations_data(data)

        # Before scheduled time -> does not execute
        before_time = datetime.datetime(2026, 11, 8, 13, 59, 50, tzinfo=luna_server.ISTANBUL_TZ)
        res_before = await luna_server.evaluate_and_run_automations(current_time=before_time)
        self.assertEqual(len(res_before), 0)

        # At scheduled time -> executes exactly once
        with patch("luna_server.dispatch_notification", return_value={"status": "delivered"}) as mock_disp:
            res_at = await luna_server.evaluate_and_run_automations(current_time=sched_time)
            self.assertEqual(len(res_at), 1)
            self.assertEqual(res_at[0]["automation_id"], cleaned["id"])
            mock_disp.assert_called_once()

        # Check state: enabled should be False, execution_count = 1
        data_after = luna_server.load_automations_data()
        target = [a for a in data_after["automations"] if a["id"] == cleaned["id"]][0]
        self.assertFalse(target["enabled"])
        self.assertEqual(target["execution_count"], 1)

        # After scheduled time -> does NOT execute again
        after_time = datetime.datetime(2026, 11, 8, 14, 1, 0, tzinfo=luna_server.ISTANBUL_TZ)
        with patch("luna_server.dispatch_notification") as mock_disp2:
            res_after = await luna_server.evaluate_and_run_automations(current_time=after_time)
            self.assertEqual(len(res_after), 0)
            mock_disp2.assert_not_called()
        print("  [Phase 7D Test 1 PASSED] One-time schedule executes once and safely disables.")

    async def test_02_daily_schedule_execution_and_duplicate_prevention(self):
        """Test 2: Daily schedule executes once per day at designated time, preventing repeat runs in same minute."""
        auto_spec = {
            "name": "Günlük Sabah Pomodoro Başlatıcı",
            "schedule": {
                "kind": "daily",
                "time": "09:00"
            },
            "action": {
                "action_id": "dispatch_study_reminder",
                "params": {"text": "Sabah çalışma bloğu: 40dk AYT Matematik"}
            },
            "enabled": True
        }

        valid, err, cleaned = luna_server.validate_automation_definition(auto_spec)
        self.assertTrue(valid)
        data = luna_server.load_automations_data()
        data["automations"].append(cleaned)
        luna_server.save_automations_data(data)

        # Day 1: 09:00:10 -> triggers
        day1_0900 = datetime.datetime(2026, 11, 8, 9, 0, 10, tzinfo=luna_server.ISTANBUL_TZ)
        with patch("luna_server.dispatch_notification", return_value={"status": "delivered"}) as mock_d:
            res1 = await luna_server.evaluate_and_run_automations(current_time=day1_0900)
            self.assertEqual(len(res1), 1)
            mock_d.assert_called_once()

        # Day 1: 09:00:40 (same minute, duplicate tick) -> MUST NOT trigger
        day1_0900_dup = datetime.datetime(2026, 11, 8, 9, 0, 40, tzinfo=luna_server.ISTANBUL_TZ)
        with patch("luna_server.dispatch_notification") as mock_d2:
            res_dup = await luna_server.evaluate_and_run_automations(current_time=day1_0900_dup)
            self.assertEqual(len(res_dup), 0)
            mock_d2.assert_not_called()

        # Day 2: 09:00:15 -> triggers next day
        day2_0900 = datetime.datetime(2026, 11, 9, 9, 0, 15, tzinfo=luna_server.ISTANBUL_TZ)
        with patch("luna_server.dispatch_notification", return_value={"status": "delivered"}) as mock_d3:
            res2 = await luna_server.evaluate_and_run_automations(current_time=day2_0900)
            self.assertEqual(len(res2), 1)
            mock_d3.assert_called_once()

        data_final = luna_server.load_automations_data()
        target = [a for a in data_final["automations"] if a["id"] == cleaned["id"]][0]
        self.assertEqual(target["execution_count"], 2)
        print("  [Phase 7D Test 2 PASSED] Daily schedule triggers once daily without duplicate ticks.")

    async def test_03_weekly_schedule_execution(self):
        """Test 3: Weekly schedule triggers on specified weekday and ignores non-matching weekdays."""
        auto_spec = {
            "name": "Hafta Sonu YKS Analiz Raporu",
            "schedule": {
                "kind": "weekly",
                "time": "18:00",
                "days": ["sat", "sun"]
            },
            "action": {
                "action_id": "dispatch_proactive_notification",
                "params": {"text": "Haftalık net analizi ve soru dağılımı hazırlandı."}
            },
            "enabled": True
        }

        valid, err, cleaned = luna_server.validate_automation_definition(auto_spec)
        self.assertTrue(valid)
        data = luna_server.load_automations_data()
        data["automations"].append(cleaned)
        luna_server.save_automations_data(data)

        # 2026-11-11 is Wednesday -> should NOT trigger
        wednesday = datetime.datetime(2026, 11, 11, 18, 0, 0, tzinfo=luna_server.ISTANBUL_TZ)
        res_wed = await luna_server.evaluate_and_run_automations(current_time=wednesday)
        self.assertEqual(len(res_wed), 0)

        # 2026-11-14 is Saturday -> MUST trigger
        saturday = datetime.datetime(2026, 11, 14, 18, 0, 0, tzinfo=luna_server.ISTANBUL_TZ)
        with patch("luna_server.dispatch_notification", return_value={"status": "delivered"}):
            res_sat = await luna_server.evaluate_and_run_automations(current_time=saturday)
            self.assertEqual(len(res_sat), 1)

        print("  [Phase 7D Test 3 PASSED] Weekly schedule triggers strictly on specified weekdays.")

    async def test_04_disabled_automation_is_ignored(self):
        """Test 4: Disabled automations are completely bypassed during evaluation."""
        auto_spec = {
            "name": "Pasif Görev",
            "schedule": {"kind": "daily", "time": "12:00"},
            "action": {"action_id": "dispatch_study_reminder", "params": {"text": "Test"}},
            "enabled": False
        }
        valid, _, cleaned = luna_server.validate_automation_definition(auto_spec)
        data = luna_server.load_automations_data()
        data["automations"].append(cleaned)
        luna_server.save_automations_data(data)

        match_time = datetime.datetime(2026, 11, 8, 12, 0, 0, tzinfo=luna_server.ISTANBUL_TZ)
        res = await luna_server.evaluate_and_run_automations(current_time=match_time)
        self.assertEqual(len(res), 0)
        print("  [Phase 7D Test 4 PASSED] Disabled automations safely bypassed.")

    async def test_05_invalid_action_and_injection_rejected(self):
        """Test 5: Unapproved action IDs, shell strings, and malicious parameters strictly rejected."""
        malicious_specs = [
            {"name": "Bad 1", "schedule": {"kind": "daily", "time": "12:00"}, "action": {"action_id": "shell_exec", "params": {"cmd": "calc.exe"}}},
            {"name": "Bad 2", "schedule": {"kind": "daily", "time": "12:00"}, "action": {"action_id": "eval_python", "params": {"code": "import os"}}},
            {"name": "Bad 3", "schedule": {"kind": "daily", "time": "12:00"}, "action": {"action_id": "kill_process", "params": {"pid": 1234}}},
            {"name": "Bad 4", "schedule": {"kind": "daily", "time": "12:00"}, "action": {"action_id": "open_allowlisted_view", "params": {"view": "malicious_page.html"}}},
            {"name": "Bad 5", "schedule": {"kind": "daily", "time": "12:00"}, "action": {"action_id": "change_ambient_mood", "params": {"mood": "hacked_mood"}}},
            {"name": "Bad 6", "schedule": {"kind": "daily", "time": "12:00"}, "action": {"action_id": ""}}
        ]

        for spec in malicious_specs:
            valid, err, _ = luna_server.validate_automation_definition(spec)
            self.assertFalse(valid, f"Expected validation failure for {spec['action']}: got valid")

        # Direct execution of unapproved action rejected
        res_exec = await luna_server.execute_automation_action({"action_id": "arbitrary_cmd", "params": {}})
        self.assertEqual(res_exec["status"], "error")
        print("  [Phase 7D Test 5 PASSED] Unapproved action IDs and injection payloads strictly rejected.")

    async def test_06_invalid_schedule_specifications_rejected(self):
        """Test 6: Malformed times, invalid schedule kinds, and unknown days rejected."""
        bad_schedules = [
            {"name": "Bad Sched 1", "schedule": {"kind": "hourly", "time": "12:00"}, "action": {"action_id": "change_ambient_mood", "params": {"mood": "focus"}}},
            {"name": "Bad Sched 2", "schedule": {"kind": "daily", "time": "25:00"}, "action": {"action_id": "change_ambient_mood", "params": {"mood": "focus"}}},
            {"name": "Bad Sched 3", "schedule": {"kind": "daily", "time": "12:60"}, "action": {"action_id": "change_ambient_mood", "params": {"mood": "focus"}}},
            {"name": "Bad Sched 4", "schedule": {"kind": "daily", "time": "invalid"}, "action": {"action_id": "change_ambient_mood", "params": {"mood": "focus"}}},
            {"name": "Bad Sched 5", "schedule": {"kind": "weekly", "time": "12:00", "days": ["someday"]}, "action": {"action_id": "change_ambient_mood", "params": {"mood": "focus"}}},
            {"name": "Bad Sched 6", "schedule": {"kind": "weekly", "time": "12:00", "days": []}, "action": {"action_id": "change_ambient_mood", "params": {"mood": "focus"}}},
            {"name": "Bad Sched 7", "schedule": {"kind": "once", "at": ""}, "action": {"action_id": "change_ambient_mood", "params": {"mood": "focus"}}}
        ]

        for spec in bad_schedules:
            valid, err, _ = luna_server.validate_automation_definition(spec)
            self.assertFalse(valid, f"Expected failure for {spec['schedule']}: got valid")
        print("  [Phase 7D Test 6 PASSED] Invalid schedule parameters safely rejected.")

    async def test_07_persistence_and_restart_recovery(self):
        """Test 7: Automation configurations survive simulated server restart and reload accurately."""
        auto_spec = {
            "name": "Kalıcı Çalışma Alarmı",
            "schedule": {"kind": "daily", "time": "15:20"},
            "action": {"action_id": "dispatch_study_reminder", "params": {"text": "Yürüyüş ve Mola Zamanı"}},
            "enabled": True
        }
        valid, _, cleaned = luna_server.validate_automation_definition(auto_spec)
        data = luna_server.load_automations_data()
        data["automations"].append(cleaned)
        luna_server.save_automations_data(data)

        # Simulate restart by reading disk from fresh load call
        fresh_data = luna_server.load_automations_data()
        self.assertEqual(len(fresh_data["automations"]), 1)
        loaded = fresh_data["automations"][0]
        self.assertEqual(loaded["name"], "Kalıcı Çalışma Alarmı")
        self.assertEqual(loaded["schedule"]["time"], "15:20")
        self.assertEqual(loaded["action"]["action_id"], "dispatch_study_reminder")
        print("  [Phase 7D Test 7 PASSED] Automations survive server restart with exact schema.")

    async def test_08_atomic_write_preserves_data_on_failure(self):
        """Test 8: Failure during atomic replace cleans temp file and leaves existing file unharmed."""
        orig_data = {"schema_version": "4.0", "revision": 1, "automations": [{"id": "a1", "name": "Initial"}]}
        luna_server.save_automations_data(orig_data)

        with patch("os.replace", side_effect=OSError("Simulated disk full")):
            with self.assertRaises(OSError):
                luna_server.save_automations_data({"schema_version": "4.0", "revision": 2, "automations": []})

        # Original file must remain intact
        recovered = luna_server.load_automations_data()
        self.assertEqual(len(recovered["automations"]), 1)
        self.assertEqual(recovered["automations"][0]["id"], "a1")
        print("  [Phase 7D Test 8 PASSED] Atomic write failure preserves original automations storage.")

    async def test_09_corrupt_storage_fails_closed_without_overwrite(self):
        """Test 9: Corrupted automations file raises error and is never silently reset or wiped."""
        with open(self.test_automations_file, "w", encoding="utf-8") as f:
            f.write("{invalid_json: true, broken")

        with self.assertRaises(ValueError):
            luna_server.load_automations_data()

        # Content must still be the broken content (not overwritten with empty array)
        with open(self.test_automations_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("broken", content)
        print("  [Phase 7D Test 9 PASSED] Corrupt storage triggers fail-closed error without silent overwrite.")

    async def test_10_deferred_notification_persistence_and_recovery(self):
        """Test 10: Deferred notifications persist across restarts in dedicated storage file."""
        # Enqueue notification during simulated gaming mode
        sched_time = datetime.datetime(2026, 11, 8, 16, 30, 0)
        res = await luna_server.dispatch_notification(
            text="Fizik Dalgalar Tekrarı Başlayacak",
            category="study_alarm",
            current_time=sched_time,
            active_window_title="Apex Legends"
        )
        self.assertEqual(res["status"], "deferred")

        # Verify persisted to disk file
        self.assertTrue(os.path.exists(self.test_notifications_file))
        with open(self.test_notifications_file, "r", encoding="utf-8") as f:
            file_data = json.load(f)
        self.assertEqual(len(file_data["notifications"]), 1)
        self.assertEqual(file_data["notifications"][0]["text"], "Fizik Dalgalar Tekrarı Başlayacak")

        # Clear memory and reload from disk
        luna_server.DEFERRED_NOTIFICATIONS.clear()
        luna_server.load_notifications_from_disk()

        deferred = luna_server.get_deferred_notifications()
        self.assertEqual(len(deferred), 1)
        self.assertEqual(deferred[0]["text"], "Fizik Dalgalar Tekrarı Başlayacak")
        print("  [Phase 7D Test 10 PASSED] Deferred notifications persist and recover cleanly.")

    async def test_11_queue_overflow_explicit_rejection_without_drop(self):
        """Test 11: Queue at 20 capacity returns explicit queue_full and never silently drops oldest."""
        for i in range(20):
            res = await luna_server.enqueue_deferred_notification(f"Alarm {i}", category="study_alarm", discard_oldest=False)
            self.assertTrue(res)

        # 21st enqueue must be explicitly rejected with queue_full
        overflow_res = await luna_server.enqueue_deferred_notification("Alarm 20 (Overflow)", category="study_alarm", discard_oldest=False)
        self.assertEqual(overflow_res, "queue_full")

        # Verify oldest (Alarm 0) was NOT dropped
        current = luna_server.get_deferred_notifications()
        self.assertEqual(len(current), 20)
        self.assertEqual(current[0]["text"], "Alarm 0")
        self.assertEqual(current[-1]["text"], "Alarm 19")

        # Verify overflow_count was tracked
        self.assertEqual(luna_server.OVERFLOW_COUNT, 1)

        # Verify dispatch_notification reflects queue_full status
        sched_time = datetime.datetime(2026, 11, 8, 16, 30, 0)
        disp_res = await luna_server.dispatch_notification(
            text="Alarm 21",
            category="study_alarm",
            current_time=sched_time,
            active_window_title="Apex Legends"
        )
        self.assertEqual(disp_res["status"], "queue_full")
        self.assertEqual(disp_res["action"], "rejected")
        print("  [Phase 7D Test 11 PASSED] Queue overflow returns explicit queue_full and preserves oldest.")

    async def test_12_notification_expiration_tracking(self):
        """Test 12: Notifications older than 2 hours (7200s) are purged and tracked in expired_count."""
        now_ts = time.time()
        fresh_entry = {"id": "n_fresh", "text": "Fresh Alarm", "category": "study_alarm", "created_at": now_ts - 100, "metadata": {}}
        expired_entry = {"id": "n_old", "text": "Old Alarm", "category": "study_alarm", "created_at": now_ts - 7300, "metadata": {}}

        async with luna_server.NOTIFICATIONS_LOCK:
            luna_server.DEFERRED_NOTIFICATIONS = [fresh_entry, expired_entry]
            luna_server.save_notifications_to_disk()

        valid_notifs = luna_server.get_deferred_notifications(filter_expired=True)
        self.assertEqual(len(valid_notifs), 1)
        self.assertEqual(valid_notifs[0]["id"], "n_fresh")
        self.assertEqual(luna_server.EXPIRED_COUNT, 1)
        print("  [Phase 7D Test 12 PASSED] Expired notifications accurately purged and counted.")

    async def test_13_active_conversation_protection(self):
        """Test 13: Conversational user responses are never queued or deferred even during gaming mode."""
        sched_time = datetime.datetime(2026, 11, 8, 16, 30, 0)
        with patch("luna_server.generate_tts", return_value="CONV_AUDIO") as mock_tts:
            res = await luna_server.dispatch_notification(
                text="Evet, Apex maçın devam ediyor ama sorduğun fizik formülü v = w * r.",
                category="conversational",
                current_time=sched_time,
                active_window_title="Apex Legends"
            )
            self.assertEqual(res["status"], "delivered")
            self.assertEqual(res["action"], "play_tts")
            self.assertEqual(res["audio_base64"], "CONV_AUDIO")
            mock_tts.assert_called_once()

        # Queue remains clean
        self.assertEqual(len(luna_server.get_deferred_notifications()), 0)
        print("  [Phase 7D Test 13 PASSED] Conversational messages never delayed or queued.")

    async def test_14_action_allowlist_full_execution(self):
        """Test 14: All 4 registered application actions execute with correct semantics."""
        # 1. Study reminder
        with patch("luna_server.dispatch_notification", return_value={"status": "delivered"}) as m1:
            res1 = await luna_server.execute_automation_action({
                "action_id": "dispatch_study_reminder",
                "params": {"text": "AYT Kimya Çalışması"}
            })
            self.assertEqual(res1["status"], "ok")
            m1.assert_called_once()

        # 2. Proactive notification
        with patch("luna_server.dispatch_notification", return_value={"status": "delivered"}) as m2:
            res2 = await luna_server.execute_automation_action({
                "action_id": "dispatch_proactive_notification",
                "params": {"text": "Uyku saati yaklaşıyor."}
            })
            self.assertEqual(res2["status"], "ok")
            m2.assert_called_once()

        # 3. Change ambient mood
        res3 = await luna_server.execute_automation_action({
            "action_id": "change_ambient_mood",
            "params": {"mood": "focus"}
        })
        self.assertEqual(res3["status"], "ok")
        self.assertEqual(luna_server.CURRENT_AMBIENT_MOOD, "focus")

        # 4. Open allowlisted view
        with patch("luna_server.execute_desktop_tool", return_value={"status": "ok"}) as m4:
            res4 = await luna_server.execute_automation_action({
                "action_id": "open_allowlisted_view",
                "params": {"view": "kokpit"}
            })
            self.assertEqual(res4["status"], "ok")
            m4.assert_called_with("open_app", {"target": "kokpit"})

        print("  [Phase 7D Test 14 PASSED] All 4 allowlisted actions confirmed operational.")

    async def test_15_scheduler_worker_lifecycle_cleanup(self):
        """Test 15: Scheduler worker starts cleanly and shuts down on cleanup context exit without leaks."""
        app = luna_server.create_app()
        runner = luna_server.web.AppRunner(app)
        await runner.setup()

        # Worker should be running
        self.assertIsNotNone(luna_server.SCHEDULER_WORKER_TASK)
        self.assertFalse(luna_server.SCHEDULER_WORKER_TASK.done())

        # Cleanup
        await runner.cleanup()
        self.assertIsNone(luna_server.SCHEDULER_WORKER_TASK)
        print("  [Phase 7D Test 15 PASSED] Scheduler worker starts and terminates cleanly.")

    async def test_16_api_crud_lifecycle(self):
        """Test 16: Complete HTTP API CRUD lifecycle (Create, List, Toggle, Patch, Delete)."""
        app = luna_server.create_app()
        runner = luna_server.web.AppRunner(app)
        await runner.setup()
        site = luna_server.web.TCPSite(runner, "127.0.0.1", 7869)
        await site.start()

        import aiohttp
        async with aiohttp.ClientSession() as session:
            # 1. Create automation (POST /api/automations)
            payload = {
                "name": "API Test Otomasyonu",
                "schedule": {"kind": "daily", "time": "21:00"},
                "action": {"action_id": "change_ambient_mood", "params": {"mood": "night"}},
                "enabled": True
            }
            async with session.post("http://127.0.0.1:7869/api/automations", json=payload) as resp:
                self.assertEqual(resp.status, 201)
                body = await resp.json()
                self.assertEqual(body["status"], "ok")
                created_id = body["automation"]["id"]

            # 2. List automations (GET /api/automations)
            async with session.get("http://127.0.0.1:7869/api/automations") as resp:
                self.assertEqual(resp.status, 200)
                body = await resp.json()
                self.assertEqual(body["count"], 1)
                self.assertEqual(body["automations"][0]["id"], created_id)

            # 3. Toggle automation (POST /api/automations/{id}/toggle)
            async with session.post(f"http://127.0.0.1:7869/api/automations/{created_id}/toggle") as resp:
                self.assertEqual(resp.status, 200)
                body = await resp.json()
                self.assertFalse(body["automation"]["enabled"])

            # 4. Patch automation (PATCH /api/automations/{id})
            async with session.patch(f"http://127.0.0.1:7869/api/automations/{created_id}", json={"name": "Guncel Isim", "enabled": True}) as resp:
                self.assertEqual(resp.status, 200)
                body = await resp.json()
                self.assertEqual(body["automation"]["name"], "Guncel Isim")
                self.assertTrue(body["automation"]["enabled"])

            # 5. Delete automation (DELETE /api/automations/{id})
            async with session.delete(f"http://127.0.0.1:7869/api/automations/{created_id}") as resp:
                self.assertEqual(resp.status, 200)
                body = await resp.json()
                self.assertEqual(body["deleted_id"], created_id)

            # Verify list is empty
            async with session.get("http://127.0.0.1:7869/api/automations") as resp:
                body = await resp.json()
                self.assertEqual(body["count"], 0)

        await runner.cleanup()
        print("  [Phase 7D Test 16 PASSED] Full HTTP API CRUD endpoints validated.")


if __name__ == "__main__":
    unittest.main()
