"""
ACCIO JARVIS V4.0 — Phase 8B.1 Automated Test Suite
Focus: Config API Security, Secret Protection, Input Validation, Atomic Persistence & Locking.
"""

import unittest
import asyncio
import os
import sys
import json
import base64
import tempfile
import shutil
from unittest.mock import patch

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


class Phase8B1ConfigSecurityTest(AioHTTPTestCase):

    async def get_application(self):
        # Create an app pointing to our isolated configuration file
        app = web.Application()
        app.router.add_get("/api/config", jarvis_server.handle_get_config)
        app.router.add_post("/api/config", jarvis_server.handle_save_config)
        return app

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="phase8b1_test_")
        self.test_config_file = os.path.join(self.test_dir, "test_config.json")
        self.test_api_txt = os.path.join(self.test_dir, "api_key.txt")

        # Mock initial config
        self.initial_config = {
            "groq_api_key": "gsk_mock_groq_secret_key_12345",
            "elevenlabs_api_key": "xi_mock_eleven_secret_key_67890",
            "elevenlabs_voice_id": "21m00Tcm4TlvDq8ikWAM",
            "openai_api_key": "sk-mock_openai_secret_key_abcdef",
            "openai_voice": "nova",
            "tts_engine": "edge_tts",
            "edge_voice": "tr-TR-EmelNeural",
            "edge_rate": "+5%",
            "edge_pitch": "+3Hz",
            "memory_learning_enabled": False
        }

        with open(self.test_config_file, "w", encoding="utf-8") as f:
            json.dump(self.initial_config, f, indent=2)

        # Redirect server paths
        self.orig_config_file = jarvis_server.CONFIG_FILE
        self.orig_base_dir = jarvis_server.BASE_DIR
        jarvis_server.CONFIG_FILE = self.test_config_file

        self.secret_storage_patches = [
            patch("jarvis_server.protect_secret", _test_protect_secret),
            patch("jarvis_server.unprotect_secret", _test_unprotect_secret),
            patch("jarvis_server.is_protected_secret", _test_is_protected_secret),
        ]
        for secret_storage_patch in self.secret_storage_patches:
            secret_storage_patch.start()

        super().setUp()

    def tearDown(self):
        super().tearDown()
        jarvis_server.CONFIG_FILE = self.orig_config_file
        for secret_storage_patch in self.secret_storage_patches:
            secret_storage_patch.stop()
        if hasattr(self, "test_dir") and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_01_get_config_never_exposes_raw_api_keys(self):
        """Test 1: GET /api/config never exposes raw Groq, OpenAI, or ElevenLabs keys."""
        resp = await self.client.get("/api/config")
        self.assertEqual(resp.status, 200)
        text = await resp.text()
        data = await resp.json()

        # Raw secrets must never appear anywhere in the response text
        self.assertNotIn("gsk_mock_groq_secret_key_12345", text)
        self.assertNotIn("xi_mock_eleven_secret_key_67890", text)
        self.assertNotIn("sk-mock_openai_secret_key_abcdef", text)

        # Secret fields must be empty strings
        self.assertEqual(data.get("groq_api_key"), "")
        self.assertEqual(data.get("elevenlabs_api_key"), "")
        self.assertEqual(data.get("openai_api_key"), "")

        # Safe non-secret fields remain visible
        self.assertEqual(data.get("tts_engine"), "edge_tts")
        self.assertEqual(data.get("openai_voice"), "nova")
        print("  [Phase 8B.1 Test 1 PASSED] GET /api/config strictly redacts raw secrets.")

    async def test_02_configured_status_indicators_work(self):
        """Test 2: Boolean indicators accurately reflect whether keys are configured."""
        resp = await self.client.get("/api/config")
        self.assertEqual(resp.status, 200)
        data = await resp.json()

        self.assertTrue(data.get("groq_api_key_configured"))
        self.assertTrue(data.get("elevenlabs_api_key_configured"))
        self.assertTrue(data.get("openai_api_key_configured"))

        # Test with empty keys
        empty_cfg = {
            "groq_api_key": "",
            "elevenlabs_api_key": "",
            "openai_api_key": "",
            "tts_engine": "edge_tts"
        }
        with open(self.test_config_file, "w", encoding="utf-8") as f:
            json.dump(empty_cfg, f)

        resp2 = await self.client.get("/api/config")
        data2 = await resp2.json()
        self.assertFalse(data2.get("groq_api_key_configured"))
        self.assertFalse(data2.get("elevenlabs_api_key_configured"))
        self.assertFalse(data2.get("openai_api_key_configured"))
        print("  [Phase 8B.1 Test 2 PASSED] Configured status indicators verified.")

    async def test_03_unknown_config_keys_are_rejected(self):
        """Test 3: Reject unknown keys with HTTP 400 and preserve disk config."""
        payload = {
            "tts_engine": "edge_tts",
            "injected_unknown_key": "malicious_payload",
            "another_bad_field": 123
        }
        resp = await self.client.post("/api/config", json=payload)
        self.assertEqual(resp.status, 400)
        data = await resp.json()
        self.assertIn("Unknown configuration key", data.get("message", ""))

        # Verify disk file untouched
        with open(self.test_config_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        self.assertNotIn("injected_unknown_key", disk_data)
        print("  [Phase 8B.1 Test 3 PASSED] Unknown config keys rejected with HTTP 400.")

    async def test_04_malformed_json_returns_http_400(self):
        """Test 4: Malformed JSON payload returns HTTP 400 Bad Request."""
        resp = await self.client.post(
            "/api/config",
            data=b'{"tts_engine": "edge_tts", broken_json',
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(resp.status, 400)
        data = await resp.json()
        self.assertEqual(data.get("status"), "error")
        self.assertIn("Invalid JSON payload", data.get("message", ""))
        print("  [Phase 8B.1 Test 4 PASSED] Malformed JSON returns HTTP 400.")

    async def test_05_non_object_json_is_rejected(self):
        """Test 5: Non-object JSON (array, string, number) returns HTTP 400."""
        resp1 = await self.client.post("/api/config", json=["item1", "item2"])
        self.assertEqual(resp1.status, 400)

        resp2 = await self.client.post("/api/config", json="just a string")
        self.assertEqual(resp2.status, 400)

        resp3 = await self.client.post("/api/config", json=12345)
        self.assertEqual(resp3.status, 400)
        print("  [Phase 8B.1 Test 5 PASSED] Non-object JSON payloads rejected.")

    async def test_06_invalid_field_types_and_excessive_lengths_are_rejected(self):
        """Test 6: Invalid field types and lengths exceed schema boundaries."""
        # 1. Invalid boolean type
        resp = await self.client.post("/api/config", json={"memory_learning_enabled": "true_str"})
        self.assertEqual(resp.status, 400)
        self.assertIn("must be a boolean", (await resp.json()).get("message", ""))

        # 2. Invalid TTS engine enum
        resp = await self.client.post("/api/config", json={"tts_engine": "unknown_voice_engine"})
        self.assertEqual(resp.status, 400)
        self.assertIn("Invalid value for 'tts_engine'", (await resp.json()).get("message", ""))

        # 3. Excessive string length
        resp = await self.client.post("/api/config", json={"edge_rate": "x" * 500})
        self.assertEqual(resp.status, 400)
        self.assertIn("exceeds maximum length", (await resp.json()).get("message", ""))

        # 4. Invalid list structure
        resp = await self.client.post("/api/config", json={"groq_fallback_models": "not_a_list"})
        self.assertEqual(resp.status, 400)
        self.assertIn("must be a list", (await resp.json()).get("message", ""))
        print("  [Phase 8B.1 Test 6 PASSED] Invalid types and lengths rejected.")

    async def test_07_omitted_api_keys_preserve_existing_values(self):
        """Test 7: Omitted API keys preserve existing secrets on the server."""
        payload = {
            "tts_engine": "elevenlabs",
            "memory_learning_enabled": True
        }
        resp = await self.client.post("/api/config", json=payload)
        self.assertEqual(resp.status, 200)

        with open(self.test_config_file, "r", encoding="utf-8") as f:
            saved = json.load(f)

        # Non-secret fields updated
        self.assertEqual(saved.get("tts_engine"), "elevenlabs")
        self.assertTrue(saved.get("memory_learning_enabled"))

        # Secret fields strictly preserved
        self.assertEqual(_test_unprotect_secret(saved.get("groq_api_key")), "gsk_mock_groq_secret_key_12345")
        self.assertEqual(_test_unprotect_secret(saved.get("elevenlabs_api_key")), "xi_mock_eleven_secret_key_67890")
        self.assertEqual(_test_unprotect_secret(saved.get("openai_api_key")), "sk-mock_openai_secret_key_abcdef")
        print("  [Phase 8B.1 Test 7 PASSED] Omitted API keys preserve existing values.")

    async def test_08_masked_placeholders_cannot_overwrite_real_keys(self):
        """Test 8: Masked placeholders, empty strings, and redact tokens never overwrite real keys."""
        placeholders = [
            "gsk_***REDACTED***",
            "***",
            "●●●●●●●● (Kayıtlı anahtar korunuyor)",
            "",
            "   "
        ]
        for ph in placeholders:
            resp = await self.client.post("/api/config", json={"groq_api_key": ph})
            self.assertEqual(resp.status, 200)

            with open(self.test_config_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(_test_unprotect_secret(saved.get("groq_api_key")), "gsk_mock_groq_secret_key_12345")
        print("  [Phase 8B.1 Test 8 PASSED] Masked placeholders cannot overwrite real keys.")

    async def test_09_explicit_key_replacement_works(self):
        """Test 9: Explicit new key updates the target while leaving others intact."""
        new_key = "gsk_new_verified_secret_key_99999"
        resp = await self.client.post("/api/config", json={"groq_api_key": new_key})
        self.assertEqual(resp.status, 200)

        with open(self.test_config_file, "r", encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(_test_unprotect_secret(saved.get("groq_api_key")), new_key)
        self.assertEqual(_test_unprotect_secret(saved.get("elevenlabs_api_key")), "xi_mock_eleven_secret_key_67890")
        self.assertEqual(_test_unprotect_secret(saved.get("openai_api_key")), "sk-mock_openai_secret_key_abcdef")
        print("  [Phase 8B.1 Test 9 PASSED] Explicit key replacement works safely.")

    async def test_10_atomic_writes_preserve_valid_configuration(self):
        """Test 10: Atomic write protects against zero-byte files and fail-closed on corrupt config."""
        # 1. Simulate write failure during atomic replace
        real_replace = os.replace

        def fail_primary_replace(src, dst):
            if os.path.abspath(dst) == os.path.abspath(self.test_config_file):
                raise IOError("Simulated disk write failure")
            return real_replace(src, dst)

        with patch("jarvis_server.os.replace", side_effect=fail_primary_replace):
            with self.assertRaises(IOError):
                jarvis_server.save_config({"tts_engine": "edge_tts"})

        # Original config file must be intact and non-empty
        self.assertTrue(os.path.exists(self.test_config_file))
        self.assertGreater(os.path.getsize(self.test_config_file), 0)

        # 2. Corrupt configuration triggers fail-closed error without silent overwrite
        backup_file = f"{self.test_config_file}.bak"
        if os.path.exists(backup_file):
            os.remove(backup_file)
        with open(self.test_config_file, "w", encoding="utf-8") as f:
            f.write("{corrupt: json content[}")

        resp = await self.client.post("/api/config", json={"tts_engine": "openai"})
        self.assertEqual(resp.status, 503)
        data = await resp.json()
        self.assertEqual(data.get("error"), "CORRUPT_CONFIG_FILE")

        # Must not have overwritten corrupted file with defaults
        with open(self.test_config_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "{corrupt: json content[}")
        print("  [Phase 8B.1 Test 10 PASSED] Atomic write and fail-closed corrupt handling verified.")

    async def test_11_concurrent_config_updates_do_not_lose_unrelated_fields(self):
        """Test 11: Concurrent config updates with asyncio.gather preserve all distinct fields."""
        tasks = [
            self.client.post("/api/config", json={"elevenlabs_voice_id": "voice_concurrency_test"}),
            self.client.post("/api/config", json={"openai_voice": "alloy"}),
            self.client.post("/api/config", json={"tts_engine": "openai"}),
            self.client.post("/api/config", json={"edge_rate": "+10%"}),
            self.client.post("/api/config", json={"memory_learning_enabled": True})
        ]
        responses = await asyncio.gather(*tasks)
        for r in responses:
            self.assertEqual(r.status, 200)

        with open(self.test_config_file, "r", encoding="utf-8") as f:
            saved = json.load(f)

        # Verify all concurrent updates survived
        self.assertEqual(saved.get("elevenlabs_voice_id"), "voice_concurrency_test")
        self.assertEqual(saved.get("openai_voice"), "alloy")
        self.assertEqual(saved.get("tts_engine"), "openai")
        self.assertEqual(saved.get("edge_rate"), "+10%")
        self.assertTrue(saved.get("memory_learning_enabled"))
        self.assertEqual(_test_unprotect_secret(saved.get("groq_api_key")), "gsk_mock_groq_secret_key_12345")
        print("  [Phase 8B.1 Test 11 PASSED] Concurrent updates preserved under CONFIG_ASYNC_LOCK.")

    def test_12_existing_frontend_settings_behavior_remains_functional(self):
        """Test 12: Verify index.html settings markup, safe placeholders, and empty payload logic."""
        index_path = os.path.join(jarvis_server.BASE_DIR, "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()

        # Check DOM elements
        self.assertIn('id="settingsModal"', html)
        self.assertIn('id="ttsEngineSelect"', html)
        self.assertIn('id="elevenlabsGroup"', html)
        self.assertIn('id="openaiGroup"', html)
        self.assertIn('id="groqKey"', html)
        self.assertIn('id="elevenlabsKey"', html)
        self.assertIn('id="openaiKey"', html)
        self.assertIn('id="saveSettingsBtn"', html)

        # Status badge spans
        self.assertIn('id="groqKeyStatus"', html)
        self.assertIn('id="elevenlabsKeyStatus"', html)
        self.assertIn('id="openaiKeyStatus"', html)

        # Check JavaScript submission logic does not send empty keys
        self.assertIn("const gv = groqKey.value.trim();", html)
        self.assertIn("if (gv) payload.groq_api_key = gv;", html)
        self.assertIn("const ev = elevenlabsKey.value.trim();", html)
        self.assertIn("if (ev) payload.elevenlabs_api_key = ev;", html)
        self.assertIn("const ov = openaiKey.value.trim();", html)
        self.assertIn("if (ov) payload.openai_api_key = ov;", html)

        # Check password fields are cleared on load
        self.assertIn("groqKey.value = '';", html)
        self.assertIn("elevenlabsKey.value = '';", html)
        self.assertIn("openaiKey.value = '';", html)
        print("  [Phase 8B.1 Test 12 PASSED] Frontend settings security & functionality verified.")


if __name__ == "__main__":
    unittest.main()
