// A recorder session owns its capture, quiet timer and local upload.
class LocalVoiceRecorder {
  start(track, continuous, context) {
    const stream = new MediaStream([track]);
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    const controller = new AbortController();
    let recorder, timer, uploadTimer;
    let finished = false;
    let manual = false;
    let turnSequence = 0;
    const transcripts = [];

    const release = error => {
      if (finished) return;
      finished = true;
      clearInterval(timer);
      clearTimeout(uploadTimer);
      controller.abort();
      source.disconnect();
      track.removeEventListener('ended', trackEnded);
      if (recorder?.state === 'recording') recorder.stop();
      if (error) this.onerror?.({ error });
      this.onend?.();
    };
    const trackEnded = () => release('audio-capture');
    track.addEventListener('ended', trackEnded, { once: true });
    this.abort = () => release();
    this.stop = () => {
      manual = true;
      if (recorder?.state === 'recording') recorder.stop();
    };

    const begin = () => {
      const chunks = [];
      const mimeType = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4']
        .find(type => MediaRecorder.isTypeSupported(type));
      recorder = mimeType ? new MediaRecorder(stream, { mimeType, audioBitsPerSecond: 32000 }) : new MediaRecorder(stream);
      let speech = false;
      let speechStart = 0;
      let loudFrames = 0;
      let lastSound = 0;
      let noiseBaseline = 0.3;
      const started = performance.now();
      recorder.ondataavailable = event => {
        if (event.data.size && !window.isSpeaking) chunks.push(event.data);
      };
      recorder.onerror = () => release('audio-capture');
      recorder.onstop = async () => {
        clearInterval(timer);
        if (finished) return;
        const speechDuration = speech ? (lastSound - speechStart) : 0;
        // 500 ms altı sesleri eleme (gürültü/geçici ses filtresi; manuel durdurmada kullanıcı kararına saygı duyulur)
        const isEligibleSpeech = speech && (manual || speechDuration >= 500);
        if (chunks.length && isEligibleSpeech && !window.isSpeaking) {
          const currentTurn = ++turnSequence;
          try {
            const audio = new Blob(chunks, { type: recorder.mimeType || chunks[0].type });
            if (audio.size > 1024 * 1024) throw new Error('oversize');
            const form = new FormData();
            form.append('audio', audio, 'speech');
            form.append('language', 'tr');
            uploadTimer = setTimeout(() => release('local-stt'), 15000);
            const response = await fetch('/api/stt', { method: 'POST', body: form, signal: controller.signal });
            if (!response.ok) throw new Error('local-stt');
            const data = await response.json();
            clearTimeout(uploadTimer);
            if (finished || currentTurn !== turnSequence) return;
            if (typeof data.text !== 'string') throw new Error('local-stt');
            const text = data.text.trim();
            if (text) {
              transcripts.push(text);
              this.onresult?.({ results: transcripts.map(value =>
                Object.assign([{ transcript: value + ' ' }], { isFinal: true })) });
            }
          } catch {
            release('local-stt');
            return;
          }
        }
        if (!finished && continuous && !manual && track.readyState === 'live') begin();
        else release();
      };
      recorder.start();
      let wasSpeaking = false;
      timer = setInterval(() => {
        // Barge-In & Hoparlör Yankı İzolasyonu
        if (window.isSpeaking) {
          if (rms >= speechThreshold + 4.5 && ++loudFrames >= 3) {
            if (typeof window.interruptSpeech === 'function') {
              window.interruptSpeech();
            }
          } else {
            wasSpeaking = true;
            loudFrames = 0;
            speech = false;
            chunks.length = 0;
            return;
          }
        }
        if (wasSpeaking) {
          wasSpeaking = false;
          lastSound = performance.now();
          loudFrames = 0;
          speech = false;
        }

        analyser.getByteTimeDomainData(samples);
        const rms = Math.sqrt(samples.reduce((sum, sample) => sum + (sample - 128) ** 2, 0) / samples.length);
        const now = performance.now();
        this.onvolume?.(rms);

        const speechThreshold = Math.max(3.8, noiseBaseline + 2.2);
        const silenceThreshold = Math.max(2.2, noiseBaseline + 1.1);

        if (rms >= speechThreshold) {
          if (++loudFrames >= 2 && !speech) {
            speech = true;
            speechStart = now;
            this.onspeechstart?.();
          }
          if (speech) lastSound = now;
        } else if (rms <= silenceThreshold) {
          loudFrames = 0;
          noiseBaseline = noiseBaseline * 0.96 + rms * 0.04;
        }

        if ((speech && now - lastSound >= 700) || now - started >= 14000) recorder.stop();
      }, 60);
    };
    try {
      begin();
      this.onstart?.();
      this.onaudiostart?.();
    } catch {
      release('audio-capture');
    }
  }
}
