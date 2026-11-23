const { chromium } = require('playwright');
const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel:'chrome'});
  try {
    const page = await browser.newPage({ reducedMotion: 'reduce' });
    let blockPortraits = false;
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.origin !== 'http://127.0.0.1:7860') return route.abort();
      if (blockPortraits && /\/static\/avatars\/study_mommy_.*\.webp$/.test(url.pathname)) return route.abort();
      const file = path.join(__dirname, url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname));
      if (file.startsWith(__dirname) && fs.existsSync(file) && fs.statSync(file).isFile()) {
        // The Windows aiohttp runtime serves these valid WebP files as octet-stream.
        const contentType = file.endsWith('.webp') ? 'application/octet-stream' : undefined;
        return route.fulfill({path:file, contentType});
      }
      if (url.pathname === '/api/models/hub') return route.fulfill({json:{status:'ok',active_model:'local-demo',models:[{id:'local-demo',name:'Yerel model',provider:'local',pricing:'FREE'}]}});
      return route.fulfill({json:{}});
    });
    await page.goto('http://127.0.0.1:7860/');
    const phase = process.argv[2] || 'after';
    for (const [width,height] of [[1280,720],[760,900]]) {
      await page.setViewportSize({width,height});
      await page.evaluate(() => scrollTo(0, 0));
      await page.locator('#animeAvatarImg').waitFor();
      if (phase.includes('after')) await page.waitForFunction(() => localStorage.getItem('jarvis_active_avatar_char') && document.getElementById('animeAvatarImg').naturalWidth > 0);
      else await page.waitForFunction(() => document.getElementById('animeAvatarImg').complete);
      console.log('avatar', await page.locator('#animeAvatarImg').evaluate(e=>({src:e.src,width:e.naturalWidth})));
      await page.screenshot({path:path.join(__dirname, 'dashboard-' + phase + '-' + width + '.png')});
      const result = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > innerWidth,
        controls: ['textInput','promptMicBtn','studyMommyModeBtn','hpBtnModel','sidebarNewChatBtn'].map(id => {
          const control = document.getElementById(id);
          const r = control.getBoundingClientRect();
          const hit = (x, y) => control.contains(document.elementFromPoint(x, y));
          return {id, usable:r.width>0 && r.left>=0 && r.right<=innerWidth && r.top>=0 && r.bottom<=innerHeight
            && hit(r.left+r.width/2,r.top+2) && hit(r.left+r.width/2,r.bottom-2)};
        })
      }));
      console.log(width, JSON.stringify(result));
      if (phase.includes('after')) { assert(!result.overflow); assert(result.controls.every(c=>c.usable)); }
      for (const [name, selector] of [['models','#hpBtnModel'],['notifications','#hpBtnNotifications']]) {
        await page.locator(selector).click();
        await page.locator('#hpCard').waitFor();
        if (name === 'models') await page.locator('#hpCard').getByText('Yerel model',{exact:true}).waitFor();
        else await page.locator('#hpCard').getByText('Etkinlik günlüğü',{exact:true}).waitFor();
        await page.screenshot({path:path.join(__dirname, 'dashboard-' + phase + '-' + name + '-' + width + '.png')});
        await page.locator('#hpCloseBtn').click();
      }
      const nav = page.locator('#compactNavToggle');
      if (width === 760 && await nav.isVisible()) {
        await nav.press('Enter');
        assert.equal(await nav.getAttribute('aria-expanded'), 'true');
        for (const button of await page.locator('#zeroMainSidebar .sidebar-item').all()) {
          await button.scrollIntoViewIfNeeded();
          await button.click({ trial: true });
          await button.focus();
          assert(await button.evaluate(el => document.activeElement === el));
        }
      }
      for (const [name, title] of [['memory','Hafıza ve veri kaynakları'],['tasks','Görevler & Radarlar'],['diagnostics','Güvenlik ve günlükler']]) {
        await page.getByRole('button',{name:new RegExp(title)}).click();
        if (width === 760 && await nav.isVisible()) await nav.click();
        await page.screenshot({path:path.join(__dirname, 'dashboard-' + phase + '-' + name + '-' + width + '.png')});
        if (width === 760 && await nav.isVisible()) await nav.click();
      }
      await page.getByRole('button',{name:/Ana ekran/}).click();
      if (width === 760 && await nav.isVisible()) await nav.click();
      await page.evaluate(() => scrollTo(0, 0));
    }
    if (phase.includes('after')) {
      for (const [character, portrait] of [['rose','rose'],['bob','lavender'],['braid','sage']]) {
        await page.locator(`.char-pick-btn[data-char="${character}"]`).click();
        await page.waitForFunction(name => {
          const image = document.getElementById('animeAvatarImg');
          return image.src.endsWith('/study_mommy_' + name + '.webp') && image.complete && image.naturalWidth > 0;
        }, portrait);
      }
      blockPortraits = true;
      await page.reload();
      await page.locator('#avatarFallback').getByText('Sage', { exact: true }).waitFor();
      assert(await page.locator('#animeAvatarImg').isHidden());
      console.log('PASS: three decoded portraits and deliberate fallback under a blocked image response');
    }
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
