"""
ZERO CORE OS (LUNA-AI) V15 - PHASE 15A.1 TEST SUITE
Test: Hard Paid API Protection, Authorization Tokens, Single-use & Expiration Guarantees
"""

import sys
import os
import time
import asyncio
import unittest
from unittest.mock import patch, MagicMock

# Proje dizinini ekle
PROJECT_DIR = r"C:\Users\negr1\Projeler\LUNA-AI"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from luna_server import (
    get_model_cost_category,
    create_paid_model_authorization,
    validate_and_consume_paid_authorization,
    PAID_MODEL_AUTHORIZATIONS,
    PAID_AUTH_TTL_SECONDS,
    handle_chat,
    handle_request_paid_auth,
    AI_MODEL_CATALOG
)
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

class TestPhase15A1PaidProtection(AioHTTPTestCase):

    async def get_application(self):
        app = web.Application()
        app.router.add_post("/api/chat", handle_chat)
        app.router.add_post("/api/models/paid_auth/request", handle_request_paid_auth)
        return app

    def setUp(self):
        super().setUp()
        PAID_MODEL_AUTHORIZATIONS.clear()

    def test_01_cost_category_detection(self):
        """Ücretli, ücretsiz ve bilinmeyen modellerin doğru sınıflandırıldığını doğrula."""
        cat_free, _ = get_model_cost_category("nvidia/nemotron-3.5-lightning:free")
        self.assertEqual(cat_free, "free")

        cat_paid, _ = get_model_cost_category("z-ai/glm-5.3")
        self.assertEqual(cat_paid, "paid")

        cat_paid2, _ = get_model_cost_category("openai/gpt-4o")
        self.assertEqual(cat_paid2, "paid")

        cat_unknown, _ = get_model_cost_category("non_existent/model-x")
        self.assertEqual(cat_unknown, "unknown")

    def test_02_token_lifecycle_and_validation(self):
        """Onay belirtecinin üretimi, doğrulanması ve tek kullanımlık olduğunu doğrula."""
        token = create_paid_model_authorization("z-ai/glm-5.3", "openrouter")
        self.assertTrue(token.startswith("pauth_"))

        # 1. Başarılı doğrulama ve tüketim
        ok, msg = validate_and_consume_paid_authorization(token, "z-ai/glm-5.3", "openrouter")
        self.assertTrue(ok)

        # 2. Tekrar kullanım engeli (Single-use / Replay attack)
        ok_reuse, msg_reuse = validate_and_consume_paid_authorization(token, "z-ai/glm-5.3", "openrouter")
        self.assertFalse(ok_reuse)

    def test_03_token_mismatch_rejection(self):
        """Model veya sağlayıcı uyuşmazlığında belirtecin reddedildiğini doğrula."""
        token = create_paid_model_authorization("z-ai/glm-5.3", "openrouter")

        # Farklı model
        ok_wrong_model, _ = validate_and_consume_paid_authorization(token, "openai/gpt-4o", "openrouter")
        self.assertFalse(ok_wrong_model)

        # Farklı sağlayıcı
        ok_wrong_prov, _ = validate_and_consume_paid_authorization(token, "z-ai/glm-5.3", "groq")
        self.assertFalse(ok_wrong_prov)

    def test_04_token_expiration(self):
        """Süresi dolan belirtecin reddedildiğini doğrula."""
        token = create_paid_model_authorization("z-ai/glm-5.3", "openrouter")
        
        # Süreyi yapay olarak geçmişe çek
        PAID_MODEL_AUTHORIZATIONS[token]["expires_at"] = time.time() - 10

        ok_expired, msg = validate_and_consume_paid_authorization(token, "z-ai/glm-5.3", "openrouter")
        self.assertFalse(ok_expired)
        self.assertIn("zaman aşımı", msg)

    @unittest_run_loop
    async def test_05_chat_paid_model_without_approval_blocked(self):
        """Ücretli model onaysız çağrıldığında HTTP 402 ve confirmation_required dönmeli."""
        payload = {
            "message": "Merhaba",
            "config": {
                "model": "z-ai/glm-5.3"
            }
        }
        resp = await self.client.post("/api/chat", json=payload)
        self.assertEqual(resp.status, 402)
        
        data = await resp.json()
        self.assertEqual(data.get("status"), "confirmation_required")
        self.assertEqual(data.get("error_code"), "PAID_MODEL_CONFIRMATION_REQUIRED")
        self.assertTrue("auth_token" in data)

    @unittest_run_loop
    async def test_06_chat_unknown_model_blocked(self):
        """Bilinmeyen maliyetli model çağrıldığında kilitlenmeli (HTTP 402)."""
        payload = {
            "message": "Test mesajı",
            "config": {
                "model": "mysterious/unknown-llm"
            }
        }
        resp = await self.client.post("/api/chat", json=payload)
        self.assertEqual(resp.status, 402)
        data = await resp.json()
        self.assertEqual(data.get("status"), "confirmation_required")

    @unittest_run_loop
    async def test_07_chat_paid_model_with_valid_token_accepted(self):
        """Geçerli token sağlandığında ücretli model onaylanır ve sağlayıcı adımına geçer."""
        token = create_paid_model_authorization("z-ai/glm-5.3", "openrouter")

        payload = {
            "message": "Hesaplama yap",
            "paid_auth_token": token,
            "config": {
                "model": "z-ai/glm-5.3"
            }
        }
        
        # Mocking groq/openrouter to prevent real network calls
        with patch("luna_server.load_config", return_value={"groq_api_key": ""}):
            resp = await self.client.post("/api/chat", json=payload)
            # 402 dönmemeli, onay aşamasını geçmiş olmalı
            self.assertNotEqual(resp.status, 402)

    @unittest_run_loop
    async def test_08_paid_auth_request_endpoint(self):
        """POST /api/models/paid_auth/request endpointi test edilir."""
        # Ücretli model için onay talebi
        resp = await self.client.post("/api/models/paid_auth/request", json={"model_id": "z-ai/glm-5.3"})
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data.get("requires_confirmation"))
        self.assertTrue(data.get("auth_token", "").startswith("pauth_"))

        # Ücretsiz model için talep
        resp_free = await self.client.post("/api/models/paid_auth/request", json={"model_id": "nvidia/nemotron-3.5-lightning:free"})
        self.assertEqual(resp_free.status, 200)
        data_free = await resp_free.json()
        self.assertEqual(data_free.get("cost_category"), "free")
        self.assertFalse(data_free.get("requires_confirmation", False))

if __name__ == "__main__":
    unittest.main()
