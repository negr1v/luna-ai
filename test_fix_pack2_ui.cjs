const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.stack));
    const calls = [];
    const chatRequests = [];
    const previewRequests = [];
    const taskWrites = [];
    let rejectTaskLoad = false;
    const taskFixture = [
      { id: 'open-task', subject: 'İngilizce çalış', duration: 40, category: 'genel', done: false },
      { id: 'done-task', subject: 'Fizik notları', duration: 20, category: 'fizik', done: true }
    ];
    const memoryWrites = [];
    const memoryDeletes = [];
    let rejectMemoryLoad = false;
    let rejectMemoryWrite = false;
    const memoryFixture = {
      notes: [
        '07.11 Babaya söyleme ve ilk deneme hedefi',
        'Black Friday 27.11.2026 AM5 alım hedefi'
      ],
      revision: 4,
      revision_token: 'tok-rev-4'
    };
    memoryFixture.entries = memoryFixture.notes.map((text, i) => ({ id: 'note-' + i, text }));
    const recommendationQueries = [];
    let active = 'first';
    const notificationFixture = [{ id: 'disposable' }];
    const modelFixture = [
      { id: 'first', name: 'first', pricing: 'FREE' },
      { id: 'second', name: 'second', isFree: true, pricing: 'FREE', capabilities: ['coding'] },
      { id: 'locked', name: 'locked', pricing: 'FREE' },
      { id: 'paid', name: 'paid', isFree: false, pricing: 'PAID', capabilities: ['coding'] },
    ];
    await page.route('**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin !== 'http://127.0.0.1:7860') return route.abort();
      const endpoint = url.pathname;
      if (endpoint === '/') return route.fulfill({ path: path.join(__dirname, 'index.html'), contentType: 'text/html' });
      if (endpoint === '/static/js/local_stt.js') {
        return route.fulfill({ path: path.join(__dirname, 'static/js/local_stt.js'), contentType: 'application/javascript' });
      }
      const method = request.method();
      calls.push([method, endpoint]);
      let status = 200;
      let json = {};
      if (endpoint === '/api/tasks' && method === 'GET') {
        status = rejectTaskLoad ? 503 : 200;
        json = taskFixture;
      }
      if (endpoint === '/api/tasks' && method === 'POST') {
        taskWrites.push(request.postDataJSON());
        json = { status: 'ok' };
      }
      if (endpoint === '/api/memory' && method === 'GET') {
        status = rejectMemoryLoad ? 503 : 200;
        json = memoryFixture;
      }
      if (endpoint === '/api/memory/notes' && method === 'POST') {
        if (rejectMemoryWrite) return route.fulfill({ status: 503, json: {} });
        const body = request.postDataJSON();
        memoryWrites.push(body);
        const newNote = body.text;
        memoryFixture.notes.push(newNote);
        const entry = { text: newNote, id: 'note-added' };
        memoryFixture.entries.push(entry);
        json = { status: 'ok', entry, revision: 5, revision_token: 'tok-rev-5' };
      }
      if (endpoint.startsWith('/api/memory/notes/') && method === 'DELETE') {
        memoryDeletes.push({ endpoint, revision: request.headers()['x-memory-revision-token'] });
        json = { status: 'ok', revision: 6, revision_token: 'tok-rev-6' };
      }
      if (endpoint === '/api/agent/status') { status = 503; json = { status: 'offline' }; }
      if (endpoint === '/api/desktop/status') json = { mode: 'stub' };
      if (endpoint === '/api/config' && method === 'GET') {
        json = { active_model: active, tts_engine: 'fish_audio', fish_audio_api_key_configured: true };
      }
      if (endpoint === '/api/tts_direct' && method === 'POST') {
        previewRequests.push(request.postDataJSON());
        json = { audio_base64: null };
      }
      if (endpoint === '/api/health/rate_limits') json = { status: 'ok', chat: {}, tts: {} };
      if (endpoint === '/api/notifications/deferred') json = { count: notificationFixture.length, deferred_notifications: notificationFixture };
      if (endpoint === '/api/activity_logs') {
        json = [{ timestamp: '12:00:00', type: 'model_selected', details: 'Örnek model etkinliği' }];
      }
      if (endpoint === '/api/models/hub') {
        json = { status: 'ok', active_model: active, models: modelFixture };
      }
      if (endpoint === '/api/models/recommend') {
        const task = url.searchParams.get('task');
        const freeOnly = url.searchParams.get('free_only');
        recommendationQueries.push({ task, freeOnly });
        json = { status: 'ok', recommendations: modelFixture
          .filter(model => model.capabilities?.includes(task))
          .filter(model => freeOnly !== 'true' || model.isFree || model.pricing === 'FREE')
          .map(({ id, ...model }) => ({ model_id: id, ...model })) };
      }
      if (endpoint === '/api/models/select' && method === 'POST') {
        const { model_id } = request.postDataJSON();
        if (model_id === 'locked') { status = 403; json = { status: 'error', message: 'Model kilitli.' }; }
        else { active = model_id; json = { status: 'ok', active_model: active, model_name: active }; }
      }
      if (endpoint === '/api/chat/stream' && method === 'POST') {
        const body = request.postDataJSON();
        chatRequests.push(body);
        const result = { reply: 'Sahte yanıt', model: body.config?.model || active };
        return route.fulfill({
          status: 200, contentType: 'text/event-stream',
          body: 'event: done\ndata: ' + JSON.stringify(result) + '\n\n',
        });
      }
      return route.fulfill({ status, json });
    });
    await page.goto('http://127.0.0.1:7860/');
    const sidebar = page.locator('#zeroMainSidebar');
    async function verifyMemory() {
      assert.equal(await page.locator('#zeroMainSidebar [data-view="memory"]').count(), 0);
      await page.locator('#openSettingsBtn').click();
      await page.locator('#settingsTabStudio').click();
      await page.locator('#manageMemoryBtn').click();
      await page.locator('#viewMemory').waitFor({ state: 'visible' });
      assert(await page.locator('#viewMemory').evaluate(element => document.activeElement === element));
      await page.locator('#memCountBadge').getByText('2 / 2 Kayıt', { exact: true }).waitFor();
      await page.locator('#memorySearchInput').fill('babaya');
      assert.equal(await page.locator('#memoryNotesList .memory-note-item').count(), 1);
      await page.locator('#memorySearchInput').fill('bulunmayan_kelime_xyz');
      await page.locator('#memoryNotesList').getByText('Aramana uyan not bulunamadı.', { exact: true }).waitFor();
      await page.locator('#memorySearchInput').fill('');
      assert.equal(await page.locator('#memoryNotesList .memory-note-item').count(), 2);
      rejectMemoryLoad = true;
      await page.locator('#refreshMemoryBtn').click();
      await page.locator('#memoryLoadStatus').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#memoryNotesList .memory-note-item').count(), 2);
      rejectMemoryLoad = false;
      await page.locator('#newMemoryInput').fill('Yeni hedef notu');
      rejectMemoryWrite = true;
      await page.locator('#addMemoryBtn').click();
      await page.locator('#memoryLoadStatus').getByText('Not eklenemedi. Taslak korundu.').waitFor();
      assert.equal(await page.locator('#newMemoryInput').inputValue(), 'Yeni hedef notu');
      rejectMemoryWrite = false;
      await page.locator('#addMemoryBtn').evaluate(button => {
        button.click();
        button.click();
      });
      await page.waitForFunction(() => !document.querySelector('#newMemoryInput').value);
      assert.deepEqual(memoryWrites.map(write => write.text), ['Yeni hedef notu']);
      await page.locator('#memorySearchInput').fill('black friday');
      const deleteNote = page.locator('#memoryNotesList .memory-del-btn');
      page.once('dialog', dialog => dialog.dismiss());
      await deleteNote.click();
      assert.equal(memoryDeletes.length, 0);
      page.once('dialog', dialog => dialog.accept());
      await deleteNote.click();
      await page.locator('#memoryLoadStatus').getByText('Not silindi.').waitFor();
      assert.deepEqual(memoryDeletes, [{ endpoint: '/api/memory/notes/note-1', revision: 'tok-rev-5' }]);
      await page.locator('#memorySearchInput').fill('');
      assert.equal(await page.locator('#memoryNotesList .memory-note-item').count(), 2);
      await page.locator('#zeroMainSidebar [data-view="cockpit"]').click();
      console.log('PASS: memory navigation, search, refresh failure, draft retry, and confirmed deletion');
      const chatInput = page.locator('#textInput');
      if (await chatInput.isHidden()) await page.locator('#studioSearchBtn').click();
      const transcript = page.locator('#transcript');
      const providerCalls = chatRequests.length;
      await chatInput.fill('Bunu unutma: Sessiz yanıtları tercih ediyorum.');
      await chatInput.press('Enter');
      await transcript.getByText('Hafızaya kaydettim.', { exact: true }).waitFor();
      assert.equal(memoryWrites.at(-1).text, 'Sessiz yanıtları tercih ediyorum.');
      assert.equal(memoryWrites.at(-1).source, 'explicit_user_command');
      await chatInput.fill('Hafızaya kaydet: Toplantı notları kısa olsun.');
      await chatInput.press('Enter');
      await transcript.getByText('Hafızaya kaydettim.', { exact: true }).nth(1).waitFor();
      assert.equal(memoryWrites.at(-1).text, 'Toplantı notları kısa olsun.');

      rejectMemoryWrite = true;
      await chatInput.fill('Hafızaya kaydet: Kaydedilemeyen örnek');
      await chatInput.press('Enter');
      await transcript.getByText(/Hafızaya kaydedildiğini doğrulayamadım/).waitFor();
      rejectMemoryWrite = false;
      assert.equal(chatRequests.length, providerCalls, 'Memory command must bypass the chat provider');
      console.log('PASS: local remember command, confirmed write, and truthful error');

    }
    if (process.argv.includes('--memory')) {
      await verifyMemory();
      assert.deepEqual(pageErrors, [], 'Unexpected browser script error');
      return;
    }
    const systemPanel = page.locator('#ojCockpitSidePanel');
    const toolsMenu = page.locator('.dashboard-tools');
    const menuSummary = toolsMenu.locator('summary').first();
    const openTools = async () => {
      if (!(await toolsMenu.evaluate(element => element.open))) await menuSummary.press('Enter');
    };
    const systemToggle = page.locator('#toggleSystemPanelBtn');
    assert(await systemPanel.isHidden(), 'System panel must start collapsed');
    const studioSearch = page.locator('#studioSearchBtn');
    const composerInputs = ['textInput', 'promptMicBtn', 'sendBtn'];
    assert.deepEqual(pageErrors, [], 'Browser failed during startup');
    await page.waitForFunction(() => typeof document.querySelector('#studioSearchBtn').onclick === 'function', null, { timeout: 4000 });
    for (const [width, height] of [[1280, 720], [760, 900]]) {
      await page.setViewportSize({width, height});
      assert.equal(await studioSearch.getAttribute('aria-expanded'), 'false');
      for (const id of composerInputs) assert(await page.locator('#' + id).isHidden(), id + ' must start hidden');
      await studioSearch.click({ trial: true });
      await studioSearch.press('Enter');
      await page.waitForFunction(() => document.activeElement?.id === 'textInput');
      assert.equal(await studioSearch.getAttribute('aria-expanded'), 'true');
      const result = await page.evaluate(composerInputs => {
        const ids = composerInputs;
        const rect = element => element.getBoundingClientRect();
        const boxes = ids.map(id => {
          const element = document.getElementById(id);
          const r = rect(element);
          const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return { id, left: r.left, right: r.right, top: r.top, bottom: r.bottom,
            visible: r.width > 0 && r.height > 0 && r.left >= 0 && r.right <= innerWidth
              && r.top >= 0 && r.bottom <= innerHeight && element.contains(hit) };
        });
        const group = ['.orb-box', '.openjarvis-prompt-container'].map(selector => {
          const r = rect(document.querySelector(selector));
          return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
        });
        return { boxes, group, overflow: document.documentElement.scrollWidth > innerWidth };
      }, composerInputs);
      console.log(`Viewport ${width}x${height}: ${JSON.stringify(result)}`);
      assert(!result.overflow, 'Horizontal overflow');
      assert(result.boxes.every(box => box.visible), 'Primary control clipped or obstructed');
      const composerBoxes = result.boxes.slice(0, composerInputs.length).sort((left, right) => left.left - right.left);
      assert(composerBoxes.every((box, i) => !i || composerBoxes[i - 1].right <= box.left), 'Composer controls overlap');
      assert(result.group[0].bottom <= result.group[1].top, 'Avatar and composer overlap');
      assert(result.group.every(box => box.left >= 0 && box.right <= width), 'Visual group clipped horizontally');
      const centers = result.group.map(box => (box.left + box.right) / 2);
      assert(Math.max(...centers) - Math.min(...centers) < 2, 'Visual group centers do not align');
      await page.locator('#studioSettingsBtn').click();
      await page.locator('#settingsSectionStudio').waitFor({ state: 'visible' });
      await page.locator('#closeSettingsBtn').click();
      await page.locator('#headerFocusRoomBtn').click();
      await page.locator('#focusRoom[open]').waitFor({ state: 'visible' });
      await page.locator('#focusRoom').getByRole('button', { name: 'Kapat', exact: true }).click();
      const newChat = page.locator('#sidebarNewChatBtn');
      await newChat.scrollIntoViewIfNeeded();
      await newChat.click({ trial: true });
      const nav = page.locator('#compactNavToggle');
      if (await nav.isVisible()) {
        await nav.press('Enter');
        assert.equal(await nav.getAttribute('aria-expanded'), 'true');
      }
      else assert((await sidebar.boundingBox()).width <= 224, 'Desktop sidebar takes too much space');
      for (const button of await sidebar.locator('.sidebar-item:visible').all()) {
        await button.scrollIntoViewIfNeeded();
        await button.click({ trial: true });
        await button.focus();
        assert(await button.evaluate(element => document.activeElement === element), 'Sidebar keyboard focus failed');
      }
      if (await nav.isVisible()) await nav.click();
      await page.locator('#studioCollapseBtn').click();
      assert.equal(await studioSearch.getAttribute('aria-expanded'), 'false');
      for (const id of composerInputs) assert(await page.locator('#' + id).isHidden(), id + ' must collapse again');
      await page.waitForFunction(() => document.activeElement?.id === 'studioSearchBtn');
    }
    if (process.argv.includes('--viewport')) {
      assert.deepEqual(pageErrors, [], 'Unexpected browser script error');
      assert(!calls.some(([method]) => method !== 'GET'), 'Viewport checks must stay read-only');
      console.log('PASS: collapsed composer, keyboard open, layout and close at both viewport sizes');
      return;
    }
    await page.setViewportSize({ width: 1280, height: 720 });
    await studioSearch.click();
    assert.equal(await menuSummary.count(), 1, 'Dashboard tools menu is missing from the current header');
    const beforeToggles = calls.length;
    await menuSummary.press('Space');
    assert(await toolsMenu.evaluate(element => element.open));
    assert.equal(await toolsMenu.getByRole('button', {name: /Windows Optimizasyonu/i}).count(), 0);
    assert(await page.locator('#sidebarModelPill').isHidden(), 'Only one model entry belongs in the normal menu');
    for (const id of ['studyMommyModeBtn', 'gameModeToggleBtn']) {
      const toggle = page.locator('#' + id);
      await openTools();
      await toggle.click();
      assert.equal(await toggle.getAttribute('aria-pressed'), 'true');
      if (id === 'studyMommyModeBtn') assert(await page.locator('#studyBlackboardHud').isVisible());
      await openTools();
      await toggle.click();
      assert.equal(await toggle.getAttribute('aria-pressed'), 'false');
      if (id === 'studyMommyModeBtn') assert(await page.locator('#studyBlackboardHud').isHidden());
    }
    assert(!calls.slice(beforeToggles).some(([method]) => method !== 'GET'), 'Board and Quiet HUD must stay local');
    await menuSummary.click();
    const desktopCalls = () => calls.filter(([method, url]) => method === 'GET' && url === '/api/desktop/status').length;
    const beforeDesktop = desktopCalls();
    const desktopStatus = page.waitForResponse(response => new URL(response.url()).pathname === '/api/desktop/status');
    await sidebar.locator('.sidebar-secondary > summary').press('Enter');
    await sidebar.locator('[data-view="desktop"]').press('Enter');
    await desktopStatus;
    await page.locator('#viewDesktop').waitFor({ state: 'visible' });
    assert.equal(desktopCalls() - beforeDesktop, 1, 'One navigation action must load desktop status once');
    const start = calls.length;
    await page.getByRole('button', { name: /Güvenlik ve günlükler/ }).click();
    assert.equal(calls.slice(start).filter(([method]) => method !== 'GET').length, 0);
    await page.locator('#runDiagTestBtn').click();
    await page.locator('#diagResultsContainer').getByText(/Kullanılamıyor.*503/).waitFor({ timeout: 4000 });
    assert(calls.slice(start).some(([method, url]) => method === 'GET' && url === '/api/health/rate_limits'));
    assert(!calls.slice(start).some(([method, url]) => method !== 'GET' || url.endsWith('/execute')));

    for (const [width, height] of [[1280, 720], [760, 900]]) {
      await page.setViewportSize({ width, height });
      await openTools();
      await page.locator('#hpBtnNotifications').press('Enter', { timeout: 2500 });
      await page.locator('#hpCardTitle').getByText('Bildirimler', { exact: true }).waitFor();
      await page.locator('.activity-preview').getByText('Örnek model etkinliği').waitFor();
      const notificationBounds = await page.locator('#hpCard').boundingBox();
      assert(notificationBounds.x >= 0 && notificationBounds.x + notificationBounds.width <= width);
      assert.equal(await page.locator('#hpCard').getByRole('button', { name: 'Temizle' }).count(), 0);
      await page.locator('#hpCard').getByRole('button', { name: 'Etkinlik günlüğü' }).click();
      assert.deepEqual(notificationFixture, [{ id: 'disposable' }]);
      await openTools();
      await page.locator('#hpBtnModel').click({ timeout: 2500 });
      await page.locator('[data-model-id="locked"]').waitFor();
      const bounds = await page.locator('#hpCard').boundingBox();
      assert(bounds && bounds.x >= 0 && bounds.x + bounds.width <= width,
        JSON.stringify({ width, bounds, header: await page.locator('header').boundingBox() }));
      await page.locator('#hpCloseBtn').click();
    }

    await openTools();
    await page.locator('#hpBtnModel').click();
    await page.locator('[data-model-id="second"]').click();
    await page.locator('#quickModelFeedback').getByText('Aktif model: second').waitFor();
    await page.locator('.model-hub-current').getByText('second', { exact: true }).waitFor();
    await page.locator('[data-model-id="locked"]').click();
    await page.locator('#quickModelFeedback').getByText('Model seçilemedi: Model kilitli.').waitFor();
    assert.match(await page.locator('[data-model-id="second"]').innerText(), /Aktif/);
    assert.equal(await page.locator('#dashboardModelLabel').textContent(), 'second');
    assert.deepEqual(calls.filter(([method]) => method !== 'GET'), [
      ['POST', '/api/models/select'], ['POST', '/api/models/select']
    ]);

    const hub = page.locator('#hpCard');
    const codingChip = hub.getByRole('button', { name: /Kodlama/ });
    const freeChip = hub.getByRole('button', { name: /Sadece Ücretsiz/ });
    await codingChip.click();
    await hub.locator('[data-model-id="paid"]').waitFor();
    assert.equal(await codingChip.getAttribute('aria-pressed'), 'true');
    assert.equal(await hub.locator('[data-model-id="first"]').count(), 0);
    assert.equal(await hub.locator('.hp-item-row').getByText('Kodlama', { exact: true }).count(), 2);
    await freeChip.click();
    await hub.locator('[data-model-id="second"]').waitFor();
    assert.equal(await freeChip.getAttribute('aria-pressed'), 'true');
    assert.equal(await hub.locator('[data-model-id="paid"]').count(), 0);
    assert.deepEqual(recommendationQueries, [
      { task: 'coding', freeOnly: 'false' },
      { task: 'coding', freeOnly: 'true' },
    ]);
    await hub.getByRole('button', { name: 'Tümü' }).click();
    await hub.locator('[data-model-id="first"]').waitFor();
    assert.equal(await hub.locator('[data-model-id="paid"]').count(), 0);
    await hub.getByRole('button', { name: /Model Merkezi/ }).click();
    const modelCenter = page.locator('#modelSelectModal');
    await modelCenter.waitFor({ state: 'visible' });
    await modelCenter.locator('#closeModelModalBtn').click();
    await modelCenter.waitFor({ state: 'hidden' });

    await page.setViewportSize({ width: 1280, height: 720 });
    await page.locator('#zeroMainSidebar [data-view="cockpit"]').click();
    await menuSummary.press('Enter');
    await systemToggle.press('Enter');
    await systemPanel.waitFor({ state: 'visible' });
    assert.equal(await systemToggle.getAttribute('aria-expanded'), 'true');
    await systemToggle.press('Enter');
    await systemPanel.waitFor({ state: 'hidden' });
    assert.equal(await systemToggle.getAttribute('aria-expanded'), 'false');
    if (await page.locator('.dashboard-tools[open]').count()) {
      await menuSummary.click();
    }
    const secondary = sidebar.locator('.sidebar-secondary');
    if (!(await secondary.evaluate(element => element.open))) await secondary.locator('summary').press('Enter');
    await sidebar.locator('[data-view="automations"]').click();
    const automationDetails = page.locator('.automation-details');
    assert(await page.locator('#createAutoForm').isVisible());
    assert(await page.locator('#deferredNotifsCard').isHidden(), 'Technical details should start collapsed');
    await automationDetails.locator('summary').press('Enter');
    assert(await page.locator('#deferredNotifsCard').isVisible());
    await automationDetails.locator('summary').press('Enter');
    await sidebar.locator('[data-view="cockpit"]').click();
    await page.locator('#quickActionTasksBtn').click();
    await page.locator('#viewTasks').waitFor({ state: 'visible' });
    assert(await page.locator('#viewTasks').evaluate(element => document.activeElement === element));
    await page.locator('#taskProgressSummary').getByText('1 açık · 1 tamamlandı', { exact: true }).waitFor();
    assert.equal(await page.locator('#yksProgressText').innerText(), '20 / 60 dk');
    await page.locator('#taskSearchInput').fill('ingilizce');
    assert.equal(await page.locator('#liveTaskList .task-item').count(), 1);
    await page.locator('#taskFilterCompleted').click();
    assert.equal(await page.locator('#liveTaskList .task-item').count(), 0);
    await page.locator('#taskFilterAll').click();
    await page.locator('#taskSearchInput').fill('');
    rejectTaskLoad = true;
    await page.locator('#btnRefreshTasksTop').click();
    await page.locator('#taskLoadStatus').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#liveTaskList .task-item').count(), 2);
    rejectTaskLoad = false;
    await page.locator('#newTaskInput').fill('Örnek plan');
    await page.locator('#newTaskDueDate').fill('2030-02-03');
    await page.locator('#addTaskBtn').click();
    await page.waitForFunction(() => !document.querySelector('#newTaskInput').value);
    assert.equal(taskWrites[0]?.due_date, '2030-02-03');
    await page.locator('#zeroMainSidebar [data-view="cockpit"]').click();

    await verifyMemory();

    await page.locator('#textInput').fill('Model yönlendirme kontrolü');
    await page.locator('#textInput').press('Enter');
    await page.locator('#transcript').getByText('Sahte yanıt', { exact: true }).waitFor();
    assert.equal(chatRequests.length, 1);
    assert.equal(chatRequests[0].message, 'Model yönlendirme kontrolü');
    assert.equal(chatRequests[0].config?.model, undefined, 'Chat must use the saved server model');
    assert.equal(calls.filter(([method, endpoint]) => method === 'POST' && endpoint === '/api/chat').length, 0);
    assert.equal(await page.locator('#dashboardModelLabel').textContent(), 'second');
    await openTools();
    await page.locator('#hpBtnConfig').press('Enter');
    const preferences = page.locator('#hpCard');
    await preferences.getByRole('checkbox', { name: 'Model Hub', exact: true }).uncheck();
    await preferences.getByRole('checkbox', { name: 'Bildirimler', exact: true }).uncheck();
    await preferences.locator('#hpCloseBtn').press('Escape');
    assert(await menuSummary.evaluate(element => document.activeElement === element));
    await page.reload();
    await openTools();
    await page.locator('#hpBtnModel').waitFor({ state: 'hidden' });
    await page.locator('#hpBtnNotifications').waitFor({ state: 'hidden' });
    assert(await page.locator('#sidebarModelPill').isVisible(), 'Model Center should remain accessible when Model Hub is off');
    await page.locator('#sidebarModelPill').press('Enter');
    await modelCenter.waitFor({ state: 'visible' });
    await modelCenter.locator('#closeModelModalBtn').click();
    await openTools();
    await page.locator('#openSettingsBtn').click();
    await page.locator('#fishAudioGroup').waitFor({state: 'visible'});
    assert.equal(await page.locator('#ttsEngineSelect').inputValue(), 'fish_audio');
    assert.equal(await page.locator('#fishAudioKey').inputValue(), '');
    const previewRequest = page.waitForRequest(request =>
      request.method() === 'POST' && new URL(request.url()).pathname === '/api/tts_direct'
    );
    await page.locator('#voicePreviewBtn').click();
    await previewRequest;
    await page.waitForFunction(() => !document.querySelector('#voicePreviewBtn').disabled);
    assert.equal(previewRequests.length, 1);
    assert.equal(previewRequests[0].tts_engine, 'fish_audio');
    assert.equal(previewRequests[0].fish_audio_api_key, undefined);
    assert.equal(previewRequests[0].fish_audio_model_id, undefined);
    assert.deepEqual(pageErrors, [], 'Unexpected browser script error');
    console.log('PASS: diagnostics, notifications, two viewport widths, Model Hub success/rejection, saved visibility, Pack 1 toggles');
    console.log('PASS: narrow sidebar, keyboard disclosure, single Desktop navigation request, and opt-in system panel');
    console.log('PASS: Model Hub filters, Model Center open/close, confirmed label, SSE without stale model override, and Tasks shortcut');
    console.log('PASS: memory workspace Turkish search, count badge, offline/503 preservation, draft protection');
    console.log('PASS: settings menu preserves Fish Audio preview routing and keeps the saved key/reference server-side');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
