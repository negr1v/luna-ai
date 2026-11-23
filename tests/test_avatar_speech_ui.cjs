const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { test } = require('node:test');
const { chromium } = require('playwright');
const origin = 'http://127.0.0.1:7860';

async function fixture(browser, delayed = false, realAvatar = false) {
  const page = await browser.newPage();
  const calls = [];
  await page.addInitScript(({ delayed }) => {
    window.avatarCalls = [];
    window.resolveAvatarLoad = null;
    window.delayedAvatar = delayed;
    window.testInputLevel = 128;
    window.MediaStream = class {};
    window.testMicRequests = 0;
    navigator.mediaDevices.getUserMedia = async () => {
      window.testMicRequests++;
      const track = new EventTarget();
      track.readyState = 'live';
      track.stop = () => { track.readyState = 'ended'; };
      return { getTracks: () => [track], getAudioTracks: () => [track] };
    };
    window.MediaRecorder = class {
      static isTypeSupported() { return true; }
      mimeType = 'audio/webm';
      state = 'inactive';
      start() { this.state = 'recording'; }
      stop() {
        this.state = 'inactive';
        queueMicrotask(() => {
          this.ondataavailable?.({data:new Blob(['speech'], {type:this.mimeType})});
          this.onstop?.();
        });
      }
    };
    class FakeAudioContext {
      constructor() { this.state = 'running'; this.destination = {}; this.currentTime = 0; }
      decodeAudioData(data, success) { success({duration: 1}); }
      createBufferSource() {
        const node = { playbackRate: {value: 1}, connect() {}, disconnect() {}, start() {}, stop() {} };
        window.testAudioSource = node;
        return node;
      }
      createMediaStreamSource() { return { connect(node) { node.isMic = true; }, disconnect() {} }; }
      createAnalyser() { return { fftSize: 128, frequencyBinCount: 64, connect() {}, getByteFrequencyData(array) { array.fill(64); }, getByteTimeDomainData(array) { array.fill(this.isMic ? window.testInputLevel : 160); } }; }
      createOscillator() { return { connect() {}, start() {}, stop() {}, frequency: {setValueAtTime(){}, exponentialRampToValueAtTime(){}, linearRampToValueAtTime(){}} }; }
      createGain() { return { connect() {}, gain: {setValueAtTime(){}, exponentialRampToValueAtTime(){}, linearRampToValueAtTime(){}} }; }
    }
    window.AudioContext = FakeAudioContext;
    window.webkitAudioContext = FakeAudioContext;
  }, { delayed });
  await page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === '/') return route.fulfill({path: path.join(__dirname, 'index.html'), contentType: 'text/html'});
    if (realAvatar && /^\/static\/[\w/.-]+$/.test(url.pathname) && !url.pathname.includes('..')) {
      const file = path.join(__dirname, url.pathname.slice(1));
      if (fs.existsSync(file) && fs.statSync(file).isFile()) return route.fulfill({path: file});
    }
    if (url.pathname === '/static/study_mommy_live.js') return route.fulfill({contentType: 'application/javascript', body: `
      window.StudyMommyLive = { loadCharacter: async function(canvas, id) {
        if (window.delayedAvatar) await new Promise(resolve => window.resolveAvatarLoad = resolve);
        return { id, setManner(value) { window.avatarCalls.push(['manner', value]); },
          setSpeaking(value, volume) { window.avatarCalls.push(['speaking', value, volume]); },
          nod() {}, destroy() {} };
      } };
    `});
    if (url.pathname === '/static/js/local_stt.js') return route.fulfill({path:path.join(__dirname,'static/js/local_stt.js'),contentType:'application/javascript'});
    calls.push(url.pathname);
    if (url.pathname === '/api/stt') {
      assert.match(request.postData(), /name="language"\r\n\r\ntr\r\n/);
      return route.fulfill({json:{text:'Merhaba'}});
    }
    if (url.pathname === '/api/chat/stream') return route.fulfill({contentType:'text/event-stream',body:'event: done\ndata: {"reply":"Merhaba"}\n\n'});
    if (url.pathname === '/api/config') return route.fulfill({json:{tts_engine:'fish_audio', fish_audio_api_key_configured:true}});
    if (url.pathname === '/api/tts_direct') return route.fulfill({json:{audio_base64:'AQIDBA=='}});
    return route.fulfill({json:{}});
  });
  await page.goto(origin);
  await page.waitForFunction(() => window.StudyMommyLive);
  return {page, calls};
}
async function playPreview(page) {
  await page.locator('#voicePreviewBtn').evaluate(button => button.click());
  await page.waitForFunction(() => !!window.testAudioSource);
}

test('avatar follows actual audio lifecycle', async t => {
  const browser = await chromium.launch({channel:'chrome', args:['--enable-unsafe-swiftshader']});
  t.after(() => browser.close());
  await t.test('audio starts and ends with the avatar speaking state', async t => {
    const {page} = await fixture(browser); t.after(() => page.close());
    await page.waitForFunction(() => !!window.studyMommyCtrl);
    await playPreview(page);
    assert(await page.evaluate(() => window.avatarCalls.some(([kind, value]) => kind === 'speaking' && value === true)));
    await page.evaluate(() => window.testAudioSource.onended());
    assert.equal(await page.evaluate(() => window.avatarCalls.filter(([kind]) => kind === 'speaking').at(-1)?.[1]), false);
    await page.waitForTimeout(450);
    assert.equal(await page.evaluate(() => window.testMicRequests), 0, 'Voice preview must not activate the microphone');
  });
  await t.test('interrupted playback stops avatar speech', async t => {
    const {page} = await fixture(browser); t.after(() => page.close());
    await page.waitForFunction(() => !!window.studyMommyCtrl);
    await playPreview(page);
    await page.locator('#ojAudioStopBtn').evaluate(button => button.click());
    assert.equal(await page.evaluate(() => window.avatarCalls.filter(([kind]) => kind === 'speaking').at(-1)?.[1]), false);
  });
  await t.test('avatar loaded after audio starts joins ongoing speech', async t => {
    const {page} = await fixture(browser, true); t.after(() => page.close());
    await page.waitForFunction(() => !!window.resolveAvatarLoad);
    await playPreview(page);
    await page.evaluate(() => window.resolveAvatarLoad());
    await page.waitForFunction(() => !!window.studyMommyCtrl);
    assert(await page.evaluate(() => window.avatarCalls.some(([kind, value]) => kind === 'speaking' && value === true)));
  });
  await t.test('local recording and Ahu playback drive the avatar in sequence', async t => {
    const {page,calls} = await fixture(browser); t.after(() => page.close());
    await page.waitForFunction(() => !!window.studyMommyCtrl);
    await page.keyboard.press('F8');
    await page.getByText('Sizi dinliyorum',{exact:true}).waitFor();
    await page.evaluate(() => { window.testInputLevel = 160; });
    await page.getByText('Ses algılandı, metne çevriliyor…',{exact:true}).waitFor();
    await page.evaluate(() => { window.testInputLevel = 128; });
    await page.waitForFunction(() => !!window.testAudioSource);
    assert.deepEqual(calls.filter(url => ['/api/stt','/api/chat/stream','/api/tts_direct'].includes(url)),
      ['/api/stt','/api/chat/stream','/api/tts_direct']);
    assert(await page.evaluate(() => window.avatarCalls.some(([kind,value]) => kind === 'speaking' && value)));
    await page.evaluate(() => window.testAudioSource.onended());
    await page.getByText('Sizi dinliyorum',{exact:true}).waitFor();
  });
  await t.test('real WebGL portrait renders and opens its mouth during playback', async t => {
    const {page} = await fixture(browser, false, true); t.after(() => page.close());
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.waitForFunction(() => !!window.studyMommyCtrl?.currentPose, null, { timeout: 15000 });
    assert.equal(await page.locator('#liveFaceCanvas').evaluate(el => el.style.opacity), '1');
    await playPreview(page);
    await page.waitForFunction(() => window.studyMommyCtrl?.currentPose?.open > 0.01, null, { timeout: 10000 });
    await page.evaluate(() => window.testAudioSource.onended());
    await page.waitForFunction(() => window.studyMommyCtrl?.currentPose?.open < 0.03, null, { timeout: 10000 });
    assert.deepEqual(pageErrors, []);
  });
});
