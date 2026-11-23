/**
 * ZERO OS / LUNA-AI Telemetry & System Metrics Module
 * Handles live hardware monitoring (CPU, RAM, Disk, Active Window, Gaming Mode),
 * Header Pill Tooltips, Connection State & Monotonic Sequence Reconnects.
 */

(function(window, document) {
  'use strict';

  let telemetryIntervalId = null;
  let isTelemetryPolling = false;
  let lastTelemetrySeq = 0;
  let currentTelemetryIntervalMs = 3000;

  let connectionState = 'ONLINE'; // 'ONLINE' | 'OFFLINE' | 'RECONNECTING'
  let consecutiveNetworkFailures = 0;
  const OFFLINE_FAILURE_THRESHOLD = 2;

  function resolveApiUrl(url) {
    if (url.startsWith('http://') || url.startsWith('https://')) return url;
    if (window.location.protocol === 'file:' || !window.location.origin || window.location.origin === 'null') {
      return 'http://127.0.0.1:7860' + (url.startsWith('/') ? url : '/' + url);
    }
    return url;
  }

  async function zeroSafeFetch(url, options = {}, timeoutMs = 8000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const finalUrl = resolveApiUrl(url);
      const res = await fetch(finalUrl, { ...options, signal: controller.signal });
      clearTimeout(timeoutId);
      setConnectionOnline();
      return res;
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        setConnectionOffline('Sunucu Yanıtı Zaman Aşımına Uğradı (Timeout)');
      } else {
        setConnectionOffline();
      }
      throw err;
    }
  }

  function setConnectionOffline(customMsg) {
    if (connectionState === 'ONLINE') {
      connectionState = 'OFFLINE';
    } else {
      connectionState = 'RECONNECTING';
    }
    const banner = document.getElementById('reconnectBanner');
    const bannerText = document.getElementById('reconnectStatusText');
    if (banner) banner.style.display = 'flex';
    if (bannerText && customMsg) bannerText.textContent = `ZERO AI BAĞLANTI HATTI — ${customMsg.toUpperCase()}`;
    const sysServerStatus = document.getElementById('sysServerStatus');
    if (sysServerStatus) {
      sysServerStatus.textContent = 'Bağlantı Kesildi';
      sysServerStatus.style.color = '#ef4444';
    }
  }

  function setConnectionOnline() {
    const wasOffline = (connectionState !== 'ONLINE');
    connectionState = 'ONLINE';
    consecutiveNetworkFailures = 0;
    const banner = document.getElementById('reconnectBanner');
    if (banner) banner.style.display = 'none';
    const sysServerStatus = document.getElementById('sysServerStatus');
    if (sysServerStatus) {
      sysServerStatus.textContent = 'Çevrimiçi';
      sysServerStatus.style.color = '#10b981';
    }
  }

  function setTelemetryOffline() {
    const cpuMetric = document.getElementById('cpuMetric');
    const ramMetric = document.getElementById('ramMetric');
    const pillCpuVal = document.getElementById('pillCpuVal');
    const pillRamVal = document.getElementById('pillRamVal');
    const pillDiskVal = document.getElementById('pillDiskVal');
    if (cpuMetric) cpuMetric.textContent = '--%';
    if (ramMetric) ramMetric.textContent = '-- GB';
    if (pillCpuVal) pillCpuVal.textContent = '--%';
    if (pillRamVal) pillRamVal.textContent = '--%';
    if (pillDiskVal) pillDiskVal.textContent = '--%';
  }

  async function pollSystemMetrics() {
    if (isTelemetryPolling) return;
    isTelemetryPolling = true;
    try {
      const res = await zeroSafeFetch('/api/system_metrics', {}, 4000);
      if (!res.ok) {
        console.warn('System metrics HTTP status:', res.status);
        setTelemetryOffline();
        return;
      }
      const data = await res.json();
      if (data && data.status === 'ok') {
        setConnectionOnline();

        // Server epoch recovery
        if (data.server_epoch && data.server_epoch !== window.__lastServerEpoch) {
          window.__lastServerEpoch = data.server_epoch;
          lastTelemetrySeq = 0;
        }

        // Monotonic sequence guard against stale out-of-order network responses
        if (data.telemetry_seq && lastTelemetrySeq > 0 && data.telemetry_seq < lastTelemetrySeq) {
          return;
        }
        if (data.telemetry_seq) {
          lastTelemetrySeq = data.telemetry_seq;
        }

        // Adaptive Performance Profile Synchronization
        if (data.performance_profile) {
          window.currentPerformanceProfile = data.performance_profile;
          window.currentPerformanceSpecs = data.performance_specs || {};
        }
        if (data.polling_interval_ms && typeof updateTelemetryInterval === 'function') {
          updateTelemetryInterval(data.polling_interval_ms);
        }

        // Header Minimal Smooth Hover Pill Bar Update
        const pillCpuVal = document.getElementById('pillCpuVal');
        const ttCpuPct = document.getElementById('ttCpuPct');
        if (data.cpu_percent !== null) {
          if (pillCpuVal) pillCpuVal.textContent = `${data.cpu_percent}%`;
          if (ttCpuPct) ttCpuPct.textContent = `${data.cpu_percent}%`;
        }

        const pillRamVal = document.getElementById('pillRamVal');
        const ttRamUsed = document.getElementById('ttRamUsed');
        const ttRamTotal = document.getElementById('ttRamTotal');
        const ttRamAvail = document.getElementById('ttRamAvail');
        if (data.ram_percent !== null) {
          if (pillRamVal) pillRamVal.textContent = `${data.ram_percent}%`;
          if (ttRamUsed && data.ram_used_gb !== null) ttRamUsed.textContent = `${data.ram_used_gb} GB`;
          if (ttRamTotal && data.ram_total_gb !== null) ttRamTotal.textContent = `${data.ram_total_gb} GB`;
          if (ttRamAvail && data.ram_available_gb !== null) ttRamAvail.textContent = `${data.ram_available_gb} GB`;
        }

        const pillDiskVal = document.getElementById('pillDiskVal');
        const ttDiskPct = document.getElementById('ttDiskPct');
        const ttDiskFree = document.getElementById('ttDiskFree');
        if (data.disk_percent !== null) {
          if (pillDiskVal) pillDiskVal.textContent = `${data.disk_percent}%`;
          if (ttDiskPct) ttDiskPct.textContent = `${data.disk_percent}%`;
          if (ttDiskFree && data.disk_free_gb !== null) ttDiskFree.textContent = `${data.disk_free_gb} GB Boş`;
        }

        // System View Meters
        const sysCpuVal = document.getElementById('sysCpuVal');
        const sysCpuFill = document.getElementById('sysCpuFill');
        if (sysCpuVal) sysCpuVal.textContent = data.cpu_percent !== null ? `${data.cpu_percent}%` : '--%';
        if (sysCpuFill && data.cpu_percent !== null) {
          sysCpuFill.style.width = `${Math.min(100, Math.max(0, data.cpu_percent))}%`;
        }

        const sysRamVal = document.getElementById('sysRamVal');
        const sysRamFill = document.getElementById('sysRamFill');
        const sysRamPct = document.getElementById('sysRamPct');
        const sysRamAvail = document.getElementById('sysRamAvail');
        if (sysRamVal) sysRamVal.textContent = data.ram_used_gb !== null ? `${data.ram_used_gb} / ${data.ram_total_gb} GB` : '--/-- GB';
        if (sysRamFill && data.ram_percent !== null) {
          sysRamFill.style.width = `${Math.min(100, Math.max(0, data.ram_percent))}%`;
        }
        if (sysRamPct) sysRamPct.textContent = data.ram_percent !== null ? `Kullanım: %${data.ram_percent}` : 'Kullanım: --%';
        if (sysRamAvail && data.ram_available_gb !== null) sysRamAvail.textContent = `Boş: ${data.ram_available_gb} GB`;

        const sysDiskVal = document.getElementById('sysDiskVal');
        const sysDiskFill = document.getElementById('sysDiskFill');
        const sysDiskPct = document.getElementById('sysDiskPct');
        if (sysDiskVal) sysDiskVal.textContent = data.disk_free_gb !== null ? `${data.disk_free_gb} GB Boş` : '--';
        if (sysDiskFill && data.disk_percent !== null) {
          sysDiskFill.style.width = `${Math.min(100, Math.max(0, data.disk_percent))}%`;
        }
        if (sysDiskPct) sysDiskPct.textContent = data.disk_percent !== null ? `Doluluk: %${data.disk_percent}` : 'Doluluk: --%';

        // Active Window & Server Status
        const rightWindowFocus = document.getElementById('rightWindowFocus');
        if (rightWindowFocus) rightWindowFocus.textContent = data.active_window || 'Masaüstü';

        const sysServerStatus = document.getElementById('sysServerStatus');
        const sysServerUptime = document.getElementById('sysServerUptime');
        if (sysServerStatus) {
          sysServerStatus.textContent = data.server_status === 'online' ? 'Çevrimiçi' : 'Bağlantı Kesildi';
          sysServerStatus.style.color = data.server_status === 'online' ? '#10b981' : '#ef4444';
        }
        if (sysServerUptime && data.server_uptime_str) {
          sysServerUptime.textContent = data.server_uptime_str;
        }

        const hpBadgeSystem = document.getElementById('hpBadgeSystem');
        if (hpBadgeSystem && data.cpu_percent !== null) {
          hpBadgeSystem.textContent = `CPU %${Math.round(data.cpu_percent)}`;
        }
      } else {
        setTelemetryOffline();
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        consecutiveNetworkFailures++;
        if (consecutiveNetworkFailures >= OFFLINE_FAILURE_THRESHOLD) {
          setConnectionOffline();
        }
      }
      console.warn('Telemetry poll hatası:', e);
      setTelemetryOffline();
    } finally {
      isTelemetryPolling = false;
    }
  }

  function updateTelemetryInterval(newIntervalMs) {
    if (!newIntervalMs || newIntervalMs === currentTelemetryIntervalMs) return;
    currentTelemetryIntervalMs = newIntervalMs;
    if (telemetryIntervalId) {
      clearInterval(telemetryIntervalId);
      telemetryIntervalId = setInterval(() => {
        if (!document.hidden) pollSystemMetrics();
      }, currentTelemetryIntervalMs);
    }
  }

  function startTelemetryPolling() {
    if (!telemetryIntervalId) {
      pollSystemMetrics();
      telemetryIntervalId = setInterval(() => {
        if (!document.hidden) pollSystemMetrics();
      }, currentTelemetryIntervalMs);
    }
  }

  // Auto-start polling on page load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startTelemetryPolling);
  } else {
    startTelemetryPolling();
  }

  // Export module
  window.TelemetryModule = {
    pollSystemMetrics,
    startTelemetryPolling,
    setConnectionOnline,
    setConnectionOffline,
    zeroSafeFetch,
    resolveApiUrl
  };
  window.pollSystemMetrics = pollSystemMetrics;
  window.startTelemetryPolling = startTelemetryPolling;
  window.zeroSafeFetch = zeroSafeFetch;

})(window, document);
