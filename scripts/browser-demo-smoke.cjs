// Real installed Chrome, against the isolated demo only. No external AI calls.
// Set AUDITMIND_DEMO_PASSWORD; optionally AUDITMIND_PLATFORM_PASSWORD.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('../frontend/node_modules/playwright');

(async () => {
  if (!process.env.AUDITMIND_DEMO_PASSWORD) throw new Error('Set AUDITMIND_DEMO_PASSWORD');
  const output = path.resolve(__dirname, '../temp/auditmind-demo/browser');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const failures = [];
  const evidence = { browser: browser.version(), channel: 'chrome', checks: [] };
  try {
    const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    let authorization;
    page.on('request', request => {
      const header = request.headers().authorization;
      if (header && request.url().startsWith('http://localhost:3000/api/')) authorization = header;
    });
    page.on('pageerror', error => failures.push(error.message));
    page.on('response', response => {
      if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`);
    });
    async function signIn(email, password) {
      await page.goto('http://localhost:3000/login');
      await page.getByLabel('Email', { exact: true }).fill(email);
      await page.getByLabel('Password', { exact: true }).fill(password);
      await page.getByRole('button', { name: 'Sign in', exact: true }).click();
      await page.waitForURL('http://localhost:3000/');
    }
    await signIn('demo.admin@example.com', process.env.AUDITMIND_DEMO_PASSWORD);
    await page.getByTestId('overall-score').waitFor();
    assert.match(await page.locator('body').innerText(), /4 assets/);
    assert.match(await page.locator('body').innerText(), /7 findings/);
    evidence.checks.push('Admin sign-in; dashboard has 4 assets and 7 findings');
    assert.ok(authorization);
    const worker = await page.request.get('http://localhost:3000/api/v1/worker-status', { headers: { authorization } });
    assert.equal(worker.status(), 200);
    assert.equal((await worker.json()).running, true);
    evidence.checks.push('Authenticated API confirms worker heartbeat');
    await page.screenshot({ path: path.join(output, 'dashboard.png'), fullPage: true });
    for (const name of ['Assets', 'Findings', 'Uploads', 'Archived', 'Activity', 'Documents', 'People', 'Settings', 'Reports']) {
      const link = page.getByRole('link', { name, exact: true });
      const href = await link.getAttribute('href');
      await link.click();
      await page.waitForURL(`http://localhost:3000${href}`);
      await page.getByRole('heading', { level: 1 }).first().waitFor();
      // Polling is intentional in this app, so networkidle is not readiness.
      await page.getByText(/^Loading(?:…|\.\.\.)?$/).first().waitFor({ state: 'hidden' });
      assert.doesNotMatch(await page.locator('body').innerText(), /Internal Server Error|Application error: a client-side exception/);
      evidence.checks.push(`Organization page: ${name}`);
      if (name === 'Assets') {
        const filter = page.getByRole('searchbox', { name: 'Filter hostname', exact: true });
        await filter.fill('demo-web-01');
        await page.waitForURL(url => url.searchParams.get('hostname') === 'demo-web-01');
        await page.getByRole('row').filter({ hasText: 'demo-web-01' }).waitFor();
        await page.getByRole('row').filter({ hasText: 'demo-backup-01' }).waitFor({ state: 'hidden' });
        await filter.fill('');
        await page.waitForURL(url => !url.searchParams.has('hostname'));
        await page.getByRole('row').filter({ hasText: 'demo-backup-01' }).waitFor();
        evidence.checks.push('Asset hostname filter applies and clears');
        const menu = page.locator('details').filter({ has: page.locator('summary[aria-label^="Filter type:"]') });
        const summary = menu.locator('summary');
        await summary.click();
        const server = menu.getByRole('checkbox', { name: 'Server', exact: true });
        await server.check();
        assert.equal(await menu.evaluate(element => element.open), true);
        await page.getByRole('heading', { name: 'Assets', exact: true }).click();
        assert.equal(await menu.evaluate(element => element.open), false);
        await summary.click();
        assert.equal(await server.isChecked(), true);
        await server.focus();
        await page.keyboard.press('Escape');
        assert.equal(await menu.evaluate(element => element.open), false);
        assert.equal(await summary.evaluate(element => element === document.activeElement), true);
        await summary.click();
        await menu.getByRole('button', { name: 'Clear', exact: true }).click();
        assert.equal(await menu.evaluate(element => element.open), true);
        await page.getByRole('heading', { name: 'Assets', exact: true }).click();
        evidence.checks.push('Type picker: internal selection stays open; outside click/Escape close; selection retained; Clear works');
      }
    }
    const row = page.getByRole('row').filter({ hasText: 'DEMO - Rule-based preview (not AI)' });
    await row.getByRole('button', { name: 'View', exact: true }).click();
    await page.getByText('TEST-ONLY RULE-BASED REPORT.', { exact: false }).first().waitFor();
    await page.screenshot({ path: path.join(output, 'report.png'), fullPage: true });
    for (const format of ['HTML', 'PDF']) {
      const downloadPromise = page.waitForEvent('download');
      await page.getByRole('button', { name: `Download ${format}`, exact: true }).first().click();
      const download = await downloadPromise;
      assert.equal(await download.failure(), null);
      const file = path.join(output, `report.${format.toLowerCase()}`);
      await download.saveAs(file);
      const content = await fs.readFile(file);
      assert.ok(content.length > 100);
      if (format === 'PDF') assert.equal(content.subarray(0, 5).toString(), '%PDF-');
      else assert.match(content.toString(), /TEST-ONLY RULE-BASED REPORT/);
      evidence.checks.push(`Downloaded and validated ${format}`);
    }
    await page.reload();
    await page.getByRole('heading', { name: 'Audit Reports' }).waitFor();
    evidence.checks.push('Session survives browser refresh');
    await page.getByRole('button', { name: '+ Rule-based test report', exact: true }).click();
    const previewTitle = `Chrome smoke preview ${Date.now()}`;
    await page.getByLabel('Report title', { exact: true }).fill(previewTitle);
    await page.getByRole('button', { name: 'Generate Test Report', exact: true }).click();
    await page.getByRole('row').filter({ hasText: previewTitle }).waitFor();
    evidence.checks.push('Created a non-AI test report through the UI');
    if (process.env.AUDITMIND_PLATFORM_PASSWORD) {
      // A separate context proves independent platform authentication.
      await context.clearCookies();
      await signIn('demo.platform@example.com', process.env.AUDITMIND_PLATFORM_PASSWORD);
      for (const name of ['Organizations', 'Accounts', 'Platform activity', 'Security defaults', 'Shared standards']) {
        const link = page.getByRole('link', { name, exact: true });
        const href = await link.getAttribute('href');
        await link.click();
        await page.waitForURL(`http://localhost:3000${href}`);
        await page.getByRole('heading', { level: 1 }).first().waitFor();
        await page.getByText(/^Loading(?:…|\.\.\.)?$/).first().waitFor({ state: 'hidden' });
        evidence.checks.push(`Platform page: ${name}`);
      }
    }
    assert.deepEqual(failures, [], 'Browser exceptions or server errors');
    evidence.checks.push('No uncaught browser exceptions or HTTP 5xx responses');
    console.log(JSON.stringify(evidence, null, 2));
    await fs.writeFile(path.join(output, 'result.json'), JSON.stringify(evidence, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
