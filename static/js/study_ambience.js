// Study With Mommy - Procedural Web Audio Ambient Soundscape Engine
// Provides authentic, infinite, zero-bandwidth room ambience:
// 1. "rain" -> Mommy's office (Rain on the window)
// 2. "snow" -> Winter attic (Snow falling, crackling candlelight/fireplace)
// 3. "city" -> City at night (High over the city lights, lo-fi night air)

(function(window) {
  'use strict';

  class StudyAmbienceEngine {
    constructor() {
      this.ctx = null;
      this.activeMode = 'rain'; // 'rain' | 'snow' | 'city'
      this.volume = 0.35;
      this.enabled = false;
      this.masterGain = null;
      this.noiseNode = null;
      this.crackleTimer = null;
      this.rainTimer = null;
    }

    initCtx() {
      if (!this.ctx) {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        this.ctx = new AudioCtx();
        this.masterGain = this.ctx.createGain();
        this.masterGain.gain.setValueAtTime(this.enabled ? this.volume : 0, this.ctx.currentTime);
        this.masterGain.connect(this.ctx.destination);
      }
      if (this.ctx.state === 'suspended') {
        this.ctx.resume().catch(() => {});
      }
    }

    createNoiseBuffer(type = 'pink') {
      const bufferSize = this.ctx.sampleRate * 3;
      const buffer = this.ctx.createBuffer(1, bufferSize, this.ctx.sampleRate);
      const data = buffer.getChannelData(0);

      if (type === 'pink') {
        let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
        for (let i = 0; i < bufferSize; i++) {
          const white = Math.random() * 2 - 1;
          b0 = 0.99886 * b0 + white * 0.0555179;
          b1 = 0.99332 * b1 + white * 0.0750759;
          b2 = 0.96900 * b2 + white * 0.1538520;
          b3 = 0.86650 * b3 + white * 0.3104856;
          b4 = 0.55000 * b4 + white * 0.5329522;
          b5 = -0.7616 * b5 - white * 0.0168980;
          data[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.11;
          b6 = white * 0.115926;
        }
      } else if (type === 'brown') {
        let lastOut = 0.0;
        for (let i = 0; i < bufferSize; i++) {
          const white = Math.random() * 2 - 1;
          data[i] = (lastOut + (0.02 * white)) / 1.02;
          lastOut = data[i];
          data[i] *= 3.5;
        }
      } else { // white noise
        for (let i = 0; i < bufferSize; i++) {
          data[i] = (Math.random() * 2 - 1) * 0.12;
        }
      }
      return buffer;
    }

    startRainSoundscape() {
      // Pink noise through lowpass & bandpass for cozy window rain
      const noise = this.ctx.createBufferSource();
      noise.buffer = this.createNoiseBuffer('pink');
      noise.loop = true;

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(1400, this.ctx.currentTime);

      const gain = this.ctx.createGain();
      gain.gain.setValueAtTime(0.55, this.ctx.currentTime);

      noise.connect(filter);
      filter.connect(gain);
      gain.connect(this.masterGain);
      noise.start(0);
      this.noiseNode = noise;

      // Occasional soft droplets against glass
      const playDrop = () => {
        if (!this.enabled || this.activeMode !== 'rain') return;
        try {
          const osc = this.ctx.createOscillator();
          const dropGain = this.ctx.createGain();
          osc.type = 'sine';
          const freq = 1200 + Math.random() * 1600;
          osc.frequency.setValueAtTime(freq, this.ctx.currentTime);
          osc.frequency.exponentialRampToValueAtTime(300, this.ctx.currentTime + 0.04);
          dropGain.gain.setValueAtTime(0.06 * (Math.random() * 0.6 + 0.4), this.ctx.currentTime);
          dropGain.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + 0.04);
          osc.connect(dropGain);
          dropGain.connect(this.masterGain);
          osc.start();
          osc.stop(this.ctx.currentTime + 0.05);
        } catch(e){}
        this.rainTimer = setTimeout(playDrop, 120 + Math.random() * 600);
      };
      this.rainTimer = setTimeout(playDrop, 400);
    }

    startSnowSoundscape() {
      // Brown noise for wind & crackling candlelight / fireplace
      const noise = this.ctx.createBufferSource();
      noise.buffer = this.createNoiseBuffer('brown');
      noise.loop = true;

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(450, this.ctx.currentTime);

      const gain = this.ctx.createGain();
      gain.gain.setValueAtTime(0.4, this.ctx.currentTime);

      noise.connect(filter);
      filter.connect(gain);
      gain.connect(this.masterGain);
      noise.start(0);
      this.noiseNode = noise;

      // Fire crackles
      const playCrackle = () => {
        if (!this.enabled || this.activeMode !== 'snow') return;
        try {
          const crackleBuffer = this.ctx.createBuffer(1, Math.floor(this.ctx.sampleRate * 0.015), this.ctx.sampleRate);
          const cData = crackleBuffer.getChannelData(0);
          for (let i = 0; i < cData.length; i++) cData[i] = (Math.random() * 2 - 1) * Math.exp(-i / 100);
          const src = this.ctx.createBufferSource();
          src.buffer = crackleBuffer;
          const cFilter = this.ctx.createBiquadFilter();
          cFilter.type = 'bandpass';
          cFilter.frequency.setValueAtTime(2200, this.ctx.currentTime);
          const cGain = this.ctx.createGain();
          cGain.gain.setValueAtTime(0.18 * (Math.random() * 0.8 + 0.2), this.ctx.currentTime);
          src.connect(cFilter);
          cFilter.connect(cGain);
          cGain.connect(this.masterGain);
          src.start();
        } catch(e){}
        this.crackleTimer = setTimeout(playCrackle, 80 + Math.random() * 500);
      };
      this.crackleTimer = setTimeout(playCrackle, 300);
    }

    startCitySoundscape() {
      // Deep low-frequency lo-fi night air and subtle drone
      const noise = this.ctx.createBufferSource();
      noise.buffer = this.createNoiseBuffer('pink');
      noise.loop = true;

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'bandpass';
      filter.frequency.setValueAtTime(500, this.ctx.currentTime);
      filter.Q.setValueAtTime(0.6, this.ctx.currentTime);

      const gain = this.ctx.createGain();
      gain.gain.setValueAtTime(0.28, this.ctx.currentTime);

      // Low sub drone
      const drone = this.ctx.createOscillator();
      drone.type = 'sine';
      drone.frequency.setValueAtTime(75, this.ctx.currentTime);
      const droneGain = this.ctx.createGain();
      droneGain.gain.setValueAtTime(0.04, this.ctx.currentTime);
      drone.connect(droneGain);
      droneGain.connect(this.masterGain);
      drone.start(0);

      noise.connect(filter);
      filter.connect(gain);
      gain.connect(this.masterGain);
      noise.start(0);

      this.noiseNode = {
        stop: () => {
          try { noise.stop(); } catch(e){}
          try { drone.stop(); } catch(e){}
        }
      };
    }

    stopAll() {
      clearTimeout(this.rainTimer);
      clearTimeout(this.crackleTimer);
      if (this.noiseNode) {
        try { this.noiseNode.stop(); } catch(e){}
        this.noiseNode = null;
      }
    }

    setMode(mode) {
      this.activeMode = mode;
      if (this.enabled) {
        this.stopAll();
        this.initCtx();
        if (mode === 'rain') this.startRainSoundscape();
        else if (mode === 'snow') this.startSnowSoundscape();
        else if (mode === 'city') this.startCitySoundscape();
      }
    }

    setVolume(vol) {
      this.volume = Math.max(0, Math.min(1, vol));
      if (this.masterGain && this.ctx) {
        this.masterGain.gain.setTargetAtTime(this.enabled ? this.volume : 0, this.ctx.currentTime, 0.05);
      }
    }

    setEnabled(enabled) {
      this.enabled = !!enabled;
      this.initCtx();
      if (this.enabled) {
        this.masterGain.gain.setTargetAtTime(this.volume, this.ctx.currentTime, 0.1);
        this.setMode(this.activeMode);
      } else {
        this.masterGain.gain.setTargetAtTime(0, this.ctx.currentTime, 0.1);
        setTimeout(() => { if (!this.enabled) this.stopAll(); }, 150);
      }
    }
  }

  window.StudyAmbience = new StudyAmbienceEngine();
})(window);
