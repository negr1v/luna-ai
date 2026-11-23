# -*- coding: utf-8 -*-
import os, sys, re, subprocess

ROOT = r"C:\Users\negr1\Projeler\ACCIO-JARVIS"
HTML_PATH = os.path.join(ROOT, "index.html")
DIST_HTML_PATH = os.path.join(ROOT, "dist", "ACCIO-JARVIS-PORTABLE", "app", "index.html")

with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# 1. Add floating breathing keyframe to avatar CSS
if "avatarBreathe" not in html:
    breathe_css = """
  @keyframes avatarBreathe {
    0%, 100% { transform: translateY(0px) scale(1); }
    50% { transform: translateY(-6px) scale(1.015); }
  }
  .avatar-stage-wrap {
    animation: avatarBreathe 3.6s ease-in-out infinite;
  }
"""
    html = html.replace(".avatar-stage-wrap {", breathe_css + "\n  .avatar-stage-wrap {", 1)

# 2. Make animeAvatarBox active & visible by default in HTML
html = html.replace(
    '<div class="anime-avatar-box" id="animeAvatarBox">',
    '<div class="anime-avatar-box active" id="animeAvatarBox" style="display:flex;">',
    1
)

# 3. Hide orbCanvas and orb-center-hud by default in HTML
html = html.replace(
    '<canvas id="orbCanvas" width="500" height="500" title="Tıkla: Konuş / Sözünü Kes"></canvas>',
    '<canvas id="orbCanvas" width="500" height="500" title="Tıkla: Konuş / Sözünü Kes" style="display:none;"></canvas>',
    1
)

html = html.replace(
    '<div class="orb-center-hud">',
    '<div class="orb-center-hud" style="display:none;">',
    1
)

# 4. Set toggle button text to show "Reaktör Orb" as alternative
html = html.replace(
    '<span id="avatarViewToggleIcon">👧</span> <span id="avatarViewToggleLabel">Anime Modu</span>',
    '<span id="avatarViewToggleIcon">🔮</span> <span id="avatarViewToggleLabel">Reaktör Orb</span>',
    1
)

# 5. Set JS default state isAnimeAvatarView = true
html = html.replace('let isAnimeAvatarView = false;', 'let isAnimeAvatarView = true;', 1)

# Ensure startAvatarBlinking() is called on DOM init
if "startAvatarBlinking();" not in html[html.find("window.addEventListener('DOMContentLoaded'"): ]:
    html = html.replace(
        "window.addEventListener('DOMContentLoaded', () => {",
        "window.addEventListener('DOMContentLoaded', () => {\n    if (typeof startAvatarBlinking === 'function') startAvatarBlinking();",
        1
    )

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

if os.path.exists(DIST_HTML_PATH):
    with open(DIST_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)

print("[✓] index.html anime girl default olarak ayarlandı!")
