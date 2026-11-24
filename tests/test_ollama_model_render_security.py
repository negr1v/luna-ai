import os
import unittest


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(PROJECT_DIR, "index.html")


class OllamaModelRenderSecurityTests(unittest.TestCase):
    def test_api_model_name_is_rendered_as_text_not_html(self):
        with open(INDEX_PATH, "r", encoding="utf-8") as handle:
            html = handle.read()

        start = html.index("  async function loadOllamaModels() {")
        end = html.index("\n  const refreshOllamaModelsBtn", start)
        renderer = html[start:end]

        self.assertIn("modelName.textContent = String(m.name ?? '')", renderer)
        self.assertIn("span.append(indicator, modelName, sizeLabel)", renderer)
        self.assertNotIn("${m.name}", renderer)
        self.assertNotIn("span.innerHTML", renderer)


if __name__ == "__main__":
    unittest.main()
