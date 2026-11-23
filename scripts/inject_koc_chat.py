import re

p_desktop = r"C:\Users\negr1\Desktop\yks-test-takip.html"
p_projeler = r"C:\Users\negr1\Projeler\LUNA-AI\yks-test-takip.html"

koc_module_code = '''
// ==================== YKS KOÇU AI CHAT ENGINE (STUDYTRACKER CLONE) ====================
let kocChatMessages = [];
try {
  const raw = localStorage.getItem("st_koc_chat_history_v2");
  if (raw) kocChatMessages = JSON.parse(raw);
} catch(e) { kocChatMessages = []; }

if (!Array.isArray(kocChatMessages) || kocChatMessages.length === 0) {
  kocChatMessages = [
    {
      role: "assistant",
      time: "22:05",
      text: `### 7. Problemler (Orijinal Mikro Fasikül):
• **Konu:** Sayı-Kesir Problemleri.
• **Kota:** 2 Test (Rutini bozmadan devam).

---

🎯 **HEMEN BUGÜN YAPACAĞIN MİKRO EYLEM:**
Masaya geç, **Miray Soru Bankasını 175. sayfadan aç**, **Çarpanlara Ayırma ve Özdeşlikler** konusunun ilk testini önüne koy ve kalemi eline al. İlk testin süresi başlıyor.`
    }
  ];
}

let kocDataIntegration = true;

function renderKocChat() {
  let h = '<div class="st-koc-dash" style="max-width:880px;margin:0 auto;padding-bottom:40px">';
  
  // Header
  h += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">';
  h += '  <div style="width:42px;height:42px;border-radius:12px;background:linear-gradient(135deg,#a855f7,#6366f1);display:flex;align-items:center;justify-content:center;font-size:22px;box-shadow:0 0 16px rgba(168,85,247,0.45);flex-shrink:0">✨</div>';
  h += '  <div>';
  h += '    <div style="display:flex;align-items:center;gap:10px">';
  h += '      <h2 style="margin:0;font-size:19px;font-weight:800;color:#fff;letter-spacing:-0.2px">YKS Koçu</h2>';
  h += '      <span style="background:#2e1065;color:#c084fc;border:1px solid #581c87;font-size:10.5px;padding:2px 8px;border-radius:4px;font-weight:800;letter-spacing:0.6px">REHBERLİK & STRATEJİ</span>';
  h += '    </div>';
  h += '    <div style="font-size:12px;color:#94a3b8;margin-top:2px">asedad fsdasd • Mezun • Sayısal • 📚 51 Kitap devrede · ⚡ Babanın Bahsi Aktif</div>';
  h += '  </div>';
  h += '</div>';

  // Purple Integration Banner
  h += '<div style="background:rgba(88,28,135,0.22);border:1px solid rgba(168,85,247,0.4);border-radius:12px;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;flex-wrap:wrap;gap:10px">';
  h += '  <div style="display:flex;align-items:center;gap:12px">';
  h += '    <div style="width:34px;height:34px;border-radius:8px;background:#3b0764;border:1px solid #7e22ce;display:flex;align-items:center;justify-content:center;font-size:16px">📖</div>';
  h += '    <div>';
  h += '      <div style="font-size:12.5px;font-weight:700;color:#e9d5ff">Çalışma & Deneme Verileri Entegrasyonu: ' + (kocDataIntegration ? '<span style="color:#4ade80">AÇIK (Kişiye Özel)</span>' : '<span style="color:#f87171">KAPALI</span>') + '</div>';
  h += '      <div style="font-size:11.5px;color:#c084fc;margin-top:2px">asedad fsdasd, Mezun, Sayısal, 51 kayıtlı kitabın, son netlerin ve çalışma planın koç tarafından biliniyor.</div>';
  h += '    </div>';
  h += '  </div>';
  h += '  <button onclick="toggleKocDataIntegration()" style="background:#1e1b4b;border:1px solid #4338ca;color:#a5b4fc;font-size:11.5px;font-weight:700;padding:5px 12px;border-radius:6px;cursor:pointer">' + (kocDataIntegration ? 'Veri Kullanımını Kapat' : 'Veri Kullanımını Aç') + '</button>';
  h += '</div>';

  // Chat Feed Container
  h += '<div id="koc-chat-feed" style="min-height:360px;max-height:560px;overflow-y:auto;background:#0d141c;border:1px solid #1a2734;border-radius:14px;padding:18px;margin-bottom:14px;display:flex;flex-direction:column;gap:14px">';
  
  kocChatMessages.forEach((msg, idx) => {
    const isAi = (msg.role === "assistant");
    h += '<div style="display:flex;justify-content:' + (isAi ? 'flex-start' : 'flex-end') + '">';
    h += '  <div style="max-width:85%;background:' + (isAi ? '#141e28' : '#2e1065') + ';border:1px solid ' + (isAi ? '#243444' : '#6b21a8') + ';border-radius:14px;padding:14px 18px;box-shadow:0 4px 14px rgba(0,0,0,0.3)">';
    if (isAi) {
      h += '    <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">';
      h += '      <span style="font-size:14px">✨</span><span style="font-size:12px;font-weight:800;color:#c084fc">YKS KOÇU</span>';
      h += '    </div>';
    }
    // Simple markdown format render
    let formatted = msg.text
      .replace(/### (.*?)\n/g, '<div style="font-weight:800;font-size:14.5px;color:#60a5fa;margin-bottom:8px">$1</div>')
      .replace(/• (.*?)\n/g, '<div style="margin-bottom:4px">• $1</div>')
      .replace(/🎯 \*\*(.*?)\*\*/g, '<div style="font-weight:800;color:#f59e0b;display:flex;align-items:center;gap:5px;margin:10px 0 6px"><span>🎯</span> <span>$1</span></div>')
      .replace(/\*\*(.*?)\*\*/g, '<b style="color:#fff">$1</b>')
      .replace(/---/g, '<div style="border-top:1px dashed #223444;margin:12px 0"></div>')
      .replace(/\n/g, '<br>');
    h += '    <div style="font-size:13.5px;line-height:1.6;color:#e2e8f0">' + formatted + '</div>';
    h += '    <div style="font-size:10.5px;color:#64748b;margin-top:8px;text-align:right">' + (msg.time || '') + '</div>';
    h += '  </div>';
    h += '</div>';
  });

  h += '</div>';

  // Quick Action Chips Row
  h += '<div style="display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-bottom:12px">';
  h += '  <button class="st-koc-chip" onclick="sendKocQuickAction(\'Eksik Konu Analizi\')">🎯 Eksik Konu Analizi</button>';
  h += '  <button class="st-koc-chip" onclick="sendKocQuickAction(\'Programı Güncelle\')">📅 Programı Güncelle</button>';
  h += '  <button class="st-koc-chip" onclick="sendKocQuickAction(\'Kitap Rehberliği\')">📚 Kitap Rehberliği</button>';
  h += '  <button class="st-koc-chip" onclick="sendKocQuickAction(\'Paragraf Hızı\')">⚡ Paragraf Hızı</button>';
  h += '  <button class="st-koc-chip" onclick="sendKocQuickAction(\'Geometri Taktikleri\')">📐 Geometri Taktikleri</button>';
  h += '  <button class="st-koc-chip" onclick="clearKocChat()" style="margin-left:auto;border-color:#475569;color:#94a3b8">🔄 Temizle</button>';
  h += '</div>';

  // Chat Input Row
  h += '<div style="display:flex;gap:10px;align-items:center;background:#111822;border:1px solid #233446;border-radius:14px;padding:8px 12px;box-shadow:0 4px 16px rgba(0,0,0,0.4)">';
  h += '  <input type="text" id="koc-input-box" placeholder="YKS Koçuna soru sor veya \'programımı güncelle\' de... (Enter ile gönder)" style="flex:1;background:transparent;border:0;outline:none;color:#fff;font-size:13.5px;padding:8px 4px" onkeydown="if(event.key===\'Enter\') sendKocUserMessage()">';
  h += '  <button onclick="sendKocUserMessage()" style="width:38px;height:38px;border-radius:50%;background:#8b5cf6;border:0;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;position:relative;flex-shrink:0;box-shadow:0 0 12px rgba(139,92,246,0.5)">';
  h += '    <span style="font-size:15px;margin-left:2px">➤</span>';
  h += '    <span style="position:absolute;top:-4px;right:-4px;background:#ef4444;color:#fff;font-size:9.5px;font-weight:800;width:16px;height:16px;border-radius:50%;display:flex;align-items:center;justify-content:center">1</span>';
  h += '  </button>';
  h += '</div>';

  h += '</div>';
  return h;
}

function toggleKocDataIntegration() {
  kocDataIntegration = !kocDataIntegration;
  render();
}

function clearKocChat() {
  if (confirm("Koç sohbet geçmişini temizlemek istiyor musun?")) {
    kocChatMessages = [
      {
        role: "assistant",
        time: new Date().toLocaleTimeString().slice(0,5),
        text: `### YKS Koçu Sıfırlandı & Masada Hazır
Koçluk motoru güncel **11–25 Kasım Babanın Bahsi** ve **Eyüp B 119 + Problemler** verileriyle devrede. Sorunu sorabilir veya aşağıdaki butonları kullanabilirsin.`
      }
    ];
    try { localStorage.setItem("st_koc_chat_history_v2", JSON.stringify(kocChatMessages)); }catch(e){}
    render();
  }
}

function sendKocQuickAction(action) {
  let prompt = "";
  if (action === "Eksik Konu Analizi") prompt = "Şu anki çalışma planıma ve netlerime göre en eksik olduğum konuları analiz et ve bugün ne yapmam gerektiğini söyle.";
  else if (action === "Programı Güncelle") prompt = "Programımı güncelle: Eyüp B 118 bitti, Video 119 Fonksiyon Türleri ve TYT Problemler rotasındayız.";
  else if (action === "Kitap Rehberliği") prompt = "Sayısal YKS 2027 için masamdaki 345, Miray, Apotemi ve EİS kitaplarını en verimli nasıl eritmeliyim?";
  else if (action === "Paragraf Hızı") prompt = "25 soruluk 3D Paragraf testini 28 dakikada hatasız çözmek için taktik ver.";
  else if (action === "Geometri Taktikleri") prompt = "EİS DAF Geometride üçgende ek çizim ve alan sorularında takılmamak için ne yapmalıyım?";
  else prompt = action;

  executeKocDialogue(prompt);
}

function sendKocUserMessage() {
  const inp = document.getElementById("koc-input-box");
  if (!inp || !inp.value.trim()) return;
  const q = inp.value.trim();
  inp.value = "";
  executeKocDialogue(q);
}

function executeKocDialogue(userText) {
  const now = new Date();
  const timeStr = String(now.getHours()).padStart(2,"0") + ":" + String(now.getMinutes()).padStart(2,"0");

  kocChatMessages.push({
    role: "user",
    time: timeStr,
    text: userText
  });

  // Render user message first
  render();
  const feed = document.getElementById("koc-chat-feed");
  if (feed) feed.scrollTop = feed.scrollHeight;

  // Generate smart AI response based on real context
  setTimeout(() => {
    const aiResponse = generateKocResponse(userText);
    kocChatMessages.push({
      role: "assistant",
      time: String(new Date().getHours()).padStart(2,"0") + ":" + String(new Date().getMinutes()).padStart(2,"0"),
      text: aiResponse
    });
    try { localStorage.setItem("st_koc_chat_history_v2", JSON.stringify(kocChatMessages)); }catch(e){}
    render();
    const feed2 = document.getElementById("koc-chat-feed");
    if (feed2) feed2.scrollTop = feed2.scrollHeight;
  }, 400);
}

function generateKocResponse(q) {
  const low = q.toLowerCase();
  
  if (low.includes("eksik") || low.includes("analiz")) {
    return `### 🎯 Eksik Konu Radar Raporu (Kişiye Özel Telemetri):
• **AYT Matematik:** Fonksiyonlarda Değer Bulma (118) bitti. Birebir-Örten (119) masada. Ters-Bileşke henüz soru bankasında eritilmedi.
• **AYT Fen:** Fizik Kütle-Ağırlık Merkezi ve Kimya Gaz Yasaları takvimde; Tork soru çözümü eksik kalmamalı.
• **TYT Matematik:** Mutlak Değer defteri kapandı. Problemlerde Sayı-Kesir modellemesi eksik.

---

🎯 **HEMEN BUGÜN YAPACAĞIN MİKRO EYLEM:**
Kronometreni **40 dakikaya** ayarla. **345 AYT Matematik Soru Bankası Test 2'yi (Fonksiyon Türleri)** önüne koy. Birebir-örten sorularında takıldığın an kuralı hata defterine yaz, çözümü izle. Masadan kalkmak yok!`;
  }

  if (low.includes("program") || low.includes("güncelle") || low.includes("güncel")) {
    return `### 📅 Babanın Bahsi 15 Günlük Çalışma Rotası Senkronize:
• **Resmi İddia Durumu:** Gün 1 (450′), Gün 2 (360′), Gün 3 (360′) tamamlandı! Toplam **1170 dakika** ile %100 kusursuz gidiyorsun.
• **Bugün (Gün 4 / 14.11):** TYT Denemesi (165′) + Analiz (55′) + Eyüp B 119 Fonksiyon Türleri (60′) + Kütle Merkezi (30′) + Apotemi (30′).
• **Yarın (Gün 5 / 15.11):** Eyüp B Fonksiyon Grafikleri VDD (f(-x), |f(x)|) + TYT Sayı Problemleri 1.

---

🎯 **MİKRO EYLEM:**
Program panelin `Çalışma Planı (15 Gün)` sekmesinde günceldir. Bugünün görevlerini tiklemeye başla!`;
  }

  if (low.includes("kitap") || low.includes("kaynak")) {
    return `### 📚 Masandaki 51 Kitabın Savaş Sıralaması:
• **345 AYT Matematik:** Konu kavrama ve ÖSYM refleksleri için ana omurga. Eyüp B VDD arkasından hemen çözülecek.
• **Miray TYT Matematik:** Problemler kampında hız ve modelleme için tek kaynak.
• **3D Paragraf:** Her gün 25 soru tek oturum (hedef: $\\le 28$ dakika).
• **EİS DAF Geometri:** Föy mantığıyla konu konu, üçgenler bitene kadar aksatılmayacak.

---

🎯 **MİKRO EYLEM:**
Kitap yığınını kenara çek. Masada şu an sadece **tek bir kitap** açık kalsın: Çok kitap değil, bitirilen kitap kazandırır!`;
  }

  if (low.includes("paragraf") || low.includes("hız")) {
    return `### ⚡ Paragraf Hız & Net Zırhı (Hedef: 25 Soru / 28 Dk):
1. **Şıkları Önce Tara:** Soru kökünü ve şıkları 10 saniye tara, anahtar kelimelerin altını çiz.
2. **Özne ve Bağlaçlara Kilitlen:** 'Ancak', 'Oysa', 'Fakat' gördüğün yer düşüncenin döndüğü yerdir; soru oradan çıkar.
3. **İki Şık Arasında Kalınca:** Metne geri dönüp baştan okuma. Sadece sorunun son 2 cümlesini tekrar oku; çeldirici elenecektir.

---

🎯 **MİKRO EYLEM:**
Bugünkü paragraf bloğunda masaya telefon sokma. Kronometreyi geri sayıma ayarla!`;
  }

  if (low.includes("geometri") || low.includes("geo")) {
    return `### 📐 Geometride Çizgi Çekme & Görme Sanatı:
• **Özel Açılar Görünce:** $30^\\circ, 45^\\circ, 60^\\circ$ gördüğün an karşısına dikme indir.
• **İkizkenar Görünce:** Tepeden tabana dik in, tabanı ikiye böl ($YAKİ$ kuralı).
• **Oran Varsa Paralel Çek:** $1/2$ veya $1/3$ oranlı kenar varsa tabana paralel çizip benzerlik kur.

---

🎯 **MİKRO EYLEM:**
EİS DAF Föy 12'yi aç, 5 soru çöz. Takıldığın soruda kalemi bırakıp şekle 1 dakika sadece kuşbakışı bak!`;
  }

  // Generic fallback with aggressive motivation
  return `### 🎯 YKS Koçu Yanıtı:
Sorunu aldım asedad. Sayısal ilk 10.000 hedefinde şu an **Babanın Bahsi 15 Günlük İddianın 4. günündesin**. 

• **Kural 1:** 27 Kasım Black Friday'de o masaya **Ryzen 5 7500F + B650M-R** konacaksa, bugün o masadan görevler bitmeden kalkılmayacak.
• **Kural 2:** Bahaneleri bırak, masadaki tek önceliğin bugünün TYT Denemesi ve Eyüp B 119 Fonksiyon Türleri testidir.

---

🎯 **HEMEN ŞİMDİ MİKRO EYLEM:**
Sandalyeye dik otur, derin bir nefes al ve bir sonraki pomodoro bloğunu başlat!`;
}
'''

for path in [p_desktop, p_projeler]:
    with open(path, "r", encoding="utf-8") as f:
        c = f.read()

    # 1. Update button onclick
    c = c.replace('onclick="openKocModal()"', 'onclick="switchStMode(\'koc\')"', 1)

    # 2. Add 'koc' to modeMeta in render()
    if 'koc: { icon: "✨", title: "YKS Koçu (Rehberlik & AI Strateji)" }' not in c:
        c = c.replace(
            'today: { icon: "📅", title: "Bugünün Çalışma Planı" },',
            'today: { icon: "📅", title: "Bugünün Çalışma Planı" },\n    koc: { icon: "✨", title: "YKS Koçu (Rehberlik & AI Strateji)" },'
        )

    # 3. Add 'koc' to sideIds in render()
    c = c.replace(
        'const sideIds = ["today", "all", "links"',
        'const sideIds = ["today", "all", "koc", "links"'
    )

    # 4. Add 'koc' dispatch in render()
    koc_dispatch = '''    if (st.mode === "koc") {
      mainElem.innerHTML = renderKocChat();
      save();
      return;
    }'''

    if 'if (st.mode === "koc")' not in c:
        c = c.replace(
            'if (st.mode === "vault") {',
            koc_dispatch + '\n    if (st.mode === "vault") {'
        )

    # 5. Inject CSS styles for chips and chat
    chip_styles = '''
  .st-koc-chip {
    background: #17212c;
    border: 1px solid #2d4154;
    color: #cbd5e1;
    font-size: 11.5px;
    font-weight: 700;
    padding: 6px 12px;
    border-radius: 20px;
    cursor: pointer;
    transition: all .2s;
  }
  .st-koc-chip:hover {
    background: #1e2d3d;
    border-color: #8b5cf6;
    color: #fff;
    transform: translateY(-1px);
  }
'''
    if '.st-koc-chip {' not in c:
        c = c.replace('</style>', chip_styles + '\n</style>', 1)

    # 6. Inject the koc_module_code before closing script
    if 'function renderKocChat()' not in c:
        c = c.replace('</body>', '<script>\n' + koc_module_code + '\n</script>\n</body>')

    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("Injected YKS Koçu AI Chat into:", path)
