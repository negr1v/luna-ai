/**
 * ZERO OS / ACCIO-JARVIS Voice Module
 * Handles Web Speech API (SpeechRecognition / STT), AudioContext,
 * Real-Time Audio-Reactive Visualizer (Halo Glow), Silence Timer (VAD),
 * Push-to-Talk / Push-to-Send (F8 / Space / Mic Button).
 */

(function(window, document) {
  'use strict';

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  let recognition = null;
  let isListening = false;
  let isRecognitionStarting = false;
  let isRecognitionStopping = false;
  let speechDraftPrefix = '';
  let speechSubmitTimer = null;

  let activeMicVisualizerStream = null;
  let activeMicAnimFrame = null;

  let micConsentGranted = false;
  if (localStorage.getItem('jarvis_mic_consent') !== 'false') {
    micConsentGranted = true;
  }

  function cancelSpeechSubmission() {
    if (speechSubmitTimer) {
      clearTimeout(speechSubmitTimer);
      speechSubmitTimer = null;
    }
  }

  function startMicVisualizer(stream) {
    if (typeof window.initAudioCtx !== 'function') return;
    const ctx = window.initAudioCtx();
    if (!ctx || !stream) return;
    try {
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyser);
      const dataArr = new Uint8Array(analyser.frequencyBinCount);
      const halo = document.getElementById('avatarHaloRing');

      function tick() {
        if (!isListening) {
          if (halo) halo.style.transform = '';
          const avatarArt = document.querySelector('.avatar-art-container');
          if (avatarArt) avatarArt.style.transform = '';
          return;
        }
        analyser.getByteFrequencyData(dataArr);
        let sum = 0;
        for (let i = 0; i < dataArr.length; i++) sum += dataArr[i];
        const avg = sum / dataArr.length;
        const scale = Math.min(1.24, 1 + (avg / 120) * 0.20);
        if (halo && isListening) {
          halo.style.transform = `scale(${scale})`;
        }
        const avatarArt = document.querySelector('.avatar-art-container');
        if (avatarArt && isListening) {
          const artScale = Math.min(1.06, 1 + (avg / 160) * 0.05);
          avatarArt.style.transform = `scale(${artScale})`;
        }
        activeMicAnimFrame = requestAnimationFrame(tick);
      }
      tick();
    } catch(e) {
      console.warn('[Mic Visualizer]:', e);
    }
  }

  function stopMicVisualizer() {
    if (activeMicAnimFrame) cancelAnimationFrame(activeMicAnimFrame);
    activeMicAnimFrame = null;
    const halo = document.getElementById('avatarHaloRing');
    if (halo) halo.style.transform = '';
    const avatarArt = document.querySelector('.avatar-art-container');
    if (avatarArt) avatarArt.style.transform = '';
    if (activeMicVisualizerStream) {
      try {
        activeMicVisualizerStream.getTracks().forEach(t => t.stop());
      } catch(e){}
      activeMicVisualizerStream = null;
    }
  }

  function initSpeechRecognition() {
    const micBtn = document.getElementById('micBtn');
    if (!SpeechRecognition) {
      if (micBtn) {
        micBtn.disabled = true;
        micBtn.title = 'Tarayıcınız sesli tanımayı desteklemiyor (Chrome veya Edge kullanın).';
        micBtn.style.opacity = '0.5';
        micBtn.style.cursor = 'not-allowed';
      }
      return null;
    }

    const rec = new SpeechRecognition();
    rec.lang = 'tr-TR';
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onstart = () => {
      isRecognitionStarting = false;
      isListening = true;
      const textInput = document.getElementById('textInput');
      speechDraftPrefix = textInput ? textInput.value.trim() : '';
      document.getElementById('promptMicBtn')?.setAttribute('aria-pressed', 'true');
      if (micBtn) micBtn.classList.add('active');
      if (typeof window.setCoreState === 'function') window.setCoreState('LISTENING');
      if (textInput) textInput.placeholder = 'Dinleniyor... Konuşun (Söz kesmek için konuşabilirsiniz)';
    };

    rec.onresult = (e) => {
      if (!isListening) return;
      let finalTranscript = '';
      let interimTranscript = '';
      for (let i = 0; i < e.results.length; ++i) {
        if (e.results[i].isFinal) {
          finalTranscript += e.results[i][0].transcript;
        } else {
          interimTranscript += e.results[i][0].transcript;
        }
      }

      const text = (finalTranscript + interimTranscript).trim();
      if (!text) return;

      const textInput = document.getElementById('textInput');
      if (textInput) {
        textInput.value = [speechDraftPrefix, text].filter(Boolean).join(' ');
        textInput.dispatchEvent(new Event('input', {bubbles: true}));
      }

      if ((window.isSpeaking || window.isThinking) && (interimTranscript || finalTranscript)) {
        const lower = (interimTranscript || finalTranscript).trim().toLowerCase();
        if (lower.includes('dur') || lower.includes('tamam') || lower.includes('kes') || lower.includes('yeter') || lower.includes('sus')) {
          if (typeof window.interruptSpeech === 'function') window.interruptSpeech();
          stopListening();
          if (typeof window.showZeroToast === 'function') window.showZeroToast('Söz Kesildi', 'Sesli yanıt durduruldu.', 'info', 2000);
          return;
        }
        // Asistan konuşurken hoparlörden gelen kendi sesinin asistanı kesmesini engelle
        if (window.isSpeaking) {
          return;
        }
        if (window.isThinking && typeof window.interruptSpeech === 'function') {
          window.interruptSpeech();
        }
      }

      cancelSpeechSubmission();
      const currentDraft = (textInput ? textInput.value : '').trim();
      if (currentDraft && (finalTranscript.trim() || interimTranscript.trim())) {
        speechSubmitTimer = setTimeout(() => {
          speechSubmitTimer = null;
          if (isListening && textInput && textInput.value.trim() === currentDraft) {
            window.isVoiceSessionActive = false;
            window.isF8VoiceActive = false;
            stopListening();
            if (typeof window.submitComposerMessage === 'function') {
              window.submitComposerMessage(true);
            }
          }
        }, 1100);
      }
    };

    rec.onerror = (e) => {
      cancelSpeechSubmission();
      console.warn('SpeechRecognition hatası:', e.error);
      isRecognitionStarting = false;
      isRecognitionStopping = false;
      isListening = false;
      document.getElementById('promptMicBtn')?.setAttribute('aria-pressed', 'false');
      const pMic = document.getElementById('promptMicBtn');
      if (pMic) {
        pMic.style.background = '';
        pMic.style.borderColor = '';
        pMic.style.color = '';
      }
      if (micBtn) micBtn.classList.remove('active');
      const textInput = document.getElementById('textInput');
      if (textInput) textInput.placeholder = "ACCIO'ya bir şey sor veya F8 ile konuş…";

      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        if (typeof window.appendBubble === 'function') {
          window.appendBubble('⚠️ Mikrofon izni verilmedi. Sesli komut için tarayıcı adres çubuğundaki kilit simgesinden mikrofon iznini etkinleştirin.', 'assistant');
        }
        if (typeof window.setCoreState === 'function') window.setCoreState('ERROR');
        setTimeout(() => {
          if (!window.isSpeaking && !window.isThinking && typeof window.setCoreState === 'function') window.setCoreState('IDLE');
        }, 3000);
      } else if (e.error === 'audio-capture') {
        if (typeof window.appendBubble === 'function') {
          window.appendBubble('⚠️ Mikrofon donanımı bulunamadı veya başka bir program tarafından kullanılıyor.', 'assistant');
        }
        if (typeof window.setCoreState === 'function') window.setCoreState('ERROR');
        setTimeout(() => {
          if (!window.isSpeaking && !window.isThinking && typeof window.setCoreState === 'function') window.setCoreState('IDLE');
        }, 3000);
      } else if (e.error === 'network') {
        if (typeof window.appendBubble === 'function') {
          window.appendBubble('⚠️ Ses tanıma servisine ulaşılamadı (ağ hatası).', 'assistant');
        }
        if (typeof window.setCoreState === 'function') window.setCoreState('ERROR');
        setTimeout(() => {
          if (!window.isSpeaking && !window.isThinking && typeof window.setCoreState === 'function') window.setCoreState('IDLE');
        }, 2000);
      } else {
        if (!window.isSpeaking && !window.isThinking && typeof window.setCoreState === 'function') window.setCoreState('IDLE');
      }
    };

    rec.onend = () => {
      isRecognitionStarting = false;
      isRecognitionStopping = false;
      isListening = false;
      document.getElementById('promptMicBtn')?.setAttribute('aria-pressed', 'false');
      const pMic = document.getElementById('promptMicBtn');
      if (pMic) {
        pMic.style.background = '';
        pMic.style.borderColor = '';
        pMic.style.color = '';
      }
      if (micBtn) micBtn.classList.remove('active');
      const textInput = document.getElementById('textInput');
      if (textInput) textInput.placeholder = "ACCIO'ya bir şey sor veya F8 ile konuş…";
      if (!window.isSpeaking && !window.isThinking && window.currentCoreState && window.currentCoreState.key === 'LISTENING') {
        if (typeof window.setCoreState === 'function') window.setCoreState('IDLE');
      }
      const pendingVoiceText = (textInput ? textInput.value : '').trim();
      if (pendingVoiceText && (window.isF8VoiceActive || window.isF8PendingSubmit || window.isVoiceSessionActive) && !window.isThinking && !window.isSpeaking) {
        window.isF8PendingSubmit = false;
        window.isF8VoiceActive = false;
        window.isVoiceSessionActive = false;
        if (typeof window.submitComposerMessage === 'function') {
          window.submitComposerMessage(true);
        }
      }
    };

    return rec;
  }

  recognition = initSpeechRecognition();

  async function startListening() {
    if (!recognition) {
      if (typeof window.showZeroToast === 'function') {
        window.showZeroToast('Mikrofon Hatası', 'Tarayıcınız sesli tanımayı desteklemiyor (Chrome veya Edge kullanın).', 'error', 3500);
      }
      return;
    }
    if (isListening || isRecognitionStarting || isRecognitionStopping) return;
    cancelSpeechSubmission();

    if (window.isSpeaking && typeof window.interruptSpeech === 'function') {
      window.interruptSpeech();
    }

    if (typeof window.initAudioCtx === 'function') window.initAudioCtx();

    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        activeMicVisualizerStream = stream;
        startMicVisualizer(stream);
      } catch (micErr) {
        console.warn('[Mikrofon İzni / Donanım]:', micErr);
        if (micErr.name === 'NotAllowedError' || micErr.name === 'PermissionDeniedError') {
          if (typeof window.appendBubble === 'function') {
            window.appendBubble('⚠️ Mikrofon izni engellendi. Tarayıcı adres çubuğundaki kilit/izin simgesinden mikrofona izin verin.', 'assistant');
          }
          if (typeof window.setCoreState === 'function') window.setCoreState('ERROR');
          setTimeout(() => { if (!window.isSpeaking && !window.isThinking && typeof window.setCoreState === 'function') window.setCoreState('IDLE'); }, 3000);
          return;
        }
      }
    }

    isRecognitionStarting = true;
    window.isVoiceSessionActive = true;
    if (typeof window.playSound === 'function') window.playSound('wake');

    try {
      recognition.start();
    } catch (err) {
      isRecognitionStarting = false;
      const micBtn = document.getElementById('micBtn');
      if (err.name === 'InvalidStateError') {
        isListening = true;
        if (micBtn) micBtn.classList.add('active');
        if (typeof window.setCoreState === 'function') window.setCoreState('LISTENING');
      } else {
        isListening = false;
        if (micBtn) micBtn.classList.remove('active');
        if (typeof window.setCoreState === 'function') window.setCoreState('IDLE');
      }
    }
  }

  function stopListening() {
    cancelSpeechSubmission();
    stopMicVisualizer();
    if (!isListening && !isRecognitionStarting) return;
    isListening = false;
    isRecognitionStarting = false;
    isRecognitionStopping = true;
    document.getElementById('promptMicBtn')?.setAttribute('aria-pressed', 'false');
    const micBtn = document.getElementById('micBtn');
    if (micBtn) micBtn.classList.remove('active');
    if (!window.isSpeaking && !window.isThinking && typeof window.setCoreState === 'function') {
      window.setCoreState('IDLE');
    }

    if (recognition) {
      try {
        recognition.stop();
      } catch (err) {
        try { recognition.abort(); } catch(e){}
      }
    }
  }

  function isEditableElement(el) {
    if (!el) return false;
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
    if (el.isContentEditable) return true;
    return false;
  }

  window.handleVoiceInputToggle = function() {
    if (typeof window.initAudioCtx === 'function') window.initAudioCtx();
    const promptMic = document.getElementById('promptMicBtn');
    const textInput = document.getElementById('textInput');
    if (!isListening && !isRecognitionStarting) {
      window.isVoiceSessionActive = true;
      window.isF8VoiceActive = true;
      window.isF8PendingSubmit = false;
      if (textInput) textInput.value = '';
      cancelSpeechSubmission();
      startListening();
      if (typeof window.showZeroToast === 'function') {
        window.showZeroToast('🎙 Dinleniyor...', 'Konuşun... Bitince tekrar mikrofona basın (veya susunca otomatik gider).', 'info', 3000);
      }
      if (promptMic) {
        promptMic.style.background = 'rgba(239, 68, 68, 0.25)';
        promptMic.style.borderColor = '#ef4444';
        promptMic.style.color = '#fff';
      }
      if (textInput) textInput.placeholder = '🎙️ Dinleniyor... Göndermek için tekrar mikrofona basın!';
    } else {
      window.isVoiceSessionActive = false;
      window.isF8VoiceActive = false;
      window.isF8PendingSubmit = true;
      if (promptMic) {
        promptMic.style.background = '';
        promptMic.style.borderColor = '';
        promptMic.style.color = '';
      }
      if (textInput) textInput.placeholder = "ACCIO'ya bir şey sor veya F8 ile konuş…";
      stopListening();
      const txt = (textInput ? textInput.value : '').trim();
      if (txt && typeof window.submitComposerMessage === 'function') {
        window.isF8PendingSubmit = false;
        window.submitComposerMessage(true);
      }
    }
  };

  // Space Bar Push-to-Talk Shortcut
  window.addEventListener('keydown', (e) => {
    if (e.code === 'Space') {
      const activeEl = document.activeElement;
      if (isEditableElement(e.target) || isEditableElement(activeEl)) return;
      e.preventDefault();
      window.handleVoiceInputToggle();
    }
    if (e.code === 'F8') {
      e.preventDefault();
      window.handleVoiceInputToggle();
    }
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden && isListening) {
      stopListening();
    }
  });

  window.addEventListener('beforeunload', () => {
    if (recognition) {
      try { recognition.abort(); } catch(e){}
    }
  });

  // Export module to global scope
  window.VoiceModule = {
    startListening,
    stopListening,
    initSpeechRecognition,
    isEditableElement,
    get isListening() { return isListening; },
    get isRecognitionStarting() { return isRecognitionStarting; }
  };
  window.startListening = startListening;
  window.stopListening = stopListening;
  window.isEditableElement = isEditableElement;

})(window, document);
