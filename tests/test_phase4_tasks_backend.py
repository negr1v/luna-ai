"""
ACCIO JARVIS V4.0 — Phase 4 / Stage 4A
Isolated Backend Tests for Task Engine Persistence, Normalization, Concurrency, and REST API.

Covers at minimum:
1. Existing V1 task list loads without data loss.
2. Existing task IDs and ordering remain unchanged.
3. Unknown/custom task fields survive normalization and saving.
4. Missing optional metadata receives correct defaults.
5. Invalid new task input returns HTTP 400.
6. Invalid duration values are rejected.
7. Malformed existing task files fail closed and remain byte-identical.
8. A genuinely missing task file follows the intended default initialization behavior.
9. Atomic write failure preserves the existing task file.
10. Concurrent task mutations are serialized by TASKS_LOCK.
11. Existing GET response format remains compatible.
12. Existing bulk POST behavior remains compatible.
13. PATCH updates only the requested fields.
14. DELETE removes only the selected task.
15. Toggle changes only the selected task's completion state.
16. Unknown task IDs return 404.
17. Stale revision handling works where strict revision validation is implemented.
18. Activity logging does not break task persistence.
19. Pomodoro-related task fields and duration values remain compatible.
20. Single-task POST creates valid item and returns 201.
"""

import os
import json
import uuid
import asyncio
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web

import jarvis_server


class Phase4Stage4ABackendTest(AioHTTPTestCase):
    async def get_application(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stage4a_task_test_")
        self.test_tasks_file = os.path.join(self.temp_dir.name, "test_tasks.json")

        # Initial baseline tasks for testing
        self.initial_tasks = [
            {"id": "t1", "subject": "AYT Mat: Polinom Kapanışı", "duration": 90, "done": True, "custom_tag": "vip"},
            {"id": "t2", "subject": "Paragraf: 25 Soru Süreli (3D)", "duration": 40, "done": False},
            {"id": "t3", "subject": "TYT Mat: Çarpanlara Ayırma (Miray)", "duration": 40, "done": False}
        ]
        with open(self.test_tasks_file, "w", encoding="utf-8") as f:
            json.dump(self.initial_tasks, f, ensure_ascii=False, indent=2)

        self.p_task_file = patch("jarvis_server.TASKS_FILE", self.test_tasks_file)
        self.p_task_file.start()

        return jarvis_server.create_app()

    async def tearDownAsync(self):
        self.p_task_file.stop()
        self.temp_dir.cleanup()

    async def test_01_existing_v1_task_list_loads_without_data_loss(self):
        resp = await self.client.get("/api/tasks")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]["subject"], "AYT Mat: Polinom Kapanışı")
        self.assertEqual(data[0]["duration"], 90)
        self.assertTrue(data[0]["done"])
        print("  [Stage 4A Test 1 PASSED] Existing V1 task list loads without data loss.")

    async def test_02_existing_task_ids_and_ordering_remain_unchanged(self):
        resp = await self.client.get("/api/tasks")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        ids = [t["id"] for t in data]
        self.assertEqual(ids, ["t1", "t2", "t3"])
        print("  [Stage 4A Test 2 PASSED] Existing task IDs and ordering remain strictly unchanged.")

    async def test_03_unknown_custom_task_fields_survive_normalization_and_saving(self):
        resp = await self.client.get("/api/tasks")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data[0].get("custom_tag"), "vip")

        # Save back through bulk post
        p_resp = await self.client.post("/api/tasks", json=data)
        self.assertEqual(p_resp.status, 200)

        # Re-read from disk
        with open(self.test_tasks_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        self.assertEqual(disk_data[0].get("custom_tag"), "vip")
        print("  [Stage 4A Test 3 PASSED] Unknown custom fields survive normalization and round-trip persistence.")

    async def test_04_missing_optional_metadata_receives_correct_defaults(self):
        resp = await self.client.get("/api/tasks")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        for t in data:
            self.assertIn("category", t)
            self.assertIn("priority", t)
            self.assertIn("created_at", t)
            self.assertIn("updated_at", t)
            self.assertEqual(t["category"], "genel")
            self.assertEqual(t["priority"], "medium")
        print("  [Stage 4A Test 4 PASSED] Missing optional metadata receives expected defaults.")

    async def test_05_invalid_new_task_input_returns_http_400(self):
        # Empty subject
        r1 = await self.client.post("/api/tasks", json={"subject": "", "duration": 40})
        self.assertEqual(r1.status, 400)

        # Subject too long (> 200 chars)
        r2 = await self.client.post("/api/tasks", json={"subject": "A" * 201, "duration": 40})
        self.assertEqual(r2.status, 400)

        # Invalid category
        r3 = await self.client.post("/api/tasks", json={"subject": "Test", "duration": 40, "category": "invalid_cat"})
        self.assertEqual(r3.status, 400)

        # Invalid priority
        r4 = await self.client.post("/api/tasks", json={"subject": "Test", "duration": 40, "priority": "super_urgent"})
        self.assertEqual(r4.status, 400)

        # Invalid due_date format
        r5 = await self.client.post("/api/tasks", json={"subject": "Test", "duration": 40, "due_date": "not-a-date"})
        self.assertEqual(r5.status, 400)
        print("  [Stage 4A Test 5 PASSED] Invalid new task inputs cleanly rejected with HTTP 400.")

    async def test_06_invalid_duration_values_are_rejected(self):
        # Zero duration
        r1 = await self.client.post("/api/tasks", json={"subject": "Test", "duration": 0})
        self.assertEqual(r1.status, 400)

        # Negative duration
        r2 = await self.client.post("/api/tasks", json={"subject": "Test", "duration": -30})
        self.assertEqual(r2.status, 400)

        # Excess duration (> 360)
        r3 = await self.client.post("/api/tasks", json={"subject": "Test", "duration": 361})
        self.assertEqual(r3.status, 400)

        # Non-integer duration
        r4 = await self.client.post("/api/tasks", json={"subject": "Test", "duration": "abc"})
        self.assertEqual(r4.status, 400)
        print("  [Stage 4A Test 6 PASSED] Invalid duration values rejected.")

    async def test_07_malformed_existing_task_files_fail_closed_and_remain_byte_identical(self):
        corrupt_bytes = b"CORRUPTED_JSON_DATA{{{"
        with open(self.test_tasks_file, "wb") as f:
            f.write(corrupt_bytes)

        resp = await self.client.get("/api/tasks")
        self.assertEqual(resp.status, 503)
        data = await resp.json()
        self.assertEqual(data.get("error"), "CORRUPT_TASK_FILE")

        # Mutating endpoints must also fail closed
        r_post = await self.client.post("/api/tasks", json={"subject": "New Task", "duration": 40})
        self.assertEqual(r_post.status, 503)

        # Verify disk file is untouched
        with open(self.test_tasks_file, "rb") as f:
            self.assertEqual(f.read(), corrupt_bytes)
        print("  [Stage 4A Test 7 PASSED] Malformed task storage fails closed and remains byte-identical.")

    async def test_08_genuinely_missing_task_file_follows_default_initialization(self):
        if os.path.exists(self.test_tasks_file):
            os.remove(self.test_tasks_file)

        resp = await self.client.get("/api/tasks")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(len(data), 6) # 6 default study tasks
        self.assertEqual(data[0]["id"], "t1")
        self.assertEqual(data[0]["subject"], "AYT Mat: Polinom Kapanışı")
        print("  [Stage 4A Test 8 PASSED] Missing file returns default YKS task initialization.")

    async def test_09_atomic_write_failure_preserves_existing_task_file(self):
        with open(self.test_tasks_file, "rb") as f:
            orig_bytes = f.read()

        with patch("os.replace", side_effect=OSError("Simulated Atomic Replace Failure")):
            resp = await self.client.post("/api/tasks", json={"subject": "Should Fail", "duration": 40})
            self.assertEqual(resp.status, 500)

        with open(self.test_tasks_file, "rb") as f:
            cur_bytes = f.read()
        self.assertEqual(orig_bytes, cur_bytes)
        print("  [Stage 4A Test 9 PASSED] Atomic write failure preserves existing task file.")

    async def test_10_concurrent_task_mutations_are_serialized_by_tasks_lock(self):
        # Fire 5 concurrent single task adds
        async def add_task(idx):
            return await self.client.post("/api/tasks", json={
                "subject": f"Eşzamanlı Görev {idx}",
                "duration": 30
            })

        results = await asyncio.gather(*(add_task(i) for i in range(5)))
        for r in results:
            self.assertEqual(r.status, 201)

        resp = await self.client.get("/api/tasks")
        data = await resp.json()
        self.assertEqual(len(data), 3 + 5) # 3 initial + 5 added
        print("  [Stage 4A Test 10 PASSED] Concurrent mutations serialized cleanly by TASKS_LOCK.")

    async def test_11_existing_get_response_format_remains_compatible(self):
        resp = await self.client.get("/api/tasks")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertIsInstance(data, list)
        for t in data:
            self.assertIn("id", t)
            self.assertIn("subject", t)
            self.assertIn("duration", t)
            self.assertIn("done", t)
        print("  [Stage 4A Test 11 PASSED] Existing GET response format is 100% backwards compatible.")

    async def test_12_existing_bulk_post_behavior_remains_compatible(self):
        bulk_payload = [
            {"id": "tb1", "subject": "Toplu Görev 1", "duration": 50, "done": True},
            {"id": "tb2", "subject": "Toplu Görev 2", "duration": 25, "done": False}
        ]
        resp = await self.client.post("/api/tasks", json=bulk_payload)
        self.assertEqual(resp.status, 200)
        res_data = await resp.json()
        self.assertEqual(res_data.get("status"), "ok")
        self.assertEqual(res_data.get("count"), 2)

        # Verify disk
        r_get = await self.client.get("/api/tasks")
        data = await r_get.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["subject"], "Toplu Görev 1")
        print("  [Stage 4A Test 12 PASSED] Existing bulk POST behavior remains compatible.")

    async def test_13_patch_updates_only_requested_fields(self):
        # Update subject and done for t2
        resp = await self.client.patch("/api/tasks/t2", json={
            "subject": "Paragraf: Güncellenmiş Deneme",
            "done": True
        })
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data.get("status"), "ok")
        updated_t = data.get("task")
        self.assertEqual(updated_t["subject"], "Paragraf: Güncellenmiş Deneme")
        self.assertTrue(updated_t["done"])
        self.assertEqual(updated_t["duration"], 40) # Unchanged

        # Verify t1 and t3 were untouched
        r_all = await self.client.get("/api/tasks")
        all_data = await r_all.json()
        t1 = next(t for t in all_data if t["id"] == "t1")
        self.assertEqual(t1["subject"], "AYT Mat: Polinom Kapanışı")
        print("  [Stage 4A Test 13 PASSED] PATCH updates only requested fields granularly.")

    async def test_14_delete_removes_only_selected_task(self):
        resp = await self.client.delete("/api/tasks/t2")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data.get("deleted_id"), "t2")

        r_all = await self.client.get("/api/tasks")
        all_data = await r_all.json()
        ids = [t["id"] for t in all_data]
        self.assertEqual(ids, ["t1", "t3"])
        print("  [Stage 4A Test 14 PASSED] DELETE removes only the selected task.")

    async def test_15_toggle_changes_only_selected_task_completion_state(self):
        # t2 is initially done: False
        resp = await self.client.post("/api/tasks/t2/toggle")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["task"]["done"])

        # Toggle back
        resp2 = await self.client.post("/api/tasks/t2/toggle")
        self.assertEqual(resp2.status, 200)
        data2 = await resp2.json()
        self.assertFalse(data2["task"]["done"])
        print("  [Stage 4A Test 15 PASSED] Toggle endpoint toggles task completion state.")

    async def test_16_unknown_task_ids_return_404(self):
        r_patch = await self.client.patch("/api/tasks/t_unknown", json={"done": True})
        self.assertEqual(r_patch.status, 404)

        r_del = await self.client.delete("/api/tasks/t_unknown")
        self.assertEqual(r_del.status, 404)

        r_tog = await self.client.post("/api/tasks/t_unknown/toggle")
        self.assertEqual(r_tog.status, 404)
        print("  [Stage 4A Test 16 PASSED] Unknown task IDs return HTTP 404.")

    async def test_17_stale_revision_handling_works_when_header_sent(self):
        # Get revision token
        r_get = await self.client.get("/api/tasks")
        token = r_get.headers.get("X-Task-Revision-Token")
        self.assertIsNotNone(token)

        # First patch succeeds
        r_p1 = await self.client.patch("/api/tasks/t1", headers={"X-Task-Revision-Token": token}, json={"duration": 80})
        self.assertEqual(r_p1.status, 200)
        new_token = r_p1.headers.get("X-Task-Revision-Token")
        self.assertNotEqual(token, new_token)

        # Second patch with old token gets 409
        r_p2 = await self.client.patch("/api/tasks/t1", headers={"X-Task-Revision-Token": token}, json={"duration": 70})
        self.assertEqual(r_p2.status, 409)
        err_json = await r_p2.json()
        self.assertEqual(err_json.get("error"), "STALE_TASK_REVISION")
        print("  [Stage 4A Test 17 PASSED] Stale task revision token cleanly rejected with HTTP 409.")

    async def test_18_activity_logging_does_not_break_task_persistence(self):
        with patch("jarvis_server.log_activity", side_effect=Exception("Logging Subsystem Failure")):
            # Task creation should still succeed or fail gracefully without crashing server
            # Since log_activity is called after persistence, we test that tasks are persisted
            resp = await self.client.post("/api/tasks", json={"subject": "Log Test Task", "duration": 40})
            # If log_activity raises, it might bubble up or be handled. Let's verify disk was written
            with open(self.test_tasks_file, "r", encoding="utf-8") as f:
                disk = json.load(f)
            subjects = [t["subject"] for t in disk]
            self.assertIn("Log Test Task", subjects)
        print("  [Stage 4A Test 18 PASSED] Activity logging does not corrupt task persistence.")

    async def test_19_pomodoro_related_task_fields_and_duration_remain_compatible(self):
        resp = await self.client.get("/api/tasks")
        data = await resp.json()
        completed_minutes = sum(int(t["duration"]) for t in data if t.get("done"))
        total_minutes = sum(int(t["duration"]) for t in data)
        self.assertEqual(completed_minutes, 90) # t1 is 90 min and done
        self.assertEqual(total_minutes, 170) # 90 + 40 + 40
        print("  [Stage 4A Test 19 PASSED] Pomodoro durations and progress calculations match exactly.")

    async def test_20_single_task_post_creates_valid_item_and_returns_201(self):
        resp = await self.client.post("/api/tasks", json={
            "subject": "Fizik: Elektrik ve Manyetizma (Apotemi)",
            "duration": 50,
            "category": "fizik",
            "priority": "high",
            "due_date": "2026-11-08"
        })
        self.assertEqual(resp.status, 201)
        data = await resp.json()
        self.assertEqual(data.get("status"), "ok")
        created = data.get("task")
        self.assertTrue(created["id"].startswith("t_"))
        self.assertEqual(created["subject"], "Fizik: Elektrik ve Manyetizma (Apotemi)")
        self.assertEqual(created["duration"], 50)
        self.assertEqual(created["category"], "fizik")
        self.assertEqual(created["priority"], "high")
        self.assertEqual(created["due_date"], "2026-11-08")
        print("  [Stage 4A Test 20 PASSED] Single-task creation returns HTTP 201 with populated V2 metadata.")


if __name__ == "__main__":
    unittest.main()
