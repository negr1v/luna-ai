# LUNA AI // MİMARİ, GÜVENLİK VE DEVİR RAPORU
**Sürüm:** V4.2 (OLED & Accio Work Standartları)  
**Tarih:** 2026-11-23  
**Hedef Kitle:** Genel Kullanıcı (Zero-Configuration, Tak-Çalıştır Masaüstü Asistanı)  
**Kredi Koruma Uyumluluğu:** 0-Kredi Protokolü & İzolasyon Korumalı  

---

## 1. MEVCUT DURUM VE SON DEĞİŞİKLİKLER ÖZETİ

Son geliştirme turlarında sistem genel kullanıcı deneyimi ve stabilite odaklı olarak köklü şekilde sadeleştirildi:

1. **Arayüz Temizliği ve OLED Sadeliği (Tamamlandı):**
   - Ekranda geliştirici kalıntısı olarak duran `Desktop Agent V1`, `Hedef, Onay ve Doğrulama` ve sol menüdeki `Masaüstü Ajanı` bağlantısı bütünüyle kaldırıldı.
   - Ana ekran kokpitindeki kaba `#agentHudCard` (Ajan görevi ver / IDLE paneli) kalıcı olarak gizlendi.
   - "Merhaba" ve avatar üzerindeki gereksiz açılır/kapanır katlama okları (`#avatarCollapseToggleBtn`, `#chatCollapseToggleBtn`) temizlendi.
   - Accio Work ve ChatGPT masaüstü standartlarına uygun tam boy, dikeyde ferah sohbet akışı sağlandı.
   - Anime kızı avatarı; üst barda 7/24 durum ışığıyla parlayan mini rozet, asistan mesajlarında mini kart portresi ve F8 tuşuna basıldığında açılan tam ekran ses modu olarak konumlandırıldı.

2. **Ses Altyapısı (STT & TTS) Durumu:**
   - **TTS:** Fish Audio / Edge TTS destekli `/api/tts_direct` uç noktası stabil. Görev bitimlerinde ve molalarda devreye giren "Gothic Mommy" övgü/motivasyon seslendirme havuzu eklendi.
   - **STT (Yeni):** `luna_server.py` içine Groq Whisper (`whisper-large-v3-turbo`) destekli yüksek hızlı `POST /api/stt` rotası yazıldı. Ayrıca yerel çevrimdışı Vosk desteği (`luna_local_stt.py`) sunucuya bağlandı.
   - **Sorun:** Tarayıcı tarafındaki eski `webkitSpeechRecognition` API'si ve tıklanmayan "Türkçe paket kur" butonu devreden çıkarılıp, istemcinin `MediaRecorder` ile doğrudan yerel `/api/stt` rotasına bağlanması gerekiyor.

---

## 2. SİSTEMDEKİ TEHLİKELER, AÇIKLAR VE KÖR NOKTALAR (RİSK ANALİZİ)

### A. STT (Ses Girişi) Zinciri Riskleri
1. **Yarış Durumu (Race Condition) & Çift Gönderim:**
   - Kullanıcı konuşurken veya durakladığında VAD (Ses Aktivite Algılama) birden fazla parça üretirse sunucuya ardışık iki `/api/stt` isteği gidebilir.
   - İkinci istek ilk istekten önce dönerse sohbet akışında mesajlar ters sırayla ekrana basılır veya çift mesaj gönderilir.
   - *Çözüm:* İstemcide her ses kaydı için artan bir `turn_id` tutulmalı; önceki istek sonuçlanmadan veya iptal edilmeden yeni istek sohbet akışına basılmamalı.
2. **Codec ve Konteyner Uyuşmazlığı:**
   - Windows Chrome ve Edge'de `MediaRecorder`, `audio/webm;codecs=opus` üretirken bazı tarayıcılar `audio/ogg` veya `audio/wav` üretebilir.
   - *Çözüm:* `/api/stt` rotası hem multipart ses dosyasını hem de base64 JSON yükünü kabul edecek şekilde esnek tutulmalı (backend'de uygulandı).
3. **Boş / Gürültülü Kayıt Spam'i:**
   - Kullanıcı mikrofonu açık unuttuğunda klavye veya ortam gürültüsü VAD eşiğini aşıp sunucuya 0.2 saniyelik boş sesler gönderebilir.
   - *Çözüm:* Minimum ses süresi eşiği (örn: en az 600ms) ve minimum RMS/desibel enerjisi kontrolü yapılmalı; boş veya fısıltı seviyesindeki parçalar `/api/stt`'ye hiç gönderilmemeli.

### B. Chat & LLM Akış Riskleri
1. **Söz Kesme (Interruption / Barge-in) Eksikliği:**
   - Asistan uzun bir yanıtı seslendirirken kullanıcı yeni bir şey söylediğinde veya Esc'ye bastığında, devam eden TTS akışı ve ses oynatımı anında kesilmeli.
   - Şu anki `interruptBtn` tıklandığında istemci sesi durduruyor ancak sunucudaki token üretimi bazen arkadan gelmeye devam edebiliyor.
   - *Çözüm:* Her yeni soru gönderildiğinde önceki `AbortController` sinyaliyle devam eden `/api/chat/stream` bağlantısı anında kapatılmalı.
2. **Model Gecikmesi & Yanıtsızlık:**
   - OpenRouter veya Groq API kotası dolduğunda veya ağ geciktiğinde kullanıcı "Asistan dondu" hissine kapılabilir.
   - *Çözüm:* İstek atıldığı anda ekranda anlık "Düşünüyor..." animasyonu ve 12 saniyeyi aşan yanıtsızlıklarda otomatik kullanıcı dostu yeniden deneme bildirimi çıkmalı.

### C. Bellek ve Dosya Şişmesi (Monolitik Risk)
1. **`index.html` (15.200 Satır):**
   - Tek bir dosyada HTML, CSS ve JavaScript iç içe olduğu için DOM üzerinde yapılan cerrahi müdahaleler bazen beklenmedik yan etkilere yol açabiliyor.
   - *Çözüm:* Testler geçip ses motoru canlıda doğrulandıktan hemen sonra CSS bloğu `luna_oled.css` olarak dışarı alınmalı.

---

## 3. ADIM ADIM UYGULAMA VE GEÇİŞ PLANI (YOL HARİTASI)

### [AŞAMA 1] İstemci STT Motorunu /api/stt'ye Bağlama (ÖNCELİK: KRİTİK)
- **Sorumlu:** ChatGPT / Codex (Frontend)
- **Hedef:** Tıklanmayan "cihaza paket kur" butonunu ve SpeechRecognition'ı tamamen söküp `MediaRecorder` + VAD yapısına geçmek.
- **Detay:**
  1. `index.html` içinde mikrofon butonu (`#promptMicBtn`) tıklandığında `navigator.mediaDevices.getUserMedia` ile 16kHz ses akışı başlatılır.
  2. Kullanıcı konuştuğu sürece ses parçaları (chunks) toplanır.
  3. Konuşma durakladığında (1000ms sessizlik VAD eşiği) veya mikrofona tekrar basıldığında ses bloğu `FormData` ile `POST /api/stt` adresine gönderilir.
  4. Gelen `{ status: "success", text: "..." }` yanıtı doğrudan `#textInput` alanına yazılır ve otomatik olarak `#sendBtn` tetiklenir.

### [AŞAMA 2] Sunucu Yeniden Başlatma & Canlı Doğrulama
- **Sorumlu:** Kullanıcı & ACCIO (Terminal/Operasyon)
- **Hedef:** Yeni `/api/stt` ve güncel frontend'in 7860 portunda çalışmasını sağlamak.
- **Komut:**
  ```powershell
  Set-Location "C:\Users\negr1\Projeler\LUNA-AI"; powershell -ExecutionPolicy Bypass -File .\start_luna.ps1
  ```

### [AŞAMA 3] Gelişmiş VAD & Ses Kesme Entegrasyonu
- Ses oynatılırken kullanıcının sesi algılanırsa asistanın konuşmasını durdurma (Barge-in).
- Web Audio API `AnalyserNode` üzerinden gerçek zamanlı mik seviyesi ile anime kızının halosu senkronize edilmeye devam edilecek.

### [AŞAMA 4] Taşınabilir Paketleme (Zero-Dependency Portable)
- `dist/LUNA-AI-PORTABLE` klasörünün tek tıklamayla (.bat / .exe) her Windows bilgisayarda sıfır kurulumla çalışacak hale getirilmesi.
- Embedded Python çalışma zamanı ile sistem Python'ına bağımlılığın sıfırlanması.

---

## 4. KREDİ KORUMA VE İŞ BÖLÜMÜ PROTOKOLÜ

1. **Codex / ChatGPT:**
   - `index.html`, CSS ve istemci JavaScript dosyalarını düzenler.
   - Node.js tabanlı izole testleri (`test_voice_composer_ui.cjs`, `test_avatar_speech_ui.cjs`, `test_fix_pack2_ui.cjs`) çalıştırıp yeşil olduğunu teyit eder.
2. **ACCIO:**
   - Sunucu tarafı mimari rotaları (`luna_server.py`), API entegrasyonlarını, taşınabilir dağıtım senkronizasyonunu yönetir.
   - Asla terminalden ağır test veya kontrolsüz script koşturmaz (0-Kredi İlkesi).
   - Kullanıcıya canlı doğrulama için tek satırlık pratik PowerShell komutları sunar.

---
*Bu rapor ACCIO asistanı tarafından proje kök dizininde kalıcı olarak oluşturulmuştur.*
