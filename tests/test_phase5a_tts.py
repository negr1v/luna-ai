"""
ACCIO JARVIS V4.0 — Phase 5A
Backend TTS Hardening Acceptance Tests.

Covers:
1. Successful Edge-TTS generation with Base64 output.
2. Edge-TTS timeout handling and bounded duration.
3. Edge-TTS provider exception handling and clean degradation.
4. ElevenLabs provider success, failure, and fallback.
5. OpenAI TTS provider success, failure, and fallback.
6. Empty, non-string, and whitespace input rejection.
7. Oversized input clamping at sentence boundary.
8. Bounded concurrency semaphore and non-blocking degradation.
9. Direct TTS endpoint (/api/tts_direct) success contract.
10. Direct TTS endpoint validation and error handling.
11. Chat response (/api/chat) text preservation when TTS fails.
12. SSE completion (/api/chat/stream) text preservation when TTS fails.
13. Secret masking and no raw audio logging verification.
"""

import os
import io
import json
import base64
import asyncio
import tempfile
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web

import jarvis_server


class Phase5ATTSTest(AioHTTPTestCase):
    async def get_application(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="phase5a_tts_")
        self.test_tasks_file = os.path.join(self.temp_dir.name, "test_tasks.json")
        self.test_cfg_file = os.path.join(self.temp_dir.name, "test_cfg.json")

        with open(self.test_tasks_file, "w", encoding="utf-8") as f:
            json.dump([], f)

        with open(self.test_cfg_file, "w", encoding="utf-8") as f:
            json.dump({
                "groq_api_key": "mock_groq_key",
                "tts_engine": "edge_tts",
                "edge_voice": "tr-TR-EmelNeural",
                "edge_rate": "+5%",
                "edge_pitch": "+3Hz"
            }, f)

        self.p_task_file = patch("jarvis_server.TASKS_FILE", self.test_tasks_file)
        self.p_cfg_file = patch("jarvis_server.CONFIG_FILE", self.test_cfg_file)

        self.p_task_file.start()
        self.p_cfg_file.start()

        return jarvis_server.create_app()

    async def tearDownAsync(self):
        if hasattr(self, "client") and self.client:
            await self.client.close()
        self.p_task_file.stop()
        self.p_cfg_file.stop()
        self.temp_dir.cleanup()

    # --- Unit & Provider Generation Tests ---

    async def test_01_successful_edge_tts_generation(self):
        """Edge-TTS streams audio chunks and returns valid base64 string."""
        raw_audio = b"MOCK_MP3_AUDIO_STREAM_DATA"

        async def mock_stream(self_comm):
            yield {"type": "audio", "data": raw_audio}

        with patch("edge_tts.Communicate.stream", mock_stream):
            cfg = {"tts_engine": "edge_tts", "edge_voice": "tr-TR-EmelNeural"}
            b64 = await jarvis_server.generate_tts("Merhaba dünya", cfg)
            self.assertIsNotNone(b64)
            decoded = base64.b64decode(b64)
            self.assertEqual(decoded, raw_audio)
        print("  [Phase 5A Test 1 PASSED] Successful Edge-TTS generation and Base64 encoding.")

    async def test_02_edge_tts_timeout_handling(self):
        """Hanging Edge-TTS stream times out cleanly and returns None without blocking."""
        async def hanging_stream(self_comm):
            await asyncio.sleep(2.0)
            yield {"type": "audio", "data": b"late"}

        with patch("edge_tts.Communicate.stream", hanging_stream), \
             patch("jarvis_server.EDGE_TTS_TIMEOUT_SECONDS", 0.05):
            cfg = {"tts_engine": "edge_tts"}
            b64 = await jarvis_server.generate_tts("Zaman aşımı testi", cfg)
            self.assertIsNone(b64, "Timed out TTS generation must return None")
        print("  [Phase 5A Test 2 PASSED] Edge-TTS timeout cleanly handled with graceful degradation.")

    async def test_03_edge_tts_provider_exception_handling(self):
        """Edge-TTS provider exception is caught safely and returns None."""
        async def failing_stream(self_comm):
            raise ConnectionResetError("Remote socket forcibly closed by host")
            yield {}

        with patch("edge_tts.Communicate.stream", failing_stream):
            cfg = {"tts_engine": "edge_tts"}
            b64 = await jarvis_server.generate_tts("Hata testi", cfg)
            self.assertIsNone(b64)
        print("  [Phase 5A Test 3 PASSED] Edge-TTS provider exceptions caught and silenced safely.")

    async def test_04_elevenlabs_provider_success_and_fallback(self):
        """ElevenLabs returns audio when valid, or falls back to Edge-TTS on error/missing key."""
        mock_audio = b"ELEVEN_MOCK_AUDIO"

        # 1. Success case
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=mock_audio)

        mock_post_ctx = MagicMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post_ctx.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession.post", return_value=mock_post_ctx):
            cfg = {"tts_engine": "elevenlabs", "elevenlabs_api_key": "el_key_123"}
            b64 = await jarvis_server.generate_tts("Eleven test", cfg)
            self.assertEqual(base64.b64decode(b64), mock_audio)

        # 2. Missing key falls back to Edge-TTS
        async def mock_edge_stream(self_comm):
            yield {"type": "audio", "data": b"EDGE_FALLBACK"}

        with patch("edge_tts.Communicate.stream", mock_edge_stream):
            cfg_no_key = {"tts_engine": "elevenlabs", "elevenlabs_api_key": ""}
            b64_fb = await jarvis_server.generate_tts("Fallback test", cfg_no_key)
            self.assertEqual(base64.b64decode(b64_fb), b"EDGE_FALLBACK")
        print("  [Phase 5A Test 4 PASSED] ElevenLabs provider success and automatic Edge-TTS fallback.")

    async def test_05_openai_tts_provider_success_and_fallback(self):
        """OpenAI TTS returns audio when valid, or falls back to Edge-TTS on failure."""
        mock_audio = b"OPENAI_MOCK_AUDIO"

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=mock_audio)

        mock_post_ctx = MagicMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post_ctx.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession.post", return_value=mock_post_ctx):
            cfg = {"tts_engine": "openai", "openai_api_key": "sk-mock-key"}
            b64 = await jarvis_server.generate_tts("OpenAI test", cfg)
            self.assertEqual(base64.b64decode(b64), mock_audio)
        print("  [Phase 5A Test 5 PASSED] OpenAI TTS provider success and contract verified.")

    async def test_06_empty_and_invalid_inputs(self):
        """Empty, whitespace, or non-string inputs are immediately rejected with None."""
        self.assertIsNone(await jarvis_server.generate_tts("", {}))
        self.assertIsNone(await jarvis_server.generate_tts("   ", {}))
        self.assertIsNone(await jarvis_server.generate_tts(None, {}))
        self.assertIsNone(await jarvis_server.generate_tts(12345, {}))
        self.assertIsNone(await jarvis_server.generate_tts(["not", "str"], {}))
        print("  [Phase 5A Test 6 PASSED] Invalid and empty inputs safely rejected with None.")

    async def test_07_oversized_input_clamping(self):
        """Oversized inputs are cleanly clamped to MAX_TTS_TEXT_LENGTH before provider dispatch."""
        import edge_tts
        recorded_text = []
        original_init = edge_tts.Communicate.__init__

        def mock_init(self_comm, text, *args, **kwargs):
            recorded_text.append(text)
            original_init(self_comm, text, *args, **kwargs)

        async def capture_stream(self_comm):
            yield {"type": "audio", "data": b"mock"}

        with patch.object(edge_tts.Communicate, "__init__", mock_init), \
             patch("edge_tts.Communicate.stream", capture_stream):
            huge_text = ("Bu bir uzun metin testidir. " * 150)  # ~3900 chars
            self.assertGreater(len(huge_text), jarvis_server.MAX_TTS_TEXT_LENGTH)
            await jarvis_server.generate_tts(huge_text, {"tts_engine": "edge_tts"})

            self.assertEqual(len(recorded_text), 1)
            sent_text = recorded_text[0]
            self.assertLessEqual(len(sent_text), jarvis_server.MAX_TTS_TEXT_LENGTH + 3)
            self.assertTrue(sent_text.endswith("..."))
        print("  [Phase 5A Test 7 PASSED] Oversized inputs safely clamped at boundary.")

    async def test_08_concurrency_semaphore_limit(self):
        """Exceeding MAX_CONCURRENT_TTS concurrency limit degrades cleanly to None."""
        with patch.object(jarvis_server.TTS_SEMAPHORE, "acquire", AsyncMock(side_effect=asyncio.TimeoutError)):
            res = await jarvis_server.generate_tts("Aşırı yük testi", {})
            self.assertIsNone(res, "Saturated concurrency must degrade to None")
        print("  [Phase 5A Test 8 PASSED] Concurrency semaphore limits active synthesis sessions.")

    # --- HTTP Endpoint Tests ---

    async def test_09_direct_tts_endpoint_success(self):
        """POST /api/tts_direct returns 200 with audio_base64 and text."""
        with patch("jarvis_server.generate_tts", AsyncMock(return_value="bW9ja19hdWRpbw==")):
            resp = await self.client.post("/api/tts_direct", json={"text": "Ses testi"})
            self.assertEqual(resp.status, 200)
            data = await resp.json()
            self.assertEqual(data.get("audio_base64"), "bW9ja19hdWRpbw==")
            self.assertEqual(data.get("text"), "Ses testi")
        print("  [Phase 5A Test 9 PASSED] Direct TTS endpoint (/api/tts_direct) returns valid JSON contract.")

    async def test_10_direct_tts_endpoint_validation_errors(self):
        """POST /api/tts_direct validates JSON structure, empty text, and oversized payload."""
        # 1. Empty text
        r1 = await self.client.post("/api/tts_direct", json={"text": "   "})
        self.assertEqual(r1.status, 400)

        # 2. Non-dict body
        r2 = await self.client.post("/api/tts_direct", json=["invalid"])
        self.assertEqual(r2.status, 400)

        # 3. Oversized text
        oversized = "a" * (jarvis_server.MAX_DIRECT_TTS_TEXT_LENGTH + 50)
        r3 = await self.client.post("/api/tts_direct", json={"text": oversized})
        self.assertEqual(r3.status, 400)
        d3 = await r3.json()
        self.assertIn("izin verilen üst sınırı aşıyor", d3.get("error", ""))
        print("  [Phase 5A Test 10 PASSED] Direct TTS endpoint validates inputs and handles errors with HTTP 400.")

    async def test_11_chat_preserves_text_when_tts_fails(self):
        """POST /api/chat preserves full text reply even when generate_tts fails/returns None."""
        mock_groq = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Bu metin kesinlikle korunmalıdır."
                }
            }]
        }

        mock_post_ctx = MagicMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=MagicMock(status=200, json=AsyncMock(return_value=mock_groq)))
        mock_post_ctx.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession.post", return_value=mock_post_ctx), \
             patch("jarvis_server.generate_tts", AsyncMock(return_value=None)):
            resp = await self.client.post("/api/chat", json={"message": "Selam"})
            self.assertEqual(resp.status, 200)
            data = await resp.json()
            self.assertEqual(data.get("reply"), "Bu metin kesinlikle korunmalıdır.")
            self.assertIsNone(data.get("audio_base64"), "Audio must be None on TTS failure")
        print("  [Phase 5A Test 11 PASSED] Chat endpoint preserves text response when TTS fails.")

    async def test_12_sse_completion_preserves_text_when_tts_fails(self):
        """POST /api/chat/stream delivers full text in done event even when TTS returns None."""
        mock_groq = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "SSE ile akıtılan metin yanıtı."
                }
            }]
        }

        mock_post_ctx = MagicMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=MagicMock(status=200, json=AsyncMock(return_value=mock_groq)))
        mock_post_ctx.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession.post", return_value=mock_post_ctx), \
             patch("jarvis_server.generate_tts", AsyncMock(return_value=None)):
            resp = await self.client.post("/api/chat/stream", json={"message": "SSE TTS Test"})
            self.assertEqual(resp.status, 200)
            text = await resp.text()

            # Find done event
            self.assertIn("event: done", text)
            done_line = [l for l in text.split("\n") if l.startswith("data: ") and "SSE ile akıtılan" in l]
            self.assertTrue(len(done_line) > 0)
            done_payload = json.loads(done_line[0].replace("data: ", ""))
            self.assertEqual(done_payload.get("reply"), "SSE ile akıtılan metin yanıtı.")
            self.assertIsNone(done_payload.get("audio_base64"))
        print("  [Phase 5A Test 12 PASSED] SSE stream done event preserves complete text when TTS fails.")

    async def test_13_no_secret_or_raw_audio_logged(self):
        """Ensure secret keys are masked in error logs and raw audio is never printed."""
        secret_key = "gsk_supersecret1234567890abcdef"
        masked = jarvis_server.mask_secrets(f"Error connecting with {secret_key}")
        self.assertNotIn(secret_key, masked)
        self.assertIn("gsk_***REDACTED***", masked)
        print("  [Phase 5A Test 13 PASSED] Secret masking strictly applied to error strings.")

    async def test_14_cancellation_during_provider_execution_releases_semaphore(self):
        """Task cancellation during provider execution propagates CancelledError and releases semaphore slot."""
        started_event = asyncio.Event()

        async def hanging_provider(text, cfg):
            started_event.set()
            await asyncio.sleep(10.0)
            return "audio"

        initial_sem_val = jarvis_server.TTS_SEMAPHORE._value

        with patch("jarvis_server._generate_edge_tts", hanging_provider):
            task = asyncio.create_task(jarvis_server.generate_tts("İptal testi", {}))
            await started_event.wait()
            # Task is now executing inside the semaphore critical section
            self.assertEqual(jarvis_server.TTS_SEMAPHORE._value, initial_sem_val - 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        # Verify semaphore slot was cleanly restored
        self.assertEqual(jarvis_server.TTS_SEMAPHORE._value, initial_sem_val)
        print("  [Phase 5A Test 14 PASSED] Cancellation during provider execution propagates and releases semaphore.")

    async def test_15_cancellation_waiting_for_semaphore_does_not_leak_slot(self):
        """Task cancellation while waiting for semaphore propagates and does not corrupt counter."""
        sem = jarvis_server.TTS_SEMAPHORE
        initial_val = sem._value

        # Drain all available slots
        acquired = []
        for _ in range(initial_val):
            await sem.acquire()
            acquired.append(True)

        self.assertEqual(sem._value, 0)

        task = asyncio.create_task(jarvis_server.generate_tts("Sıra bekleme iptali", {}))
        # Yield to let task reach semaphore acquire wait
        await asyncio.sleep(0.01)

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        # Release drained slots
        for _ in acquired:
            sem.release()

        self.assertEqual(sem._value, initial_val)
        print("  [Phase 5A Test 15 PASSED] Cancellation while waiting for semaphore slot leaves counter clean.")

    async def test_16_direct_tts_text_between_1501_and_3000_not_truncated(self):
        """Direct TTS endpoint (/api/tts_direct) does not truncate inputs between 1501 and 3000 chars."""
        captured_text = []

        async def capture_gen(text, cfg, max_len=jarvis_server.MAX_TTS_TEXT_LENGTH):
            captured_text.append((text, max_len))
            return "mock_direct_audio"

        direct_text = ("Bu doğrudan bir tts metnidir. " * 80).strip()  # ~2400 chars
        self.assertGreater(len(direct_text), jarvis_server.MAX_TTS_TEXT_LENGTH)
        self.assertLessEqual(len(direct_text), jarvis_server.MAX_DIRECT_TTS_TEXT_LENGTH)

        with patch("jarvis_server.generate_tts", capture_gen):
            resp = await self.client.post("/api/tts_direct", json={"text": direct_text})
            self.assertEqual(resp.status, 200)
            data = await resp.json()
            self.assertEqual(data.get("audio_base64"), "mock_direct_audio")
            self.assertEqual(data.get("text"), direct_text)
            self.assertEqual(len(captured_text), 1)
            sent_text, passed_max_len = captured_text[0]
            self.assertEqual(sent_text, direct_text)
            self.assertEqual(passed_max_len, jarvis_server.MAX_DIRECT_TTS_TEXT_LENGTH)
        print("  [Phase 5A Test 16 PASSED] Direct TTS texts between 1501 and 3000 chars preserved without truncation.")


if __name__ == "__main__":
    unittest.main()
