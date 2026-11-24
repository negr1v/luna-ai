# LUNA AI — MULTI-AGENT OTOMATİK SENKRONİZASYON PROTOKOLÜ

Bu protokol, **Manus**, **Claude** ve **Accio** arasında kullanıcının manuel mesaj taşımasına gerek kalmadan GitHub üzerinden senkronize çalışmayı sağlar.

---

## 1. Dallar ve Roller

| Model | Rolü | Çalıştığı Dal | Görevi |
|---|---|---|---|
| **Manus** | Arka Uç Güvenliği ve Testler | `manus-fixes` | Regresyon testlerini (30 fail, 38 error) düzeltmek, token/onay kapılarını test etmek. |
| **Claude** | Baş Mimar ve UI/UX | `claude-ui` | Study With Mommy tarzı cam dock (`.callbar`), sidebar düzeltmeleri ve arayüz JS'leri. |
| **Accio** | Yerel Orkestratör ve Test Koşucusu | `main` | Dallar arasındaki birleştirmeleri yapmak, yerel Windows testlerini çalıştırmak ve panoyu güncellemek. |

---

## 2. Çalışma ve İletişim Kuralı

1. **Gözlem Noktası:** Her model işe başlamadan önce `.agents/SYNC_BOARD.json` dosyasını okur.
2. **Kendi Dalına Pushlama:**
   - Manus hiçbir zaman doğrudan `main`e pushlamaz; `origin/manus-fixes` dalına pushlar.
   - Claude arayüz kodlarını `origin/claude-ui` dalına pushlar (veya diff olarak sunar).
3. **Senkronizasyon:**
   - Accio, yerelde çalışan `python scripts/agent_sync.py` aracıyla yeni commit'leri algılar.
   - Testleri yerel Windows ortamında çalıştırır.
   - Sonuçları `.agents/SYNC_BOARD.json` ve `.agents/TEST_REPORT.md` dosyalarına yazar.

---

## 3. Güvenlik Kuralları
- `luna_config.json`, `luna_memory.json` ve `.bak` dosyaları asla git takibine eklenmez.
- Kodlarda `luna_config.example.json` şablonu referans alınır.
