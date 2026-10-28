// Opt-in durable-job measurements against local synthetic SA01. No inference.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { chromium, expect } = require('../frontend/node_modules/playwright/test');
const root = path.resolve(__dirname, '..'), base = 'http://localhost:3000';
const runId = require('node:crypto').randomBytes(12).toString('hex');
const output = path.join(root, 'temp/testing/evidence-http', runId);
const evidence = { runId, startedAt: new Date().toISOString(), measurements: [], checks: [], externalInference: false,
  cacheControl: 'No cache flush; local worker measurements, not controlled cold/warm results' };
const cli = action => JSON.parse(execFileSync(path.join(root, 'backend/.venv/Scripts/python.exe'),
  [path.join(root, 'backend/scripts/evidence_http_fixture.py'), action, '--run-id', runId],
  { cwd: path.join(root, 'backend'), windowsHide: true, encoding: 'utf8' }));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const owner = page => page.getByRole('region', { name: 'Organization-wide evidence evaluation', exact: true });
const active = job => ['pending', 'running'].includes(job.status);
function check(name) { evidence.checks.push(name); console.log('PASS ' + name); }
(async () => {
  fs.mkdirSync(output, { recursive: true });
  let browser, prepared = false, endpoint;
  const ownedJobs = new Map();
  try {
    evidence.before = cli('inspect');
    assert.equal(evidence.before.active_jobs, 0, 'Wait for active demo jobs');
    assert.equal(evidence.before.active_inventory_connections, 0, 'Wait for existing inventory reads');
    const seed = cli('prepare'); prepared = true;
    endpoint = `/api/v1/orgs/${seed.org_id}/scoring/evaluations`;
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    evidence.browser = browser.version();
    async function actor(credentials) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: 'America/New_York' });
      const login = await context.request.post(base + '/api/v1/auth/login', { data: credentials,
        headers: { Origin: base, 'X-Requested-With': 'AuditMind' } });
      assert.equal(login.status(), 200, 'Temporary account sign-in failed');
      const headers = { Authorization: 'Bearer ' + (await login.json()).access_token };
      const page = await context.newPage(); await page.goto(base + '/settings');
      await expect(page.getByRole('heading', { name: 'Scoring and evidence review', exact: true })).toBeVisible();
      const mode = await context.request.get(base + `/api/v1/orgs/${seed.org_id}/scoring/settings`, { headers });
      assert.equal(mode.status(), 200); assert.equal((await mode.json()).evidence_qualified_enabled, false);
      await expect(owner(page).getByRole('button', { name: 'Evaluate evidence across all domains', exact: true })).toBeEnabled();
      return { context, page, headers };
    }
    async function read(actor, id) {
      const response = await actor.context.request.get(base + endpoint + '/' + id, { headers: actor.headers });
      assert.equal(response.status(), 200); return response.json();
    }
    async function start(actor) {
      const started = performance.now();
      const reply = actor.page.waitForResponse(r => r.url() === base + endpoint && r.request().method() === 'POST');
      await owner(actor.page).getByRole('button', { name: 'Evaluate evidence across all domains', exact: true }).click();
      const response = await reply; assert.equal(response.status(), 202);
      const job = await response.json(); if (job.can_cancel) ownedJobs.set(job.id, actor);
      return { actor, started, id: job.id, acknowledgementMs: +(performance.now() - started).toFixed(1) };
    }
    async function completed(startedJob, label) {
      const { actor, started, id, acknowledgementMs } = startedJob;
      let firstProcessedMs = null, samples = [], lastLog = 0, result;
      for (;;) {
        result = await read(actor, id); const elapsed = performance.now() - started;
        if (result.progress?.processed > 0 && firstProcessedMs === null) firstProcessedMs = +elapsed.toFixed(1);
        if (result.progress && samples.at(-1)?.processed !== result.progress.processed) samples.push(result.progress);
        if (elapsed - lastLog > 15000) { console.log(label + ': ' + JSON.stringify(result.progress)); lastLog = elapsed; }
        if (!active(result)) break;
        assert.ok(elapsed < 360000, 'Worker evaluation exceeded six minutes'); await pause(1000);
      }
      assert.equal(result.status, 'completed'); assert.equal(result.is_current, true); assert.ok(result.result);
      assert.equal(result.progress.processed, result.progress.total);
      assert.ok(samples.every((s, i) => i === 0 || s.processed >= samples[i - 1].processed));
      const measurement = { label, id, acknowledgementMs, elapsedMs: +(performance.now() - started).toFixed(1),
        workerElapsedSeconds: result.progress.elapsed_seconds, firstProcessedMs, progressSamples: samples.length,
        totalRecords: result.progress.total, inventory: result.result.inventory, qualifiedDomains: result.result.qualified_domain_count };
      evidence.measurements.push(measurement); console.log('RESULT ' + JSON.stringify(measurement));
      ownedJobs.delete(id); return measurement;
    }
    const a = await actor(seed.credentials[0]), b = await actor(seed.credentials[1]);
    check('Independent temporary viewers sign in; qualified scoring stays disabled');
    if (!process.argv.includes('--cancel-only')) {
      const firstJob = await start(a); await a.page.goto(base + '/findings');
      const joined = await b.context.request.post(base + endpoint, { headers: b.headers });
      assert.equal(joined.status(), 202); const shared = await joined.json();
      assert.equal(shared.id, firstJob.id); assert.equal(shared.can_cancel, false);
      const pingStarted = performance.now();
      const state = await b.context.request.get(base + `/api/v1/orgs/${seed.org_id}/scoring/dashboard-state`, { headers: b.headers });
      assert.equal(state.status(), 200); evidence.concurrentStateReadMs = +(performance.now() - pingStarted).toFixed(1);
      const first = await completed(firstJob, 'first-pass-shared-job'); await a.page.goto(base + '/settings');
      await expect(owner(a.page).getByText(/Coverage assessment:/)).toBeVisible({ timeout: 30000 });
      check('Navigation preserves the job; a second viewer shares it and cheap state reads remain available');
      const repeat = await completed(await start(a), 'repeat'); assert.deepEqual(first.inventory, repeat.inventory);
      check('Repeated durable evaluations agree and process every inventory/lifecycle record');
      await a.page.screenshot({ path: path.join(output, 'completed-evaluation.png'), fullPage: true });
    }
    const cancelling = await start(a), deadline = performance.now() + 180000;
    for (;;) {
      const job = await read(a, cancelling.id);
      if (job.status === 'running' && job.progress?.phase === 'assets') break;
      assert.ok(active(job) && performance.now() < deadline, 'Expected an active asset scan'); await pause(500);
    }
    await pause(2000); assert.ok(cli('inspect').active_inventory_connections > 0, 'Cancel must exercise a real database fetch');
    const cancelStarted = performance.now();
    await owner(a.page).getByRole('button', { name: 'Cancel operation', exact: true }).click();
    await expect(owner(a.page).getByRole('status', { name: 'Organization evaluation progress', exact: true })).toContainText(/Cancellation requested|Evaluation cancelled/);
    evidence.cancelAcknowledgementMs = +(performance.now() - cancelStarted).toFixed(1);
    for (;;) {
      const job = await read(a, cancelling.id);
      if (!active(job)) { assert.equal(job.status, 'cancelled'); assert.equal(job.result, null); break; }
      assert.ok(performance.now() - cancelStarted < 180000, 'Cancelled worker did not drain'); await pause(1000);
    }
    ownedJobs.delete(cancelling.id); evidence.cancelDatabaseDrainMs = +(performance.now() - cancelStarted).toFixed(1);
    await expect(owner(a.page).getByText('Evaluation cancelled. No partial result was published.')).toBeVisible({ timeout: 15000 });
    check('Worker cancellation drains the current fetch and publishes no partial result');
    evidence.after = cli('inspect');
    for (const key of ['assets', 'findings', 'ai_usage']) assert.equal(evidence.after[key], evidence.before[key]);
    assert.equal(evidence.after.active_jobs, 0); assert.equal(evidence.after.active_inventory_connections, 0);
    check('Inventory and AI usage are unchanged; no active evaluation readers remain');
  } catch (error) { evidence.failure = error.message; throw error; }
  finally {
    for (const [id, actor] of ownedJobs) {
      try { await actor.context.request.post(base + endpoint + '/' + id + '/cancel', { headers: actor.headers }); } catch {}
    }
    if (browser) await browser.close();
    if (prepared) evidence.cleanup = cli('cleanup');
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(evidence, null, 2)); console.log('Artifacts: ' + output);
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
