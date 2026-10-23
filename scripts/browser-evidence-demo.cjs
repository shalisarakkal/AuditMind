// Installed Chrome acceptance for persistent synthetic examples; no inference.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('../frontend/node_modules/playwright');
(async () => {
  const password = process.env.AUDITMIND_DEMO_PASSWORD;
  const sessionCookie = process.env.AUDITMIND_DEMO_SESSION;
  if (!password && !sessionCookie) throw new Error('Set AUDITMIND_DEMO_PASSWORD; never print it');
  const output = path.resolve(__dirname, '../temp/auditmind-demo/evidence-examples');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const checks = [], errors = [];
  try {
    const page = await browser.newPage({ acceptDownloads: true });
    page.on('pageerror', error => errors.push(error.message));
    if (sessionCookie) {
      await page.context().addCookies([{ name: 'auditmind_session', value: sessionCookie, domain: 'localhost', path: '/api/v1/auth', httpOnly: true, sameSite: 'Strict' }]);
      await page.goto('http://localhost:3000/');
    } else {
      await page.goto('http://localhost:3000/login');
      await page.getByLabel('Email', { exact: true }).fill('demo.admin@example.com');
      await page.getByLabel('Password', { exact: true }).fill(password);
      await page.getByRole('button', { name: 'Sign in', exact: true }).click();
      await page.waitForURL('http://localhost:3000/');
    }
    await page.getByLabel('Organization', { exact: true }).selectOption({ label: 'Evidence examples - SYNTHETIC ONLY' });
    for (const state of ['sufficient', 'limited', 'insufficient', 'conflicting']) {
      await page.goto('http://localhost:3000/reports');
      const title = `SYNTHETIC - ${state[0].toUpperCase() + state.slice(1)} evidence example`;
      await page.getByRole('row').filter({ hasText: title }).getByRole('button', { name: 'View', exact: true }).click();
      await page.getByRole('note').filter({ hasText: 'Synthetic mock:' }).waitFor();
      assert.match(await page.locator('body').innerText(), /Synthetic mock.*No AI calls/);
      if (state !== 'sufficient') {
        await page.getByText('Partial AI assessment — overall score unavailable', { exact: true }).waitFor();
        assert.equal(await page.getByText('Not scored', { exact: true }).count(), 7);
      } else await page.getByText('Simulated score (not a real assessment)', { exact: true }).waitFor();
      await page.screenshot({ path: path.join(output, `${state}.png`), fullPage: true });
      for (const format of ['HTML', 'PDF']) {
        const pending = page.waitForEvent('download');
        await page.getByRole('button', { name: `Download ${format}`, exact: true }).click();
        const download = await pending;
        assert.equal(await download.failure(), null);
        const target = path.join(output, `${state}.${format.toLowerCase()}`);
        await download.saveAs(target);
        const content = await fs.readFile(target);
        if (format === 'HTML') assert.match(content.toString(), /Synthetic mock - no AI calls/);
        else assert.equal(content.subarray(0, 5).toString(), '%PDF-');
        checks.push(`${state}: ${format} export`);
      }
      checks.push(`${state}: visible synthetic warning and correct score state`);
    }
    await page.goto('http://localhost:3000/reports');
    for (const [value, count] of [['complete', 1], ['partial', 3]]) {
      await page.getByLabel('Assessment completeness').selectOption(value);
      await page.waitForFunction(expected => document.querySelectorAll('tbody tr').length === expected, count);
      checks.push(`${value}: ${count} reports`);
    }
    assert.deepEqual(errors, []);
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify({ date: new Date().toISOString(), browser: browser.version(), checks, errors }, null, 2));
    console.log(`${checks.length} Chrome checks passed; screenshots and exports saved under temp/auditmind-demo/evidence-examples`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
