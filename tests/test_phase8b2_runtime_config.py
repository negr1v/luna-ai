"""
ACCIO JARVIS V4.0 — Phase 8B.2 Automated Test Suite
Focus: Runtime Config Sanitization, Custom Config Whitelisting,
       API Key Verification Endpoint (/api/config/test),
       TTS Graceful Edge Fallback, Frontend Test & Parameter Controls.
"""

import unittest
import asyncio
import os
import sys
import json
import tempfile
import shutil
from unittest.mock import patch, AsyncMock, MagicMock

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

import jarvis_server


class Phase8B2RuntimeConfigTest(AioHTTPTestCase):

    async def get_application(self):
        app = web.Application()
        app.router.add_get("/api/config", jarvis_server.handle_get_config)
        app.router.add_post("/api/config", jarvis_server.handle_save_config)
        app.router.add_post("/api/config/test", jarvis_server.handle_test_config)
        app.router.add_post("/api/chat", jarvis_server.handle_chat)
        return app

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="phase8b2_test_")
        self.test_config_file = os.path.join(self.test_dir, "test_config.json")

        self.initial_config = {
            "groq_api_key": "gsk_legit_server_groq_key_99999",
            "elevenlabs_api_key": "",
            "elevenlabs_voice_id": "21m00Tcm4TlvDq8ikWAM",
            "openai_api_key": "",
            "openai_voice": "nova",
            "tts_engine": "edge_tts",
            "edge_voice": "tr-TR-EmelNeural",
            "edge_rate": "+5%",
            "edge_pitch": "+3Hz",
            "memory_learning_enabled": False
        }

        with open(self.test_config_file, "w", encoding="utf-8") as f:
            json.dump(self.initial_config, f, indent=2)

        self.orig_config_file = jarvis_server.CONFIG_FILE
        jarvis_server.CONFIG_FILE = self.test_config_file

        super().setUp()

    def tearDown(self):
        super().tearDown()
        jarvis_server.CONFIG_FILE = self.orig_config_file
        if hasattr(self, "test_dir") and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_sanitize_runtime_custom_config_strips_secrets_and_unknowns(self):
        """Test 1: sanitize_runtime_custom_config strictly strips secret keys and unknown fields."""
        malicious_input = {
            "groq_api_key": "gsk_attacker_key",
            "elevenlabs_api_key": "xi_attacker_key",
            "openai_api_key": "sk_attacker_key",
            "arbitrary_backdoor": "enabled",
            "tts_engine": "openai",
            "edge_rate": "+15%",
            "edge_pitch": "+5Hz",
            "memory_learning_enabled": True
        }
        sanitized = jarvis_server.sanitize_runtime_custom_config(malicious_input)

        # Secrets and unknown fields must be completely absent
        self.assertNotIn("groq_api_key", sanitized)
        self.assertNotIn("elevenlabs_api_key", sanitized)
        self.assertNotIn("openai_api_key", sanitized)
        self.assertNotIn("arbitrary_backdoor", sanitized)

        # Allowed safe runtime overrides must be preserved
        self.assertEqual(sanitized.get("tts_engine"), "openai")
        self.assertEqual(sanitized.get("edge_rate"), "+15%")
        self.assertEqual(sanitized.get("edge_pitch"), "+5Hz")
        self.assertTrue(sanitized.get("memory_learning_enabled"))
        print("  [Phase 8B.2 Test 1 PASSED] Runtime custom config strictly sanitizes secrets & unknown keys.")

    def test_02_sanitize_runtime_custom_config_validates_enums_and_types(self):
        """Test 2: sanitize_runtime_custom_config validates enum and type constraints."""
        invalid_input = {
            "tts_engine": "invalid_engine_name",
            "edge_rate": 12345,  # wrong type
            "memory_learning_enabled": "not_a_bool"  # wrong type
        }
        sanitized = jarvis_server.sanitize_runtime_custom_config(invalid_input)
        self.assertEqual(sanitized, {})

        # Valid input
        valid_input = {
            "tts_engine": "elevenlabs",
            "edge_rate": "+10%"
        }
        sanitized_valid = jarvis_server.sanitize_runtime_custom_config(valid_input)
        self.assertEqual(sanitized_valid, {"tts_engine": "elevenlabs", "edge_rate": "+10%"})
        print("  [Phase 8B.2 Test 2 PASSED] Runtime enum and type constraints strictly enforced.")

    async def test_03_test_config_endpoint_rejects_invalid_payloads_and_providers(self):
        """Test 3: POST /api/config/test rejects malformed JSON and unknown providers with HTTP 400."""
        # Non-JSON
        resp1 = await self.client.post("/api/config/test", data="invalid json")
        self.assertEqual(resp1.status, 400)

        # Non-dict
        resp2 = await self.client.post("/api/config/test", json=["not", "a", "dict"])
        self.assertEqual(resp2.status, 400)

        # Unknown provider
        resp3 = await self.client.post("/api/config/test", json={"provider": "unknown_provider"})
        self.assertEqual(resp3.status, 400)
        data3 = await resp3.json()
        self.assertIn("Geçersiz sağlayıcı", data3.get("message", ""))
        print("  [Phase 8B.2 Test 3 PASSED] POST /api/config/test rejects invalid payloads and unknown providers.")

    async def test_04_test_config_endpoint_missing_api_key_returns_400(self):
        """Test 4: POST /api/config/test returns 400 when tested key is missing from payload and storage."""
        resp = await self.client.post("/api/config/test", json={"provider": "elevenlabs"})
        self.assertEqual(resp.status, 400)
        data = await resp.json()
        self.assertEqual(data.get("status"), "error")
        self.assertIn("sağlanmadı veya sistemde kayıtlı değil", data.get("message", ""))
        print("  [Phase 8B.2 Test 4 PASSED] Missing API key returns explanatory HTTP 400.")

    async def test_05_test_config_endpoint_mock_success(self):
        """Test 5: POST /api/config/test returns 200 on successful provider ping without leaking key."""
        mock_resp = AsyncMock()
        mock_resp.status = 200

        mock_session_inst = MagicMock()
        mock_session_inst.get.return_value.__aenter__.return_value = mock_resp
        mock_session_inst.__aenter__.return_value = mock_session_inst

        with patch("aiohttp.ClientSession", return_value=mock_session_inst):
            resp = await self.client.post("/api/config/test", json={
                "provider": "groq",
                "api_key": "gsk_mock_valid_key_secret_123"
            })
            self.assertEqual(resp.status, 200)
            data = await resp.json()
            text = await resp.text()

            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("provider"), "groq")
            self.assertIn("doğrulandı", data.get("message", ""))

            # Key must NEVER leak into response text
            self.assertNotIn("gsk_mock_valid_key_secret_123", text)
        print("  [Phase 8B.2 Test 5 PASSED] Mock provider success returns HTTP 200 with zero key leakage.")

    async def test_06_test_config_endpoint_mock_unauthorized(self):
        """Test 6: POST /api/config/test returns HTTP 401 when provider returns 401 Unauthorized."""
        mock_resp = AsyncMock()
        mock_resp.status = 401

        mock_session_inst = MagicMock()
        mock_session_inst.get.return_value.__aenter__.return_value = mock_resp
        mock_session_inst.__aenter__.return_value = mock_session_inst

        with patch("aiohttp.ClientSession", return_value=mock_session_inst):
            resp = await self.client.post("/api/config/test", json={
                "provider": "openai",
                "api_key": "sk_mock_invalid_key_secret_456"
            })
            self.assertEqual(resp.status, 401)
            data = await resp.json()
            text = await resp.text()

            self.assertEqual(data.get("status"), "error")
            self.assertIn("geçersiz veya yetkisiz", data.get("message", ""))
            self.assertNotIn("sk_mock_invalid_key_secret_456", text)
        print("  [Phase 8B.2 Test 6 PASSED] Mock provider unauthorized returns HTTP 401 safely.")

    async def test_07_test_config_endpoint_mock_timeout(self):
        """Test 7: POST /api/config/test returns HTTP 504 on provider timeout."""
        mock_session_inst = MagicMock()
        mock_session_inst.get.side_effect = asyncio.TimeoutError("Connection timed out")
        mock_session_inst.__aenter__.return_value = mock_session_inst

        with patch("aiohttp.ClientSession", return_value=mock_session_inst):
            resp = await self.client.post("/api/config/test", json={
                "provider": "groq",
                "api_key": "gsk_mock_timeout_key"
            })
            self.assertEqual(resp.status, 504)
            data = await resp.json()
            self.assertEqual(data.get("status"), "error")
            self.assertIn("zaman aşımına uğradı", data.get("message", ""))
        print("  [Phase 8B.2 Test 7 PASSED] Provider timeout gracefully caught and returns HTTP 504.")

    async def test_08_tts_graceful_fallback_when_api_key_missing(self):
        """Test 8: generate_tts safely falls back to Edge-TTS when ElevenLabs key is empty."""
        test_cfg = {
            "tts_engine": "elevenlabs",
            "elevenlabs_api_key": "",
            "edge_voice": "tr-TR-EmelNeural"
        }
        with patch("jarvis_server._generate_edge_tts", new=AsyncMock(return_value="edge_mock_audio_b64")):
            audio = await jarvis_server.generate_tts("Selam Negr1", test_cfg)
            self.assertEqual(audio, "edge_mock_audio_b64")
        print("  [Phase 8B.2 Test 8 PASSED] Missing ElevenLabs key automatically triggers Edge-TTS fallback.")

    async def test_09_tts_graceful_fallback_when_provider_fails(self):
        """Test 9: generate_tts safely falls back to Edge-TTS when ElevenLabs HTTP fails."""
        test_cfg = {
            "tts_engine": "elevenlabs",
            "elevenlabs_api_key": "xi_mock_key",
            "edge_voice": "tr-TR-EmelNeural"
        }
        with patch("jarvis_server._generate_elevenlabs_tts", new=AsyncMock(return_value=None)), \
             patch("jarvis_server._generate_edge_tts", new=AsyncMock(return_value="edge_mock_audio_fallback")):
            audio = await jarvis_server.generate_tts("Selam Negr1", test_cfg)
            self.assertEqual(audio, "edge_mock_audio_fallback")
        print("  [Phase 8B.2 Test 9 PASSED] ElevenLabs failure automatically triggers Edge-TTS fallback.")

    def test_10_frontend_settings_and_test_controls_verified(self):
        """Test 10: Verify index.html contains Rate, Pitch, and Provider Test buttons & handlers."""
        index_path = os.path.join(jarvis_server.BASE_DIR, "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()

        # Input elements
        self.assertIn('id="edgeRateInput"', html)
        self.assertIn('id="edgePitchInput"', html)
        self.assertIn('id="testGroqKeyBtn"', html)
        self.assertIn('id="testElevenlabsKeyBtn"', html)
        self.assertIn('id="testOpenaiKeyBtn"', html)

        # JS logic
        self.assertIn("testApiKey('groq'", html)
        self.assertIn("testApiKey('elevenlabs'", html)
        self.assertIn("testApiKey('openai'", html)
        self.assertIn("payload.edge_rate = edgeRateInput.value.trim();", html)
        self.assertIn("payload.edge_pitch = edgePitchInput.value.trim();", html)
        self.assertIn("fetch('/api/config/test'", html)
        print("  [Phase 8B.2 Test 10 PASSED] Frontend DOM controls and verification bindings verified.")


if __name__ == "__main__":
    unittest.main()
