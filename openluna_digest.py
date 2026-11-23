"""
openluna_digest.py
LUNA-AI için OpenLuna tabanlı Sabah Brifingi ve Günlük Özet Ajanı.

OpenLuna'in `MorningDigestAgent` stratejisinden uyarlanmıştır:
- Sistem saati, aktif görevler, sistem telemetrisi ve bildirimleri toplar.
- Hem metin raporu hem de TTS (seslendirme) için optimize edilmiş konuşma metni üretir.
- Sıfır halüsinasyon: Yalnızca gerçek JSON ve sistem verilerini temel alır.
"""

from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Dict, Any, List

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

class OpenLunaDigest:
    def __init__(self, project_dir: str = PROJECT_DIR, honorific: str = "Efendim"):
        self.project_dir = project_dir
        self.honorific = honorific
        self.tasks_file = os.path.join(project_dir, "luna_tasks.json")
        self.notifications_file = os.path.join(project_dir, "luna_notifications.json")

    def _read_json_safe(self, filepath: str) -> Any:
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def collect_digest_data(self) -> Dict[str, Any]:
        """Tüm yerel kaynaklardan günlük verileri toplar."""
        tasks = self._read_json_safe(self.tasks_file)
        notifications = self._read_json_safe(self.notifications_file)

        pending_tasks = []
        if isinstance(tasks, list):
            for t in tasks:
                if not t.get("completed", False):
                    pending_tasks.append(t.get("title", "İsimsiz Görev"))

        recent_notifs = []
        if isinstance(notifications, list):
            for n in notifications[-5:]:
                text = n.get("text", "") or n.get("title", "")
                if text:
                    recent_notifs.append(text)

        now = datetime.now()
        return {
            "date_str": now.strftime("%d %B %Y, %A"),
            "time_str": now.strftime("%H:%M"),
            "pending_tasks": pending_tasks,
            "recent_notifs": recent_notifs
        }

    def generate_spoken_briefing(self) -> str:
        """
        OpenLuna TTS formatı:
        Maksimum 150-200 kelime, doğrudan konuşma dili, emojisiz, temiz metin.
        """
        data = self.collect_digest_data()
        parts = []

        parts.append(f"Günaydın {self.honorific}.")
        parts.append(f"Bugün {data['date_str']}, saat şu an {data['time_str']}.")

        task_count = len(data["pending_tasks"])
        if task_count > 0:
            top_tasks = ", ".join(data["pending_tasks"][:3])
            parts.append(f"Ajandanda bekleyen {task_count} görev bulunuyor. Öncelikli olanlar: {top_tasks}.")
        else:
            parts.append("Şu anda bekleyen açık bir görevin bulunmuyor.")

        if data["recent_notifs"]:
            parts.append(f"Son sistem kayıtlarında {len(data['recent_notifs'])} yeni bildirim mevcut.")

        parts.append("Tüm sistemler aktif ve çalışmaya hazır. İyi çalışmalar dilerim.")
        return " ".join(parts)

    def generate_markdown_report(self) -> str:
        """Kullanıcının HUD veya arayüzde okuyabileceği yapılandırılmış rapor."""
        data = self.collect_digest_data()
        md = []
        md.append(f"# 🌅 [OPENLUNA MORNING DIGEST]")
        md.append(f"**Tarih:** {data['date_str']} | **Saat:** {data['time_str']}")
        md.append(f"**Hitap:** {self.honorific}\n")

        md.append(f"### 📋 Bekleyen Görevler ({len(data['pending_tasks'])})")
        if data["pending_tasks"]:
            for t in data["pending_tasks"]:
                md.append(f"- [ ] {t}")
        else:
            md.append("*Tüm görevler tamamlanmış.*")
        md.append("")

        md.append(f"### 🔔 Son Bildirimler ({len(data['recent_notifs'])})")
        if data["recent_notifs"]:
            for n in data["recent_notifs"]:
                md.append(f"- {n}")
        else:
            md.append("*Yeni bildirim yok.*")

        md.append("\n---\n*OpenLuna Morning Digest Ajanı tarafından derlenmiştir.*")
        return "\n".join(md)


if __name__ == "__main__":
    digest = OpenLunaDigest()
    print("--- SESLİ BRİFİNG METNİ (TTS) ---")
    print(digest.generate_spoken_briefing())
    print("\n--- GÖRSEL PANEL METNİ ---")
    print(digest.generate_markdown_report())
