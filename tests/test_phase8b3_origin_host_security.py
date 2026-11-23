"""
ACCIO JARVIS V4.0 — Phase 8B.3 Automated Test Suite
Focus: Origin & Host Validation, CSRF Defense, CORS Preflight, Loopback/LAN Parsing & Secret Isolation.
"""

import unittest
import asyncio
import os
import sys
import json
import tempfile
import shutil
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

import jarvis_server


class Phase8B3OriginHostSecurityTest(AioHTTPTestCase):

    async def get_application(self):
        # Build app using the official create_app() to test full middleware stack
        return jarvis_server.create_app()

    def setUp(self):
        super().setUp()
        self.test_dir = tempfile.mkdtemp(prefix="phase8b3_test_")
        self.test_config_file = os.path.join(self.test_dir, "jarvis_config.json")
        self.test_memory_file = os.path.join(self.test_dir, "jarvis_memory.json")
        self.test_tasks_file = os.path.join(self.test_dir, "jarvis_tasks.json")
        self.test_tg_file = os.path.join(self.test_dir, "jarvis_telegram.json")

        self.initial_config = {
            "groq_api_key": "gsk_secret_production_key_xyz",
            "telegram_bot_token": "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_12345678",
            "allowed_hosts": ["custom-jarvis.internal"],
            "trusted_proxy_enabled": False
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

    def tearDown(self):
        jarvis_server.CONFIG_FILE = self.orig_cfg_file
        jarvis_server.MEMORY_FILE = self.orig_mem_file
        jarvis_server.TASKS_FILE = self.orig_tasks_file
        jarvis_server.TELEGRAM_FILE = self.orig_tg_file

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)
        super().tearDown()

    async def tearDownAsync(self):
        await jarvis_server.stop_telegram_worker()
        await super().tearDownAsync()

    # =========================================================================
    # 1. VALID HOST AND ORIGIN
    # =========================================================================

    async def test_01_valid_host_and_origin_allowed(self):
        """Test 01: Valid Host (localhost:7860) and Origin (http://localhost:7860) are allowed with CORS headers."""
        headers = {
            "Host": "localhost:7860",
            "Origin": "http://localhost:7860"
        }
        resp = await self.client.get("/api/config", headers=headers)
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "http://localhost:7860")
        self.assertEqual(resp.headers.get("Access-Control-Allow-Credentials"), "true")

    async def test_02_fake_origin_rejected_on_state_change(self):
        """Test 02: State-changing POST with fake Origin (http://evil.com) returns 403 Forbidden."""
        headers = {
            "Host": "localhost:7860",
            "Origin": "http://evil.com"
        }
        resp = await self.client.post("/api/telegram/messages", headers=headers, json={"text": "Attack payload"})
        self.assertEqual(resp.status, 403)
        data = await resp.json()
        self.assertEqual(data.get("error"), "FORBIDDEN_ORIGIN")
        self.assertNotIn("Access-Control-Allow-Origin", resp.headers)

    async def test_03_null_origin_rejected_on_state_change(self):
        """Test 03: Sandboxed iframe CSRF vector (Origin: null) returns 403 Forbidden on state-changing requests."""
        headers = {
            "Host": "127.0.0.1:7860",
            "Origin": "null"
        }
        resp = await self.client.post("/api/config", headers=headers, json={"tts_engine": "edge_tts"})
        self.assertEqual(resp.status, 403)
        data = await resp.json()
        self.assertEqual(data.get("error"), "FORBIDDEN_ORIGIN")

    # =========================================================================
    # 2. HOST VALIDATION & MANIPULATION DEFENSE
    # =========================================================================

    async def test_04_invalid_untrusted_host_rejected(self):
        """Test 04: Untrusted Host (attacker.com:7860) is rejected with 400 Bad Request."""
        headers = {
            "Host": "attacker.com:7860"
        }
        resp = await self.client.get("/api/config", headers=headers)
        self.assertEqual(resp.status, 400)
        data = await resp.json()
        self.assertEqual(data.get("error"), "INVALID_HOST")

    async def test_05_host_header_manipulation_injection_rejected(self):
        """Test 05: Host header containing CRLF, null bytes or whitespace is safely rejected with 400."""
        # Test CRLF
        h1, _ = jarvis_server.parse_host_header("localhost:7860\r\nX-Injected: 1")
        self.assertEqual(h1, "")

        # Test Null Byte
        h2, _ = jarvis_server.parse_host_header("localhost:7860\0attacker.com")
        self.assertEqual(h2, "")

        # Test Space
        h3, _ = jarvis_server.parse_host_header("localhost :7860")
        self.assertEqual(h3, "")

    async def test_06_malformed_authority_and_invalid_port_rejected(self):
        """Test 06: Malformed ports (negative, non-numeric, >65535) and bad authorities are rejected."""
        h1, p1 = jarvis_server.parse_host_header("localhost:99999")
        self.assertEqual(h1, "")
        self.assertIsNone(p1)

        h2, p2 = jarvis_server.parse_host_header("localhost:abc")
        self.assertEqual(h2, "")

        h3, p3 = jarvis_server.parse_host_header("bad::host:7860")
        self.assertEqual(h3, "")

        headers = {"Host": "localhost:99999"}
        resp = await self.client.get("/api/config", headers=headers)
        self.assertEqual(resp.status, 400)

    # =========================================================================
    # 3. LEGITIMATE REQUESTS & REFERER FALLBACK
    # =========================================================================

    async def test_07_legitimate_requests_without_origin_allowed(self):
        """Test 07: Legitimate desktop clients, curl and test suites without Origin are allowed."""
        headers = {
            "Host": "127.0.0.1:7860"
        }
        resp = await self.client.post("/api/telegram/messages", headers=headers, json={"text": "Local CLI message"})
        self.assertEqual(resp.status, 200)

    async def test_08_referer_fallback_valid_allowed(self):
        """Test 08: Missing Origin with valid Referer (http://127.0.0.1:7860/dashboard) is allowed."""
        headers = {
            "Host": "127.0.0.1:7860",
            "Referer": "http://127.0.0.1:7860/dashboard"
        }
        resp = await self.client.post("/api/telegram/messages", headers=headers, json={"text": "Dashboard action"})
        self.assertEqual(resp.status, 200)

    async def test_09_referer_fallback_untrusted_rejected(self):
        """Test 09: Missing Origin with malicious Referer (http://evil.com/exploit.html) returns 403 Forbidden."""
        headers = {
            "Host": "127.0.0.1:7860",
            "Referer": "http://evil.com/exploit.html"
        }
        resp = await self.client.post("/api/telegram/messages", headers=headers, json={"text": "CSRF attack"})
        self.assertEqual(resp.status, 403)
        data = await resp.json()
        self.assertEqual(data.get("error"), "FORBIDDEN_REFERER")

    # =========================================================================
    # 4. CORS PREFLIGHT (OPTIONS)
    # =========================================================================

    async def test_10_cors_preflight_options_valid_origin(self):
        """Test 10: Preflight OPTIONS request with valid Origin returns 204 with CORS allow headers."""
        headers = {
            "Host": "localhost:7860",
            "Origin": "http://localhost:7860",
            "Access-Control-Request-Method": "POST"
        }
        resp = await self.client.options("/api/chat", headers=headers)
        self.assertEqual(resp.status, 204)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "http://localhost:7860")
        self.assertIn("POST", resp.headers.get("Access-Control-Allow-Methods", ""))

    async def test_11_cors_preflight_options_untrusted_origin_rejected(self):
        """Test 11: Preflight OPTIONS request with untrusted Origin returns 403 without CORS headers."""
        headers = {
            "Host": "localhost:7860",
            "Origin": "http://malicious-site.com"
        }
        resp = await self.client.options("/api/chat", headers=headers)
        self.assertEqual(resp.status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", resp.headers)

    # =========================================================================
    # 5. IPV4, IPV6, AND PRIVATE LAN RECOGNITION
    # =========================================================================

    async def test_12_ipv4_and_ipv6_loopback_hosts_accepted(self):
        """Test 12: Loopback IPv4 (127.0.0.1), loopback IPv6 ([::1]), and localhost are recognized."""
        for host in ["127.0.0.1:7860", "localhost:7860", "[::1]:7860"]:
            headers = {"Host": host}
            resp = await self.client.get("/api/config", headers=headers)
            self.assertEqual(resp.status, 200, f"Host {host} should be accepted")

    async def test_13_private_lan_hosts_accepted(self):
        """Test 13: Private RFC1918 IPv4 ranges (10.x, 172.16-31.x, 192.168.x) are accepted for local LAN."""
        self.assertTrue(jarvis_server.is_allowed_hostname("192.168.1.105"))
        self.assertTrue(jarvis_server.is_allowed_hostname("10.0.0.15"))
        self.assertTrue(jarvis_server.is_allowed_hostname("172.20.10.2"))
        # Public IP should NOT be allowed by default
        self.assertFalse(jarvis_server.is_allowed_hostname("8.8.8.8"))
        self.assertFalse(jarvis_server.is_allowed_hostname("1.1.1.1"))

    # =========================================================================
    # 6. PROXY FORWARDING & CONFIG ALLOWLIST
    # =========================================================================

    async def test_14_untrusted_forwarded_host_ignored_by_default(self):
        """Test 14: X-Forwarded-Host is strictly ignored when trusted_proxy_enabled is False."""
        headers = {
            "Host": "localhost:7860",
            "X-Forwarded-Host": "evil-hacker.com"
        }
        # Since trusted_proxy_enabled is False, Host is evaluated as localhost:7860 -> 200 OK
        resp = await self.client.get("/api/config", headers=headers)
        self.assertEqual(resp.status, 200)

    async def test_15_configured_allowed_hosts_accepted(self):
        """Test 15: Custom domain declared in allowed_hosts configuration is accepted."""
        headers = {
            "Host": "custom-jarvis.internal:7860"
        }
        resp = await self.client.get("/api/config", headers=headers)
        self.assertEqual(resp.status, 200)

    # =========================================================================
    # 7. SECURITY ISOLATION & NO SECRET LEAKAGE
    # =========================================================================

    async def test_16_rejection_responses_do_not_leak_secrets_or_internals(self):
        """Test 16: Security rejections return generic error bodies with zero internal key/path leaks."""
        headers = {"Host": "unauthorized.attacker.org"}
        resp = await self.client.get("/api/config", headers=headers)
        self.assertEqual(resp.status, 400)
        body = await resp.text()

        # Verify no token or secret leakage
        self.assertNotIn("gsk_", body)
        self.assertNotIn("123456789", body)
        self.assertNotIn("pre-install", body)
        self.assertNotIn("Traceback", body)


if __name__ == "__main__":
    unittest.main()
