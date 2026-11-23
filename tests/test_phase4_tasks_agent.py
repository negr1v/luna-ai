"""
ACCIO JARVIS V4.0 — Phase 4 / Stage 4B
Comprehensive Isolated Tests for Agent Engine Task Management Tool Integration,
Mixed-Concurrency Synchronization, and Idempotency Correction.

Covers:
1. Explicit add request creates one task.
2. Ordinary task-related conversation does not create a task.
3. Explicit task creation with omitted duration uses 40 minutes.
4. Invalid duration is rejected.
5. Invalid category is rejected.
6. Main JARVIS is authorized.
7. Luna is authorized and normalized to canonical profile.
8. Unauthorized agents cannot execute the tool.
9. List returns the correct task data and revision token.
10. Complete marks only the intended task done.
11. Ambiguous completion does not mutate any task.
12. Missing task ID or unknown task returns a controlled error.
13. Normal chat remains functional when a tool fails.
14. SSE chat remains functional when a tool fails.
15. Existing task IDs and custom fields are preserved.

Mixed-Concurrency & Idempotency:
16. HTTP task creation racing with agent task creation (prevents lost updates).
17. HTTP task completion racing with agent task completion.
18. HTTP bulk save racing with agent task creation.
19. Multiple simultaneous agent task creations.
20. Same tool-call ID executed concurrently: exactly one task is created.
21. Same tool-call ID retried after success: original task is returned.
22. Different tool-call IDs with identical subjects: separate intentional tasks are allowed.
23. Persistence failure does not commit the idempotency key.
24. Agent mutations increment the task revision counter.
25. Previous revision token becomes stale after an agent mutation.
26. Luna alias cannot gain permissions beyond the approved canonical profile.
27. Unauthorized agent attempts remain strictly denied.
"""

import os
import json
import uuid
import asyncio
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web

import jarvis_server


class Phase4Stage4BAgentTest(AioHTTPTestCase):
    async def get_application(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stage4b_task_agent_")
        self.test_tasks_file = os.path.join(self.temp_dir.name, "test_tasks.json")
        self.test_cfg_file = os.path.join(self.temp_dir.name, "test_cfg.json")

        self.initial_tasks = [
            {"id": "t1", "subject": "AYT Mat: Polinom Kapanışı", "duration": 90, "done": True, "custom_prop": "keep_me"},
            {"id": "t2", "subject": "Paragraf: 25 Soru Süreli (3D)", "duration": 40, "done": False},
            {"id": "t3", "subject": "Paragraf: 20 Soru Deneme", "duration": 30, "done": False}
        ]
        with open(self.test_tasks_file, "w", encoding="utf-8") as f:
            json.dump(self.initial_tasks, f, ensure_ascii=False, indent=2)

        with open(self.test_cfg_file, "w", encoding="utf-8") as f:
            json.dump({"groq_api_key": "mock_key"}, f)

        self.p_task_file = patch("jarvis_server.TASKS_FILE", self.test_tasks_file)
        self.p_cfg_file = patch("jarvis_server.CONFIG_FILE", self.test_cfg_file)
        self.p_tts = patch("jarvis_server.generate_tts", AsyncMock(return_value=""))

        self.p_task_file.start()
        self.p_cfg_file.start()
        self.p_tts.start()

        return jarvis_server.create_app()

    async def tearDownAsync(self):
        self.p_task_file.stop()
        self.p_cfg_file.stop()
        self.p_tts.stop()
        self.temp_dir.cleanup()

    # --- Core Functional Tests (1 - 15) ---

    async def test_01_explicit_add_request_creates_one_task(self):
        res = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "AYT Biyoloji: Solunum", "duration": 50, "category": "biyoloji"},
            user_context="Bunu görevlerime ekle: AYT Biyoloji Solunum",
            tool_call_id="call_add_1"
        )
        self.assertEqual(res.get("status"), "ok")
        created = res.get("task")
        self.assertEqual(created["subject"], "AYT Biyoloji: Solunum")
        self.assertEqual(created["duration"], 50)
        self.assertEqual(created["category"], "biyoloji")
        self.assertEqual(created["tool_call_id"], "call_add_1")

        tasks = jarvis_server.load_tasks()
        self.assertEqual(len(tasks), 4)
        print("  [Stage 4B Test 1 PASSED] Explicit add request created exactly one task.")

    async def test_02_ordinary_task_related_conversation_does_not_create_task(self):
        res = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "AYT Biyoloji çalışmam lazım", "duration": 40},
            user_context="Bugün AYT Biyoloji çalışmam lazım."
        )
        self.assertEqual(res.get("status"), "error")
        self.assertIn("açık kullanıcı talebi", res.get("message", ""))

        tasks = jarvis_server.load_tasks()
        self.assertEqual(len(tasks), 3, "Ordinary conversation must never create a task")
        print("  [Stage 4B Test 2 PASSED] Ordinary conversation without explicit intent rejected.")

    async def test_03_explicit_task_creation_with_omitted_duration_uses_40_minutes(self):
        res = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "Kimya: Gazlar"},
            user_context="Ders programıma ekle Kimya Gazlar",
            tool_call_id="call_add_default_dur"
        )
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("task")["duration"], 40)
        print("  [Stage 4B Test 3 PASSED] Omitted duration safely defaulted to 40 minutes.")

    async def test_04_invalid_duration_is_rejected(self):
        r1 = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "Ders", "duration": 0},
            user_context="Görev oluştur Ders"
        )
        self.assertEqual(r1.get("status"), "error")

        r2 = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "Ders", "duration": 400},
            user_context="Görev oluştur Ders"
        )
        self.assertEqual(r2.get("status"), "error")
        print("  [Stage 4B Test 4 PASSED] Out of range duration cleanly rejected.")

    async def test_05_invalid_category_is_rejected(self):
        r = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "Ders", "category": "astronomi"},
            user_context="Görev listeme ekle Ders"
        )
        self.assertEqual(r.get("status"), "error")
        print("  [Stage 4B Test 5 PASSED] Invalid category cleanly rejected.")

    async def test_06_main_jarvis_is_authorized(self):
        res = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "list"}
        )
        self.assertEqual(res.get("status"), "ok")
        print("  [Stage 4B Test 6 PASSED] Main JARVIS is authorized to execute manage_tasks.")

    async def test_07_luna_is_authorized_and_normalized_to_canonical(self):
        res1 = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Luna",
            tool_name="manage_tasks",
            args={"action": "list"}
        )
        self.assertEqual(res1.get("status"), "ok")

        res2 = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Luna (Sert Koç)",
            tool_name="manage_tasks",
            args={"action": "list"}
        )
        self.assertEqual(res2.get("status"), "ok")
        print("  [Stage 4B Test 7 PASSED] Luna agent aliases are authorized and normalized.")

    async def test_08_unauthorized_agents_cannot_execute_tool(self):
        unauth_agents = ["Study Mentor", "Hardware Research Agent", "System Intelligence Agent"]
        for agent in unauth_agents:
            res = jarvis_server.execute_desktop_tool_with_allowlist(
                agent_name=agent,
                tool_name="manage_tasks",
                args={"action": "list"}
            )
            self.assertEqual(res.get("status"), "denied", f"Agent {agent} should be denied access")
        print("  [Stage 4B Test 8 PASSED] Unauthorized agents strictly denied server-side.")

    async def test_09_list_returns_correct_task_data_and_revision_token(self):
        res = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "list"}
        )
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("count"), 3)
        self.assertEqual(len(res.get("tasks")), 3)
        self.assertIn(f"{jarvis_server.SERVER_EPOCH}:task_", res.get("revision_token"))
        print("  [Stage 4B Test 9 PASSED] List action returns accurate task inventory and revision token.")

    async def test_10_complete_marks_only_intended_task_done(self):
        res = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "complete", "task_id": "t2"}
        )
        self.assertEqual(res.get("status"), "ok")
        self.assertTrue(res.get("task")["done"])

        tasks = jarvis_server.load_tasks()
        t2 = next(t for t in tasks if t["id"] == "t2")
        t3 = next(t for t in tasks if t["id"] == "t3")
        self.assertTrue(t2["done"])
        self.assertFalse(t3["done"], "Untargeted task must remain undone")
        print("  [Stage 4B Test 10 PASSED] Complete marks only the targeted task.")

    async def test_11_ambiguous_completion_does_not_mutate_any_task(self):
        res = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "complete", "subject": "Paragraf"}
        )
        self.assertEqual(res.get("status"), "ambiguous")

        tasks = jarvis_server.load_tasks()
        t2 = next(t for t in tasks if t["id"] == "t2")
        t3 = next(t for t in tasks if t["id"] == "t3")
        self.assertFalse(t2["done"])
        self.assertFalse(t3["done"])
        print("  [Stage 4B Test 11 PASSED] Ambiguous task completion safely halted without mutations.")

    async def test_12_missing_task_id_or_unknown_task_returns_controlled_error(self):
        res = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "complete", "task_id": "t_nonexistent"}
        )
        self.assertEqual(res.get("status"), "error")
        self.assertIn("bulunamadı", res.get("message", ""))
        print("  [Stage 4B Test 12 PASSED] Unknown task ID returns controlled error.")

    async def test_13_normal_chat_remains_functional_when_tool_fails(self):
        mock_groq = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "tc_fail_1",
                        "function": {
                            "name": "manage_tasks",
                            "arguments": json.dumps({"action": "add", "subject": "Invalid" * 50})
                        }
                    }]
                }
            }]
        }

        mock_post_ctx = MagicMock()
        mock_post_ctx.__aenter__ = AsyncMock()
        mock_resp_obj = MagicMock()
        mock_resp_obj.status = 200
        mock_resp_obj.json = AsyncMock(return_value=mock_groq)
        mock_post_ctx.__aenter__.return_value = mock_resp_obj
        mock_post_ctx.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession.post", return_value=mock_post_ctx):
            resp = await self.client.post("/api/chat", json={"message": "Test fail chat"})
            self.assertEqual(resp.status, 200)
            data = await resp.json()
            self.assertIn("reply", data)
        print("  [Stage 4B Test 13 PASSED] Normal chat survived tool execution failure.")

    async def test_14_sse_chat_remains_functional_when_tool_fails(self):
        mock_groq = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "tc_fail_2",
                        "function": {
                            "name": "manage_tasks",
                            "arguments": json.dumps({"action": "complete", "task_id": "nonexistent"})
                        }
                    }]
                }
            }]
        }

        mock_post_ctx = MagicMock()
        mock_post_ctx.__aenter__ = AsyncMock()
        mock_resp_obj = MagicMock()
        mock_resp_obj.status = 200
        mock_resp_obj.json = AsyncMock(return_value=mock_groq)
        mock_post_ctx.__aenter__.return_value = mock_resp_obj
        mock_post_ctx.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession.post", return_value=mock_post_ctx):
            resp = await self.client.post("/api/chat/stream", json={"message": "Test fail sse"})
            self.assertEqual(resp.status, 200)
            text = await resp.text()
            self.assertIn("event: done", text)
        print("  [Stage 4B Test 14 PASSED] SSE chat survived tool execution failure.")

    async def test_15_existing_task_ids_and_custom_fields_are_preserved(self):
        res = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "complete", "task_id": "t1"}
        )
        self.assertEqual(res.get("status"), "ok")

        tasks = jarvis_server.load_tasks()
        t1 = next(t for t in tasks if t["id"] == "t1")
        self.assertEqual(t1.get("custom_prop"), "keep_me")
        self.assertEqual(t1.get("id"), "t1")
        print("  [Stage 4B Test 15 PASSED] Existing task IDs and custom fields preserved.")

    # --- Mixed-Concurrency & Idempotency Tests (16 - 27) ---

    async def test_16_http_add_racing_with_agent_add_prevents_lost_update(self):
        """Simulate preemption delay in HTTP handler to prove that unified lock prevents lost update."""
        orig_load = jarvis_server.load_tasks_result

        def slow_load():
            res = orig_load()
            time.sleep(0.04)
            return res

        def agent_worker():
            time.sleep(0.01)
            return jarvis_server.execute_desktop_tool_with_allowlist(
                agent_name="Main JARVIS",
                tool_name="manage_tasks",
                args={"action": "add", "subject": "Agent Race Task"},
                user_context="Görevlerime ekle Agent Race Task",
                tool_call_id="call_race_add"
            )

        loop = asyncio.get_running_loop()
        with patch("jarvis_server.load_tasks_result", slow_load):
            http_task = self.client.post("/api/tasks", json={"subject": "HTTP Race Task", "duration": 40})
            agent_task = loop.run_in_executor(None, agent_worker)
            res_http, res_agent = await asyncio.gather(http_task, agent_task)

        self.assertEqual(res_http.status, 201)
        self.assertEqual(res_agent.get("status"), "ok")

        tasks = jarvis_server.load_tasks()
        subjects = [t["subject"] for t in tasks]
        self.assertIn("Agent Race Task", subjects, "Agent task must NOT be lost!")
        self.assertIn("HTTP Race Task", subjects, "HTTP task must NOT be lost!")
        self.assertEqual(len(tasks), 3 + 2)
        print("  [Stage 4B Test 16 PASSED] HTTP add racing with agent add: zero lost updates.")

    async def test_17_http_complete_racing_with_agent_complete(self):
        """HTTP toggle on t2 racing with agent complete on t3."""
        def agent_complete_worker():
            return jarvis_server.execute_desktop_tool_with_allowlist(
                agent_name="Main JARVIS",
                tool_name="manage_tasks",
                args={"action": "complete", "task_id": "t3"}
            )

        loop = asyncio.get_running_loop()
        http_toggle = self.client.post("/api/tasks/t2/toggle")
        agent_comp = loop.run_in_executor(None, agent_complete_worker)
        res_http, res_agent = await asyncio.gather(http_toggle, agent_comp)

        self.assertEqual(res_http.status, 200)
        self.assertEqual(res_agent.get("status"), "ok")

        tasks = jarvis_server.load_tasks()
        t2 = next(t for t in tasks if t["id"] == "t2")
        t3 = next(t for t in tasks if t["id"] == "t3")
        self.assertTrue(t2["done"], "t2 must be completed by HTTP toggle")
        self.assertTrue(t3["done"], "t3 must be completed by agent complete")
        print("  [Stage 4B Test 17 PASSED] HTTP complete racing with agent complete: both committed.")

    async def test_18_http_bulk_save_racing_with_agent_add(self):
        """HTTP bulk save with revision token racing with background thread agent task addition."""
        resp_get = await self.client.get("/api/tasks")
        self.assertEqual(resp_get.status, 200)
        token = resp_get.headers.get("X-Task-Revision-Token")
        curr_tasks = await resp_get.json()
        bulk_payload = curr_tasks + [{"id": "t_bulk", "subject": "Bulk Appended Task", "duration": 35}]

        def agent_add_worker():
            return jarvis_server.execute_desktop_tool_with_allowlist(
                agent_name="Main JARVIS",
                tool_name="manage_tasks",
                args={"action": "add", "subject": "Agent Concurrent To Bulk"},
                user_context="Bunu görevlerime ekle Agent Concurrent To Bulk",
                tool_call_id="call_bulk_race"
            )

        loop = asyncio.get_running_loop()
        http_bulk = self.client.post("/api/tasks", json=bulk_payload, headers={"X-Task-Revision-Token": token})
        agent_add = loop.run_in_executor(None, agent_add_worker)
        res_http, res_agent = await asyncio.gather(http_bulk, agent_add)

        self.assertEqual(res_agent.get("status"), "ok")
        self.assertIn(res_http.status, (200, 409))

        tasks = jarvis_server.load_tasks()
        subjects = [t["subject"] for t in tasks]
        self.assertIn("Agent Concurrent To Bulk", subjects, "Agent task must never be lost")
        if res_http.status == 200:
            self.assertIn("Bulk Appended Task", subjects, "If bulk succeeded first, bulk task is present")
        else:
            self.assertNotIn("Bulk Appended Task", subjects, "If bulk was stale, it was rejected with 409 Conflict")
        print("  [Stage 4B Test 18 PASSED] HTTP bulk save racing with agent add: OCC and lock safely prevent lost updates.")

    async def test_19_multiple_simultaneous_agent_task_creations(self):
        def sync_worker(idx):
            return jarvis_server.execute_desktop_tool_with_allowlist(
                agent_name="Main JARVIS",
                tool_name="manage_tasks",
                args={"action": "add", "subject": f"Paralel Ders {idx}"},
                user_context=f"Görevlerime ekle Paralel Ders {idx}",
                tool_call_id=f"call_multi_{idx}"
            )

        loop = asyncio.get_running_loop()
        futs = [loop.run_in_executor(None, sync_worker, i) for i in range(5)]
        results = await asyncio.gather(*futs)

        for r in results:
            self.assertEqual(r.get("status"), "ok")

        tasks = jarvis_server.load_tasks()
        self.assertEqual(len(tasks), 3 + 5)
        print("  [Stage 4B Test 19 PASSED] 5 simultaneous agent task creations safely serialized.")

    async def test_20_same_tool_call_id_concurrently_creates_exactly_one_task(self):
        """Multiple concurrent calls with the same tool_call_id create exactly one task; others return idempotent."""
        call_id = "tc_shared_unique_123"

        def sync_caller(idx):
            return jarvis_server.execute_desktop_tool_with_allowlist(
                agent_name="Main JARVIS",
                tool_name="manage_tasks",
                args={"action": "add", "subject": "Tekil Ders Görevi"},
                user_context="Görevlerime ekle Tekil Ders Görevi",
                tool_call_id=call_id
            )

        loop = asyncio.get_running_loop()
        futs = [loop.run_in_executor(None, sync_caller, i) for i in range(5)]
        results = await asyncio.gather(*futs)

        for r in results:
            self.assertEqual(r.get("status"), "ok")

        created_count = sum(1 for r in results if not r.get("idempotent"))
        idempotent_count = sum(1 for r in results if r.get("idempotent"))
        self.assertEqual(created_count, 1, "Exactly one task must be created")
        self.assertEqual(idempotent_count, 4, "Four callers must receive idempotent duplicate notification")

        tasks = jarvis_server.load_tasks()
        matching = [t for t in tasks if t.get("tool_call_id") == call_id]
        self.assertEqual(len(matching), 1)
        print("  [Stage 4B Test 20 PASSED] Concurrent calls with identical tool_call_id created exactly one task.")

    async def test_21_same_tool_call_id_retried_returns_original_task(self):
        call_id = "tc_retry_test_999"
        r1 = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "Geometri Tekrarı"},
            user_context="Bunu görevlerime ekle Geometri Tekrarı",
            tool_call_id=call_id
        )
        self.assertEqual(r1.get("status"), "ok")
        self.assertFalse(r1.get("idempotent", False))
        t1_id = r1["task"]["id"]

        # Retry with identical tool_call_id
        r2 = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "Geometri Tekrarı"},
            user_context="Bunu görevlerime ekle Geometri Tekrarı",
            tool_call_id=call_id
        )
        self.assertEqual(r2.get("status"), "ok")
        self.assertTrue(r2.get("idempotent", False))
        self.assertEqual(r2["task"]["id"], t1_id)
        print("  [Stage 4B Test 21 PASSED] Sequential retry with same tool_call_id returned original task.")

    async def test_22_different_tool_call_ids_with_identical_subjects_create_separate_tasks(self):
        """User asking to add identical tasks in separate turns with different tool-call IDs."""
        r1 = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "Paragraf 25 Soru"},
            user_context="Görevlerime ekle Paragraf 25 Soru",
            tool_call_id="call_turn_1"
        )
        self.assertEqual(r1.get("status"), "ok")
        self.assertFalse(r1.get("idempotent", False))

        r2 = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "Paragraf 25 Soru"},
            user_context="Görevlerime ekle Paragraf 25 Soru",
            tool_call_id="call_turn_2"
        )
        self.assertEqual(r2.get("status"), "ok")
        self.assertFalse(r2.get("idempotent", False))

        self.assertNotEqual(r1["task"]["id"], r2["task"]["id"])
        tasks = jarvis_server.load_tasks()
        paragraf_tasks = [t for t in tasks if t["subject"] == "Paragraf 25 Soru"]
        self.assertEqual(len(paragraf_tasks), 2, "Both distinct intentional tasks must be created")
        print("  [Stage 4B Test 22 PASSED] Different tool_call_ids with identical subjects preserved as separate tasks.")

    async def test_23_persistence_failure_does_not_commit_idempotency_key(self):
        call_id = "tc_fail_and_retry"
        with patch("jarvis_server.save_tasks", side_effect=OSError("Disk Out of Space")):
            r1 = jarvis_server.execute_desktop_tool_with_allowlist(
                agent_name="Main JARVIS",
                tool_name="manage_tasks",
                args={"action": "add", "subject": "Fail Task"},
                user_context="Görevlerime ekle Fail Task",
                tool_call_id=call_id
            )
            self.assertEqual(r1.get("status"), "error")

        # Now disk is healthy; retry with same call_id must succeed and create the task
        r2 = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "Fail Task"},
            user_context="Görevlerime ekle Fail Task",
            tool_call_id=call_id
        )
        self.assertEqual(r2.get("status"), "ok")
        self.assertFalse(r2.get("idempotent", False), "Must not think key was committed before persistence")
        print("  [Stage 4B Test 23 PASSED] Persistence failure did not commit idempotency key.")

    async def test_24_agent_mutation_increments_task_revision_counter(self):
        rev_before = jarvis_server.TASK_REVISION_COUNTER
        r_add = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "Counter Test Task"},
            user_context="Görevlerime ekle Counter Test Task",
            tool_call_id="call_counter_1"
        )
        self.assertEqual(r_add.get("status"), "ok")
        self.assertEqual(jarvis_server.TASK_REVISION_COUNTER, rev_before + 1)

        t_id = r_add["task"]["id"]
        r_comp = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "complete", "task_id": t_id}
        )
        self.assertEqual(r_comp.get("status"), "ok")
        self.assertEqual(jarvis_server.TASK_REVISION_COUNTER, rev_before + 2)
        print("  [Stage 4B Test 24 PASSED] Agent task creation and completion both increment revision counter.")

    async def test_25_previous_revision_token_stale_after_agent_mutation(self):
        # 1. HTTP client fetches tasks and gets revision token T1
        resp_get = await self.client.get("/api/tasks")
        self.assertEqual(resp_get.status, 200)
        token_t1 = resp_get.headers.get("X-Task-Revision-Token")
        self.assertTrue(token_t1)

        # 2. Agent mutates task list
        res_agent = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Main JARVIS",
            tool_name="manage_tasks",
            args={"action": "add", "subject": "Invalidate HTTP Token Task"},
            user_context="Görevlerime ekle Invalidate HTTP Token Task",
            tool_call_id="call_stale_test"
        )
        self.assertEqual(res_agent.get("status"), "ok")

        # 3. HTTP client attempts mutation using stale token T1 -> must return 409 Conflict
        resp_patch = await self.client.patch(
            "/api/tasks/t2",
            json={"done": True},
            headers={"X-Task-Revision-Token": token_t1}
        )
        self.assertEqual(resp_patch.status, 409)
        data_patch = await resp_patch.json()
        self.assertEqual(data_patch.get("error"), "STALE_TASK_REVISION")
        print("  [Stage 4B Test 25 PASSED] Prior HTTP revision token invalidated by agent mutation (HTTP 409).")

    async def test_26_luna_alias_cannot_gain_permissions_beyond_canonical_profile(self):
        self.assertEqual(jarvis_server.normalize_agent_name("Luna"), "Luna (Sert Koç)")
        self.assertEqual(jarvis_server.normalize_agent_name("Luna (Sert Koç)"), "Luna (Sert Koç)")

        canonical_tools = jarvis_server.AGENT_PROFILES["Luna (Sert Koç)"]["allowed_tools"]
        alias_tools = jarvis_server.AGENT_PROFILES["Luna"]["allowed_tools"]
        self.assertEqual(canonical_tools, alias_tools)

        # Verify an unallowed tool for Luna is strictly denied
        res_denied = jarvis_server.execute_desktop_tool_with_allowlist(
            agent_name="Luna",
            tool_name="get_hardware_price",
            args={"item": "7500F"}
        )
        self.assertEqual(res_denied.get("status"), "denied")
        print("  [Stage 4B Test 26 PASSED] Luna alias normalized to canonical profile without permission elevation.")

    async def test_27_unauthorized_agent_attempts_strictly_denied(self):
        unauth = ["Study Mentor", "Hardware Research Agent", "System Intelligence Agent", "Unknown Bot"]
        for agent in unauth:
            res = jarvis_server.execute_desktop_tool_with_allowlist(
                agent_name=agent,
                tool_name="manage_tasks",
                args={"action": "add", "subject": "Sneaky Task"},
                user_context="Görevlerime ekle Sneaky Task"
            )
            self.assertEqual(res.get("status"), "denied")
        print("  [Stage 4B Test 27 PASSED] Unauthorized agent tool invocations strictly denied server-side.")


if __name__ == "__main__":
    unittest.main()
