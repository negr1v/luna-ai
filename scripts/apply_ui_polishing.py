# -*- coding: utf-8 -*-
"""
LUNA-AI UI Polishing & Sidebar Streamlining Script
1. Premium Cyber-Glass Button & Chip Styling (High-end gradients, glow, micro-interactions)
2. Cohesive Quick Chips Bar (Data Sources, YKS, Telegram, AM5, Ekran, Study Mommy, Anime Kızı)
3. Streamlined Left Sidebar: groups related categories logically, removes visual clutter
4. Syntax validation via Node.js
5. Sync to portable dist
"""

import os
import sys
import re
import subprocess

ROOT = r"C:\Users\negr1\Projeler\LUNA-AI"
HTML_PATH = os.path.join(ROOT, "index.html")
DIST_HTML_PATH = os.path.join(ROOT, "dist", "LUNA-AI-PORTABLE", "app", "index.html")

print("[*] LUNA-AI UI Kalite & Sadeleştirme güncellemesi başlatılıyor...")

if not os.path.exists(HTML_PATH):
    print(f"[!] HATA: {HTML_PATH} bulunamadı!")
    sys.exit(1)

with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# =========================================================================
# 1. UPGRADE CSS: Premium Cyber-Glass Buttons, Chips & Refined Header
# =========================================================================
premium_css = """
  /* ========================================================
     PREMIUM CYBER-GLASS BUTTONS & CHIPS (ULTRA QUALITY HUD)
     ======================================================== */
  .btn-sm, .cyber-btn {
    background: linear-gradient(180deg, rgba(18, 26, 42, 0.75) 0%, rgba(10, 16, 28, 0.85) 100%) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    color: #e2e8f0 !important;
    padding: 6px 12px !important;
    border-radius: 8px !important;
    cursor: pointer !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px !important;
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    backdrop-filter: blur(14px) !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
    transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1) !important;
    user-select: none !important;
  }
  .btn-sm:hover, .cyber-btn:hover {
    background: linear-gradient(180deg, rgba(30, 42, 68, 0.85) 0%, rgba(16, 24, 42, 0.95) 100%) !important;
    border-color: rgba(34, 211, 238, 0.45) !important;
    color: #ffffff !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 16px rgba(34, 211, 238, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.15) !important;
  }
  .btn-sm:active, .cyber-btn:active {
    transform: translateY(1px) scale(0.98) !important;
  }

  /* Premium Quick Action Chips Deck */
  .welcome-quick-chips {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 8px !important;
    justify-content: center !important;
    align-items: center !important;
    max-width: 860px !important;
    margin: 8px auto 14px auto !important;
    padding: 8px 12px !important;
    background: rgba(10, 15, 26, 0.65) !important;
    border: 1px solid rgba(255, 255, 255, 0.07) !important;
    border-radius: 20px !important;
    backdrop-filter: blur(20px) !important;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
  }

  .quick-chip-premium {
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    padding: 6px 14px !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    letter-spacing: 0.2px !important;
    border-radius: 14px !important;
    background: rgba(255, 255, 255, 0.03) !important;
    border: 1px solid rgba(255, 255, 255, 0.09) !important;
    color: #cbd5e1 !important;
    cursor: pointer !important;
    transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1) !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3) !important;
  }
  .quick-chip-premium:hover {
    background: rgba(255, 255, 255, 0.08) !important;
    color: #ffffff !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5) !important;
  }

  /* Specific Glowing Accents for High-Impact Chips */
  .quick-chip-data {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(6, 182, 212, 0.08) 100%) !important;
    border-color: rgba(16, 185, 129, 0.35) !important;
    color: #34d399 !important;
  }
  .quick-chip-data:hover {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.22) 0%, rgba(6, 182, 212, 0.16) 100%) !important;
    border-color: #10b981 !important;
    color: #ffffff !important;
    box-shadow: 0 0 16px rgba(16, 185, 129, 0.3) !important;
  }

  .quick-chip-mommy {
    background: linear-gradient(135deg, rgba(244, 114, 182, 0.14) 0%, rgba(219, 39, 119, 0.08) 100%) !important;
    border-color: rgba(244, 114, 182, 0.35) !important;
    color: #f472b6 !important;
  }
  .quick-chip-mommy:hover {
    background: linear-gradient(135deg, rgba(244, 114, 182, 0.25) 0%, rgba(219, 39, 119, 0.18) 100%) !important;
    border-color: #f472b6 !important;
    color: #ffffff !important;
    box-shadow: 0 0 16px rgba(244, 114, 182, 0.35) !important;
  }

  .quick-chip-scan {
    background: linear-gradient(135deg, rgba(56, 189, 248, 0.12) 0%, rgba(14, 165, 233, 0.08) 100%) !important;
    border-color: rgba(56, 189, 248, 0.35) !important;
    color: var(--cyan) !important;
  }
  .quick-chip-scan:hover {
    background: linear-gradient(135deg, rgba(56, 189, 248, 0.22) 0%, rgba(14, 165, 233, 0.18) 100%) !important;
    border-color: var(--cyan) !important;
    color: #ffffff !important;
    box-shadow: 0 0 16px rgba(56, 189, 248, 0.3) !important;
  }

  .quick-chip-anime {
    background: linear-gradient(135deg, rgba(168, 85, 247, 0.14) 0%, rgba(236, 72, 153, 0.08) 100%) !important;
    border-color: rgba(168, 85, 247, 0.35) !important;
    color: #c084fc !important;
  }
  .quick-chip-anime:hover {
    background: linear-gradient(135deg, rgba(168, 85, 247, 0.24) 0%, rgba(236, 72, 153, 0.18) 100%) !important;
    border-color: #c084fc !important;
    color: #ffffff !important;
    box-shadow: 0 0 16px rgba(168, 85, 247, 0.35) !important;
  }

  /* Refined Top Navigation Trigger Bar */
  .hover-panel-trigger {
    background: rgba(15, 23, 42, 0.6) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 8px !important;
    padding: 5px 12px !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    color: #94a3b8 !important;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
  }
  .hover-panel-trigger:hover, .hover-panel-trigger.active {
    background: rgba(34, 211, 238, 0.1) !important;
    border-color: rgba(34, 211, 238, 0.35) !important;
    color: #ffffff !important;
    box-shadow: 0 2px 10px rgba(34, 211, 238, 0.15) !important;
  }
"""

if "PREMIUM CYBER-GLASS BUTTONS & CHIPS" not in html:
    html = html.replace("</style>", premium_css + "\n</style>", 1)
    print("[+] Premium Cyber-Glass CSS stilleri enjekte edildi.")

# =========================================================================
# 2. STREAMLINE LEFT SIDEBAR: Group related items logically
# =========================================================================
# Replace old Group 1, Group 2, Group 3 in sidebar with streamlined 2 clean groups:
old_sidebar_regex = r'<!-- Group 1: ANA MENÜ -->[\s\S]*?<!-- Group 3: BİLİŞ & OTOMASYON -->[\s\S]*?</div>\s*</div>'

new_sidebar_html = """<!-- Group 1: STÜDYO & AKIL (WORKSPACE) -->
    <div>
      <div class="sidebar-section-title" style="font-size:10px; font-weight:800; color:#38bdf8; letter-spacing:1px; margin-bottom:6px; padding-left:4px; display:flex; align-items:center; gap:6px;">
        <span>⚡</span> STÜDYO & ÇALIŞMA
      </div>
      <div class="sidebar-nav-group" style="display:flex; flex-direction:column; gap:3px;">
        <button class="sidebar-item active hud-cat-btn" data-view="cockpit" onclick="switchView('cockpit')">
          <span class="item-icon">⚡</span>
          <span>Dashboard & AI</span>
        </button>
        <button class="sidebar-item hud-cat-btn" data-view="holoCommand" onclick="switchView('holoCommand')">
          <span class="item-icon">💬</span>
          <span>Chat & Konsol</span>
        </button>
        <button class="sidebar-item hud-cat-btn" data-view="radarLab" onclick="switchView('radarLab')">
          <span class="item-icon">🔬</span>
          <span>Deep Research</span>
        </button>
        <button class="sidebar-item hud-cat-btn" data-view="memory" id="navTabMemory" onclick="switchView('memory')">
          <span class="item-icon">🧠</span>
          <span>Hafıza & Data Sources</span>
          <span class="sidebar-badge" id="memoryNavBadge" style="display:none; background:#06b6d4; color:#000;">0</span>
        </button>
      </div>
    </div>

    <!-- Group 2: SİSTEM & TELEMETRİ (OPS) -->
    <div>
      <div class="sidebar-section-title" style="font-size:10px; font-weight:800; color:#94a3b8; letter-spacing:1px; margin-bottom:6px; padding-left:4px; display:flex; align-items:center; gap:6px;">
        <span>🖥️</span> SİSTEM & OTOMASYON
      </div>
      <div class="sidebar-nav-group" style="display:flex; flex-direction:column; gap:3px;">
        <button class="sidebar-item hud-cat-btn" data-view="automations" id="navTabAutomations" onclick="switchView('automations')">
          <span class="item-icon">⏱️</span>
          <span>Görevler & Radarlar</span>
          <span class="sidebar-badge" id="autoNavBadge" style="display:none; background:#f59e0b; color:#000;">0</span>
        </button>
        <button class="sidebar-item hud-cat-btn" data-view="system" onclick="switchView('system')">
          <span class="item-icon">🖥️</span>
          <span>Sistem & Telemetri</span>
        </button>
        <button class="sidebar-item hud-cat-btn" data-view="securityDiag" onclick="switchView('securityDiag')">
          <span class="item-icon">🛡️</span>
          <span>Güvenlik & Loglar</span>
        </button>
      </div>
    </div>"""

if re.search(old_sidebar_regex, html):
    html = re.sub(old_sidebar_regex, new_sidebar_html, html, count=1)
    print("[+] Sol menü sadeleştirildi ve ilgili kategoriler tek çatı altında toplandı.")

# =========================================================================
# 3. UPGRADE WELCOME QUICK CHIPS (Data Sources + All Actions In Cohesive Flow)
# =========================================================================
old_chips_regex = r'<div class="welcome-quick-chips"[\s\S]*?</div>\s*</div>\s*</div>'

new_chips_html = """<div class="welcome-quick-chips">
        <button id="chipDataSourcesBtn" class="quick-chip-premium quick-chip-data" title="Veri Kaynakları & Akıllı Hafıza Grafiği">
          <span>🧠</span> Data Sources & Graph
        </button>
        <button id="chipStudyMommyBtn" class="quick-chip-premium quick-chip-mommy" title="Study With Mommy: Şefkatli Ders Partneri & Canlı Tahta">
          <span>👩‍🏫</span> Şefkatli Ders (Tahta)
        </button>
        <button id="chipScreenScanBtn" class="quick-chip-premium quick-chip-scan" title="Ekrandaki Soruyu / Pencereyi Tara">
          <span>📸</span> Ekranı İncele
        </button>
        <button id="chipAnimeAvatarBtn" class="quick-chip-premium quick-chip-anime" title="Canlı Tepki Veren Anime Kızı Modunu Aç/Kapat">
          <span>👧</span> Anime Avatarı
        </button>
        <button id="chipYksTasksBtn" class="quick-chip-premium" title="YKS 2027 Sayısal Hedefleri & Günlük Görevler">
          <span>⏱️</span> YKS & Görevler
        </button>
        <button id="chipTelegramRadarBtn" class="quick-chip-premium" title="Telegram Fırsat ve Bildirim Radarı">
          <span>✈️</span> Telegram Radar
        </button>
        <button id="chipAm5PriceBtn" class="quick-chip-premium" title="Ryzen 7500F / B650 AM5 Canlı Fiyat Takibi">
          <span>🖥️</span> AM5 Fırsat
        </button>
      </div>
    </div>"""

if '<div class="welcome-quick-chips"' in html:
    # Match from welcome-quick-chips to end of welcome deck
    deck_pattern = r'<div class="welcome-quick-chips"[\s\S]*?</div>\s*</div>'
    html = re.sub(deck_pattern, new_chips_html, html, count=1)
    print("[+] Karşılama çipleri ve Data Sources düğmeleri premium seviyeye yükseltildi.")

# =========================================================================
# 4. WIRE chipAnimeAvatarBtn in JS if needed
# =========================================================================
if "chipAnimeAvatarBtn" in html and "chipAnimeAvatarBtn" not in html[html.find("<script>"): ]:
    wire_chip_js = """
  document.getElementById('chipAnimeAvatarBtn')?.addEventListener('click', () => {
    if (typeof toggleAvatarView === 'function') toggleAvatarView();
    else document.getElementById('avatarViewToggleBtn')?.click();
  });
"""
    html = html.replace("// Hızlı Çip Bağlantıları", "// Hızlı Çip Bağlantıları" + wire_chip_js, 1)

# Write output file
with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"[✓] Ana HTML kaydedildi: {HTML_PATH}")

# Sync to portable dist
if os.path.exists(DIST_HTML_PATH):
    with open(DIST_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[✓] Portable kopyası eşitlendi: {DIST_HTML_PATH}")

# Syntax check
node_test = '''
const fs = require('fs');
const html = fs.readFileSync('C:/Users/negr1/Projeler/LUNA-AI/index.html', 'utf8');
const scriptRegex = /<script>([\s\S]*?)<\/script>/gi;
let match, count = 0;
while ((match = scriptRegex.exec(html)) !== null) {
  count++;
  try {
    new Function(match[1]);
    console.log('Script ' + count + ' SYNTAX PERFECT!');
  } catch (err) {
    console.error('SCRIPT ' + count + ' SYNTAX ERROR:', err.message);
  }
}
'''
res = subprocess.run(['node', '-e', node_test], capture_output=True, text=True)
print("NODE CHECK:", res.stdout.strip())
if res.stderr:
    print("NODE STDERR:", res.stderr.strip())

print("[🎉] ARAYÜZ VE MENÜ GÜNCELLEMESİ BAŞARIYLA TAMAMLANDI!")
