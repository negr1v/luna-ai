# ACCIO LUNA ULTRA — Yerel ses hattı devir dosyası

## Durum ve sıra

| Öncelik | Kanıt | ACCIO'nun sonraki adımı |
|---|---|---|
| P0 · Canlı sürümü doğrula | Kaynakta GET /api/stt/status ve yerel POST /api/stt var. Açık localhost süreci durum rotasında HTTP 404 döndü. Önceki kaynakta POST /api/stt mikrofon verisini Groq Whisper'a gönderebiliyordu. | Mevcut başlatıcının güvenli kapatma yolunu kullan. Gerekirse açık sunucu konsolunda Ctrl+C ile kapatıp proje başlatıcısıyla aç. Durum rotası 200 ve ready dönünce kısa Türkçe cümleyle mikrofon → sohbet → Ahu turu yap. STT aşamasında dış istek olmadığını gözle. |
| P0 · Temiz Windows paketi | build_portable_package.ps1 AppFiles listesinde luna_local_stt.py yer almıyor. | Python modülü, statik kayıt betiği, model, FFmpeg ve Vosk bağımlılığının paket içinde veya belgelenmiş kurulum yolunda erişilebilirliğini doğrula. Sürüm, lisans ve bütünlük bilgilerini pakete ekle. PATH'i boş, kullanıcı verisi olmayan Windows ortamında test et. |
| P1 · Ahu sesini sabitle | luna_server.py generate_tts içinde Edge fallback bulunuyor. index.html /api/tts_direct çağrısına metnin ilk 450 karakterini veriyor. | Fish/Ahu hata verirse sessiz metin ve açık tekrar deneme seçeneği göster. Başka sağlayıcıya geçiş için kullanıcı tercihi iste. Uzun yanıtları cümle sınırında bölmeyi ölç, kesilmeyi ve tekrar sentezi önle. |
| P1 · Çift sohbet ve kaynak tüketimi | index.html önce /api/chat/stream, hata halinde bazı durumlarda /api/chat dener. Yanıt kaybolduğunda ilk isteğin sunucuda tamamlanmış olması mümkün. | Sunucu tur kimliğiyle tekrarları birleştir. Otomatik yeniden denemeyi ilk turun çalışmadığı doğrulanabilen hatalarla sınırla. Araçlı turu otomatik tekrarlama. |
| P1 · Ses dayanıklılığı | Kayıt sabit RMS eşiğiyle iki örnekte açılıyor, 750 ms sessizlikte veya 14 sn sınırında bitiyor. Tek STT isteği kabul ediliyor. Canlı mikrofon ve gürültü ölçülmedi. | Gürültülü oda, kısa kelime, yavaş konuşma, uzun dikte, kulaklıksız Ahu, Alt+Tab, mikrofon çıkarma ve iki sekmeyi dene. 429/503/codec/timeout için ayrı kullanıcı mesajları ve güvenli manuel tekrar uygula. |
| P1 · Kayıt sınırları | STT multipart boyut sınırı 1 MiB. FFmpeg 16 sn PCM sınırı ve 8 sn çözümleme süresi var. Dosyaya yazmadan çalışıyor. | Tek etkin istek ve sınırları koru. Paketlenen FFmpeg sürümünü güncel tut. Hatalı ve kesilmiş WebM/Ogg/MP4 örneklerinin güvenli reddedildiğini doğrula. Vosk model yükleme başarısızlığı ve uzun süren çalışma için ölçüm ekle. |
| P2 · Transkript saklama | index.html mevcut sohbet geçmişini yerel depodan innerHTML ile geri kuruyor. Saldırı yolu doğrulanmadı. | Eski geçmişi koruyarak sürümlü metin tabanlı kayıt ve güvenli DOM oluşturma yoluna geç. |
| P2 · Ölçüm ve optimizasyon | Donanım hedefi i5-8250U, 8 GB RAM, UHD 620. Bu donanımda uçtan uca gecikme ölçülmedi. | Soğuk ve sıcak modelle ilk metne, ilk sohbet yanıtına ve ilk Ahu sesine p50/p95 süreleri ölç. CPU, RAM ve avatar kare hızını kaydet. Türkçe kelime hata oranını sessiz ve gürültülü örneklerle ölç. Ham kayıt ve konuşma içeriğini loglama. |

Kredi azsa önce güncel süreci ve temiz paketi doğrula. Sonra gerçek mikrofon ve Ahu kabulünü yap. İlk ölçümden önce ses motoru, yeni VAD bağımlılığı veya genel arayüz değişimine girme. STT yerel, sohbet ve Ahu mevcut sağlayıcı ayarlarını kullanıyor. Uzun konuşmayı yönetmek ve Ahu çalarken yankıyı kullanıcı konuşmasından ayırmak için ayrı kabul gerekir. Firefox ve MP4 seçen tarayıcıların kabulü açık.

MediaRecorder son verisini durdurma sırasında ayrı olayla teslim eder. Testler bu sırayı korumalı. Zaman dilimini güvenilir toplam süre ölçümü olarak kullanma. [MDN dataavailable](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/dataavailable_event) · [Vosk model listesi](https://alphacephei.com/vosk/models)

## ChatGPT’ye gönderilecek metin

ACCIO LUNA ULTRA üzerinde Windows ve düşük donanım hedefiyle yerel Türkçe sesli sohbet geliştiriyorum. Tarayıcı SpeechRecognition ve dil paketi arayüzünü kaldırdım. Yeni hat MediaRecorder + RMS VAD → multipart POST /api/stt → FFmpeg (16 kHz mono PCM) → yerel Vosk → {text} → sohbet akışı → Fish Audio Ahu /api/tts_direct. Hedef i5-8250U, 8 GB RAM, UHD 620. aiohttp tek süreç çalışıyor. WebM/Ogg/MP4 desteği amaçlanıyor, Chrome davranışı izole test edildi. Başlangıç ayarları 60 ms RMS örneği, iki ardışık eşik geçişi, 750 ms sessizlik, 14 sn kayıt sınırı, 1 MiB yük, tek etkin STT isteği. 11 izole tarayıcı kontrolü geçti. Canlı mikrofon, gerçek Ahu ve temiz taşınabilir paket henüz kabul edilmedi.

Şu beş başlıkta uygulanabilir bir teknik inceleme ver. Her bulguda öncelik, kullanıcının göreceği sonuç, en küçük düzeltme, ölçülebilir kabul testi ve maliyet belirt. Kod görülmeden verilen çıkarımları hipotez olarak işaretle.

1. Kayıt, final blob ve iptal arasında yarış, çift gönderim, eski yanıtın yeni tura karışması, codec uyumsuzluğu ve STT/TTS zaman aşımı nasıl ele alınmalı?
2. Türkçe kalite ve CPU/RAM hedefi için VAD gürültü tabanı, başlangıç tamponu, sessizlik, kayıt sınırı, multipart ve model ısınması nasıl ölçülüp ayarlanmalı? Hangi p50/p95 gecikme ve kelime hata oranı hedefleri önce ölçülmeli?
3. Boş veya uzun kayıt, gürültü, mikrofon izni reddi/kesilmesi, paralel sekme, 429/503, TTS hatası, kullanıcı iptali ve Ahu yankısında uygulanabilir durum akışı ne olmalı? Kullanıcının haberi olmadan STT’yi dışarı göndermeyi veya Ahu’yu başka sesle değiştirmeyi önerme.
4. test_voice_composer_ui.cjs ve test_avatar_speech_ui.cjs dosyalarında hangi kontroller simüle edilmeli, hangileri gerçek tarayıcı ve gerçek ses cihazıyla ölçülmeli? Son blob, bırakılan mikrofon, sıradaki turun dinlemeye dönmesi, sessiz metin sohbeti, tek STT/sohbet/TTS çağrısı ve geç sonuç özellikle ele alınsın.
5. Kaynak ve kredi sırası ne olmalı? Temiz Windows paketi, ses kasıtlı durdurma, sağlayıcı değişimi, tur kimliği, performans telemetrisi ve veri gizliliğinde eksikleri sırala. En yüksek etkiye sahip üç işi ve daha sonra yapılacakları ver.
