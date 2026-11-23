/**
 * ZERO OS / LUNA-AI Navigation & View Management Module
 * Handles multi-view switcher (Cockpit, Tasks, Radar, System, Desktop, Logs),
 * Fail-safe global event delegation for all menu buttons, Hover Panel Toolbars,
 * and Command Palette modal toggles.
 */

(function(window, document) {
  'use strict';

  window.switchView = function(target) {
    if (!target) return;
    try {
      if (typeof window.playSound === 'function') window.playSound('tab');
    } catch (_) {}

    document.querySelectorAll('.hud-cat-btn').forEach(t => {
      t.classList.toggle('active', t.dataset.view === target);
    });

    const views = {
      cockpit: document.getElementById('viewCockpit'),
      tasks: document.getElementById('viewTasks'),
      system: document.getElementById('viewSystem'),
      automations: document.getElementById('viewAutomations'),
      memory: document.getElementById('viewMemory'),
      logs: document.getElementById('viewLogs'),
      radarLab: document.getElementById('viewRadarLab'),
      securityDiag: document.getElementById('viewSecurityDiag'),
      desktop: document.getElementById('viewDesktop')
    };

    for (const [key, el] of Object.entries(views)) {
      if (el) {
        if (key === target) {
          el.style.setProperty('display', 'flex', 'important');
        } else {
          el.style.setProperty('display', 'none', 'important');
        }
      }
    }

    if (target === 'tasks') {
      document.getElementById('viewTasks')?.focus();
      if (typeof window.loadLiveTasks === 'function') window.loadLiveTasks();
    }
    if (target === 'system') {
      if (typeof window.pollSystemMetrics === 'function') window.pollSystemMetrics();
    }
    if (target === 'radarLab') {
      if (typeof window.loadTelegramFeed === 'function') window.loadTelegramFeed();
    }
    if (target === 'automations' && typeof window.loadAutomationsView === 'function') {
      window.loadAutomationsView();
    }
    if (target === 'memory') {
      document.getElementById('viewMemory')?.focus();
      if (typeof window.loadMemoryView === 'function') window.loadMemoryView();
    }
    if (target === 'logs' && typeof window.loadLogsView === 'function') {
      window.loadLogsView();
    }
    if (target === 'desktop' && typeof window.loadDesktopStatus === 'function') {
      window.loadDesktopStatus();
    }
  };

  // Fail-safe global click delegation for navigation tabs
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.hud-cat-btn');
    if (btn) {
      e.preventDefault();
      const v = btn.dataset.view || btn.getAttribute('data-view');
      if (v) window.switchView(v);
    }
  });

  // Modal open / close helpers
  window.openModal = function(modalId) {
    const m = document.getElementById(modalId);
    if (m) m.classList.add('open');
  };

  window.closeModal = function(modalId) {
    const m = document.getElementById(modalId);
    if (m) m.classList.remove('open');
  };

  // Global escape key listener for all open modals
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      const palette = document.getElementById('paletteModal');
      if (palette) {
        if (palette.classList.contains('open')) {
          palette.classList.remove('open');
        } else {
          palette.classList.add('open');
          document.getElementById('paletteInput')?.focus();
        }
      }
    }
  });

  // Command button click in topbar
  const headerPaletteBtn = document.getElementById('headerPaletteBtn');
  if (headerPaletteBtn) {
    headerPaletteBtn.addEventListener('click', () => {
      const palette = document.getElementById('paletteModal');
      if (palette) {
        palette.classList.add('open');
        document.getElementById('paletteInput')?.focus();
      }
    });
  }

  // Export module
  window.NavigationModule = {
    switchView: window.switchView,
    openModal: window.openModal,
    closeModal: window.closeModal
  };

})(window, document);
