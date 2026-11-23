// Luna AI — Yan Sohbet (Side Chat / Parallel Independent Chat)
// Inspired by Manus AI: Ana görevi, sesi veya arka plan işlemlerini kesintiye uğratmadan soru ve fikir danışma paneli.

(function() {
  'use strict';

  let sideChatAbortController = null;
  let isSideChatStreaming = false;
  const STORAGE_KEY = 'luna_side_chat_history';
  const INTRO_SEEN_KEY = 'luna_side_chat_intro_seen';

  function initSideChat() {
    const toggleBtn = document.getElementById('sideChatToggleBtn');
    const tooltip = document.getElementById('sideChatTooltip');
    const tooltipDismissBtn = document.getElementById('sideChatTooltipDismissBtn');
    const drawer = document.getElementById('sideChatDrawer');
    const closeBtn = document.getElementById('sideChatCloseBtn');
    const clearBtn = document.getElementById('sideChatClearBtn');
    const transcript = document.getElementById('sideChatTranscript');
    const form = document.getElementById('sideChatForm');
    const input = document.getElementById('sideChatInput');
    const badgeDot = document.querySelector('.side-chat-badge-dot');

    if (!toggleBtn || !drawer) return;

    // Load persisted history
    loadHistory();

    // Check onboarding popover
    const introSeen = localStorage.getItem(INTRO_SEEN_KEY) === 'true';
    if (!introSeen && tooltip) {
      // Auto-show tooltip briefly after 2 seconds
      setTimeout(() => {
        if (localStorage.getItem(INTRO_SEEN_KEY) !== 'true') {
          tooltip.style.display = 'block';
        }
      }, 1500);
    }

    if (tooltipDismissBtn && tooltip) {
      tooltipDismissBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        tooltip.style.display = 'none';
        localStorage.setItem(INTRO_SEEN_KEY, 'true');
        if (badgeDot) badgeDot.style.display = 'none';
        openSideChat();
      });
    }

    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (tooltip && tooltip.style.display !== 'none') {
        tooltip.style.display = 'none';
        localStorage.setItem(INTRO_SEEN_KEY, 'true');
        if (badgeDot) badgeDot.style.display = 'none';
      }
      toggleSideChat();
    });

    closeBtn?.addEventListener('click', closeSideChat);
    clearBtn?.addEventListener('click', clearHistory);

    // Close on Escape key
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && drawer.classList.contains('open')) {
        closeSideChat();
      }
    });

    form?.addEventListener('submit', (e) => {
      e.preventDefault();
      sendSideChatMessage();
    });

    function toggleSideChat() {
      if (drawer.classList.contains('open')) {
        closeSideChat();
      } else {
        openSideChat();
      }
    }

    function openSideChat() {
      drawer.style.display = 'flex';
      // Trigger reflow for transition
      drawer.offsetHeight;
      drawer.classList.add('open');
      drawer.setAttribute('aria-hidden', 'false');
      toggleBtn.setAttribute('aria-expanded', 'true');
      input?.focus();
      scrollTranscriptToBottom();
    }

    function closeSideChat() {
      drawer.classList.remove('open');
      drawer.setAttribute('aria-hidden', 'true');
      toggleBtn.setAttribute('aria-expanded', 'false');
      setTimeout(() => {
        if (!drawer.classList.contains('open')) {
          drawer.style.display = 'none';
        }
      }, 250);
    }

    function scrollTranscriptToBottom() {
      if (transcript) {
        transcript.scrollTop = transcript.scrollHeight;
      }
    }

    function getHistory() {
      try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      } catch {
        return [];
      }
    }

    function saveHistory(history) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(-30)));
      } catch {}
    }

    function loadHistory() {
      const history = getHistory();
      if (!transcript) return;
      if (history.length === 0) return;

      transcript.innerHTML = '';
      history.forEach(item => {
        appendBubble(item.text, item.sender, false);
      });
      scrollTranscriptToBottom();
    }

    function clearHistory() {
      if (!confirm('Yan sohbet geçmişini temizlemek istiyor musunuz?')) return;
      localStorage.removeItem(STORAGE_KEY);
      if (transcript) {
        transcript.innerHTML = `
          <div class="side-chat-starter">
            <p>💡 <strong>Paralel Düşünce Alanı</strong></p>
            <p>Luna ana ekranda çalışırken buraya bağımsız sorular yazabilir, fikir danışabilir veya not düşebilirsiniz.</p>
          </div>
        `;
      }
    }

    function appendBubble(text, sender, save = true) {
      const starter = transcript.querySelector('.side-chat-starter');
      if (starter) starter.remove();

      const bubbleWrap = document.createElement('div');
      bubbleWrap.className = `side-chat-msg ${sender}`;

      const bubble = document.createElement('div');
      bubble.className = 'side-chat-bubble';
      bubble.textContent = text;

      bubbleWrap.appendChild(bubble);
      transcript.appendChild(bubbleWrap);
      scrollTranscriptToBottom();

      if (save) {
        const history = getHistory();
        history.push({ text, sender, time: Date.now() });
        saveHistory(history);
      }

      return bubble;
    }

    async function sendSideChatMessage() {
      if (!input || isSideChatStreaming) return;
      const text = input.value.trim();
      if (!text) return;

      input.value = '';
      appendBubble(text, 'user', true);

      // Create assistant placeholder bubble
      const assistantBubble = appendBubble('...', 'assistant', false);
      assistantBubble.classList.add('streaming');

      isSideChatStreaming = true;
      if (sideChatAbortController) {
        try { sideChatAbortController.abort(); } catch(e) {}
      }
      sideChatAbortController = new AbortController();

      let fullReply = '';

      try {
        const response = await fetch('/api/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: text,
            voice_mode: false,
            voice_reply: false,
            context: 'side_chat'
          }),
          signal: sideChatAbortController.signal
        });

        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split('\n\n');
          buffer = blocks.pop() || '';

          for (const block of blocks) {
            const lines = block.split('\n');
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const raw = line.slice(6).trim();
                if (raw === '[DONE]') continue;
                try {
                  const data = JSON.parse(raw);
                  if (data.token) {
                    fullReply += data.token;
                    assistantBubble.textContent = fullReply;
                    scrollTranscriptToBottom();
                  } else if (data.reply) {
                    fullReply = data.reply;
                    assistantBubble.textContent = fullReply;
                    scrollTranscriptToBottom();
                  }
                } catch(e) {}
              }
            }
          }
        }

        assistantBubble.classList.remove('streaming');
        if (!fullReply.trim()) {
          fullReply = 'Yanıt alınamadı.';
          assistantBubble.textContent = fullReply;
        }

        // Save assistant response to history
        const history = getHistory();
        history.push({ text: fullReply, sender: 'assistant', time: Date.now() });
        saveHistory(history);

      } catch (err) {
        if (err.name === 'AbortError') {
          assistantBubble.textContent = fullReply || '[Durduruldu]';
        } else {
          assistantBubble.textContent = 'Bağlantı hatası: Sunucu yanıt vermedi.';
        }
        assistantBubble.classList.remove('streaming');
      } finally {
        isSideChatStreaming = false;
        sideChatAbortController = null;
        scrollTranscriptToBottom();
      }
    }
  }

  // Initialize on DOMContentLoaded or directly if already loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSideChat);
  } else {
    initSideChat();
  }
})();
