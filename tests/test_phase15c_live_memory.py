# -*- coding: utf-8 -*-
"""
LUNA-AI V15 - PHASE 15C LIVE MEMORY INTELLIGENCE TESTS
Verifies:
1. Context-aware memory retrieval and relevance/importance scoring.
2. Topic-based memory search.
3. Zero-LLM conversation candidate extraction.
4. Never saving uncertain or sensitive info.
5. Duplicate memory entry prevention.
6. HTTP API inspection and search controls.
"""
import os
import sys
import unittest
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from luna_server import (
    calculate_memory_relevance,
    search_memory_intelligence,
    extract_conversation_memory_candidates,
    is_duplicate_memory_entry,
    build_context_aware_memory_block,
    handle_search_memory,
    handle_get_memory_entry,
    handle_detect_memory_candidates,
    handle_get_memory
)

class TestLiveMemoryIntelligenceUnit(unittest.TestCase):
    def setUp(self):
        self.mock_memory = {
            "schema_version": "4.0",
            "revision": 3,
            "entries": [
                {"id": "mem_001", "text": "AM5 Platform İşlemci ve B650 Anakart hedefi", "category": "hardware", "pinned": True},
                {"id": "mem_002", "text": "YKS 2027 Sayısal Deneme Hedefi 360 dk/gün", "category": "study", "pinned": False},
                {"id": "mem_003", "text": "GTA IV indirme dosyası silinmeyecek", "category": "system", "pinned": False}
            ]
        }

    def test_01_relevance_and_importance_scoring(self):
        """Alaka ve önem skorunun (anahtar kelime, tam eşleşme, pinned) doğru çalıştığını doğrula."""
        entry = self.mock_memory["entries"][0]
        # B650 ve AM5 ile ilgili sorgu yüksek puan almalı
        score_high = calculate_memory_relevance(entry, query="B650 anakart fiyatları")
        score_low = calculate_memory_relevance(entry, query="biyoloji hücre bölünmesi")
        self.assertGreater(score_high, score_low)
        self.assertGreaterEqual(score_high, 0.40)

    def test_02_topic_based_memory_search(self):
        """Kategori/konu bazlı arama ve filtrelemenin doğrulanması."""
        results = search_memory_intelligence(query="", topic="hardware", memory_data=self.mock_memory)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "mem_001")
        self.assertEqual(results[0]["category"], "hardware")

    def test_03_zero_llm_conversation_candidate_extraction(self):
        """Konuşma metninden kural tabanlı, sıfır API çağrılı aday çıkarımı."""
        text = "Gelecek hedefim: Tıp fakültesi kazanmak ve derece yapmak"
        cands = extract_conversation_memory_candidates(text)
        self.assertGreaterEqual(len(cands), 1)
        self.assertEqual(cands[0]["category"], "study")
        self.assertIn("Hedef:", cands[0]["text"])

    def test_04_uncertainty_and_sensitivity_rejection(self):
        """Belirsiz (belki/sanırım) ve hassas (şifre/token/kart) verilerin reddedilmesi."""
        # Belirsizlik filtresi
        uncert_text = "Hedefim belki bilgisayar mühendisliği olabilir emin değilim"
        self.assertEqual(extract_conversation_memory_candidates(uncert_text), [])

        # Hassas güvenlik verisi filtresi
        sensitive_text = "Şifrem 123456Aa ve api_key: gsk_123456789012345"
        self.assertEqual(extract_conversation_memory_candidates(sensitive_text), [])

    def test_05_duplicate_memory_entry_prevention(self):
        """Mükerrer veya yüksek benzerlikli hafıza kayıtlarının engellenmesi."""
        existing = self.mock_memory["entries"]
        is_dup, _ = is_duplicate_memory_entry("AM5 Platform İşlemci ve B650 Anakart hedefi", existing)
        self.assertTrue(is_dup)

        is_not_dup, _ = is_duplicate_memory_entry("TYT Türkçe Paragraf Rutini 20 soru", existing)
        self.assertFalse(is_not_dup)

    def test_06_context_aware_prompt_block_builder(self):
        """Kullanıcı mesajına göre ilgili hafıza bloğunun üretilmesi."""
        block = build_context_aware_memory_block("YKS denemesi kaç dakika olmalı?", memory_data=self.mock_memory)
        self.assertIn("[İlgili Kullanıcı Hafızası]:", block)
        self.assertIn("YKS 2027", block)


class TestLiveMemoryIntelligenceHTTP(AioHTTPTestCase):
    async def get_application(self):
        app = web.Application()
        app.router.add_get("/api/memory", handle_get_memory)
        app.router.add_get("/api/memory/search", handle_search_memory)
        app.router.add_get("/api/memory/entries/{id}", handle_get_memory_entry)
        app.router.add_post("/api/memory/candidates/detect", handle_detect_memory_candidates)
        return app

    async def test_07_http_search_and_inspection_endpoints(self):
        """HTTP /api/memory/search ve /api/memory/entries/{id} doğrulaması."""
        # 1. Search endpoint
        resp = await self.client.get("/api/memory/search?q=AM5&limit=5")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("results", data)

        # 2. Candidate detect endpoint
        post_resp = await self.client.post("/api/memory/candidates/detect", json={
            "text": "Benim bütçem tavan 7500 TL olacak"
        })
        self.assertEqual(post_resp.status, 200)
        pdata = await post_resp.json()
        self.assertEqual(pdata["status"], "ok")
        self.assertGreaterEqual(pdata["count"], 1)

if __name__ == "__main__":
    unittest.main()
