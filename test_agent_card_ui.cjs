const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    let approvalCalls = 0;
    const calls = [];
    const pending = {
      task_id: 'fixture-task', state: 'AWAITING_APPROVAL', description: 'Not Defteri testi',
      steps: [{ step_id: 1, status: 'AWAITING_APPROVAL', description: 'Metni yaz',
        tool_name: 'set_text', approval_id: 'fixture-approval',
        approval: { target: { window_title: 'Not Defteri', process_name: 'notepad.exe' }, expires_at: 1 } }]
    };
    await page.route('**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin !== 'http://127.0.0.1:7860') return route.abort();
      if (url.pathname === '/') return route.fulfill({ path: path.join(__dirname, 'index.html'), contentType: 'text/html' });
      calls.push({ method: request.method(), path: url.pathname, body: request.postData() });
      if (url.pathname === '/api/agent/tasks' && request.method() === 'POST') {
        return route.fulfill({ json: { status: 'ok', task: pending } });
      }
      if (url.pathname === '/api/agent/tasks/fixture-task/approve') {
        approvalCalls++;
        if (approvalCalls === 1) return route.fulfill({ status: 500, json: { message: 'Onay gönderilemedi' } });
        return route.fulfill({ json: { status: 'ok', task: { ...pending, state: 'COMPLETED', steps: [] } } });
      }
      return route.fulfill({ json: {} });
    });
    await page.goto('http://127.0.0.1:7860/');
    assert.equal(await page.locator('#agentHudCard').isVisible(), false);
    await page.locator('.dashboard-tools > summary').click();
    await page.locator('#openAgentTaskBtn').click();
    assert.equal(await page.locator('#agentHudCard').isVisible(), true);
    assert.equal(await page.locator('#agentInput').evaluate(element => document.activeElement === element), true);
    await page.locator('#agentInput').fill('örnek görev');
    await page.locator('#agentSubmitBtn').click();
    await page.locator('#agentApprovalPanel').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#agentHudCard').isVisible(), true);
    assert.match(await page.locator('#agentApprovalText').innerText(), /notepad\.exe — Not Defteri/);
    const bell = page.locator('#approvalBellBtn');
    await page.locator('#approvalBadgeCount').waitFor({ state: 'visible' });
    await bell.press('Enter');
    assert.equal(await bell.getAttribute('aria-expanded'), 'true');
    await page.locator('#approvalOpenTaskBtn').click();
    assert.equal(await bell.getAttribute('aria-expanded'), 'false');
    assert.equal(await page.locator('#agentApprovalPanel').evaluate(panel => document.activeElement === panel), true);
    assert.equal(approvalCalls, 0);
    await page.locator('#agentApproveBtn').click();
    await page.waitForFunction(() => !document.querySelector('#agentApproveBtn').disabled);
    assert.equal(await page.locator('#agentApprovalPanel').isVisible(), true);
    assert.equal(approvalCalls, 1);
    assert.deepEqual(JSON.parse(calls.find(call => call.path.endsWith('/approve')).body),
      { step_id: 1, approval_id: 'fixture-approval' });
    await page.locator('#agentApproveBtn').click();
    await page.locator('#agentApprovalPanel').waitFor({ state: 'hidden' });
    assert.equal(await page.locator('#agentStateBadge').innerText(), 'COMPLETED');
    assert.equal(await page.locator('#approvalBadgeCount').isHidden(), true);
    assert.equal(approvalCalls, 2);
    console.log('PASS accessible task entry, approval target visible, no automatic approval, failure retains card, successful approval displays returned state');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
