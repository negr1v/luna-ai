"""
ZERO CORE OS (ACCIO-JARVIS) V15 - PHASE 15A.2 TEST SUITE
Test: Intelligent Free-Provider-First Router, Capabilities & Paid Protection Continuity
"""

import sys
import os
import unittest
from unittest.mock import patch

PROJECT_DIR = r"C:\Users\negr1\Projeler\ACCIO-JARVIS"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from jarvis_server import (
    AI_MODEL_CATALOG,
    COST_FREE_ZERO_PRICE,
    COST_FREE_TIER_QUOTA,
    COST_PAID,
    COST_UNKNOWN,
    CAP_GENERAL_CHAT,
    CAP_REASONING,
    CAP_CODING,
    CAP_VISION,
    CAP_TOOL_CALLING,
    get_model_cost_tier,
    get_model_cost_category,
    select_free_first_model,
    handle_chat,
    handle_request_paid_auth
)
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

class TestPhase15A2FreeRouter(AioHTTPTestCase):

    async def get_application(self):
        app = web.Application()
        app.router.add_post("/api/chat", handle_chat)
        app.router.add_post("/api/models/paid_auth/request", handle_request_paid_auth)
        return app

    def test_01_cost_tier_distinction(self):
        """FREE_ZERO_PRICE, FREE_TIER_QUOTA, PAID ve UNKNOWN ayrımını doğrula."""
        self.assertEqual(get_model_cost_tier("meta-llama/llama-3.3-70b-instruct:free"), COST_FREE_ZERO_PRICE)
        self.assertEqual(get_model_cost_tier("llama-3.3-70b-versatile"), COST_FREE_TIER_QUOTA)
        self.assertEqual(get_model_cost_tier("z-ai/glm-5.3"), COST_PAID)
        self.assertEqual(get_model_cost_tier("unknown/random-model"), COST_UNKNOWN)

    def test_02_deprecated_models_excluded_from_auto_routing(self):
        """Deprecated/geçersiz model ID'lerinin otomatik seçimden elendiğini doğrula."""
        cfg = {"openrouter_api_key": "sk-or-test", "groq_api_key": "gsk-test"}
        model_id, meta, _ = select_free_first_model(cfg=cfg)
        self.assertNotIn(model_id, ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"])
        self.assertFalse(meta.get("deprecated", False))

    def test_03_capability_based_routing(self):
        """İstenen yeteneğe (örn: vision, coding) göre doğru ücretsiz modelin seçildiğini doğrula."""
        cfg = {"openrouter_api_key": "sk-or-test", "groq_api_key": "gsk-test"}
        
        # Vision yeteneği gerektiren görev
        vis_id, vis_meta, _ = select_free_first_model(required_capabilities=[CAP_VISION], cfg=cfg)
        self.assertIn(CAP_VISION, vis_meta.get("capabilities", []))
        self.assertEqual(vis_id, "meta-llama/llama-3.2-11b-vision-instruct:free")

        # Coding ve Reasoning yeteneği gerektiren görev
        code_id, code_meta, _ = select_free_first_model(required_capabilities=[CAP_CODING, CAP_REASONING], cfg=cfg)
        self.assertIn(CAP_CODING, code_meta.get("capabilities", []))
        self.assertIn(CAP_REASONING, code_meta.get("capabilities", []))

    def test_04_no_keys_stops_and_notifies_user(self):
        """Hiçbir API anahtarı yoksa otomatik olarak ücretliye geçmeyip durduğunu doğrula."""
        cfg = {"openrouter_api_key": "", "groq_api_key": ""}
        model_id, meta, reason = select_free_first_model(cfg=cfg)
        self.assertIsNone(model_id)
        self.assertIn("uygun bir ücretsiz model bulunamadı", reason)

    def test_05_unknown_pricing_excluded(self):
        """Bilinmeyen fiyatlandırmaya sahip modellerin otomatik seçilmediğini doğrula."""
        cfg = {"openrouter_api_key": "sk-or-test", "groq_api_key": "gsk-test"}
        model_id, meta, _ = select_free_first_model(cfg=cfg)
        self.assertNotEqual(get_model_cost_tier(model_id), COST_UNKNOWN)

    @unittest_run_loop
    async def test_06_manual_selection_preserved(self):
        """Kullanıcının manuel seçtiği modelin (ücretli olsa bile) ezilmediğini doğrula."""
        payload = {
            "message": "Manuel model testi",
            "config": {
                "model": "z-ai/glm-5.3"  # Manuel ücretli seçim
            }
        }
        # Manuel seçim ücretli olduğu için Phase 15A.1 korumasına takılmalı (HTTP 402)
        resp = await self.client.post("/api/chat", json=payload)
        self.assertEqual(resp.status, 402)
        data = await resp.json()
        self.assertEqual(data.get("model_id"), "z-ai/glm-5.3")

    @unittest_run_loop
    async def test_07_auto_free_first_chat_routing(self):
        """Model belirtilmediğinde veya 'auto' dendiğinde otomatik ücretsiz modelle ilerlendiğini doğrula."""
        payload = {
            "message": "Python ile faktöriyel kodu yaz",
            "config": {
                "model": "auto"
            }
        }
        # OpenRouter ve Groq anahtarları mevcutmuş gibi mockla
        mock_cfg = {
            "openrouter_api_key": "sk-or-test",
            "groq_api_key": "gsk-test"
        }
        with patch("jarvis_server.load_config", return_value=mock_cfg):
            with patch("jarvis_server.select_free_first_model", return_value=("meta-llama/llama-3.3-70b-instruct:free", {}, "ok")):
                resp = await self.client.post("/api/chat", json=payload)
                # Ücretsiz model seçildiği için 402 onay istememeli
                self.assertNotEqual(resp.status, 402)

if __name__ == "__main__":
    unittest.main()
