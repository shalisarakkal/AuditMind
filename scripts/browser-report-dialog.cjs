// Installed Chrome against the production frontend, with synthetic API fixtures.
// No live sign-in, consent mutation, provider call or backend write is performed.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('../frontend/node_modules/playwright');
const AxeBuilder = require('../frontend/node_modules/@axe-core/playwright').default;

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const result = { browser: browser.version(), api: 'intercepted synthetic fixtures', checks: [] };
  const artifacts = path.resolve(__dirname, '../temp/auditmind-demo/browser');
  await fs.mkdir(artifacts, { recursive: true });
  try {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 640 }]) {
      const context = await browser.newContext({ viewport });
      let approval = false;
      let unavailable = false;
      let reportPosts = 0;
      const errors = [];
      await context.route('**/api/v1/**', async route => {
        const req = route.request();
        const endpoint = new URL(req.url()).pathname.replace('/api/v1', '');
        const send = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
        if (endpoint === '/auth/refresh') return send({ access_token: 'fixture-token', must_change_password: false });
        if (endpoint === '/auth/me') return send({ id: 'fixture-admin', email: 'admin@example.com', name: 'SA01 admin', is_sysadmin: false, must_change_password: false });
        if (endpoint === '/orgs') return send([{ id: 'sa01', name: 'SA01', role: 'admin', archived: false }]);
        if (endpoint === '/worker-status') return send({ running: true });
        if (/\/(scans|archive-jobs)$/.test(endpoint)) return send([]);
        if (endpoint.endsWith('/reports/capabilities')) return send({ rule_based_test_enabled: true });
        if (endpoint.endsWith('/facets')) return send({ status: [], frameworks: [], framework: [] });
        if (endpoint.endsWith('/documents/settings')) return unavailable ? send({ detail: 'Fixture approval service unavailable' }, 503) : send({ report_granted: approval, report_target: 'anthropic:fixture-model:fixture-prompt', embedding_target: 'local:fixture', effective_embedding: 'local', embedding_granted: false });
        if (req.method() === 'POST') { reportPosts++; return send({ detail: 'Unexpected fixture submission' }, 400); }
        if (/\/(reports|documents|events)$/.test(endpoint)) return send({ items: [], total: 0 });
        throw new Error(`Unexpected fixture request: ${req.method()} ${endpoint}`);
      });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      await page.goto('http://localhost:3000/reports');
      const opener = page.getByRole('button', { name: '+ Generate report', exact: true });
      await opener.click();
      const dialog = page.getByRole('dialog', { name: 'Generate AI audit report' });
      await dialog.getByText('External AI report processing is not approved for SA01.').waitFor();
      assert.equal(await dialog.getByRole('button', { name: 'Generate Report', exact: true }).isDisabled(), true);
      const title = dialog.getByRole('textbox', { name: 'Report title', exact: true });
      assert.equal(await title.evaluate(element => element === document.activeElement), true);
      for (let i = 0; i < 12; i++) {
        await page.keyboard.press('Tab');
        assert.equal(await dialog.evaluate(element => element.contains(document.activeElement)), true);
      }
      const box = await dialog.boundingBox();
      assert.ok(box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1);
      const cancel = dialog.getByRole('button', { name: 'Cancel', exact: true });
      await cancel.scrollIntoViewIfNeeded();
      assert.equal(await cancel.isVisible(), true);
      const axe = await new AxeBuilder({ page }).include('dialog').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      assert.deepEqual(axe.violations.map(v => ({ id: v.id, impact: v.impact })), []);
      await page.screenshot({ path: path.join(artifacts, `report-dialog-${viewport.width}.png`) });
      await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'hidden' });
      assert.equal(await opener.evaluate(element => element === document.activeElement), true);
      await opener.click();
      await dialog.getByRole('link', { name: 'Review consent in Documents' }).click();
      await page.waitForURL(url => url.pathname === '/documents' && url.searchParams.get('org') === 'sa01');
      await page.getByRole('heading', { name: 'Documents', exact: true }).waitFor();
      await page.goto('http://localhost:3000/reports');
      unavailable = true;
      await opener.click();
      await dialog.getByRole('alert').waitFor();
      unavailable = false;
      approval = true;
      await dialog.getByRole('button', { name: 'Retry approval check' }).click();
      await dialog.getByText('External AI report processing is approved for the current target.').waitFor();
      assert.equal(await dialog.getByRole('button', { name: 'Generate Report', exact: true }).isEnabled(), true);
      await dialog.getByRole('button', { name: 'Close report generation' }).click();
      await page.getByRole('button', { name: '+ Rule-based test report', exact: true }).click();
      const preview = page.getByRole('dialog', { name: 'Generate rule-based test report' });
      await preview.getByRole('note').waitFor();
      assert.equal(await preview.getByRole('button', { name: 'Generate Test Report', exact: true }).isEnabled(), true);
      await page.keyboard.press('Escape');
      assert.equal(reportPosts, 0);
      assert.deepEqual(errors, []);
      result.checks.push(`${viewport.width}x${viewport.height}: consent gating/link/retry; keyboard containment/Escape/focus return; viewport fit; reachable actions; non-AI mode; zero scoped Axe AA violations; no generation requests`);
      await context.close();
    }
    const output = path.resolve(__dirname, '../temp/auditmind-demo/browser/report-dialog.json');
    await fs.mkdir(path.dirname(output), { recursive: true });
    await fs.writeFile(output, JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
