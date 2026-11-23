const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const { chromium } = require('playwright');
const origin = 'http://127.0.0.1:7860';

async function fixture(browser, { text = 'Merhaba ACCIO', sttStatus = 200 } = {}) {
  const page = await browser.newPage({ reducedMotion: 'reduce' });
  page.setDefaultTimeout(7000);
  const requests = [];
  await page.addInitScript(() => {
    window.energy = 0;
    const Audio = window.AudioContext || window.webkitAudioContext;
    Audio.prototype.createMediaStreamSource = () => ({ connect() {}, disconnect() {} });
    AnalyserNode.prototype.getByteTimeDomainData = samples => samples.fill(128 + window.energy);
    Audio.prototype.decodeAudioData = function (_, success) { success(this.createBuffer(1, 32, 16000)); };
    const createSource = Audio.prototype.createBufferSource;
    Audio.prototype.createBufferSource = function () {
      const source = createSource.call(this);
      source.start = () => { window.testReplySource = source; };
      source.stop = () => {};
      return source;
    };
    window.MediaStream = class { constructor(tracks) { this.tracks = tracks; } };
    navigator.mediaDevices.getUserMedia = async () => {
      const track = new EventTarget();
      track.readyState = 'live';
      track.stop = () => { track.readyState = 'ended'; };
      window.testTrack = track;
      return { getTracks: () => [track], getAudioTracks: () => [track] };
    };
    window.MediaRecorder = class {
      static isTypeSupported() { return true; }
      mimeType = 'audio/webm;codecs=opus';
      state = 'inactive';
      start() { this.state = 'recording'; }
      stop() {
        this.state = 'inactive';
        queueMicrotask(() => {
          this.ondataavailable?.({ data: new Blob(['fixture'], { type: this.mimeType }) });
          this.onstop?.();
        });
      }
    };
  });
  await page.route('**/*', route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === '/') return route.fulfill({path: path.join(__dirname, 'index.html'), contentType:'text/html'});
    if (url.pathname === '/static/js/local_stt.js') return route.fulfill({path:path.join(__dirname,'static/js/local_stt.js'),contentType:'application/javascript'});
    if (url.pathname === '/api/stt') {
      requests.push(['stt', request.headers()['content-type'], request.postData()]);
      return route.fulfill({ status: sttStatus, json: { text } });
    }
    if (url.pathname === '/api/chat/stream') {
      requests.push(['chat', request.postDataJSON()]);
      return route.fulfill({contentType:'text/event-stream',body:'event: done\ndata: {"reply":"Merhaba, dinliyorum."}\n\n'});
    }
    if (url.pathname === '/api/tts_direct') {
      requests.push(['tts', request.postDataJSON()]);
      return route.fulfill({json:{audio_base64:'AQIDBA=='}});
    }
    return route.fulfill({json:{}});
  });
  await page.goto(origin);
  return {page, requests};
}

async function speakThenPause(page) {
  await page.evaluate(() => { window.energy = 18; });
  await page.getByText('Ses algılandı, metne çevriliyor…', {exact:true}).waitFor();
  await page.evaluate(() => { window.energy = 0; });
}

test('MediaRecorder uses local STT and the existing Ahu synthesis route', async t => {
  const browser = await chromium.launch({channel:'chrome'});
  t.after(() => browser.close());
  await t.test('voice pause yields one multipart, one chat and one synthesis', async t => {
    const {page,requests}=await fixture(browser); t.after(()=>page.close());
    await page.keyboard.press('F8');
    await page.getByText('Sizi dinliyorum',{exact:true}).waitFor();
    await speakThenPause(page);
    await page.waitForFunction(() => window.testReplySource);
    assert.deepEqual(requests.map(row=>row[0]), ['stt','chat','tts']);
    assert.match(requests[0][1], /^multipart\/form-data/);
    assert.match(requests[0][2], /name="audio"/);
    assert.match(requests[0][2], /name="language"\r\n\r\ntr\r\n/);
    assert.equal(requests[1][1].message,'Merhaba ACCIO');
    assert.equal(requests[1][1].voice_reply,false);
    assert.equal(requests[2][1].text,'Merhaba, dinliyorum.');
    await page.evaluate(() => window.testReplySource.onended());
    await page.getByText('Sizi dinliyorum',{exact:true}).waitFor();
  });
  await t.test('dictation send includes the final recording and does not synthesize', async t => {
    const {page,requests}=await fixture(browser); t.after(()=>page.close());
    await page.locator('#studioSearchBtn').click();
    await page.locator('#promptMicBtn').click();
    await page.getByText('Dikte dinliyor…',{exact:true}).waitFor();
    await page.evaluate(() => { window.energy = 18; });
    await page.waitForTimeout(220);
    await page.locator('#dictationStopBtn').click();
    await page.locator('#transcript').getByText('Merhaba, dinliyorum.').waitFor();
    assert.deepEqual(requests.map(row=>row[0]), ['stt','chat']);
  });
  await t.test('manual send with silent capture makes no STT request', async t => {
    const {page,requests}=await fixture(browser); t.after(()=>page.close());
    await page.locator('#studioSearchBtn').click();
    await page.locator('#promptMicBtn').click();
    await page.getByText('Dikte dinliyor…',{exact:true}).waitFor();
    await page.locator('#dictationStopBtn').click();
    await page.locator('#dictationBar').waitFor({state:'hidden'});
    assert.deepEqual(requests, []);
  });
  await t.test('empty STT and HTTP rejection never send a chat request', async t => {
    for (const opts of [{text:''},{sttStatus:503}]) {
      const {page,requests}=await fixture(browser,opts);
      try {
        await page.keyboard.press('F8');
        await page.getByText('Sizi dinliyorum',{exact:true}).waitFor();
        await speakThenPause(page);
        await page.waitForResponse(response=>new URL(response.url()).pathname==='/api/stt');
        await page.waitForTimeout(200);
        assert.deepEqual(requests.map(row=>row[0]), ['stt']);
      } finally { await page.close(); }
    }
  });
  await t.test('an open microphone with no signal reports silence and recovers', async t => {
    const {page,requests}=await fixture(browser); t.after(()=>page.close());
    await page.locator('#studioSearchBtn').click();
    await page.locator('#promptMicBtn').click();
    await page.getByText('Henüz ses sinyali algılanmadı.', {exact:false}).waitFor({timeout:9000});
    assert.deepEqual(requests, []);
    await page.evaluate(() => { window.energy = 18; });
    await page.getByText('Dikte dinliyor…', {exact:true}).waitFor();
  });
  await t.test('returning to the stage preserves messages and the unsent draft', async t => {
    const {page,requests}=await fixture(browser); t.after(()=>page.close());
    await page.locator('#studioSearchBtn').click();
    await page.locator('#textInput').fill('Sahne dönüş testi');
    await page.locator('#sendBtn').click();
    const reply = page.locator('#transcript').getByText('Merhaba, dinliyorum.', {exact:true});
    await reply.waitFor();
    await page.locator('#textInput').fill('Gönderilmemiş taslak');
    await page.locator('#exitChatToStageBtn').click();
    await page.locator('#studioCharacter').waitFor({timeout:4000});
    assert.equal(await reply.count(), 1);
    await page.locator('#studioSearchBtn').click();
    await reply.waitFor();
    assert.equal(await page.locator('#textInput').inputValue(), 'Gönderilmemiş taslak');
    assert.deepEqual(requests.map(row=>row[0]), ['chat']);
  });
  await t.test('closing the microphone discards capture', async t => {
    const {page,requests}=await fixture(browser); t.after(()=>page.close());
    await page.keyboard.press('F8');
    await page.getByText('Sizi dinliyorum',{exact:true}).waitFor();
    await page.locator('#voiceModeCloseBtn').click();
    assert.equal(await page.evaluate(()=>window.testTrack.readyState),'ended');
    assert.deepEqual(requests,[]);
  });
});
