// Opt-in real local SA01 HTTP measurements. No inference, cache flush or restarts.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { chromium, expect } = require('../frontend/node_modules/playwright/test');
const root = path.resolve(__dirname, '..');
const python = path.join(root, 'backend/.venv/Scripts/python.exe');
const fixture = path.join(root, 'backend/scripts/evidence_http_fixture.py');
const runId = require('node:crypto').randomBytes(12).toString('hex');
const output = path.join(root, 'temp/testing/evidence-http', runId);
const base = 'http://localhost:3000';
const cancelOnly = process.argv.includes('--cancel-only');
const evidence = { runId, startedAt: new Date().toISOString(), measurements: [], checks: [], externalInference: false, cacheControl: 'No cache flush or service restart; first-pass/repeated local measurements only' };
const cli = action => JSON.parse(execFileSync(python, [fixture, action, '--run-id', runId], { cwd: path.join(root, 'backend'), windowsHide: true, encoding: 'utf8' }));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function check(name) { evidence.checks.push(name); console.log('PASS ' + name); }
(async () => {
  fs.mkdirSync(output, { recursive: true });
  let browser, prepared = false;
  try {
    evidence.before = cli('inspect');
    assert.equal(evidence.before.active_jobs, 0, 'Wait for active demo jobs before benchmarking');
    assert.equal(evidence.before.active_inventory_connections, 0, 'Wait for existing inventory reads before benchmarking');
    const seed = cli('prepare'); prepared = true;
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    evidence.browser = browser.version();
    async function actor(credentials) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: 'America/New_York' });
      const login = await context.request.post(base + '/api/v1/auth/login', { data: credentials, headers: { Origin: base, 'X-Requested-With': 'AuditMind' } });
      assert.equal(login.status(), 200, 'Normal test-account sign-in failed');
      const token = (await login.json()).access_token;
      // Tee only the evidence stream inside Chrome. DevTools may discard the body
      // of a long streaming response before response.body() can retrieve it.
      // The original response is returned untouched to the normal application.
      await context.addInitScript(() => {
        const original = window.fetch.bind(window);
        window.fetch = async (...args) => {
          const response = await original(...args);
          const url = typeof args[0] === 'string' ? args[0] : args[0].url;
          if (new URL(url, location.href).pathname.endsWith('/scoring/progress/evaluation')) {
            const capture = { done: false };
            window.__evidenceCapture = capture;
            response.clone().text().then(body => {
              capture.events = body.trim().split('\n').filter(Boolean).map(line => JSON.parse(line));
              capture.done = true;
            }).catch(error => { capture.error = error.message; capture.done = true; });
          }
          return response;
        };
      });
      const page = await context.newPage();
      await page.goto(base + '/settings');
      await expect(page.getByRole('heading', { name: 'Scoring and evidence review', exact: true })).toBeVisible();
      const settingsPath = `/api/v1/orgs/${seed.org_id}/scoring/settings`;
      const mode = await context.request.get(base + settingsPath, { headers: { Authorization: 'Bearer ' + token } });
      assert.equal(mode.status(), 200); assert.equal((await mode.json()).evidence_qualified_enabled, false);
      return { context, page, token };
    }
    const a = await actor(seed.credentials[0]), b = await actor(seed.credentials[1]);
    check('Two independent temporary viewer accounts sign in normally; qualified scoring remains disabled');
    const endpoint = `/api/v1/orgs/${seed.org_id}/scoring/progress/evaluation`;
    const owner = page => page.getByRole('region', { name: 'Organization-wide evidence evaluation', exact: true });
    async function ping(actor) {
      const started = performance.now();
      const response = await actor.context.request.get(base + `/api/v1/orgs/${seed.org_id}/scoring/profiles`, { headers: { Authorization: 'Bearer ' + actor.token } });
      assert.equal(response.status(), 200);
      return +(performance.now() - started).toFixed(1);
    }
    async function evaluate(actor, label) {
      const region = owner(actor.page);
      await actor.page.evaluate(() => { window.__evidenceCapture = null; });
      const started = performance.now();
      const reply = actor.page.waitForResponse(response => response.url() === base + endpoint && response.request().method() === 'GET', { timeout: 180000 });
      const firstCount = actor.page.waitForFunction(() => {
        const region = document.querySelector('[aria-label="Organization-wide evidence evaluation"]');
        return region?.querySelector('[role="status"]')?.textContent.startsWith('Processing:') && Number(region.querySelector('progress')?.value) > 0;
      }, {}, { timeout: 360000 }).then(() => +(performance.now() - started).toFixed(1));
      // Observe early rejection too; an HTTP error must not leave an unhandled waiter.
      firstCount.catch(() => {});
      await region.getByRole('button', { name: 'Evaluate evidence across all domains', exact: true }).click();
      const response = await reply;
      assert.equal(response.status(), 200);
      const headersMs = +(performance.now() - started).toFixed(1);
      const timer = setInterval(async () => {
        try { console.log(label + ': ' + await region.getByRole('status', { name: 'Organization evaluation progress', exact: true }).innerText()); } catch {}
      }, 15000);
      try {
        await actor.page.waitForFunction(() => window.__evidenceCapture?.done, {}, { timeout: 360000 });
        const elapsedMs = +(performance.now() - started).toFixed(1);
        const capture = await actor.page.evaluate(() => window.__evidenceCapture);
        assert.equal(capture.error, undefined, 'Chrome could not capture the evidence stream');
        const events = capture.events;
        assert.ok(events.every(event => event.type !== 'error'));
        const result = events.at(-1); assert.equal(result.type, 'result');
        const progress = events.filter(event => event.type === 'progress' && Number.isInteger(event.processed));
        assert.ok(progress.length > 1);
        assert.equal(progress.at(-1).processed, progress.at(-1).total);
        assert.ok(progress.every((event, index) => index === 0 || event.processed >= progress[index - 1].processed));
        await expect(region.getByText(/Coverage assessment:/)).toBeVisible();
        await expect(region.getByRole('button', { name: 'Cancel operation', exact: true })).toHaveCount(0);
        const measurement = { label, elapsedMs, headersMs, firstProcessedMs: await firstCount, progressEvents: progress.length, totalRecords: progress.at(-1).total, inventory: result.data.inventory, qualifiedDomains: result.data.qualified_domain_count };
        evidence.measurements.push(measurement);
        console.log('RESULT ' + JSON.stringify(measurement));
        return measurement;
      } finally { clearInterval(timer); }
    }
    let first;
    if (!cancelOnly) {
      first = await evaluate(a, 'first-pass');
      const repeat = await evaluate(a, 'repeat');
      assert.deepEqual(first.inventory, repeat.inventory);
      check('Sequential real browser/proxy/API evaluations complete with monotonic progress and identical inventory fingerprints');
    }

    // Cancellation must be a real browser abort, not a stubbed response.
    const region = owner(a.page);
    await region.getByRole('button', { name: 'Evaluate evidence across all domains', exact: true }).click();
    await expect(region.getByRole('button', { name: 'Cancel operation', exact: true })).toBeEnabled();
    await expect(region.getByRole('status', { name: 'Organization evaluation progress', exact: true })).toContainText('assets', { timeout: 30000 });
    // Exercise cancellation during database work, not just the connection phase.
    await pause(2000);
    assert.ok(cli('inspect').active_inventory_connections > 0, 'A real inventory read must be active before cancellation');
    const cancelled = performance.now();
    await region.getByRole('button', { name: 'Cancel operation', exact: true }).click();
    await expect(region.getByRole('alert')).toContainText('cancelled');
    await expect(region.getByRole('button', { name: 'Evaluate evidence across all domains', exact: true })).toBeEnabled();
    evidence.cancelUiMs = +(performance.now() - cancelled).toFixed(1);
    evidence.otherViewerDuringCancellationMs = await ping(b);
    const cleanupStarted = performance.now();
    for (;;) {
      const metrics = cli('inspect');
      if (metrics.active_inventory_connections === 0) break;
      if (performance.now() - cleanupStarted > 180000) throw new Error('Cancelled inventory reader did not drain within 180s');
      console.log('Waiting for cancelled database fetch to drain');
      await pause(5000);
    }
    evidence.cancelDatabaseDrainMs = +(performance.now() - cancelled).toFixed(1);
    check('Real cancellation restores the UI, the second user remains responsive, and database inventory reads drain');

    if (!cancelOnly) {
      const concurrentA = evaluate(a, 'concurrent-viewer-1');
      const concurrentB = evaluate(b, 'concurrent-viewer-2');
      await pause(2000);
      evidence.profilesDuringConcurrentMs = await ping(b);
      const concurrent = await Promise.all([concurrentA, concurrentB]);
      for (const measurement of concurrent) assert.deepEqual(measurement.inventory, first.inventory);
      check('Two simultaneous authenticated evaluations agree; unrelated organization reads remain available');
    }
    evidence.after = cli('inspect');
    for (const key of ['assets', 'findings', 'ai_usage']) assert.equal(evidence.after[key], evidence.before[key]);
    check('Existing inventory counts and AI usage are unchanged');
    await a.page.screenshot({ path: path.join(output, 'completed-evaluation.png'), fullPage: true });
  } catch (error) { evidence.failure = error.message; throw error; }
  finally {
    if (browser) await browser.close();
    if (prepared) evidence.cleanup = cli('cleanup');
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(evidence, null, 2));
    console.log('Artifacts: ' + output);
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
