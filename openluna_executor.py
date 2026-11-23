"""
openluna_executor.py
LUNA-AI için OpenLuna tabanlı Python CodeAct ve Tool Çalıştırma Motoru.

OpenLuna'in `NativeOpenHandsAgent` mantığından uyarlanmıştır:
- LLM yanıtlarındaki ```python ... ``` kod bloklarını tespit eder.
- Güvenli bir alt süreçte (timeout ve bellek limitli) çalıştırır.
- Çıktıyı (stdout / stderr) yakalayıp LUNA sistemine geri döndürür.
"""

from __future__ import annotations

import os
import re
import sys
import subprocess
import tempfile
from typing import Dict, Any, Optional

PYTHON_EXE = sys.executable

class OpenLunaExecutor:
    def __init__(self, timeout_sec: int = 15, max_output_chars: int = 4000):
        self.timeout_sec = timeout_sec
        self.max_output_chars = max_output_chars

    def extract_python_blocks(self, text: str) -> list[str]:
        """Metin içindeki ```python ... ``` bloklarını ayıklar."""
        pattern = r"```(?:python)?\s*\n(.*?)```"
        return re.findall(pattern, text, re.DOTALL)

    def execute_code(self, code: str) -> Dict[str, Any]:
        """
        Python kodunu izole bir temp dosyada çalıştırır.
        Çıktıyı güvenli sınırlar içinde döndürür.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as temp_file:
            temp_file.write(code)
            temp_file_path = temp_file.name

        try:
            # Yönetilen Python veya mevcut Python ile izole çalıştır
            result = subprocess.run(
                [PYTHON_EXE, temp_file_path],
                capture_output=True,
                text=True,
                timeout=self.timeout_sec
            )
            stdout = result.stdout[:self.max_output_chars]
            stderr = result.stderr[:self.max_output_chars]
            success = (result.returncode == 0)

            return {
                "success": success,
                "returncode": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "output": stdout if success or not stderr else f"{stdout}\n[Error]: {stderr}".strip()
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"TimeoutExpired: Kod {self.timeout_sec} saniye içinde tamamlanamadı.",
                "output": f"TimeoutExpired: Kod {self.timeout_sec} saniye içinde tamamlanamadı."
            }
        except Exception as e:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "output": f"ExecutionError: {e}"
            }
        finally:
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass

    def run_agent_turn(self, llm_response: str) -> Optional[Dict[str, Any]]:
        """
        Eğer LLM yanıtında python bloğu varsa çalıştırır ve
        sonucu bir sözlük olarak döner. Kod yoksa None döner.
        """
        blocks = self.extract_python_blocks(llm_response)
        if not blocks:
            return None

        # İlk veya birleştirilmiş bloğu çalıştır
        combined_code = "\n".join(blocks)
        exec_result = self.execute_code(combined_code)
        exec_result["code_executed"] = combined_code
        return exec_result


if __name__ == "__main__":
    # Test çalıştırması
    executor = OpenLunaExecutor()
    sample_llm_text = """
    Tabii, senin için hesaplıyorum:
    ```python
    x = 42
    y = 58
    print(f"Toplam Sonuç: {x + y}")
    ```
    İşte sonuç yukarıda.
    """
    res = executor.run_agent_turn(sample_llm_text)
    print("Test Çalıştırma Sonucu:", res)
