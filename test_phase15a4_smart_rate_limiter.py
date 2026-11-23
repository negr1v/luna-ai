"""
Phase 15A.4: Smart Provider Rate Limiter Tests
Verifies:
1. Provider-specific concurrency limiting (e.g. Groq max_concurrent=1).
2. Bounded queue enforcement when capacity is exceeded.
3. HTTP 429 Retry-After parsing and dynamic cooldown.
4. Cooldown rejection with accurate remaining retry_after.
5. Never duplicating potentially billed requests (is_billed=True -> can_retry=False).
6. Safe cancellation and clean semaphore release.
7. End-to-end integration with /api/chat returning HTTP 429.
"""

import os
import sys
import time
import asyncio
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jarvis_server import (
    SmartProviderRateLimiter,
    ProviderRateLimitState,
    RateLimitExceededException,
    SMART_PROVIDER_LIMITER
)


class TestPhase15A4SmartRateLimiter(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.limiter = SmartProviderRateLimiter()

    async def test_01_concurrency_limiting_per_provider(self):
        """Groq has max_concurrent=1; second concurrent task must wait until first finishes."""
        groq_state = self.limiter.get_state("groq")
        self.assertEqual(groq_state.max_concurrent, 1)

        acquired_order = []

        async def worker(worker_id: int, hold_time: float):
            async with self.limiter.throttle("groq", timeout=5.0):
                acquired_order.append(f"start_{worker_id}")
                await asyncio.sleep(hold_time)
                acquired_order.append(f"end_{worker_id}")

        # Run two workers concurrently
        t1 = asyncio.create_task(worker(1, 0.05))
        await asyncio.sleep(0.01)
        t2 = asyncio.create_task(worker(2, 0.02))

        await asyncio.gather(t1, t2)

        # Worker 1 must finish before Worker 2 starts because max_concurrent == 1
        self.assertEqual(acquired_order, ["start_1", "end_1", "start_2", "end_2"])

    async def test_02_bounded_queue_rejection(self):
        """When queue exceeds max_queue, additional requests are rejected immediately."""
        custom_state = ProviderRateLimitState("test_provider", max_concurrent=1, max_queue=2, default_cooldown=1.5)
        self.limiter._states["test_provider"] = custom_state

        # Occupy slot
        allowed1, _, _ = await self.limiter.acquire_slot("test_provider")
        self.assertTrue(allowed1)

        # Fill queue to max (2 items)
        custom_state.queue_size = 2

        # Next acquire should fail due to bounded queue
        allowed3, reason, retry_after = await self.limiter.acquire_slot("test_provider")
        self.assertFalse(allowed3)
        self.assertEqual(reason, "QUEUE_BOUND_EXCEEDED")
        self.assertGreater(retry_after, 0)

        self.limiter.release_slot("test_provider")

    async def test_03_http_429_retry_after_and_cooldown(self):
        """HTTP 429 response parses Retry-After and puts provider into cooldown."""
        state = self.limiter.get_state("groq")
        now = time.time()
        self.assertLessEqual(state.cooldown_until, now)

        # Record 429 with explicit Retry-After header
        can_retry, cooldown = self.limiter.record_response("groq", 429, retry_after_header="3.5", is_billed=False, attempt=0)
        self.assertTrue(can_retry)
        self.assertEqual(cooldown, 3.5)
        self.assertGreater(state.cooldown_until, now + 3.0)

        # Attempting acquire during cooldown must be rejected
        allowed, reason, wait_rem = await self.limiter.acquire_slot("groq")
        self.assertFalse(allowed)
        self.assertEqual(reason, "COOLDOWN_ACTIVE")
        self.assertGreater(wait_rem, 0.0)

    async def test_04_never_duplicate_billed_requests(self):
        """When is_billed=True, record_response must NEVER permit retries."""
        # 1. Free request: can_retry is allowed on attempt 0
        can_retry_free, _ = self.limiter.record_response("openrouter", 429, is_billed=False, attempt=0)
        self.assertTrue(can_retry_free)

        # 2. Billed request: can_retry is ALWAYS False
        can_retry_billed, _ = self.limiter.record_response("openrouter", 429, is_billed=True, attempt=0)
        self.assertFalse(can_retry_billed)

    async def test_05_safe_cancellation_releases_semaphore(self):
        """If a waiting coroutine is cancelled, semaphore and queue counters are cleanly restored."""
        state = self.limiter.get_state("groq")
        # Occupy the single slot
        await state.semaphore.acquire()

        async def waiting_coro():
            async with self.limiter.throttle("groq", timeout=10.0):
                pass

        task = asyncio.create_task(waiting_coro())
        await asyncio.sleep(0.01)
        self.assertEqual(state.queue_size, 1)

        # Cancel the waiting task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Queue size must be restored to 0
        self.assertEqual(state.queue_size, 0)
        state.semaphore.release()


from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web
from jarvis_server import handle_chat

class TestChatRateLimitHTTP(AioHTTPTestCase):
    async def get_application(self):
        app = web.Application()
        app.router.add_post("/api/chat", handle_chat)
        return app

    async def test_06_server_chat_returns_429_when_cooldown_active(self):
        """Server /api/chat returns HTTP 429 when provider is under rate limit cooldown."""
        SMART_PROVIDER_LIMITER.get_state("groq").cooldown_until = time.time() + 5.0
        try:
            resp = await self.client.post("/api/chat", json={
                "message": "Merhaba",
                "config": {"model": "llama-3.3-70b-versatile"}
            })
            self.assertEqual(resp.status, 429)
            self.assertIn("Retry-After", resp.headers)
            data = await resp.json()
            self.assertEqual(data.get("error_code"), "PROVIDER_RATE_LIMIT")
        finally:
            SMART_PROVIDER_LIMITER.get_state("groq").cooldown_until = 0.0


if __name__ == "__main__":
    unittest.main()
