# ACCIO ZERO CORE OS — Yerel önizleme ve Vision onayı

Ekran paylaşımı artık **Yerel önizleme** olarak etiketleniyor. Önizlemeyi başlatmak, durdurmak veya seçiciyi iptal etmek analiz için kare almıyor ve Vision isteği göndermiyor. Uygulama: `index.html:2829`.

**Analiz Et** ve **Canlı Tahta → Soru Çek** aynı onay penceresini açıyor. Pencere, bir ekran görüntüsünün **OpenRouter’a (OpenAI GPT‑4o)** gönderileceğini ve çağrının ücretli olduğunu kare alınmadan önce gösteriyor. Vazgeçmek önizlemeyi açık bırakıyor. Akış biterse, kaynak değişirse veya sunucu hedefin değiştiğini bildirirse bekleyen onayla devam edilmiyor.

`jarvis_server.py:5031` ile başlayan sunucu doğrulaması, onayı tarayıcı oturumuna, sağlayıcıya ve modele bağlıyor. Onay 120 saniye geçerli ve iletimden önce tek kullanımlık olarak tüketiliyor. Groq’taki mevcut Vision modeli hizmetten kaldırıldığı için o hedef kullanılamaz olarak bildiriliyor. [Groq model kaldırma kaydı](https://console.groq.com/docs/deprecations)

## Test sonuçları

- `node test_vision_consent_ui.cjs` **geçti**. Önizleme başlatma, durdurma ve seçici iptalinde **0 kare, 0 Vision isteği**. Onay iptali, akışın bitmesi, kaynak değişimi ve hedef reddinde **0 kare, 0 analiz gönderimi**. İki onaylı düğme denemesi **2 kare ve 2 taklit gönderim** üretti.
- `python -B -m unittest -v test_vision_consent` **geçti**. Eksik, süresi dolmuş, kullanılmış ve eşleşmeyen onaylar engellendi. Aynı belirteçle eşzamanlı iki gönderim **200 ve 403** döndürdü. Taklit dış çağrı sayısı **OpenRouter 1, Groq 0**.
- `python -B test_phase7e_frontend.py` **10/10 geçti**.

## Uyumluluk ve canlı doğrulama

- Tek kare ekran taraması (`screenPreviewSendBtn`), kamera (`scanWithCamera`) ve Canlı Tahta'nın sürükle-bırak (`drop`) ile panodan yapıştırma (`paste`) yolları `executeAuthorizedVisionAnalysis` onay akışına bağlandı. Artık doğrudan onaysız `/api/vision` çağrısı yapılmıyor; tek kullanımlık onay belirteci (`approval_token`) doğrulanarak iletiliyor.
- `127.0.0.1:7860` canlı bağlantı kontrolü ve Notepad önizlemesi kullanıcı kabul aşamasında. Gerçek dış Vision çağrısı yapılmadı.
