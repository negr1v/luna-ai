"""
ACCIO JARVIS V4.0 — Phase 8B.4 Automated Test Suite
Focus: Comprehensive Secret Masking & Information Disclosure Audit
"""

import unittest
import json
import os
import sys
import base64
import tempfile
import shutil
from unittest.mock import patch, AsyncMock

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

import jarvis_server


_TEST_SECRET_PREFIX = "test-only:v1:"
_REAL_IS_PROTECTED_SECRET = jarvis_server.is_protected_secret
_REAL_UNPROTECT_SECRET = jarvis_server.unprotect_secret


def _test_is_protected_secret(value):
    return (
        isinstance(value, str) and value.startswith(_TEST_SECRET_PREFIX)
    ) or _REAL_IS_PROTECTED_SECRET(value)


def _test_protect_secret(value):
    if not value or _test_is_protected_secret(value):
        return value
    return _TEST_SECRET_PREFIX + base64.b64encode(value.encode("utf-8")).decode("ascii")


def _test_unprotect_secret(value):
    if isinstance(value, str) and value.startswith(_TEST_SECRET_PREFIX):
        encoded = value[len(_TEST_SECRET_PREFIX):]
        return base64.b64decode(encoded, validate=True).decode("utf-8")
    return _REAL_UNPROTECT_SECRET(value)


class Phase8B4SecretMaskingTest(AioHTTPTestCase):

    async def get_application(self):
        return jarvis_server.create_app()

    def setUp(self):
        super().setUp()
        self.test_dir = tempfile.mkdtemp(prefix="phase8b4_test_")
        self.test_config_file = os.path.join(self.test_dir, "jarvis_config.json")
        self.test_memory_file = os.path.join(self.test_dir, "jarvis_memory.json")
        self.test_tasks_file = os.path.join(self.test_dir, "jarvis_tasks.json")
        self.test_tg_file = os.path.join(self.test_dir, "jarvis_telegram.json")

        self.initial_config = {
            "groq_api_key": "gsk_prod_secret_key_1234567890",
            "telegram_bot_token": "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_12345678",
            "openai_api_key": "sk-proj-supersecretopenaitoken1234567890",
            "elevenlabs_api_key": "eleven_secret_token_12345678",
            "custom_api_key": "custom_secret_key_99999",
            "edge_voice": "tr-TR-EmelNeural",
            "tts_engine": "edge_tts"
        }

        with open(self.test_config_file, "w", encoding="utf-8") as f:
            json.dump(self.initial_config, f)
        with open(self.test_memory_file, "w", encoding="utf-8") as f:
            json.dump({"schema_version": 2, "user_profile": {}}, f)
        with open(self.test_tasks_file, "w", encoding="utf-8") as f:
            json.dump({"tasks": []}, f)
        with open(self.test_tg_file, "w", encoding="utf-8") as f:
            json.dump([], f)

        self.orig_cfg_file = jarvis_server.CONFIG_FILE
        self.orig_mem_file = jarvis_server.MEMORY_FILE
        self.orig_tasks_file = jarvis_server.TASKS_FILE
        self.orig_tg_file = jarvis_server.TELEGRAM_FILE

        jarvis_server.CONFIG_FILE = self.test_config_file
        jarvis_server.MEMORY_FILE = self.test_memory_file
        jarvis_server.TASKS_FILE = self.test_tasks_file
        jarvis_server.TELEGRAM_FILE = self.test_tg_file

        self.secret_storage_patches = [
            patch("jarvis_server.protect_secret", _test_protect_secret),
            patch("jarvis_server.unprotect_secret", _test_unprotect_secret),
            patch("jarvis_server.is_protected_secret", _test_is_protected_secret),
        ]
        for secret_storage_patch in self.secret_storage_patches:
            secret_storage_patch.start()

    def tearDown(self):
        jarvis_server.CONFIG_FILE = self.orig_cfg_file
        jarvis_server.MEMORY_FILE = self.orig_mem_file
        jarvis_server.TASKS_FILE = self.orig_tasks_file
        jarvis_server.TELEGRAM_FILE = self.orig_tg_file
        for secret_storage_patch in self.secret_storage_patches:
            secret_storage_patch.stop()

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)
        super().tearDown()

    async def tearDownAsync(self):
        await jarvis_server.stop_telegram_worker()
        await super().tearDownAsync()

    # =========================================================================
    # 1. SECRET MASKING PATTERNS & REDACTION
    # =========================================================================

    def test_01_telegram_token_redaction(self):
        """Test 01: Telegram bot token regex pattern is cleanly masked."""
        raw = "Failed to connect to Telegram via 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_12345678"
        masked = jarvis_server.mask_secrets(raw)
        self.assertNotIn("123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_12345678", masked)
        self.assertIn("***TELEGRAM_TOKEN_REDACTED***", masked)

    def test_02_groq_and_openai_key_redaction(self):
        """Test 02: Groq (gsk_...) and OpenAI (sk-...) API keys are masked."""
        raw_groq = "Authorization failed for gsk_secretkey1234567890abcdef"
        masked_groq = jarvis_server.mask_secrets(raw_groq)
        self.assertNotIn("gsk_secretkey1234567890abcdef", masked_groq)
        self.assertIn("gsk_***REDACTED***", masked_groq)

        raw_openai = "Connecting with sk-proj-12345678901234567890abcdef"
        masked_openai = jarvis_server.mask_secrets(raw_openai)
        self.assertNotIn("sk-proj-12345678901234567890abcdef", masked_openai)
        self.assertIn("sk-***REDACTED***", masked_openai)

    def test_03_bearer_and_authorization_header_redaction(self):
        """Test 03: Bearer tokens and Basic auth headers in logs/errors are masked."""
        raw_bearer = "Upstream response error: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        masked_bearer = jarvis_server.mask_secrets(raw_bearer)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", masked_bearer)
        self.assertIn("Bearer ***TOKEN_REDACTED***", masked_bearer)

        raw_basic = "Proxy Auth: Basic dXNlcm5hbWU6cGFzc3dvcmQxMjM="
        masked_basic = jarvis_server.mask_secrets(raw_basic)
        self.assertNotIn("dXNlcm5hbWU6cGFzc3dvcmQxMjM=", masked_basic)
        self.assertIn("Basic ***AUTH_REDACTED***", masked_basic)

    def test_04_json_and_key_value_secret_masking(self):
        """Test 04: Key-value secret patterns in JSON strings are masked."""
        raw_json = '{"api_key": "supersecretkey999", "password": "mypassword123", "status": "ok"}'
        masked_json = jarvis_server.mask_secrets(raw_json)
        self.assertNotIn("supersecretkey999", masked_json)
        self.assertNotIn("mypassword123", masked_json)
        self.assertIn('"status": "ok"', masked_json)

    def test_05_nested_dict_and_list_masking(self):
        """Test 05: mask_dict_secrets recursively redacts sensitive fields in nested structures."""
        data = {
            "status": "success",
            "auth": {
                "api_key": "secret_key_111",
                "nested_token": "token_val_222",
                "public_name": "Luna"
            },
            "credentials": [
                {"bot_token": "token_item_333"},
                {"name": "neg1"}
            ]
        }
        masked = jarvis_server.mask_dict_secrets(data)
        self.assertEqual(masked["auth"]["api_key"], "***REDACTED***")
        self.assertEqual(masked["auth"]["public_name"], "Luna")
        self.assertEqual(masked["credentials"][0]["bot_token"], "***REDACTED***")
        self.assertEqual(masked["credentials"][1]["name"], "neg1")

    def test_06_legitimate_user_text_not_mutated(self):
        """Test 06: Legitimate user communication text is not corrupted by redaction."""
        normal_texts = [
            "Bugün YKS 2027 matematik parabol ve trigonometri çalıştım.",
            "ASUS Prime B650M-R ve Ryzen 5 7500F sistem toplamayı düşünüyorum.",
            "Akakçe fiyat takibinde son durum nedir?",
            "Telegram üzerinden mesajlaşma köprüsü aktif mi?"
        ]
        for text in normal_texts:
            self.assertEqual(jarvis_server.mask_secrets(text), text)

    # =========================================================================
    # 2. CONFIG GET/POST & PRESERVATION SAFETY
    # =========================================================================

    async def test_07_api_config_get_never_exposes_secrets(self):
        """Test 07: GET /api/config returns blank strings for secrets and boolean indicators."""
        resp = await self.client.get("/api/config")
        self.assertEqual(resp.status, 200)
        data = await resp.json()

        # Secrets must be empty strings
        self.assertEqual(data.get("groq_api_key"), "")
        self.assertEqual(data.get("telegram_bot_token"), "")
        self.assertEqual(data.get("openai_api_key"), "")
        self.assertEqual(data.get("elevenlabs_api_key"), "")

        # Configured flags must be True
        self.assertTrue(data.get("groq_api_key_configured"))
        self.assertTrue(data.get("telegram_bot_token_configured"))
        self.assertTrue(data.get("openai_api_key_configured"))

    async def test_08_masked_placeholders_preserve_existing_secrets(self):
        """Test 08: POST /api/config with masked placeholder (***) does NOT overwrite secret."""
        # Send update with masked placeholders and a harmless change
        payload = {
            "groq_api_key": "gsk_***REDACTED***",
            "telegram_bot_token": "***TELEGRAM_TOKEN_REDACTED***",
            "edge_voice": "tr-TR-AhmetNeural"
        }
        resp = await self.client.post("/api/config", json=payload)
        self.assertEqual(resp.status, 200)

        # Inspect disk config: original keys must be preserved!
        with open(self.test_config_file, "r", encoding="utf-8") as f:
            saved_cfg = json.load(f)

        groq_raw = saved_cfg.get("groq_api_key")
        tg_raw = saved_cfg.get("telegram_bot_token")
        self.assertTrue(groq_raw.startswith(_TEST_SECRET_PREFIX))
        self.assertNotIn("gsk_prod_secret_key_1234567890", json.dumps(saved_cfg))
        groq_val = jarvis_server.unprotect_secret(groq_raw) if hasattr(jarvis_server, "unprotect_secret") else groq_raw
        tg_val = jarvis_server.unprotect_secret(tg_raw) if hasattr(jarvis_server, "unprotect_secret") else tg_raw
        self.assertEqual(groq_val, "gsk_prod_secret_key_1234567890")
        self.assertEqual(tg_val, "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_12345678")
        self.assertEqual(saved_cfg.get("edge_voice"), "tr-TR-AhmetNeural")

    async def test_09_unknown_or_dynamic_secret_keys_detected(self):
        """Test 09: Dynamic keys matching is_secret_key are identified and protected."""
        self.assertTrue(jarvis_server.is_secret_key("new_custom_api_key"))
        self.assertTrue(jarvis_server.is_secret_key("third_party_secret"))
        self.assertTrue(jarvis_server.is_secret_key("oauth_access_token"))
        self.assertTrue(jarvis_server.is_secret_key("db_password"))
        self.assertFalse(jarvis_server.is_secret_key("tts_engine"))
        self.assertFalse(jarvis_server.is_secret_key("groq_model"))

    # =========================================================================
    # 3. ERROR & LOGGING ISOLATION
    # =========================================================================

    async def test_10_endpoint_errors_never_leak_secrets(self):
        """Test 10: Server error responses never expose tokens, secrets or file traces."""
        # Send bad JSON or trigger validation error
        resp = await self.client.post("/api/config", json={"tts_engine": "invalid_engine"})
        self.assertEqual(resp.status, 400)
        body = await resp.text()

        self.assertNotIn("gsk_", body)
        self.assertNotIn("123456789:", body)
        self.assertNotIn("secret", body.lower())
        self.assertNotIn("Traceback", body)


if __name__ == "__main__":
    unittest.main()
