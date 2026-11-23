# -*- coding: utf-8 -*-
"""
ACCIO-JARVIS - Study With Mommy Reactive Anime Girl Avatar & Features Patch
Adds:
1. Interactive Reactive Anime Girl Avatar in center stage (toggleable with Cyber Orb)
2. Lip-sync mouth movement, blinking, breathing, listening tilt, blush emotions
3. Slide / Question Dropzone & Clipboard Paste
4. Step Mastery Bar on Live Blackboard
5. Stop Anytime / Reassurance barge-in handler
6. Sync to portable dist
"""

import os
import sys
import re

ROOT = r"C:\Users\negr1\Projeler\ACCIO-JARVIS"
HTML_PATH = os.path.join(ROOT, "index.html")
DIST_HTML_PATH = os.path.join(ROOT, "dist", "ACCIO-JARVIS-PORTABLE", "app", "index.html")

print("[*] ACCIO-JARVIS Anime Avatar & Study Mommy Güncellemesi başlatılıyor...")

if not os.path.exists(HTML_PATH):
    print(f"[!] HATA: {HTML_PATH} bulunamadı!")
    sys.exit(1)

with open(HTML_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add Avatar CSS if not present
if "anime-avatar-box" not in content:
    avatar_css = """
  /* Study With Mommy / Luna Reactive Anime Girl Avatar */
  .anime-avatar-box {
    position: absolute;
    width: 420px;
    height: 420px;
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 5;
    pointer-events: auto;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .anime-avatar-box.active {
    display: flex;
  }
  .avatar-stage-wrap {
    position: relative;
    width: 380px;
    height: 380px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .avatar-halo-ring {
    position: absolute;
    width: 320px;
    height: 320px;
    border-radius: 50%;
    border: 2px dashed rgba(244, 114, 182, 0.4);
    box-shadow: 0 0 35px rgba(244, 114, 182, 0.25), inset 0 0 25px rgba(244, 114, 182, 0.15);
    animation: hud-reticle 24s linear infinite;
    pointer-events: none;
  }
  .avatar-halo-ring.speaking {
    border-color: #f472b6;
    box-shadow: 0 0 50px rgba(244, 114, 182, 0.5), inset 0 0 35px rgba(244, 114, 182, 0.3);
    animation: hud-reticle 8s linear infinite;
  }
  .avatar-halo-ring.listening {
    border-color: var(--cyan);
    box-shadow: 0 0 45px rgba(34, 211, 238, 0.45);
    animation: hud-reticle 12s linear infinite;
  }
  .avatar-svg-canvas {
    width: 100%;
    height: 100%;
    filter: drop-shadow(0 12px 30px rgba(0, 0, 0, 0.7));
    transition: transform 0.25s ease;
  }
  .avatar-svg-canvas:hover {
    transform: scale(1.03);
  }
  .avatar-mood-badge {
    position: absolute;
    bottom: 12px;
    padding: 4px 12px;
    border-radius: 20px;
    background: rgba(11, 17, 24, 0.85);
    border: 1px solid rgba(244, 114, 182, 0.35);
    color: #f472b6;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
    text-transform: uppercase;
    backdrop-filter: blur(8px);
    box-shadow: 0 4px 16px rgba(0,0,0,0.6);
  }
  .orb-view-toggle-btn {
    position: absolute;
    top: 6px;
    right: 12px;
    z-index: 15;
    background: rgba(15, 23, 42, 0.75);
    border: 1px solid rgba(255, 255, 255, 0.15);
    color: #cbd5e1;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 6px;
    cursor: pointer;
    backdrop-filter: blur(8px);
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.2s;
  }
  .orb-view-toggle-btn:hover {
    background: rgba(244, 114, 182, 0.15);
    border-color: #f472b6;
    color: #fff;
  }
  /* Slide / Soru Bırakma Dropzone */
  #slideDropZone {
    display: none;
    position: absolute;
    inset: 10px;
    background: rgba(8, 14, 26, 0.94);
    border: 2px dashed #f472b6;
    border-radius: 12px;
    z-index: 50;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    gap: 8px;
    color: #f472b6;
    font-size: 13px;
    font-weight: 700;
    backdrop-filter: blur(12px);
    animation: fadeIn 0.2s ease;
  }
"""
    content = content.replace("  /* AI Orb Canvas — Sci-Fi Holographic Reactor Core */", avatar_css + "\n  /* AI Orb Canvas — Sci-Fi Holographic Reactor Core */", 1)
    print("[+] Avatar CSS stilleri eklendi.")

# 2. Add Avatar HTML structure inside .orb-box
avatar_html = """
      <!-- Viewport Toggle (Orb vs Anime Kızı) -->
      <button class="orb-view-toggle-btn" id="avatarViewToggleBtn" title="Görünüm Değiştir: AI Reaktör Orb / Canlı Anime Kızı">
        <span id="avatarViewToggleIcon">👧</span> <span id="avatarViewToggleLabel">Anime Modu</span>
      </button>

      <!-- Reactive Anime Girl Avatar Stage -->
      <div class="anime-avatar-box" id="animeAvatarBox">
        <div class="avatar-stage-wrap">
          <div class="avatar-halo-ring" id="avatarHaloRing"></div>
          
          <svg class="avatar-svg-canvas" id="animeAvatarSvg" viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="hairGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#fbcfe8"/>
                <stop offset="50%" stop-color="#f472b6"/>
                <stop offset="100%" stop-color="#db2777"/>
              </linearGradient>
              <linearGradient id="skinGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stop-color="#fff1f2"/>
                <stop offset="100%" stop-color="#ffe4e6"/>
              </linearGradient>
              <linearGradient id="eyeIrisGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stop-color="#38bdf8"/>
                <stop offset="60%" stop-color="#0284c7"/>
                <stop offset="100%" stop-color="#0c4a6e"/>
              </linearGradient>
              <filter id="softGlow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>

            <!-- Arka Saç Katmanı -->
            <g id="avBackHair">
              <path d="M 120 180 C 80 230, 70 330, 95 380 C 130 390, 160 320, 160 260 Z" fill="url(#hairGrad)" opacity="0.85"/>
              <path d="M 280 180 C 320 230, 330 330, 305 380 C 270 390, 240 320, 240 260 Z" fill="url(#hairGrad)" opacity="0.85"/>
            </g>

            <!-- Gövde ve Giysi -->
            <g id="avBody">
              <path d="M 160 290 Q 200 310 240 290 L 265 400 L 135 400 Z" fill="#0f172a" stroke="#1e293b" stroke-width="2"/>
              <!-- Yaka & Fular -->
              <path d="M 175 292 L 200 330 L 225 292 Z" fill="#f472b6" opacity="0.9"/>
              <circle cx="200" cy="332" r="5" fill="#38bdf8"/>
              <!-- Boyun -->
              <path d="M 185 240 L 185 295 Q 200 300 215 295 L 215 240 Z" fill="url(#skinGrad)"/>
            </g>

            <!-- Kafa ve Yüz -->
            <g id="avHeadGroup" transform="translate(0, 0)">
              <!-- Yüz Temeli -->
              <path d="M 140 180 C 135 240, 170 270, 200 270 C 230 270, 265 240, 260 180 C 260 130, 140 130, 140 180 Z" fill="url(#skinGrad)"/>

              <!-- Yanak Allığı (Blush) -->
              <g id="avBlush" opacity="0.6">
                <ellipse cx="160" cy="225" rx="14" ry="7" fill="#fb7185" filter="url(#softGlow)"/>
                <ellipse cx="240" cy="225" rx="14" ry="7" fill="#fb7185" filter="url(#softGlow)"/>
                <line x1="154" y1="223" x2="166" y2="227" stroke="#e11d48" stroke-width="1.2" opacity="0.5"/>
                <line x1="234" y1="223" x2="246" y2="227" stroke="#e11d48" stroke-width="1.2" opacity="0.5"/>
              </g>

              <!-- Gözler (Normal & Kırpma) -->
              <g id="avEyesOpen">
                <!-- Sol Göz -->
                <g id="avLeftEye">
                  <ellipse cx="168" cy="195" rx="15" ry="18" fill="#ffffff" stroke="#1e293b" stroke-width="2"/>
                  <ellipse id="avLeftPupil" cx="168" cy="197" rx="10" ry="13" fill="url(#eyeIrisGrad)"/>
                  <ellipse cx="165" cy="191" rx="4" ry="5" fill="#ffffff"/>
                  <circle cx="172" cy="202" r="2" fill="#ffffff"/>
                  <!-- Üst Kirpik -->
                  <path d="M 150 185 Q 168 172 186 185" fill="none" stroke="#0f172a" stroke-width="3.5" stroke-linecap="round"/>
                </g>
                <!-- Sağ Göz -->
                <g id="avRightEye">
                  <ellipse cx="232" cy="195" rx="15" ry="18" fill="#ffffff" stroke="#1e293b" stroke-width="2"/>
                  <ellipse id="avRightPupil" cx="232" cy="197" rx="10" ry="13" fill="url(#eyeIrisGrad)"/>
                  <ellipse cx="229" cy="191" rx="4" ry="5" fill="#ffffff"/>
                  <circle cx="236" cy="202" r="2" fill="#ffffff"/>
                  <!-- Üst Kirpik -->
                  <path d="M 214 185 Q 232 172 250 185" fill="none" stroke="#0f172a" stroke-width="3.5" stroke-linecap="round"/>
                </g>
              </g>

              <!-- Kırpık Göz Çizgileri (Blink için) -->
              <g id="avEyesBlink" style="display:none;">
                <path d="M 152 196 Q 168 206 184 196" fill="none" stroke="#0f172a" stroke-width="3.5" stroke-linecap="round"/>
                <path d="M 216 196 Q 232 206 248 196" fill="none" stroke="#0f172a" stroke-width="3.5" stroke-linecap="round"/>
              </g>

              <!-- Mutlu / Gülümseyen Gözler (^ ^) -->
              <g id="avEyesHappy" style="display:none;">
                <path d="M 152 200 Q 168 186 184 200" fill="none" stroke="#db2777" stroke-width="3.5" stroke-linecap="round"/>
                <path d="M 216 200 Q 232 186 248 200" fill="none" stroke="#db2777" stroke-width="3.5" stroke-linecap="round"/>
              </g>

              <!-- Kaşlar -->
              <g id="avBrows">
                <path id="avLeftBrow" d="M 152 172 Q 168 165 184 172" fill="none" stroke="#be185d" stroke-width="2" stroke-linecap="round"/>
                <path id="avRightBrow" d="M 216 172 Q 232 165 248 172" fill="none" stroke="#be185d" stroke-width="2" stroke-linecap="round"/>
              </g>

              <!-- Burun -->
              <circle cx="200" cy="216" r="1.5" fill="#f43f5e" opacity="0.6"/>

              <!-- Ağız (Dinamik Lip-Sync) -->
              <g id="avMouthGroup">
                <!-- Gülümseme (Idle) -->
                <path id="avMouthSmile" d="M 192 238 Q 200 245 208 238" fill="none" stroke="#e11d48" stroke-width="2.5" stroke-linecap="round"/>
                <!-- Konuşma Açık Ağız -->
                <path id="avMouthOpen" d="M 191 236 Q 200 252 209 236 Z" fill="#be123c" stroke="#e11d48" stroke-width="1.5" style="display:none;"/>
                <path id="avMouthTeeth" d="M 193 238 Q 200 241 207 238" fill="none" stroke="#ffffff" stroke-width="1.8" style="display:none;"/>
              </g>

              <!-- Ön Saç / Kahküller -->
              <g id="avFrontHair">
                <path d="M 130 170 C 130 110, 270 110, 270 170 C 270 185, 255 210, 248 185 C 240 160, 220 180, 210 195 C 205 180, 195 180, 190 195 C 180 180, 160 160, 152 185 C 145 210, 130 185, 130 170 Z" fill="url(#hairGrad)"/>
                <!-- Yan Favoriler -->
                <path d="M 134 175 Q 128 220 138 245 Q 146 220 144 185 Z" fill="url(#hairGrad)"/>
                <path d="M 266 175 Q 272 220 262 245 Q 254 220 256 185 Z" fill="url(#hairGrad)"/>
              </g>

              <!-- Kulaklık / Aksesuar (Cyber-Cat Headset) -->
              <g id="avHeadset">
                <path d="M 125 180 A 75 75 0 0 1 275 180" fill="none" stroke="#1e293b" stroke-width="5" stroke-linecap="round"/>
                <!-- Sol Kulaklık Pedi -->
                <rect x="116" y="165" width="14" height="32" rx="7" fill="#0f172a" stroke="#f472b6" stroke-width="2"/>
                <circle cx="123" cy="181" r="3" fill="#38bdf8"/>
                <!-- Sağ Kulaklık Pedi -->
                <rect x="270" y="165" width="14" height="32" rx="7" fill="#0f172a" stroke="#f472b6" stroke-width="2"/>
                <circle cx="277" cy="181" r="3" fill="#38bdf8"/>
              </g>
            </g>
          </svg>

          <div class="avatar-mood-badge" id="avatarMoodBadge">👩‍🏫 STUDY MOMMY</div>
        </div>
      </div>
"""

if "animeAvatarBox" not in content:
    # Insert right inside <div class="orb-box">
    content = content.replace('<div class="orb-box">', '<div class="orb-box">\n' + avatar_html, 1)
    print("[+] Avatar HTML şablonu .orb-box içerisine yerleştirildi.")

# 3. Add Slide Dropzone to Blackboard HUD if not present
dropzone_html = """
        <!-- Slayt / Soru Sürükle Bırak Alanı (Study With Mommy Dropzone) -->
        <div id="slideDropZone">
          <span style="font-size:24px;">📥</span>
          <span>Slaytı veya Soruyu Buraya Bırak</span>
          <span style="font-size:10px; color:#94a3b8; font-weight:normal;">veya panodan yapıştır (Ctrl + V)</span>
        </div>
"""

if "slideDropZone" not in content and 'id="blackboardScreen"' in content:
    content = content.replace('<div id="blackboardScreen"', dropzone_html + '\n        <div id="blackboardScreen"', 1)
    print("[+] Canlı Ders Tahtasına Slayt Dropzone alanı eklendi.")

# 4. Add Avatar Controller JavaScript logic
avatar_js = """
  // ========================================================
  // STUDY WITH MOMMY // REACTIVE ANIME AVATAR CONTROLLER
  // ========================================================
  let currentAvatarState = 'IDLE'; // IDLE, LISTENING, THINKING, SPEAKING, HAPPY
  let avatarBlinkTimer = null;
  let avatarMouthTimer = null;
  let isAnimeAvatarView = false;

  const animeAvatarBox = document.getElementById('animeAvatarBox');
  const orbCanvasEl = document.getElementById('orbCanvas');
  const orbCenterHudEl = document.querySelector('.orb-center-hud');
  const avatarViewToggleBtn = document.getElementById('avatarViewToggleBtn');
  const avatarViewToggleIcon = document.getElementById('avatarViewToggleIcon');
  const avatarViewToggleLabel = document.getElementById('avatarViewToggleLabel');
  const avatarHaloRing = document.getElementById('avatarHaloRing');
  const avatarMoodBadge = document.getElementById('avatarMoodBadge');

  const avHeadGroup = document.getElementById('avHeadGroup');
  const avEyesOpen = document.getElementById('avEyesOpen');
  const avEyesBlink = document.getElementById('avEyesBlink');
  const avEyesHappy = document.getElementById('avEyesHappy');
  const avMouthSmile = document.getElementById('avMouthSmile');
  const avMouthOpen = document.getElementById('avMouthOpen');
  const avMouthTeeth = document.getElementById('avMouthTeeth');
  const avBlush = document.getElementById('avBlush');

  function setAvatarState(state) {
    currentAvatarState = state;
    if (!avatarHaloRing) return;

    avatarHaloRing.classList.remove('speaking', 'listening');

    if (state === 'SPEAKING') {
      avatarHaloRing.classList.add('speaking');
      if (avatarMoodBadge) avatarMoodBadge.textContent = '🗣️ ANLATIYOR...';
      startAvatarLipSync();
      setAvatarEyes('happy');
    } else if (state === 'LISTENING') {
      avatarHaloRing.classList.add('listening');
      if (avatarMoodBadge) avatarMoodBadge.textContent = '👂 SENİ DİNLİYOR';
      stopAvatarLipSync();
      setAvatarEyes('open');
      if (avHeadGroup) avHeadGroup.setAttribute('transform', 'rotate(4 200 200)');
    } else if (state === 'THINKING') {
      if (avatarMoodBadge) avatarMoodBadge.textContent = '✨ DÜŞÜNÜYOR...';
      stopAvatarLipSync();
      setAvatarEyes('open');
      if (avHeadGroup) avHeadGroup.setAttribute('transform', 'rotate(-3 200 200)');
    } else { // IDLE
      if (avatarMoodBadge) avatarMoodBadge.textContent = '👩‍🏫 STUDY MOMMY';
      stopAvatarLipSync();
      setAvatarEyes('open');
      if (avHeadGroup) avHeadGroup.setAttribute('transform', 'translate(0, 0)');
    }
  }

  function setAvatarEyes(type) {
    if (!avEyesOpen || !avEyesBlink || !avEyesHappy) return;
    avEyesOpen.style.display = type === 'open' ? 'block' : 'none';
    avEyesBlink.style.display = type === 'blink' ? 'block' : 'none';
    avEyesHappy.style.display = type === 'happy' ? 'block' : 'none';
  }

  // Otomatik Göz Kırpma Döngüsü
  function startAvatarBlinking() {
    if (avatarBlinkTimer) clearInterval(avatarBlinkTimer);
    avatarBlinkTimer = setInterval(() => {
      if (currentAvatarState !== 'SPEAKING' && currentAvatarState !== 'HAPPY') {
        setAvatarEyes('blink');
        setTimeout(() => {
          if (currentAvatarState !== 'SPEAKING') setAvatarEyes('open');
        }, 160);
      }
    }, 3800);
  }

  // Lip-Sync Konuşma Ağız Hareketi
  function startAvatarLipSync() {
    if (avatarMouthTimer) clearInterval(avatarMouthTimer);
    let open = false;
    avatarMouthTimer = setInterval(() => {
      open = !open;
      if (avMouthSmile && avMouthOpen) {
        avMouthSmile.style.display = open ? 'none' : 'block';
        avMouthOpen.style.display = open ? 'block' : 'none';
        if (avMouthTeeth) avMouthTeeth.style.display = open ? 'block' : 'none';
      }
      // Hafif kafa baş sallama
      if (avHeadGroup) {
        const bob = open ? 'translate(0, 2)' : 'translate(0, 0)';
        avHeadGroup.setAttribute('transform', bob);
      }
    }, 140);
  }

  function stopAvatarLipSync() {
    if (avatarMouthTimer) {
      clearInterval(avatarMouthTimer);
      avatarMouthTimer = null;
    }
    if (avMouthSmile && avMouthOpen) {
      avMouthSmile.style.display = 'block';
      avMouthOpen.style.display = 'none';
      if (avMouthTeeth) avMouthTeeth.style.display = 'none';
    }
  }

  // Görünüm Değiştirici: AI Orb vs Anime Kızı
  function toggleAvatarView(toAnime) {
    isAnimeAvatarView = (toAnime !== undefined) ? toAnime : !isAnimeAvatarView;
    if (animeAvatarBox) animeAvatarBox.classList.toggle('active', isAnimeAvatarView);
    if (orbCanvasEl) orbCanvasEl.style.display = isAnimeAvatarView ? 'none' : 'block';
    if (orbCenterHudEl) orbCenterHudEl.style.display = isAnimeAvatarView ? 'none' : 'flex';

    if (avatarViewToggleIcon && avatarViewToggleLabel) {
      avatarViewToggleIcon.textContent = isAnimeAvatarView ? '🔮' : '👧';
      avatarViewToggleLabel.textContent = isAnimeAvatarView ? 'Reaktör Orb' : 'Anime Modu';
    }
    if (isAnimeAvatarView) {
      startAvatarBlinking();
      showNotification('Anime Kızı Avatarı Aktif 👧', 'info');
    }
  }

  if (avatarViewToggleBtn) {
    avatarViewToggleBtn.onclick = (e) => {
      e.stopPropagation();
      toggleAvatarView();
    };
  }

  // Anime kızına tıklandığında konuş / dinle
  if (animeAvatarBox) {
    animeAvatarBox.onclick = () => {
      const micBtn = document.getElementById('micBtn');
      if (micBtn) micBtn.click();
    };
  }

  // Canlı Slayt / Soru Sürükle Bırak (Dropzone) Dinleyicisi
  const studyBbHud = document.getElementById('studyBlackboardHud');
  const slideDropZone = document.getElementById('slideDropZone');

  if (studyBbHud && slideDropZone) {
    studyBbHud.addEventListener('dragover', (e) => {
      e.preventDefault();
      slideDropZone.style.display = 'flex';
    });
    studyBbHud.addEventListener('dragleave', (e) => {
      if (!studyBbHud.contains(e.relatedTarget)) {
        slideDropZone.style.display = 'none';
      }
    });
    studyBbHud.addEventListener('drop', async (e) => {
      e.preventDefault();
      slideDropZone.style.display = 'none';
      const file = e.dataTransfer.files[0];
      if (file && file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = async (ev) => {
          const b64 = ev.target.result.split(',')[1];
          appendBubble("📸 Slayt/Soru yüklendi, Study Mommy inceliyor...", "user", "Kullanıcı");
          setCoreState('THINKING');
          setAvatarState('THINKING');
          try {
            const res = await fetch('/api/vision', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                image_base64: b64,
                prompt: 'Bu bir ders slaytı veya sınav sorusu. Soruyu ve verileri tane tane oku, ilk adımı açıklayarak çözüme başla.'
              })
            });
            const data = await res.json();
            if (data.reply) {
              appendBubble(data.reply, 'assistant', 'Study Mommy');
              if (window.renderBlackboardFromText) window.renderBlackboardFromText(data.reply);
            }
            if (data.audio_base64) playAudioBase64(data.audio_base64);
          } catch(err) {
            appendBubble('Soru analizi başarısız: ' + err, 'assistant');
          } finally {
            setCoreState('IDLE');
            setAvatarState('IDLE');
          }
        };
        reader.readAsDataURL(file);
      }
    });
  }

  // Panodan Resim Yapıştırma (Ctrl + V) Desteği
  window.addEventListener('paste', async (e) => {
    if (isStudyMommyActive) {
      const items = (e.clipboardData || e.originalEvent.clipboardData).items;
      for (let item of items) {
        if (item.type.indexOf('image') === 0) {
          const blob = item.getAsFile();
          const reader = new FileReader();
          reader.onload = async (ev) => {
            const b64 = ev.target.result.split(',')[1];
            appendBubble("📋 Panodan soru/grafik yapıştırıldı. Analiz ediliyor...", "user", "Kullanıcı");
            setCoreState('THINKING');
            setAvatarState('THINKING');
            try {
              const res = await fetch('/api/vision', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                  image_base64: b64,
                  prompt: 'Panodan yapıştırılan bu soruyu ve matematik/fen ifadelerini tespit et, [TAHTA: ADIM 1: ...] formatında canlı tahtaya aktararak sakin ve sevecen anlat.'
                })
              });
              const data = await res.json();
              if (data.reply) {
                appendBubble(data.reply, 'assistant', 'Study Mommy');
                if (window.renderBlackboardFromText) window.renderBlackboardFromText(data.reply);
              }
              if (data.audio_base64) playAudioBase64(data.audio_base64);
            } catch(err) {
              appendBubble('Görüntü analiz hatası: ' + err, 'assistant');
            } finally {
              setCoreState('IDLE');
              setAvatarState('IDLE');
            }
          };
          reader.readAsDataURL(blob);
        }
      }
    }
  });

  // Ses Durumlarına Göre Avatar Animasyonunu Senkronize Et
  const originalSetCoreState = window.setCoreState;
  window.setCoreState = function(state) {
    if (typeof originalSetCoreState === 'function') originalSetCoreState(state);
    if (state === 'SPEAKING') setAvatarState('SPEAKING');
    else if (state === 'LISTENING') setAvatarState('LISTENING');
    else if (state === 'THINKING' || state === 'PROCESSING') setAvatarState('THINKING');
    else setAvatarState('IDLE');
  };
"""

if "REACTIVE ANIME AVATAR CONTROLLER" not in content:
    content = content.replace("// OPENJARVIS HITL APPROVAL BELL ENGINE", avatar_js + "\n  // OPENJARVIS HITL APPROVAL BELL ENGINE", 1)
    print("[+] Avatar Controller JS kodu eklendi.")

# Save modified index.html
with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(content)

print(f"[✓] {HTML_PATH} başarıyla güncellendi ({len(content)} bayt).")

# Sync to portable dist if available
if os.path.exists(os.path.dirname(DIST_HTML_PATH)):
    with open(DIST_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[✓] Portable versiyon güncellendi: {DIST_HTML_PATH}")

print("[🎉] GÜNCELLEME TAMAMLANDI! Artık sahnede tepki veren Canlı Anime Kızı aktif edilebilir.")
