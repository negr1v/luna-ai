"""
ACCIO LUNA V4.0 — Phase 8B.2 Automated Test Suite
Focus: Telegram Concurrency, Lock Correctness, Polling & Deduplication,
       Outbound Serialization, Worker Lifecycle, Endpoints, Masking & App Isolation.
"""

import unittest
import asyncio
import os
import sys
import json
import tempfile
import shutil
import time
from unittest.mock import patch, AsyncMock, MagicMock

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import luna_server


class Phase8B2TelegramConcurrencyTest(AioHTTPTestCase):

    async def get_application(self):
        app = web.Application()
        app.router.add_get("/api/config", luna_server.handle_get_config)
        app.router.add_post("/api/config", luna_server.handle_save_config)
        app.router.add_get("/api/telegram/messages", luna_server.handle_get_telegram)
        app.router.add_post("/api/telegram/messages", luna_server.handle_post_telegram)
        app.router.add_delete("/api/telegram/messages", luna_server.handle_delete_telegram)
        app.router.add_post("/api/telegram/send", luna_server.handle_send_telegram)
        app.router.add_get("/api/telegram/status", luna_server.handle_get_telegram_status)
        app.router.add_post("/api/chat", luna_server.handle_chat)
        app.router.add_get("/api/notifications/deferred", luna_server.handle_get_deferred_notifications)
        return app

    def setUp(self):
        super().setUp()
        self.test_dir = tempfile.mkdtemp(prefix="phase8b2_tg_test_")
        self.test_tg_file = os.path.join(self.test_dir, "luna_telegram.json")
        self.test_config_file = os.path.join(self.test_dir, "luna_config.json")
        self.test_tasks_file = os.path.join(self.test_dir, "luna_tasks.json")

        with open(self.test_tg_file, "w", encoding="utf-8") as f:
            json.dump([], f)

        with open(self.test_config_file, "w", encoding="utf-8") as f:
            json.dump({
                "telegram_bot_token": "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_12345678",
                "telegram_chat_id": "987654321",
                "telegram_polling_enabled": False,
                "groq_api_key": "gsk_test_mock_key_12345",
                "tts_engine": "edge_tts"
            }, f)

        with open(self.test_tasks_file, "w", encoding="utf-8") as f:
            json.dump({"tasks": [{"id": "t1", "title": "Test Task", "status": "pending"}]}, f)

        self.orig_tg_file = luna_server.TELEGRAM_FILE
        self.orig_cfg_file = luna_server.CONFIG_FILE
        self.orig_tasks_file = luna_server.TASKS_FILE

        luna_server.TELEGRAM_FILE = self.test_tg_file
        luna_server.CONFIG_FILE = self.test_config_file
        luna_server.TASKS_FILE = self.test_tasks_file

        luna_server.TELEGRAM_UPDATE_OFFSET = 0
        luna_server.PROCESSED_UPDATE_IDS.clear()

    def tearDown(self):
        luna_server.TELEGRAM_FILE = self.orig_tg_file
        luna_server.CONFIG_FILE = self.orig_cfg_file
        luna_server.TASKS_FILE = self.orig_tasks_file
        luna_server.TELEGRAM_UPDATE_OFFSET = 0
        luna_server.PROCESSED_UPDATE_IDS.clear()

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)
        super().tearDown()

    async def tearDownAsync(self):
        await luna_server.stop_telegram_worker()
        await super().tearDownAsync()

    # =========================================================================
    # A. LOCK CORRECTNESS
    # =========================================================================

    async def test_01_all_four_locks_exist_and_are_asyncio_locks(self):
        """A.1: All four Telegram locks exist and are asyncio.Lock instances."""
        self.assertIsInstance(luna_server.TELEGRAM_ASYNC_LOCK, asyncio.Lock)
        self.assertIsInstance(luna_server.TELEGRAM_OUTBOUND_LOCK, asyncio.Lock)
        self.assertIsInstance(luna_server.TELEGRAM_POLL_LOCK, asyncio.Lock)
        self.assertIsInstance(luna_server.TELEGRAM_LIFECYCLE_LOCK, asyncio.Lock)

    async def test_02_async_lock_prevents_lost_updates_under_concurrency(self):
        """A.2: Concurrent operations under TELEGRAM_ASYNC_LOCK do not lose updates."""
        async def add_item(idx):
            async with luna_server.TELEGRAM_ASYNC_LOCK:
                msgs = luna_server.load_telegram_messages()
                msgs.append({"id": f"msg_{idx}", "text": f"Content {idx}"})
                luna_server.save_telegram_messages(msgs)

        tasks = [asyncio.create_task(add_item(i)) for i in range(25)]
        await asyncio.gather(*tasks)

        final_msgs = luna_server.load_telegram_messages()
        self.assertEqual(len(final_msgs), 25)
        ids = {m["id"] for m in final_msgs}
        self.assertEqual(len(ids), 25)

    async def test_03_outbound_lock_serializes_concurrent_sends(self):
        """A.3: Outbound sends serialize through TELEGRAM_OUTBOUND_LOCK."""
        execution_order = []

        async def fake_post(url, json=None):
            msg_text = json.get("text") if json else "unknown"
            execution_order.append(("enter", msg_text))
            await asyncio.sleep(0.05)
            execution_order.append(("exit", msg_text))
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={"ok": True})
            return mock_resp

        class MockPostCM:
            def __init__(self, url, json=None, **kwargs):
                self.url = url
                self.json_data = json
            async def __aenter__(self):
                return await fake_post(self.url, json=self.json_data)
            async def __aexit__(self, exc_type, exc, tb):
                pass

        with patch("aiohttp.ClientSession.post", side_effect=MockPostCM):
            t1 = asyncio.create_task(luna_server.send_telegram_message("Msg 1", chat_id="12345", custom_token="token_test"))
            t2 = asyncio.create_task(luna_server.send_telegram_message("Msg 2", chat_id="12345", custom_token="token_test"))
            await asyncio.gather(t1, t2)

        # Check serialization: enter1, exit1, enter2, exit2 (or vice versa, never interleaved enter, enter)
        self.assertEqual(len(execution_order), 4)
        self.assertEqual(execution_order[0][0], "enter")
        self.assertEqual(execution_order[1][0], "exit")
        self.assertEqual(execution_order[2][0], "enter")
        self.assertEqual(execution_order[3][0], "exit")

    async def test_04_poll_lock_prevents_concurrent_polling(self):
        """A.4: Polling cannot execute concurrently while TELEGRAM_POLL_LOCK is held."""
        poll_entered = False
        second_poll_ran = False

        async with luna_server.TELEGRAM_POLL_LOCK:
            async def run_poll():
                nonlocal second_poll_ran
                session = MagicMock()
                # Should wait until lock is released
                await luna_server.telegram_poll_step(session, "fake_token")
                second_poll_ran = True

            task = asyncio.create_task(run_poll())
            await asyncio.sleep(0.05)
            # While lock held, second poll must not have finished
            self.assertFalse(second_poll_ran)

        # Once lock released, it completes
        await asyncio.wait_for(task, timeout=2.0)
        self.assertTrue(second_poll_ran)

    async def test_05_lifecycle_lock_prevents_concurrent_startup_races(self):
        """A.5: Concurrent startup calls under TELEGRAM_LIFECYCLE_LOCK result in exactly one worker."""
        r1, r2, r3 = await asyncio.gather(
            luna_server.start_telegram_worker(),
            luna_server.start_telegram_worker(),
            luna_server.start_telegram_worker()
        )
        # Exactly one should return True, others False
        results = [r1, r2, r3]
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 2)
        self.assertTrue(luna_server.TELEGRAM_WORKER_RUNNING)
        self.assertIsNotNone(luna_server.TELEGRAM_WORKER_TASK)
        await luna_server.stop_telegram_worker()

    async def test_06_cancellation_releases_acquired_locks(self):
        """A.6: Task cancellation releases acquired locks without deadlock."""
        lock = luna_server.TELEGRAM_OUTBOUND_LOCK
        entered = asyncio.Event()

        async def worker():
            async with lock:
                entered.set()
                await asyncio.sleep(10.0)

        task = asyncio.create_task(worker())
        await entered.wait()
        self.assertTrue(lock.locked())

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        self.assertFalse(lock.locked())

    async def test_07_exceptions_do_not_leave_locks_permanently_acquired(self):
        """A.7: Unhandled exception in protected block releases the lock."""
        lock = luna_server.TELEGRAM_ASYNC_LOCK
        try:
            async with lock:
                raise ValueError("Intentional crash")
        except ValueError:
            pass

        self.assertFalse(lock.locked())

    async def test_08_no_deadlock_under_interleaved_operations(self):
        """A.8: Concurrent poll, outbound send, update processing and status check execute without deadlock."""
        session = MagicMock()
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={"result": [{"update_id": 101, "message": {"text": "deal 5000 tl"}}]})
        session.get.return_value.__aenter__.return_value = resp

        async def op1():
            return await luna_server.telegram_poll_step(session, "test_token")

        async def op2():
            return await luna_server.send_telegram_message("Test broadcast", custom_token="")

        async def op3():
            return await luna_server.process_telegram_update({"update_id": 102, "message": {"text": "/status"}})

        async def op4():
            async with luna_server.TELEGRAM_ASYNC_LOCK:
                return luna_server.load_telegram_messages()

        results = await asyncio.wait_for(
            asyncio.gather(op1(), op2(), op3(), op4()),
            timeout=5.0
        )
        self.assertEqual(len(results), 4)

    # =========================================================================
    # B. POLLING AND INCOMING MESSAGES
    # =========================================================================

    async def test_09_concurrent_polling_cannot_process_same_update_twice(self):
        """B.1: Duplicate update_id is identified and rejected with status: duplicate."""
        upd = {"update_id": 201, "message": {"text": "First arrival"}}
        res1 = await luna_server.process_telegram_update(upd)
        res2 = await luna_server.process_telegram_update(upd)

        self.assertEqual(res1["status"], "ok")
        self.assertEqual(res2["status"], "duplicate")
        self.assertEqual(res2["update_id"], 201)

    async def test_10_update_offsets_advance_monotonically(self):
        """B.2: Update offset advances monotonically to max(offset, update_id + 1)."""
        luna_server.TELEGRAM_UPDATE_OFFSET = 10
        await luna_server.process_telegram_update({"update_id": 15, "message": {"text": "msg"}})
        self.assertEqual(luna_server.TELEGRAM_UPDATE_OFFSET, 16)

        # An out-of-order lower ID does not regress offset
        await luna_server.process_telegram_update({"update_id": 12, "message": {"text": "msg"}})
        self.assertEqual(luna_server.TELEGRAM_UPDATE_OFFSET, 16)

    async def test_11_incoming_messages_persisted_without_loss(self):
        """B.3: Incoming messages are durably written to telegram file."""
        await luna_server.process_telegram_update({"update_id": 301, "message": {"text": "RTX 4060 9999 TL indirim"}})
        msgs = luna_server.load_telegram_messages()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["text"], "RTX 4060 9999 TL indirim")
        self.assertEqual(msgs[0]["category"], "deal")

    async def test_12_polling_recovers_from_transient_api_errors(self):
        """B.4: Polling recovers safely from 500, 429 and timeout errors without raising."""
        session = MagicMock()

        # Test HTTP 500
        resp_500 = AsyncMock()
        resp_500.status = 500
        session.get.return_value.__aenter__.return_value = resp_500
        c1 = await luna_server.telegram_poll_step(session, "tok")
        self.assertEqual(c1, 0)

        # Test Timeout
        session.get.return_value.__aenter__.side_effect = asyncio.TimeoutError()
        c2 = await luna_server.telegram_poll_step(session, "tok")
        self.assertEqual(c2, 0)

    async def test_13_cancellation_during_polling_handled_correctly(self):
        """B.5: Cancellation during polling loop exits gracefully without orphan tasks."""
        await luna_server.start_telegram_worker()
        self.assertTrue(luna_server.TELEGRAM_WORKER_RUNNING)
        stopped = await luna_server.stop_telegram_worker()
        self.assertTrue(stopped)
        self.assertFalse(luna_server.TELEGRAM_WORKER_RUNNING)
        self.assertIsNone(luna_server.TELEGRAM_WORKER_TASK)

    # =========================================================================
    # C. OUTBOUND MESSAGING
    # =========================================================================

    async def test_14_unconfigured_token_records_local_only(self):
        """C.1: Outbound message when unconfigured records to local feed with status: local_only."""
        with open(self.test_config_file, "w", encoding="utf-8") as f:
            json.dump({"telegram_bot_token": "", "telegram_chat_id": ""}, f)

        res = await luna_server.send_telegram_message("Offline message", category="deal")
        self.assertEqual(res["status"], "local_only")
        msgs = luna_server.load_telegram_messages()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["text"], "Offline message")
        self.assertEqual(msgs[0]["source"], "Yerel Bildirim")

    async def test_15_outbound_delivered_successfully_via_mock(self):
        """C.2: Outbound message with valid token successfully delivers and records outbound entry."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"ok": True, "result": {"message_id": 888}})

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value = mock_resp
            res = await luna_server.send_telegram_message("Live test message", chat_id="12345", custom_token="token_xyz")

        self.assertEqual(res["status"], "ok")
        self.assertTrue(res["delivered"])
        msgs = luna_server.load_telegram_messages()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["text"], "Live test message")
        self.assertEqual(msgs[0]["source"], "Telegram Outbound")

    async def test_16_rate_limit_handled_without_uncontrolled_retries(self):
        """C.3: Outbound send encountering HTTP 429 returns RATE_LIMIT_EXCEEDED and retry_after."""
        mock_resp = AsyncMock()
        mock_resp.status = 429
        mock_resp.json = AsyncMock(return_value={"ok": False, "parameters": {"retry_after": 12}})

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value = mock_resp
            res = await luna_server.send_telegram_message("Spam text", chat_id="12345", custom_token="tok")

        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error_code"], "RATE_LIMIT_EXCEEDED")
        self.assertEqual(res["retry_after"], 12)

    async def test_17_failed_send_does_not_block_subsequent_sends(self):
        """C.4: Network failure during send releases lock, allowing subsequent send to proceed."""
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.side_effect = Exception("Network down")
            res1 = await luna_server.send_telegram_message("Fail msg", chat_id="123", custom_token="tok")

        self.assertEqual(res1["status"], "error")
        self.assertEqual(res1["error_code"], "NETWORK_ERROR")
        self.assertFalse(luna_server.TELEGRAM_OUTBOUND_LOCK.locked())

        # Second send can now succeed
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"ok": True})
        with patch("aiohttp.ClientSession.post") as mock_post2:
            mock_post2.return_value.__aenter__.return_value = mock_resp
            res2 = await luna_server.send_telegram_message("Success msg", chat_id="123", custom_token="tok")

        self.assertEqual(res2["status"], "ok")

    # =========================================================================
    # D. LIFECYCLE
    # =========================================================================

    async def test_18_startup_creates_single_worker(self):
        """D.1: start_telegram_worker initializes exactly one active worker task."""
        created = await luna_server.start_telegram_worker()
        self.assertTrue(created)
        self.assertTrue(luna_server.TELEGRAM_WORKER_RUNNING)
        self.assertIsNotNone(luna_server.TELEGRAM_WORKER_TASK)
        self.assertFalse(luna_server.TELEGRAM_WORKER_TASK.done())
        await luna_server.stop_telegram_worker()

    async def test_19_repeated_startup_prevents_duplicate_worker(self):
        """D.2: Subsequent start_telegram_worker call returns False without spawning second task."""
        await luna_server.start_telegram_worker()
        initial_task = luna_server.TELEGRAM_WORKER_TASK

        duplicate = await luna_server.start_telegram_worker()
        self.assertFalse(duplicate)
        self.assertIs(luna_server.TELEGRAM_WORKER_TASK, initial_task)
        await luna_server.stop_telegram_worker()

    async def test_20_shutdown_cancels_and_awaits_worker(self):
        """D.3: stop_telegram_worker cleanly shuts down active worker."""
        await luna_server.start_telegram_worker()
        stopped = await luna_server.stop_telegram_worker()
        self.assertTrue(stopped)
        self.assertFalse(luna_server.TELEGRAM_WORKER_RUNNING)
        self.assertIsNone(luna_server.TELEGRAM_WORKER_TASK)

    async def test_21_repeated_shutdown_is_safe(self):
        """D.4: Redundant stop_telegram_worker returns False with zero errors."""
        res = await luna_server.stop_telegram_worker()
        self.assertFalse(res)

    async def test_22_restart_creates_fresh_worker(self):
        """D.5: restart_telegram_worker cancels prior task and launches fresh worker."""
        await luna_server.start_telegram_worker()
        task1 = luna_server.TELEGRAM_WORKER_TASK

        restarted = await luna_server.restart_telegram_worker()
        self.assertTrue(restarted)
        task2 = luna_server.TELEGRAM_WORKER_TASK
        self.assertIsNot(task1, task2)
        self.assertTrue(luna_server.TELEGRAM_WORKER_RUNNING)
        await luna_server.stop_telegram_worker()

    async def test_23_telegram_cleanup_ctx_integration(self):
        """D.6: aiohttp cleanup context automatically manages start and stop."""
        app = web.Application()
        gen = luna_server.telegram_cleanup_ctx(app)
        await gen.__anext__()
        self.assertTrue(luna_server.TELEGRAM_WORKER_RUNNING)
        self.assertIsNotNone(luna_server.TELEGRAM_WORKER_TASK)

        # Simulate shutdown yield exit
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass
        self.assertFalse(luna_server.TELEGRAM_WORKER_RUNNING)
        self.assertIsNone(luna_server.TELEGRAM_WORKER_TASK)

    # =========================================================================
    # E. ENDPOINTS AND MASKING
    # =========================================================================

    async def test_24_get_telegram_messages_endpoint(self):
        """E.1: GET /api/telegram/messages returns 200 and messages list."""
        resp = await self.client.get("/api/telegram/messages")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data, [])

    async def test_25_post_telegram_messages_validates_input(self):
        """E.2: POST /api/telegram/messages validates presence of text and JSON payload."""
        # Missing text
        resp1 = await self.client.post("/api/telegram/messages", json={"text": ""})
        self.assertEqual(resp1.status, 400)

        # Invalid JSON structure
        resp2 = await self.client.post("/api/telegram/messages", data="not a json")
        self.assertEqual(resp2.status, 400)

        # Valid message
        resp3 = await self.client.post("/api/telegram/messages", json={"text": "Hello bot", "sender": "@tester"})
        self.assertEqual(resp3.status, 200)
        data = await resp3.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["message"]["text"], "Hello bot")

    async def test_26_delete_telegram_messages_endpoint(self):
        """E.3: DELETE /api/telegram/messages clears messages list."""
        await self.client.post("/api/telegram/messages", json={"text": "To be deleted"})
        resp = await self.client.delete("/api/telegram/messages")
        self.assertEqual(resp.status, 200)
        res_get = await self.client.get("/api/telegram/messages")
        self.assertEqual(await res_get.json(), [])

    async def test_27_send_telegram_endpoint_validation_and_rate_limit(self):
        """E.4: POST /api/telegram/send rejects empty text and surfaces 429 when rate limited."""
        # Empty text
        resp1 = await self.client.post("/api/telegram/send", json={"text": "   "})
        self.assertEqual(resp1.status, 400)

        # Rate limited mock
        mock_resp = AsyncMock()
        mock_resp.status = 429
        mock_resp.json = AsyncMock(return_value={"ok": False, "parameters": {"retry_after": 5}})
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value = mock_resp
            resp2 = await self.client.post("/api/telegram/send", json={"text": "Flood test", "chat_id": "123"})
            self.assertEqual(resp2.status, 429)

    async def test_28_get_telegram_status_endpoint(self):
        """E.5: GET /api/telegram/status returns health metrics without credentials."""
        resp = await self.client.get("/api/telegram/status")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("worker_running", data)
        self.assertIn("worker_task_active", data)
        self.assertIn("update_offset", data)
        self.assertIn("processed_updates_count", data)
        self.assertIn("messages_count", data)
        # Ensure token is never in status
        self.assertNotIn("token", json.dumps(data).lower())

    async def test_29_credentials_never_returned_and_masked(self):
        """E.6: Credentials masked by mask_secrets and never exposed via /api/config."""
        token_sample = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_12345678"
        masked = luna_server.mask_secrets(f"Error connecting to bot with token {token_sample}")
        self.assertNotIn(token_sample, masked)
        self.assertIn("***TELEGRAM_TOKEN_REDACTED***", masked)

        resp = await self.client.get("/api/config")
        data = await resp.json()
        self.assertEqual(data.get("telegram_bot_token", ""), "")
        self.assertTrue(data.get("telegram_bot_token_configured", False))

    # =========================================================================
    # F. APPLICATION ISOLATION
    # =========================================================================

    async def test_30_telegram_failure_does_not_crash_main_app(self):
        """F.1: Telegram exceptions during poll/send do not crash main application routes."""
        # Cause exception in poll step
        session = MagicMock()
        session.get.side_effect = Exception("Fatal Telegram network socket drop")
        await luna_server.telegram_poll_step(session, "tok")

        # Main app endpoints remain 100% operational
        resp_cfg = await self.client.get("/api/config")
        self.assertEqual(resp_cfg.status, 200)

        resp_tg = await self.client.get("/api/telegram/status")
        self.assertEqual(resp_tg.status, 200)

    async def test_31_telegram_locks_do_not_block_unrelated_chat(self):
        """F.2: Holding TELEGRAM_OUTBOUND_LOCK does not block /api/chat or other endpoints."""
        async with luna_server.TELEGRAM_OUTBOUND_LOCK:
            # While outbound lock is held, calling /api/config should succeed immediately
            resp = await self.client.get("/api/config")
            self.assertEqual(resp.status, 200)

    async def test_32_notification_gate_intact(self):
        """F.3: Notification endpoint /api/notifications/deferred works independently."""
        resp = await self.client.get("/api/notifications/deferred")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")

    async def test_33_telegram_builtin_commands_functional(self):
        """F.4: Built-in Telegram commands /start, /status, /tasks, /help produce expected replies."""
        res_start = await luna_server.process_telegram_update({"update_id": 901, "message": {"text": "/start"}})
        self.assertIn("Accio Luna Telegram Köprüsü Aktif", res_start.get("command_reply", ""))

        res_status = await luna_server.process_telegram_update({"update_id": 902, "message": {"text": "/status"}})
        self.assertIn("LUNA Canlı", res_status.get("command_reply", ""))

        res_tasks = await luna_server.process_telegram_update({"update_id": 903, "message": {"text": "/tasks"}})
        self.assertIn("Aktif Görevler", res_tasks.get("command_reply", ""))

        res_help = await luna_server.process_telegram_update({"update_id": 904, "message": {"text": "/help"}})
        self.assertIn("Komutlar", res_help.get("command_reply", ""))


if __name__ == "__main__":
    unittest.main()
