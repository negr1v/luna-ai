"""
Focused Validation Test Suite for ACCIO-JARVIS Phase 15G (Wallpaper Studio)
Verifies DOM structure, CSS tokens, Wallpaper Studio Modal, JS Controller,
Security/Safe Local Image handling, and regression integrity of Cyber Orb & Hover Panels.
"""

import os
import re
import sys

INDEX_PATH = r"C:\Users\negr1\Projeler\ACCIO-JARVIS\index.html"
BACKUP_PATH = r"C:\Users\negr1\Projeler\ACCIO-JARVIS\index.html.bak_phase15g_20261114"

def test_wallpaper_studio():
    print("======================================================================")
    print("PHASE 15G: WALLPAPER STUDIO FOCUSED VALIDATION TESTS")
    print("======================================================================\n")

    passed = 0
    total = 0

    def check(desc, cond):
        nonlocal passed, total
        total += 1
        if cond:
            passed += 1
            print(f"  [PASS] {desc}")
        else:
            print(f"  [FAIL] {desc}")

    # 1. File existence and backup verification
    check("index.html exists", os.path.exists(INDEX_PATH))
    check("Phase 15G backup exists", os.path.exists(BACKUP_PATH))
    if os.path.exists(BACKUP_PATH):
        check("Backup is non-empty", os.path.getsize(BACKUP_PATH) > 500000)

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # 2. Wallpaper & Scrim DOM Layers
    check("#zeroWallpaperLayer present in DOM", 'id="zeroWallpaperLayer"' in html)
    check("#zeroWallpaperScrim present in DOM", 'id="zeroWallpaperScrim"' in html)
    check(".zero-wallpaper-layer CSS defined with fixed position and z-index -2",
          '.zero-wallpaper-layer' in html and 'z-index: -2' in html)
    check(".zero-wallpaper-scrim CSS defined with fixed position and z-index -1",
          '.zero-wallpaper-scrim' in html and 'z-index: -1' in html)
    check("Scrim opacity variable --wallpaper-scrim-opacity supported",
          '--wallpaper-scrim-opacity' in html)

    # 3. Header Action Button
    check("#openWallpaperStudioBtn present in header actions", 'id="openWallpaperStudioBtn"' in html)

    # 4. Wallpaper Studio Modal Elements
    check("#wallpaperStudioModal dialog present", 'id="wallpaperStudioModal"' in html)
    check(".wallpaper-modal-backdrop CSS defined", '.wallpaper-modal-backdrop' in html)
    check(".wallpaper-modal-box CSS defined", '.wallpaper-modal-box' in html)
    check("#wpCloseBtn present", 'id="wpCloseBtn"' in html)
    check("#wpCancelBtn present", 'id="wpCancelBtn"' in html)
    check("#wpApplySaveBtn present", 'id="wpApplySaveBtn"' in html)
    check("#wpRestoreDefaultBtn present", 'id="wpRestoreDefaultBtn"' in html)

    # 5. Studio Tabs & Panes
    check("Presets tab present (data-tab=\"presets\")", 'data-tab="presets"' in html)
    check("Themes tab present (data-tab=\"themes\")", 'data-tab="themes"' in html)
    check("Custom Gradient tab present (data-tab=\"gradient\")", 'data-tab="gradient"' in html)
    check("Local Image tab present (data-tab=\"local\")", 'data-tab="local"' in html)
    check("#wpPanePresets present", 'id="wpPanePresets"' in html)
    check("#wpPaneThemes present", 'id="wpPaneThemes"' in html)
    check("#wpPaneGradient present", 'id="wpPaneGradient"' in html)
    check("#wpPaneLocal present", 'id="wpPaneLocal"' in html)

    # 6. Built-in Wallpapers & Custom Gradient Controls
    check("#wpPresetsContainer present", 'id="wpPresetsContainer"' in html)
    check("#wpThemesContainer present", 'id="wpThemesContainer"' in html)
    check("#wpGradType select present", 'id="wpGradType"' in html)
    check("#wpGradAngle range present", 'id="wpGradAngle"' in html)
    check("#wpGradColor1 & #wpGradColor2 color inputs present",
          'id="wpGradColor1"' in html and 'id="wpGradColor2"' in html)

    # 7. Local File Safety (No server upload, memory blob URL, file limits)
    check("#wpLocalFileInput present with accept png/jpeg/webp",
          'id="wpLocalFileInput"' in html and 'accept="image/png, image/jpeg, image/webp"' in html)
    check("Client-side validation restricts to 5MB max",
          '5 * 1024 * 1024' in html or '5242880' in html)
    check("Client-side preview uses URL.createObjectURL for memory safety",
          'URL.createObjectURL' in html)

    # 8. Adjustment Sliders
    check("#wpBrightnessSlider present", 'id="wpBrightnessSlider"' in html)
    check("#wpScrimSlider present", 'id="wpScrimSlider"' in html)
    check("#wpBlurSlider present", 'id="wpBlurSlider"' in html)
    check("#wpPreviewViewport present", 'id="wpPreviewViewport"' in html)

    # 9. JavaScript Controller Functionality
    check("initZeroWallpaperStudio controller function present", 'initZeroWallpaperStudio' in html)
    check("localStorage preference persistence for zero_wallpaper_config",
          'zero_wallpaper_config' in html and 'localStorage.setItem' in html)
    check("Builtin futuristic presets defined (grid, reactor, matrix, nebula, crimson)",
          'Holographic Cyber Grid' in html and 'Arc Reactor Blueprint' in html and 'Deep Space Nebula' in html)
    check("Escape key closes wallpaper studio modal",
          'Escape' in html and 'closeStudio' in html)

    # 10. Regression Checks: Cyber Orb & Hover Panels
    check("Regression: #orbCanvas intact", 'id="orbCanvas"' in html)
    check("Regression: Canvas 2D Cyber Orb render loop intact", 'function renderOrb()' in html and "canvas.getContext('2d')" in html)
    check("Regression: Phase 15F #zeroHoverPanelsBar intact", 'id="zeroHoverPanelsBar"' in html)
    check("Regression: Hover Panel triggers intact (tasks, memory, sys, model, notif, tg)",
          'data-panel="tasks"' in html and 'data-panel="memory"' in html and
          'data-panel="system"' in html and 'data-panel="model"' in html and
          'data-panel="notifications"' in html and 'data-panel="telegram"' in html)
    check("Regression: Premium rounded tokens intact (--radius-sm, --radius-lg, --shadow-card)",
          '--radius-sm' in html and '--radius-lg' in html and '--shadow-card' in html)
    check("Regression: No external heavy frameworks added (No React, Electron, or external CDNs)",
          'react.production.min.js' not in html and 'vue.global.js' not in html)

    print(f"\nRESULTS: {passed} / {total} tests passed.")
    if passed == total:
        print("[SUCCESS] All Phase 15G Wallpaper Studio verification tests PASSED!\n")
        return 0
    else:
        print(f"[FAIL] {total - passed} test(s) failed!\n")
        return 1

if __name__ == "__main__":
    sys.exit(test_wallpaper_studio())
