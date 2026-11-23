# -*- coding: utf-8 -*-
"""
LUNA-AI V15 - PHASE 15D SMART AI MODEL HUB TESTS (UPDATED)
Verifies:
1. Recommends models based on task type (chat, coding, reasoning, vision, tool calling).
2. Model info completeness (provider, cost category, capabilities, availability, context capacity, lifecycle, pricing).
3. Genuinely free models recommended first.
4. Separate model lifecycle (ACTIVE, PREVIEW, DEPRECATED) and pricing (FREE, PAID, UNKNOWN).
5. qwen/qwen3.8-27b = PREVIEW / PAID and openai/gpt-oss-120b = ACTIVE / PAID (not deprecated).
6. Paid models blocked from free recommendations, but allowed in non-free recommendation pool.
7. Deprecated models excluded from all recommendations and blocked from selection.
8. Paid models are NOT rejected as deprecated.
9. Manual model selection and persistence.
10. HTTP endpoints /api/models/hub and /api/models/recommend.
"""
import os
import sys
import unittest
from unittest.mock import patch
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from luna_server import (
    SmartModelAdvisor,
    AI_MODEL_CATALOG,
    DEPRECATED_MODELS,
    COST_FREE_ZERO_PRICE,
    COST_FREE_TIER_QUOTA,
    COST_PAID,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_PREVIEW,
    LIFECYCLE_DEPRECATED,
    PRICING_FREE,
    PRICING_PAID,
    PRICING_UNKNOWN,
    get_model_lifecycle,
    get_model_pricing,
    handle_get_models_hub,
    handle_recommend_models,
    handle_get_models,
    handle_select_model
)

class TestSmartModelHubUnit(unittest.TestCase):
    def setUp(self):
        self.mock_cfg = {
            "openrouter_api_key": "sk-or-test-key",
            "groq_api_key": "gsk-test-key",
            "active_model": "meta-llama/llama-3.3-70b-instruct:free"
        }

    def test_01_recommendation_by_task_type(self):
        """Farklı görev türleri için (coding, vision, reasoning) doğru modellerin önerildiğini doğrula."""
        # Vision görevi
        vis_recs = SmartModelAdvisor.recommend_for_task("vision", require_free=True, cfg=self.mock_cfg)
        self.assertGreaterEqual(len(vis_recs), 1)
        self.assertIn("vision", vis_recs[0]["capabilities"])
        self.assertEqual(vis_recs[0]["model_id"], "meta-llama/llama-3.2-11b-vision-instruct:free")

        # Coding görevi
        code_recs = SmartModelAdvisor.recommend_for_task("coding", require_free=True, cfg=self.mock_cfg)
        self.assertGreaterEqual(len(code_recs), 1)
        self.assertIn("coding", code_recs[0]["capabilities"])

    def test_02_free_models_first_ranking(self):
        """Önce sıfır maliyetli ($0), ardından kotalı ücretsiz modellerin sıralandığını doğrula."""
        chat_recs = SmartModelAdvisor.recommend_for_task("general_chat", require_free=True, cfg=self.mock_cfg)
        self.assertGreaterEqual(len(chat_recs), 2)
        # İlk önerilen model $0 maliyetli (COST_FREE_ZERO_PRICE) olmalı
        self.assertEqual(chat_recs[0]["cost_tier"], COST_FREE_ZERO_PRICE)

    def test_03_deprecated_models_excluded_and_active_paid_included(self):
        """Gerçek deprecated modeller elenir; qwen3.8-27b ve gpt-oss-120b ücretli havuzda önerilebilir."""
        recs = SmartModelAdvisor.recommend_for_task("general_chat", require_free=False, cfg=self.mock_cfg)
        rec_ids = [r["model_id"] for r in recs]
        
        # Gerçek deprecated model elenmeli
        self.assertNotIn("meta-llama/llama-2-70b-chat:deprecated", rec_ids)

        # qwen3.8-27b ve gpt-oss-120b deprecated DEĞİLDİR; require_free=False iken öneri listesinde yer alabilir
        self.assertIn("qwen/qwen3.8-27b", rec_ids)
        self.assertIn("openai/gpt-oss-120b", rec_ids)

    def test_03b_paid_models_excluded_from_free_recommendations(self):
        """Ücretli modellerin (qwen3.8-27b, gpt-oss-120b) ücretsiz öneri havuzundan elendiğini doğrula."""
        free_recs = SmartModelAdvisor.recommend_for_task("general_chat", require_free=True, cfg=self.mock_cfg)
        free_ids = [r["model_id"] for r in free_recs]
        self.assertNotIn("qwen/qwen3.8-27b", free_ids)
        self.assertNotIn("openai/gpt-oss-120b", free_ids)

    def test_04_model_info_fields_and_lifecycle_pricing_separation(self):
        """Model Hub meta verilerinde lifecycle (ACTIVE/PREVIEW/DEPRECATED) ve pricing (FREE/PAID/UNKNOWN) ayrımını doğrula."""
        hub = SmartModelAdvisor.get_models_hub_data(self.mock_cfg)
        self.assertEqual(hub["status"], "ok")
        self.assertGreater(hub["total_count"], 5)
        for m in hub["models"]:
            self.assertIn("provider", m)
            self.assertIn("capabilities", m)
            self.assertIn("cost_tier", m)
            self.assertIn("status", m)
            self.assertIn("contextWindow", m)
            self.assertIn("lifecycle", m)
            self.assertIn("pricing", m)
            self.assertIn(m["lifecycle"], [LIFECYCLE_ACTIVE, LIFECYCLE_PREVIEW, LIFECYCLE_DEPRECATED])
            self.assertIn(m["pricing"], [PRICING_FREE, PRICING_PAID, PRICING_UNKNOWN])

        # qwen3.8-27b = PREVIEW / PAID
        qwen_meta = next(m for m in hub["models"] if m["id"] == "qwen/qwen3.8-27b")
        self.assertEqual(qwen_meta["lifecycle"], LIFECYCLE_PREVIEW)
        self.assertEqual(qwen_meta["pricing"], PRICING_PAID)
        self.assertFalse(qwen_meta["isFree"])
        self.assertFalse(qwen_meta.get("deprecated", False))
        self.assertNotIn("qwen/qwen3.8-27b", DEPRECATED_MODELS)

        # gpt-oss-120b = ACTIVE / PAID
        gpt_meta = next(m for m in hub["models"] if m["id"] == "openai/gpt-oss-120b")
        self.assertEqual(gpt_meta["lifecycle"], LIFECYCLE_ACTIVE)
        self.assertEqual(gpt_meta["pricing"], PRICING_PAID)
        self.assertFalse(gpt_meta["isFree"])
        self.assertFalse(gpt_meta.get("deprecated", False))
        self.assertNotIn("openai/gpt-oss-120b", DEPRECATED_MODELS)


class TestSmartModelHubHTTP(AioHTTPTestCase):
    async def get_application(self):
        app = web.Application()
        app.router.add_get("/api/models", handle_get_models)
        app.router.add_get("/api/models/hub", handle_get_models_hub)
        app.router.add_get("/api/models/recommend", handle_recommend_models)
        app.router.add_post("/api/models/select", handle_select_model)
        return app

    async def test_05_http_hub_and_recommend_endpoints(self):
        """/api/models/hub ve /api/models/recommend API uç noktalarının doğrulanması."""
        # 1. Hub endpoint
        resp = await self.client.get("/api/models/hub")
        self.assertEqual(resp.status, 200)
        hub_data = await resp.json()
        self.assertEqual(hub_data["status"], "ok")
        self.assertIn("models", hub_data)

        # 2. Recommend endpoint (task=coding)
        resp_rec = await self.client.get("/api/models/recommend?task=coding&free_only=true")
        self.assertEqual(resp_rec.status, 200)
        rec_data = await resp_rec.json()
        self.assertEqual(rec_data["status"], "ok")
        self.assertEqual(rec_data["task"], "coding")
        self.assertIn("recommendations", rec_data)

    async def test_06_cannot_select_deprecated_model(self):
        """Deprecated model seçilmek istendiğinde HTTP 400 ile engellendiğini doğrula."""
        resp = await self.client.post("/api/models/select", json={"model_id": "meta-llama/llama-2-70b-chat:deprecated"})
        self.assertEqual(resp.status, 400)
        data = await resp.json()
        self.assertEqual(data.get("error_code"), "MODEL_DEPRECATED")

    async def test_06b_paid_models_not_rejected_as_deprecated(self):
        """Ücretli modellerin (qwen3.8-27b) deprecated olarak reddedilmediğini doğrula."""
        resp = await self.client.post("/api/models/select", json={"model_id": "qwen/qwen3.8-27b"})
        # 400 MODEL_DEPRECATED dönmemelidir (Groq anahtarı durumuna göre 200 veya 403 MODEL_LOCKED döner)
        data = await resp.json()
        self.assertNotEqual(data.get("error_code"), "MODEL_DEPRECATED")

    @patch("luna_server.save_config")
    @patch("luna_server.load_config")
    async def test_07_manual_selection_of_valid_model(self, mock_load, mock_save):
        """Geçerli bir model seçildiğinde HTTP 200 döndüğünü ve konfigürasyona yazıldığını doğrula."""
        mock_load.return_value = {"openrouter_api_key": "sk-or-test-key", "groq_api_key": "gsk-test-key"}
        resp = await self.client.post("/api/models/select", json={"model_id": "meta-llama/llama-3.3-70b-instruct"})
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["active_model"], "meta-llama/llama-3.3-70b-instruct")


if __name__ == "__main__":
    unittest.main()
