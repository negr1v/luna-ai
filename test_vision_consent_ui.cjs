const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  try {
    const page = await browser.newPage();
    await page.addInitScript(() => {
      window.frameExtractions = 0;
      window.pickerCancelled = false;
      navigator.mediaDevices.getDisplayMedia = async options => {
        window.pickerOptions = options;
        if (window.pickerCancelled) throw new DOMException('Cancelled', 'NotAllowedError');
        const source = document.createElement('canvas');
        source.width = source.height = 32;
        source.getContext('2d').fillRect(0, 0, 32, 32);
        window.previewTrack = source.captureStream(10).getVideoTracks()[0];
        return new MediaStream([window.previewTrack]);
      };
      const draw = CanvasRenderingContext2D.prototype.drawImage;
      CanvasRenderingContext2D.prototype.drawImage = function(source, ...args) {
        if (source.id === 'screenShareVideo') window.frameExtractions++;
        return draw.call(this, source, ...args);
      };
    });

    const route = { provider: 'openrouter', label: 'OpenRouter (OpenAI GPT-4o)', model: 'openai/gpt-4o', paid: true };
    let available = true;
    let changed = false;
    const visionRequests = [];
    const approvals = [];
    const submissions = [];
    await page.route('**/*', async intercept => {
      const request = intercept.request();
      const url = new URL(request.url());
      if (url.origin !== 'http://127.0.0.1:7860') return intercept.abort();
      if (url.pathname === '/') return intercept.fulfill({path: path.join(__dirname, 'index.html')});
      if (url.pathname === '/static/js/local_stt.js') {
        return intercept.fulfill({path: path.join(__dirname, 'static/js/local_stt.js'), contentType: 'application/javascript'});
      }
      if (url.pathname.startsWith('/api/vision')) visionRequests.push(url.pathname);
      if (url.pathname === '/api/vision/destination') {
        return intercept.fulfill(available ? {json: route} : {status: 503, json: {message: 'Hedef kullanılamıyor.'}});
      }
      if (url.pathname === '/api/vision/approval') {
        approvals.push(request.postDataJSON());
        return intercept.fulfill(changed
          ? {status: 409, json: {message: 'Analiz hedefi değişti. Yeniden onayla.'}}
          : {json: {approval_token: 'one-frame-test'}});
      }
      if (url.pathname === '/api/vision') {
        submissions.push(request.postDataJSON());
        return intercept.fulfill({json: {reply: 'Taklit Vision yanıtı'}});
      }
      return intercept.fulfill({json: {}});
    });

    await page.goto('http://127.0.0.1:7860/');
    const share = page.locator('#screenShareBtn');
    const preview = page.locator('#screenShareFloatingHud');
    const dialog = page.locator('#screenVisionConsent');
    const analyze = page.locator('#screenShareCaptureBtn');
    const ask = page.locator('#bbSnapshotBtn');
    const frames = () => page.evaluate(() => window.frameExtractions);
    await page.locator('.dashboard-tools > summary').click();
    await page.evaluate(() => { window.pickerCancelled = true; });
    const cancelled = page.waitForEvent('console', {predicate: event => event.text().includes('Ekran paylaşımı iptal edildi')});
    await share.click();
    await cancelled;
    assert(await preview.isHidden());
    await page.evaluate(() => { window.pickerCancelled = false; });
    await share.click();
    await preview.getByText('Yerel önizleme').waitFor();
    await page.waitForFunction(() => document.getElementById('screenShareVideo').videoWidth > 0);
    assert.equal(await page.evaluate(() => window.pickerOptions.surfaceSwitching), 'exclude');
    assert.equal(await frames(), 0);
    assert.equal(submissions.length, 0);
    await page.locator('#screenShareStopBtn').click();
    assert(await preview.isHidden());
    assert.equal(await page.evaluate(() => window.previewTrack.readyState), 'ended');
    assert.equal(await frames(), 0);
    assert.equal(submissions.length, 0);
    assert.deepEqual(visionRequests, []);

    if (!(await share.isVisible())) await page.locator('.dashboard-tools > summary').click();
    await share.click();
    await page.waitForFunction(() => document.getElementById('screenShareVideo').videoWidth > 0);
    await analyze.click();
    await dialog.getByText('1 ekran görüntüsü analiz için gönderilecek').waitFor();
    await dialog.getByText(/OpenRouter.*Ücretli API/).waitFor();
    assert.equal(await frames(), 0);
    await dialog.getByRole('button', {name: 'Vazgeç'}).click();
    await dialog.waitFor({state: 'hidden'});
    assert(await preview.isVisible());
    assert.equal(approvals.length, 0);
    const board = page.locator('#studyMommyModeBtn');
    if (!(await board.isVisible())) await page.locator('.dashboard-tools > summary').press('Enter');
    await board.click();
    await ask.click();
    await dialog.waitFor();
    await page.keyboard.press('Escape');
    await dialog.waitFor({state: 'hidden'});
    assert(await preview.isVisible());
    assert.equal(await frames(), 0);

    available = false;
    await ask.click();
    await page.getByText('Hedef kullanılamıyor.', {exact: false}).first().waitFor();
    assert(await dialog.isHidden());
    available = true;
    await ask.click();
    await dialog.waitFor();
    changed = true;
    await dialog.getByRole('button', {name: 'Gönder ve analiz et'}).click();
    await page.getByText('Analiz hedefi değişti. Yeniden onayla.', {exact: false}).first().waitFor();
    assert.equal(await frames(), 0);
    assert.equal(submissions.length, 0);
    changed = false;

    await analyze.click();
    await dialog.waitFor();
    await page.evaluate(() => { document.getElementById('screenShareVideo').srcObject = new MediaStream(); });
    await dialog.getByRole('button', {name: 'Gönder ve analiz et'}).click();
    await dialog.waitFor({state: 'hidden'});
    assert.equal(approvals.length, 1);
    assert.equal(await frames(), 0);
    await page.locator('#screenShareStopBtn').click();
    if (!(await share.isVisible())) await page.locator('.dashboard-tools > summary').click();
    await share.click();
    await page.waitForFunction(() => document.getElementById('screenShareVideo').videoWidth > 0);
    await analyze.click();
    await dialog.waitFor();
    await page.evaluate(() => window.previewTrack.dispatchEvent(new Event('ended')));
    await dialog.waitFor({state: 'hidden'});
    assert(await preview.isHidden());
    assert.equal(await frames(), 0);

    if (!(await share.isVisible())) await page.locator('.dashboard-tools > summary').click();
    await share.click();
    await page.waitForFunction(() => document.getElementById('screenShareVideo').videoWidth > 0);
    for (const [index, entry] of [analyze, ask].entries()) {
      const reply = page.getByText('Taklit Vision yanıtı', {exact: false}).nth(index);
      await entry.click();
      await dialog.getByRole('button', {name: 'Gönder ve analiz et'}).click();
      await reply.waitFor();
    }
    assert.equal(await frames(), 2);
    assert.equal(submissions.length, 2);
    assert(submissions.every(data => data.approval_token === 'one-frame-test' && data.provider === route.provider && data.image_base64));
    console.log('Preview and rejected/cancelled consents: 0 frames/0 Vision POSTs; approved UI entries: 2 frames/2 stubbed Vision POSTs');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
