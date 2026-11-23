/**
 * ZERO OS / LUNA-AI Core Application Module (app.js)
 * Orchestrates application lifecycle, theme persistence, toast notifications,
 * command palette (Ctrl+K), and centralized fail-safe initialization.
 */

(function(window, document) {
  'use strict';

  const AppModule = {
    version: '1.0.0',
    initialized: false,

    // Centralized Toast Notification System
    showToast: function(msg, type = 'info') {
      const container = document.getElementById('zeroToastContainer');
      if (!container) {
        console.log(`[Toast ${type}]: ${msg}`);
        return;
      }

      const toast = document.createElement('div');
      toast.className = `zero-toast zero-toast-${type}`;
      toast.style.cssText = `
        background: ${type === 'error' ? 'rgba(239, 68, 68, 0.95)' : type === 'success' ? 'rgba(16, 185, 129, 0.95)' : 'rgba(15, 23, 42, 0.95)'};
        color: #fff;
        padding: 8px 14px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 600;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.15);
        backdrop-filter: blur(8px);
        margin-bottom: 6px;
        transition: all 0.25s ease;
        opacity: 0;
        transform: translateY(10px);
      `;
      toast.textContent = msg;

      container.appendChild(toast);
      requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
      });

      setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-8px)';
        setTimeout(() => toast.remove(), 250);
      }, 3500);
    },

    // Clipboard copy helper
    copyToClipboard: async function(text) {
      if (!text) return false;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
        } else {
          const ta = document.createElement('textarea');
          ta.value = text;
          ta.style.position = 'fixed';
          ta.style.left = '-9999px';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          ta.remove();
        }
        AppModule.showToast('Panoya kopyalandı', 'success');
        return true;
      } catch (err) {
        console.warn('Clipboard copy failed:', err);
        AppModule.showToast('Kopyalama başarısız', 'error');
        return false;
      }
    },

    // Dynamic User Greeting
    updateGreeting: function() {
      const el = document.getElementById('dynamicGreetingText');
      if (!el) return;
      const hr = new Date().getHours();
      const user = window.CURRENT_USER_NAME || 'Negr1v';
      const greet = hr < 12 ? 'Günaydın' : hr < 18 ? 'İyi günler' : 'İyi akşamlar';
      el.textContent = `${greet}, ${user}`;
    },

    // Command Palette & Global Shortcut Registration
    initShortcuts: function() {
      window.addEventListener('keydown', function(e) {
        // Ctrl+K -> Command Palette
        if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
          e.preventDefault();
          const cmdPalette = document.getElementById('commandPaletteModal');
          if (cmdPalette) {
            const isShown = cmdPalette.classList.contains('active') || cmdPalette.style.display === 'flex';
            if (isShown) {
              cmdPalette.classList.remove('active');
              cmdPalette.style.display = 'none';
            } else {
              cmdPalette.classList.add('active');
              cmdPalette.style.display = 'flex';
              const input = document.getElementById('commandPaletteInput') || cmdPalette.querySelector('input');
              if (input) input.focus();
            }
          }
        }
      });
    },

    // Master Initialization
    init: function() {
      if (this.initialized) return;
      this.initialized = true;

      this.updateGreeting();
      this.initShortcuts();

      console.log('🚀 [AppModule] ZERO OS App Module successfully loaded and initialized.');
    }
  };

  // Expose globally
  window.AppModule = AppModule;
  window.showZeroToast = AppModule.showToast;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => AppModule.init());
  } else {
    AppModule.init();
  }

})(window, document);
