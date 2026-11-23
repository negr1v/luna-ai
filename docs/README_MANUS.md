# Luna AI (LUNA-AI) - Proje Devir ve Geliştirici Kılavuzu

Bu paket, **Luna AI** masaüstü asistanının web ve arayüz çekirdeğini içerir.

## 🎯 Temel Hedefler & Tasarım Vizyonu
1. **Study With Mommy Tasarım Dili:**
   - Referans: `https://studywithmommy.com/`
   - Akıcı cam efekti (glassmorphism), koyu transparan kartlar (`backdrop-filter: blur(28px) saturate(1.25)`).
   - Alt kısımda yüzen modern arama/ses çubuğu (`.callbar`).
   - 2 sütunlu ayarlar paneli (`.mommy-settings-dash`) tamamlanmıştır.

2. **Gereken İyileştirmeler (Manus Öncelikli Görevler):**
   - **Üst Menü Sadeleştirme:** Üst çubuktaki çakışan ve kalabalık butonları temizleyip yalnızca Luna AI logosu, ses durumu ve sağda sade bir ayarlar ikonu bırakmak.
   - **Sol Kenar Çubuğu Katlanabilirliği (Collapse):** Özellikle 1365x595 ve dar ekranlarda sohbet alanının sıkışmaması için sol sohbet çubuğunu tek tıkla gizlenebilir/daraltılabilir yapmak.
   - **Sohbet & Karakter Alan Oranı:** Karakter görselinin sahneyi tamamen kaplayıp konuşmayı sıkıştırmasını önlemek; konuşma balonlarını zarif cam kartlar haline getirmek.
   - **Kontrast ve Erişilebilirlik:** Alt callbar ve durum metinlerinde koyu arka plan üzerinde net okunabilirlik sağlamak.

## ⚠️ Dikkat Edilmesi Gereken Kritik Kural
`index.html` içinde arka plan JavaScript motorunun dinlediği DOM ID'leri mevcuttur (`ttsEngineSelect`, `assistantVolume`, `closeSettingsBtn`, `saveSettingsBtn`, `studioRoomChoices`, `char-pick-btn`, vb.). Bu ID'lerin korunması şarttır.

## 🚀 Başlatma
```bash
python luna_server.py --port 7860
```
Tarayıcıdan: `http://127.0.0.1:7860`
