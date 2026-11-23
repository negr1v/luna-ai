"""
Focused Test Suite for Phase 16C: Memory Graph Explorer
Validates Memory Graph DOM structure, SVG/Canvas rendering logic,
category grouping, stored vs suggested edge separation, 40-node cap,
accessible text-list fallback, and jarvis_memory.json integrity.
"""

import os
import json
import unittest

BASE_DIR = r"C:\Users\negr1\Projeler\ACCIO-JARVIS"

class TestPhase16CMemoryGraph(unittest.TestCase):

    def setUp(self):
        self.index_html_path = os.path.join(BASE_DIR, "index.html")
        self.memory_json_path = os.path.join(BASE_DIR, "jarvis_memory.json")
        self.backup_path = os.path.join(BASE_DIR, "index.html.bak_phase16c_20261114")

    def test_01_backup_file_exists(self):
        """Doğrulama 1: index.html için Phase 16C yedeği mevcut ve boş değil."""
        self.assertTrue(os.path.exists(self.backup_path), f"Backup file not found: {self.backup_path}")
        self.assertGreater(os.path.getsize(self.backup_path), 500000)

    def test_02_memory_json_integrity(self):
        """Doğrulama 2: jarvis_memory.json tek yetkili kaynak olarak sağlam ve geçerli."""
        self.assertTrue(os.path.exists(self.memory_json_path))
        with open(self.memory_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("user_name"), "negr1")
        self.assertIn("YKS", data.get("focus", ""))
        self.assertIn("AM5", data.get("target_hardware", ""))
        self.assertIsInstance(data.get("notes"), list)
        self.assertGreaterEqual(len(data.get("notes")), 5)
        self.assertIn("revision", data)

    def test_03_graph_dom_elements_present(self):
        """Doğrulama 3: index.html içinde Memory Graph Explorer kart ve arayüz elemanları mevcut."""
        with open(self.index_html_path, "r", encoding="utf-8") as f:
            content = f.read()

        required_ids = [
            "viewCardMemoryGraph",
            "memGraphNodeCountBadge",
            "memGraphCategoryFilter",
            "memGraphSearchInput",
            "memGraphToggleViewBtn",
            "memGraphLoadBtn",
            "memGraphViewport",
            "memGraphPlaceholder",
            "memGraphSvg",
            "memGraphTextFallback",
            "memGraphTextListContent",
            "memGraphNodeDetail",
            "memDetailTitle",
            "memDetailCategoryBadge",
            "memDetailContent",
            "memDetailRelations",
            "memDetailRev",
            "memDetailCloseBtn"
        ]

        for elem_id in required_ids:
            self.assertIn(f'id="{elem_id}"', content, f"Missing element ID: {elem_id}")

    def test_04_graph_controller_logic(self):
        """Doğrulama 4: JS controller fonksiyonu, kategorizasyon ve 40 düğüm tavanı mevcut."""
        with open(self.index_html_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("initZeroMemoryGraphExplorer", content)
        self.assertIn("MAX_NODES = 40", content)
        self.assertIn("computeStaticClusterLayout", content)
        self.assertIn("renderSvgGraph", content)
        self.assertIn("renderTextListFallback", content)
        self.assertIn("sanitizeMemoryText", content)

    def test_05_stored_vs_suggested_relationships(self):
        """Doğrulama 5: Kayıtlı ilişki ve önerilen çağrışım ayrımı doğru yapılandırılmış."""
        with open(self.index_html_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Kayıtlı İlişki", content)
        self.assertIn("Önerilen Çağrışım", content)
        self.assertIn("type === 'stored'", content)
        self.assertIn("type === 'suggested'", content)
        self.assertIn("stroke-dasharray", content)

    def test_06_performance_and_accessibility(self):
        """Doğrulama 6: Klavye erişilebilirliği ve isteğe bağlı yükleme (lazy load) mevcut."""
        with open(self.index_html_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Keyboard accessibility
        self.assertIn("tabindex", content)
        self.assertIn("aria-label", content)
        self.assertIn("Escape", content)
        # On-demand load
        self.assertIn("memGraphLoadBtn", content)
        self.assertIn("window.loadMemoryGraph", content)

if __name__ == "__main__":
    unittest.main()
