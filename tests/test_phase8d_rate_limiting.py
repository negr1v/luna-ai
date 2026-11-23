"""
ACCIO LUNA V4.0 — Phase 8D Automated Test Suite
Focus: API Rate Limiting & Quota Protection Shield (/api/chat, /api/chat/stream, /api/tts_direct).
"""

import unittest
import asyncio
import os
import sys
import json
import time
from unittest.mock import patch, AsyncMock

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

import luna_server


class Phase8DRateLimitingTest(AioHTTPTestCase):

    async def get_application(self):
        app = web.Application()
        app.router.add_post("/api/chat", luna_server.handle_chat)
        app.router.add_post("/api/chat/stream", luna_server.handle_chat_stream)
        app.router.add_post("/api/tts_direct", luna_server.handle_tts_direct)
        app.router.add_get("/api/health/rate_limits", luna_server.handle_get_rate_limits)
        return app

    async def setUpAsync(self):
        await super().setUpAsync()
        await luna_server.CHAT_RATE_LIMITER.reset()
        await luna_server.TTS_RATE_LIMITER.reset()

    async def tearDownAsync(self):
        await luna_server.CHAT_RATE_LIMITER.reset()
        await luna_server.TTS_RATE_LIMITER.reset()
        await super().tearDownAsync()

    async def test_01_sliding_window_rate_limiter_allows_under_quota(self):
        """Test 01: Limiter grants requests while under quota threshold."""
        limiter = luna_server.SlidingWindowRateLimiter(max_requests=3, window_seconds=10.0)
        for _ in range(3):
            allowed, retry_after = await limiter.acquire()
            self.assertTrue(allowed)
            self.assertEqual(retry_after, 0.0)

    async def test_02_sliding_window_rate_limiter_blocks_and_computes_retry_after(self):
        """Test 02: Limiter blocks request exceeding quota and returns valid retry_after."""
        limiter = luna_server.SlidingWindowRateLimiter(max_requests=2, window_seconds=5.0)
        await limiter.acquire()
        await limiter.acquire()
        allowed, retry_after = await limiter.acquire()
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0.0)
        self.assertLessEqual(retry_after, 5.0)

    async def test_03_sliding_window_evicts_expired_timestamps(self):
        """Test 03: Timestamps older than window_seconds are evicted."""
        limiter = luna_server.SlidingWindowRateLimiter(max_requests=2, window_seconds=0.1)
        await limiter.acquire()
        await limiter.acquire()
        allowed_blocked, _ = await limiter.acquire()
        self.assertFalse(allowed_blocked)

        # Wait for window to slide
        await asyncio.sleep(0.15)
        allowed_fresh, _ = await limiter.acquire()
        self.assertTrue(allowed_fresh)

    async def test_04_chat_endpoint_rate_limiting_returns_429(self):
        """Test 04: /api/chat enforces rate limiting and returns HTTP 429."""
        # Lower quota temporarily for quick test
        orig_max = luna_server.CHAT_RATE_LIMITER.max_requests
        luna_server.CHAT_RATE_LIMITER.max_requests = 2
        try:
            with patch("luna_server.load_config", return_value={"groq_api_key": ""}):
                resp1 = await self.client.post("/api/chat", json={"message": "Selam"})
                self.assertEqual(resp1.status, 200)

                resp2 = await self.client.post("/api/chat", json={"message": "Selam 2"})
                self.assertEqual(resp2.status, 200)

                # Third request exceeds quota
                resp3 = await self.client.post("/api/chat", json={"message": "Selam 3"})
                self.assertEqual(resp3.status, 429)
                data = await resp3.json()
                self.assertEqual(data.get("status"), "error")
                self.assertEqual(data.get("error_code"), "RATE_LIMIT_EXCEEDED")
                self.assertIn("Retry-After", resp3.headers)
        finally:
            luna_server.CHAT_RATE_LIMITER.max_requests = orig_max

    async def test_05_chat_endpoint_includes_retry_after_header(self):
        """Test 05: Blocked chat response includes standard Retry-After header."""
        orig_max = luna_server.CHAT_RATE_LIMITER.max_requests
        luna_server.CHAT_RATE_LIMITER.max_requests = 1
        try:
            with patch("luna_server.load_config", return_value={"groq_api_key": ""}):
                await self.client.post("/api/chat", json={"message": "Test 1"})
                blocked = await self.client.post("/api/chat", json={"message": "Test 2"})
                self.assertEqual(blocked.status, 429)
                self.assertIn("Retry-After", blocked.headers)
                retry_val = int(blocked.headers["Retry-After"])
                self.assertGreaterEqual(retry_val, 1)
        finally:
            luna_server.CHAT_RATE_LIMITER.max_requests = orig_max

    async def test_06_tts_endpoint_rate_limiting_returns_429(self):
        """Test 06: /api/tts_direct enforces rate limiting and returns HTTP 429."""
        orig_max = luna_server.TTS_RATE_LIMITER.max_requests
        luna_server.TTS_RATE_LIMITER.max_requests = 2
        try:
            with patch("luna_server.generate_tts", new_callable=AsyncMock) as m_tts:
                m_tts.return_value = "b64_mock"
                r1 = await self.client.post("/api/tts_direct", json={"text": "Metin 1"})
                self.assertEqual(r1.status, 200)

                r2 = await self.client.post("/api/tts_direct", json={"text": "Metin 2"})
                self.assertEqual(r2.status, 200)

                r3 = await self.client.post("/api/tts_direct", json={"text": "Metin 3"})
                self.assertEqual(r3.status, 429)
                data = await r3.json()
                self.assertEqual(data.get("error_code"), "RATE_LIMIT_EXCEEDED")
        finally:
            luna_server.TTS_RATE_LIMITER.max_requests = orig_max

    async def test_07_chat_stream_endpoint_rate_limiting_returns_429(self):
        """Test 07: /api/chat/stream is protected by rate limiting."""
        orig_max = luna_server.CHAT_RATE_LIMITER.max_requests
        luna_server.CHAT_RATE_LIMITER.max_requests = 1
        try:
            # Consume 1 slot
            await luna_server.CHAT_RATE_LIMITER.acquire()
            resp = await self.client.post("/api/chat/stream", json={"message": "Stream test"})
            self.assertEqual(resp.status, 429)
            data = await resp.json()
            self.assertEqual(data.get("error_code"), "RATE_LIMIT_EXCEEDED")
        finally:
            luna_server.CHAT_RATE_LIMITER.max_requests = orig_max

    async def test_08_health_rate_limits_endpoint_returns_metrics(self):
        """Test 08: GET /api/health/rate_limits exposes real-time quota metrics."""
        await luna_server.CHAT_RATE_LIMITER.acquire()
        await luna_server.TTS_RATE_LIMITER.acquire()

        resp = await self.client.get("/api/health/rate_limits")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertGreaterEqual(data["chat"]["current_requests"], 1)
        self.assertGreaterEqual(data["tts"]["current_requests"], 1)
        self.assertEqual(data["chat"]["max_requests"], luna_server.CHAT_RATE_LIMITER.max_requests)

    async def test_09_rate_limiter_reset_clears_usage(self):
        """Test 09: reset() flushes the sliding window immediately."""
        await luna_server.CHAT_RATE_LIMITER.acquire()
        self.assertGreater(len(luna_server.CHAT_RATE_LIMITER.requests), 0)
        await luna_server.CHAT_RATE_LIMITER.reset()
        self.assertEqual(len(luna_server.CHAT_RATE_LIMITER.requests), 0)

    async def test_10_concurrent_requests_atomic_limiting(self):
        """Test 10: Concurrent asyncio.gather strictly limits total allowed requests to max_requests."""
        limiter = luna_server.SlidingWindowRateLimiter(max_requests=5, window_seconds=10.0)

        async def worker():
            allowed, _ = await limiter.acquire()
            return allowed

        results = await asyncio.gather(*(worker() for _ in range(15)))
        passed_count = sum(1 for r in results if r is True)
        blocked_count = sum(1 for r in results if r is False)

        self.assertEqual(passed_count, 5)
        self.assertEqual(blocked_count, 10)


if __name__ == "__main__":
    unittest.main()
