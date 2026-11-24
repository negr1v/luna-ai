"""Focused tests for Phase 17 paid TTS authorization and DPAPI secret storage."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
import jarvis_server as server
from jarvis_secret_store import is_protected_secret, protect_secret, unprotect_secret


class TestPaidTtsAuthorization(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        server.PAID_MODEL_AUTHORIZATIONS.clear()

    async def test_paid_tts_without_authorization_never_calls_provider(self):
        config = {"tts_engine": "openai", "openai_api_key": "temporary-test-key"}
        with patch.object(server, "_generate_openai_tts", new=AsyncMock(return_value="paid-audio")) as paid_tts, \
             patch.object(server, "_generate_edge_tts", new=AsyncMock(return_value="fallback-audio")):
            audio, status = await server.generate_tts("Merhaba", config, return_status=True)

        self.assertEqual(audio, "fallback-audio")
        self.assertEqual(status["error_code"], "PAID_TTS_CONFIRMATION_REQUIRED")
        paid_tts.assert_not_awaited()

    async def test_paid_tts_token_is_provider_action_bound_and_single_use(self):
        token = server.create_paid_tts_authorization("elevenlabs")
        wrong_provider, _ = server.validate_and_consume_paid_tts_authorization(token, "openai")
        self.assertFalse(wrong_provider)

        valid, _ = server.validate_and_consume_paid_tts_authorization(token, "elevenlabs")
        self.assertTrue(valid)
        reused, _ = server.validate_and_consume_paid_tts_authorization(token, "elevenlabs")
        self.assertFalse(reused)

        openai_token = server.create_paid_tts_authorization("openai")
        config = {"tts_engine": "openai", "openai_api_key": "temporary-test-key"}
        with patch.object(server, "_generate_openai_tts", new=AsyncMock(return_value="paid-audio")) as paid_tts, \
             patch.object(server, "_generate_edge_tts", new=AsyncMock(return_value="fallback-audio")):
            audio = await server.generate_tts("Merhaba", config, paid_auth_token=openai_token)
            self.assertEqual(audio, "paid-audio")
            paid_tts.assert_awaited_once()
            replay_audio, replay_status = await server.generate_tts(
                "Merhaba",
                config,
                paid_auth_token=openai_token,
                return_status=True,
            )
            self.assertEqual(replay_audio, "fallback-audio")
            self.assertEqual(replay_status["error_code"], "PAID_TTS_CONFIRMATION_REQUIRED")
            paid_tts.assert_awaited_once()

    async def test_free_tts_requires_no_paid_authorization(self):
        config = {"tts_engine": "edge_tts"}
        with patch.object(server, "_generate_edge_tts", new=AsyncMock(return_value="free-audio")) as edge_tts:
            audio, status = await server.generate_tts("Merhaba", config, return_status=True)

        self.assertEqual(audio, "free-audio")
        self.assertIsNone(status)
        edge_tts.assert_awaited_once()

    async def test_paid_tts_rejects_chat_and_expired_tokens_before_provider_call(self):
        config = {"tts_engine": "openai", "openai_api_key": "temporary-test-key"}
        chat_token = server.create_paid_model_authorization("z-ai/glm-5.3", "openrouter")
        expired_tts_token = server.create_paid_tts_authorization("openai")
        server.PAID_MODEL_AUTHORIZATIONS[expired_tts_token]["expires_at"] = 0

        with patch.object(server, "_generate_openai_tts", new=AsyncMock(return_value="paid-audio")) as paid_tts, \
             patch.object(server, "_generate_edge_tts", new=AsyncMock(return_value="fallback-audio")):
            chat_audio, chat_status = await server.generate_tts(
                "Merhaba", config, paid_auth_token=chat_token, return_status=True
            )
            expired_audio, expired_status = await server.generate_tts(
                "Merhaba", config, paid_auth_token=expired_tts_token, return_status=True
            )

        self.assertEqual(chat_audio, "fallback-audio")
        self.assertEqual(expired_audio, "fallback-audio")
        self.assertEqual(chat_status["error_code"], "PAID_TTS_CONFIRMATION_REQUIRED")
        self.assertEqual(expired_status["error_code"], "PAID_TTS_CONFIRMATION_REQUIRED")
        paid_tts.assert_not_awaited()


@unittest.skipUnless(os.name == "nt", "Windows DPAPI is available only on Windows")
class TestDpapiSecretStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "jarvis_config.json"
        self.original_config_file = server.CONFIG_FILE
        self.original_base_dir = server.BASE_DIR
        server.CONFIG_FILE = str(self.config_path)
        server.BASE_DIR = self.temp_dir.name

    def tearDown(self):
        server.CONFIG_FILE = self.original_config_file
        server.BASE_DIR = self.original_base_dir
        self.temp_dir.cleanup()

    def test_dpapi_round_trip(self):
        protected = protect_secret("temporary-secret-value")
        self.assertTrue(is_protected_secret(protected))
        self.assertEqual(unprotect_secret(protected), "temporary-secret-value")

    def test_plaintext_legacy_config_loads_and_next_save_protects_secrets(self):
        legacy_secret = "temporary-legacy-secret"
        self.config_path.write_text(
            json.dumps({"groq_api_key": legacy_secret, "tts_engine": "edge_tts"}),
            encoding="utf-8",
        )

        loaded = server.load_config()
        self.assertEqual(loaded["groq_api_key"], legacy_secret)
        server.save_config(loaded)

        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertTrue(is_protected_secret(saved["groq_api_key"]))
        self.assertNotIn(legacy_secret, self.config_path.read_text(encoding="utf-8"))
        backup = json.loads(Path(str(self.config_path) + ".bak").read_text(encoding="utf-8"))
        self.assertTrue(is_protected_secret(backup["groq_api_key"]))

    def test_undecryptable_secret_is_unavailable_and_paid_provider_is_not_called(self):
        self.config_path.write_text(
            json.dumps({
                "openai_api_key": "dpapi:v1:not-valid-base64",
                "tts_engine": "openai",
            }),
            encoding="utf-8",
        )

        loaded = server.load_config()
        self.assertEqual(loaded["openai_api_key"], "")
        self.assertIn("openai_api_key", loaded["_secret_storage_errors"])

        async def run_check():
            token = server.create_paid_tts_authorization("openai")
            with patch.object(server, "_generate_openai_tts", new=AsyncMock(return_value="paid-audio")) as paid_tts, \
                 patch.object(server, "_generate_edge_tts", new=AsyncMock(return_value=None)):
                _audio, status = await server.generate_tts(
                    "Merhaba",
                    loaded,
                    paid_auth_token=token,
                    return_status=True,
                )
            paid_tts.assert_not_awaited()
            self.assertEqual(status["error_code"], "TTS_SECRET_UNAVAILABLE")

        import asyncio
        asyncio.run(run_check())


class TestPaidTtsHttpEndpoint(AioHTTPTestCase):
    async def get_application(self):
        app = web.Application()
        app.router.add_post("/api/tts_direct", server.handle_tts_direct)
        return app

    @unittest_run_loop
    async def test_paid_tts_direct_endpoint_returns_clear_402_before_provider_call(self):
        config = {"tts_engine": "elevenlabs", "elevenlabs_api_key": "temporary-test-key"}
        with patch.object(server, "load_config", return_value=config), \
             patch.object(server, "_generate_elevenlabs_tts", new=AsyncMock(return_value="paid-audio")) as paid_tts:
            response = await self.client.post("/api/tts_direct", json={"text": "Merhaba"})
            payload = await response.json()

        self.assertEqual(response.status, 402)
        self.assertEqual(payload["error_code"], "PAID_TTS_CONFIRMATION_REQUIRED")
        self.assertIn("onay", payload["message"].lower())
        paid_tts.assert_not_awaited()

    @unittest_run_loop
    async def test_paid_tts_direct_endpoint_consumes_token_once(self):
        config = {"tts_engine": "elevenlabs", "elevenlabs_api_key": "temporary-test-key"}
        token = server.create_paid_tts_authorization("elevenlabs")
        request_body = {"text": "Merhaba", "paid_tts_auth_token": token}
        with patch.object(server, "load_config", return_value=config), \
             patch.object(server, "_generate_elevenlabs_tts", new=AsyncMock(return_value="paid-audio")) as paid_tts:
            authorized = await self.client.post("/api/tts_direct", json=request_body)
            authorized_payload = await authorized.json()
            replay = await self.client.post("/api/tts_direct", json=request_body)
            replay_payload = await replay.json()

        self.assertEqual(authorized.status, 200)
        self.assertEqual(authorized_payload["audio_base64"], "paid-audio")
        paid_tts.assert_awaited_once()
        self.assertEqual(replay.status, 402)
        self.assertEqual(replay_payload["error_code"], "PAID_TTS_CONFIRMATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
