// Real Chrome, two administrators and isolated PostgreSQL. No external inference.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');
const { chromium, expect } = require('../frontend/node_modules/playwright/test');
const root = path.resolve(__dirname, '..');
const python = process.env.AUDITMIND_BROWSER_PYTHON || path.join(root, process.platform === 'win32' ? 'backend/.venv/Scripts/python.exe' : 'backend/.venv/bin/python');
const fixture = path.join(root, 'backend/scripts/phase3_browser_fixture.py');
const schema = 'phase3_browser_' + require('node:crypto').randomBytes(6).toString('hex');
const output = path.join(root, 'temp/testing/evidence-review', schema);
const base = 'http://localhost:3014';
const flags = ['--schema', schema, '--workflow', '--evidence'];
const cli = action => execFileSync(python, [fixture, action, ...flags], { cwd: path.join(root, 'backend'), windowsHide: true, encoding: 'utf8' });
const evidence = { schema, checks: [], errors: [], externalInference: false };
const children = [];
function check(name) { evidence.checks.push(name); console.log('PASS ' + name); }
async function free(port) {
  await new Promise((resolve, reject) => {
    const server = require('node:net').createServer(); server.once('error', reject);
    server.listen(port, '127.0.0.1', () => server.close(resolve));
  });
}
(async () => {
  fs.mkdirSync(output, { recursive: true });
  let browser, prepared = false;
  try {
    await free(3014); await free(8012);
    const seed = JSON.parse(cli('prepare')); prepared = true;
    function start(executable, args, name, env = {}) {
      const log = fs.openSync(path.join(output, name + '.log'), 'w');
      children.push(spawn(executable, args, { cwd: path.join(root, name === 'frontend' ? 'frontend' : 'backend'), env: { ...process.env, ...env }, windowsHide: true, detached: process.platform !== 'win32', stdio: ['ignore', log, log] }));
      fs.closeSync(log);
    }
    start(python, [fixture, 'api', ...flags], 'api');
    start(process.execPath, [path.join(root, 'frontend/node_modules/next/dist/bin/next'), 'start', '--hostname', '127.0.0.1', '--port', '3014'], 'frontend', { AUDITMIND_ISOLATED_BUILD: '1', BACKEND_URL: 'http://127.0.0.1:8012', NEXT_PUBLIC_API_URL: '/api/v1' });
    await expect.poll(async () => { try { return (await fetch(base + '/api/v1/auth/options')).status; } catch { return 0; } }, { timeout: 45000 }).toBe(200);
    browser = await chromium.launch({ ...(process.env.AUDITMIND_BROWSER_CHANNEL === 'chromium' ? {} : { channel: 'chrome' }), headless: true });
    evidence.browser = browser.version();
    const org = '/orgs/' + seed.org, scoring = org + '/scoring', qualification = scoring + '/qualifications/network_config';
    async function actor(role) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: 'America/New_York' });
      const login = await context.request.post(base + '/api/v1/auth/login', { data: { email: role + '@phase3.example', password: seed.password }, headers: { Origin: base, 'X-Requested-With': 'AuditMind' } });
      assert.equal(login.status(), 200, 'Fixture sign-in failed');
      let token = 'Bearer ' + (await login.json()).access_token;
      const page = await context.newPage();
      page.on('pageerror', error => evidence.errors.push(error.message));
      page.on('request', request => { if (request.url().startsWith(base + '/api/')) token = request.headers().authorization || token; });
      page.on('dialog', async dialog => { evidence.errors.push('Unexpected browser-native dialog'); await dialog.dismiss(); });
      await page.goto(base + '/settings');
      if (role === 'admin') await page.getByLabel('Organization', { exact: true }).selectOption({ label: 'Phase3 Alpha' });
      await expect(page.getByRole('heading', { name: 'Scoring and evidence review', exact: true })).toBeVisible();
      const panel = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Scoring and evidence review', exact: true }) });
      const request = async (endpoint, method = 'GET', body) => {
        const response = await context.request.fetch(base + '/api/v1' + endpoint, { method, headers: { Authorization: token }, ...(body ? { data: body } : {}) });
        return { status: response.status(), body: await response.json() };
      };
      return { role, context, page, panel, request, authorization: () => token };
    }
    const a = await actor('admin'), b = await actor('reviewer');
    async function open(who) {
      const domain = who.panel.getByRole('combobox', { name: /^Domain/ });
      if (await domain.inputValue() !== 'network_config') await domain.selectOption('network_config');
      await who.panel.getByRole('button', { name: 'Open / reload domain', exact: true }).click();
      const dialog = who.page.getByRole('dialog', { name: 'Discard unsaved edits?', exact: true });
      if (await dialog.count()) await dialog.getByRole('button', { name: 'Discard and reload', exact: true }).click();
      await expect(who.panel.getByLabel('Scope description')).toBeVisible();
      await expect(who.panel.getByRole('button', { name: 'Open / reload domain', exact: true })).toBeEnabled();
    }
    async function reviewForm(who, note) {
      await who.panel.getByLabel('Review / revocation note').fill(note);
      const expiry = await who.page.evaluate(() => {
        const date = new Date(Date.now() + 7 * 86400000);
        date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
        return date.toISOString().slice(0, 16);
      });
      await who.panel.getByLabel('Review expiry').fill(expiry);
      await who.panel.getByRole('checkbox', { name: /I reviewed operational evidence/ }).check();
    }
    async function action(who, label, dialogTitle) {
      await who.panel.getByRole('button', { name: label, exact: true }).click();
      await who.page.getByRole('dialog', { name: dialogTitle, exact: true }).getByRole('button', { name: label, exact: true }).click();
    }
    async function evaluate(who) {
      const region = who.panel.getByRole('region', { name: 'Organization-wide evidence evaluation', exact: true });
      await region.getByRole('button', { name: 'Evaluate evidence across all domains', exact: true }).click();
      await expect(region.getByText(/Coverage assessment:/)).toBeVisible({ timeout: 30000 });
      return region;
    }
    const initialDashboard = await a.request(org + '/dashboard');
    await open(a);
    await a.panel.getByLabel('Scope description').fill('Entire synthetic organization inventory');
    await a.panel.getByLabel('Evidence rationale').fill('Synthetic operational observations; not a real audit');
    await a.panel.getByRole('button', { name: 'Load current inventory', exact: true }).click();
    await expect(a.panel.getByText('Current inventory loaded. Save the draft to bind it.', { exact: true })).toBeVisible({ timeout: 30000 });
    const objectives = (await a.request(scoring + '/profiles')).body.profiles.network_config;
    for (const [index, objective] of objectives.entries()) {
      await a.panel.getByRole('combobox', { name: /^Objective/ }).selectOption(objective);
      await a.panel.getByLabel('Source UUID', { exact: true }).fill(seed.finding_ids[index % 2]);
      const observed = await a.page.evaluate(() => { const now = new Date(); now.setMinutes(now.getMinutes() - now.getTimezoneOffset()); return now.toISOString().slice(0, 16); });
      await a.panel.getByLabel('Observed at', { exact: true }).fill(observed);
      await a.panel.getByRole('button', { name: 'Validate source and add', exact: true }).click();
      await expect(a.panel.getByLabel('Source UUID', { exact: true })).toHaveValue('');
    }
    await a.panel.getByRole('button', { name: 'Save draft', exact: true }).click();
    await expect(a.panel.getByText(/Saved status: draft.*Version 1/)).toBeVisible({ timeout: 30000 });
    await open(b);
    await expect(b.panel.getByText(/Saved status: draft.*Version 1/)).toBeVisible();
    check('Browser binds the current inventory and three validated objectives across two sources; second administrator opens the same saved version');

    for (const who of [a, b]) {
      await who.panel.getByLabel('Scope description').fill(who.role + ' unsaved scope');
      await reviewForm(who, who.role + ' synthetic approval');
      await who.panel.getByRole('button', { name: 'Approve saved evidence', exact: true }).click();
      await expect(who.page.getByRole('dialog', { name: 'Approve saved evidence?', exact: true })).toContainText('saved version 1');
    }
    const replies = [a, b].map(who => who.page.waitForResponse(response => response.url().endsWith('/qualifications/network_config/review') && response.request().method() === 'POST'));
    await Promise.all([a, b].map(who => who.page.getByRole('dialog', { name: 'Approve saved evidence?', exact: true }).getByRole('button', { name: 'Approve saved evidence', exact: true }).click()));
    const responses = await Promise.all(replies), statuses = responses.map(response => response.status());
    assert.deepEqual([...statuses].sort(), [200, 409]); evidence.concurrentApprovalStatuses = statuses;
    const winner = statuses[0] === 200 ? a : b, loser = winner === a ? b : a;
    await expect(loser.panel.getByRole('alert')).toContainText('reload');
    await expect(loser.panel.getByLabel('Scope description')).toHaveValue(loser.role + ' unsaved scope');
    await open(loser);
    await expect(loser.panel.getByText(/Saved status: approved.*Version 2/)).toBeVisible();
    const evaluation = await evaluate(loser);
    await expect(evaluation.getByText(/Coverage assessment:/)).toContainText('1 of 7 domains qualified');
    assert.deepEqual((await a.request(org + '/dashboard')).body, initialDashboard.body);
    check('Two real administrators approve concurrently: one succeeds, one receives 409 without losing edits; reload sees version 2, eligibility is partial and Dashboard is unchanged');
    await loser.page.screenshot({ path: path.join(output, 'approved-partial.png'), fullPage: true });

    for (const role of ['viewer', 'auditor']) {
      const reader = await actor(role); await open(reader);
      await expect(reader.panel.getByLabel('Scope description')).toBeDisabled();
      await expect(reader.panel.getByRole('button', { name: 'Revoke qualification', exact: true })).toHaveCount(0);
      const stored = (await a.request(scoring + '/qualifications')).body[0];
      const draft = { expected_version: stored.version, scope: stored.scope, rationale: stored.rationale, observations: stored.observations, inventory_sha256: stored.inventory_sha256 };
      assert.equal((await reader.request(qualification, 'PUT', draft)).status, 403);
      assert.equal((await reader.request(qualification + '/revoke', 'POST', { expected_version: 2, note: 'Not allowed' })).status, 403);
      assert.equal((await reader.request(qualification + '/review', 'POST', { expected_version: 2, inventory_sha256: stored.inventory_sha256, decision: 'approve', expires_at: new Date(Date.now() + 86400000).toISOString(), note: 'Not allowed', operational_review: true, covers_entire_inventory: true, conflicts_reviewed: true })).status, 403);
    }
    const outsider = await actor('other');
    assert.equal((await outsider.request(scoring + '/evaluation')).status, 403);
    assert.equal((await a.request(scoring + '/settings', 'PATCH', { expected_version: 0, evidence_qualified_enabled: true })).status, 409);
    check('Viewer/auditor controls are read-only and server rejects all three write types; foreign organization is denied and scoring activation remains blocked');

    // Use a real streamed HTTP snapshot, no interception or artificial delay.
    const started = performance.now();
    const stream = await fetch(base + '/api/v1' + scoring + '/progress/evaluation', { headers: { Authorization: b.authorization() } });
    assert.equal(stream.status, 200);
    let pending = '', result, write, writeFinished;
    const decoder = new TextDecoder();
    for await (const bytes of stream.body) {
      pending += decoder.decode(bytes, { stream: true });
      const lines = pending.split('\n'); pending = lines.pop();
      for (const line of lines.filter(Boolean)) {
        const event = JSON.parse(line);
        assert.notEqual(event.type, 'error');
        if (!write && event.phase === 'assets') {
          write = a.request(org + '/findings', 'POST', { domain: 'network_config', severity: 'high', description: 'Synthetic concurrent inventory addition', source: 'manual' }).then(response => { writeFinished = performance.now(); return response; });
        }
        if (event.type === 'result') result = event.data;
      }
    }
    const finished = performance.now();
    assert.ok(write, 'Concurrent write must overlap the assets phase');
    assert.equal((await write).status, 201);
    assert.ok(writeFinished < finished, 'Unrelated write should finish before the evaluation finishes');
    assert.equal(result.inventory.finding_count, 2);
    assert.equal(result.qualified_domain_count, 1);
    const changed = (await b.request(scoring + '/evaluation')).body;
    assert.equal(changed.inventory.finding_count, 3);
    assert.equal(changed.domains.find(domain => domain.domain === 'network_config').reason_code, 'inventory_changed');
    evidence.concurrentWrite = { evaluationMs: +(finished - started).toFixed(1), writeCompletedMs: +(writeFinished - started).toFixed(1), snapshotFindings: 2, nextEvaluationFindings: 3 };
    check('Concurrent inventory write finishes during a real scan: in-flight evaluation uses its original snapshot, next evaluation rejects the stale binding');

    await loser.panel.getByLabel('Review / revocation note').fill('Synthetic evidence requires re-review');
    await action(loser, 'Revoke qualification', 'Revoke qualification?');
    await expect(loser.panel.getByText(/Saved status: revoked.*Version 3/)).toBeVisible();
    assert.equal((await a.request(scoring + '/evaluation')).body.domains.find(domain => domain.domain === 'network_config').reason_code, 'revoked');
    await loser.panel.getByRole('button', { name: 'Load current inventory', exact: true }).click();
    await expect(loser.panel.getByText('Current inventory loaded. Save the draft to bind it.', { exact: true })).toBeVisible({ timeout: 30000 });
    await loser.panel.getByRole('button', { name: 'Save draft', exact: true }).click();
    await expect(loser.panel.getByText(/Saved status: draft.*Version 4/)).toBeVisible({ timeout: 30000 });
    await reviewForm(loser, 'Synthetic conflicting observations across two independent references');
    await action(loser, 'Record material conflict', 'Record material conflict?');
    await expect(loser.panel.getByText(/Saved status: conflicting.*Version 5/)).toBeVisible({ timeout: 30000 });
    const conflict = await evaluate(loser);
    await expect(conflict.getByText('Network & Config: material conflict (not eligible)', { exact: true })).toBeVisible();
    await expect(conflict.getByText(/Coverage assessment:/)).toContainText('0 of 7 domains qualified');
    check('Browser revoke, authoritative inventory rebind, new draft and two-source material-conflict review all persist; revoked/conflicting evidence cannot qualify');
    await loser.page.screenshot({ path: path.join(output, 'conflicting.png'), fullPage: true });
    const mode = (await a.request(scoring + '/settings')).body;
    assert.equal(mode.evidence_qualified_enabled, false); assert.equal(mode.available, false);
    const stats = JSON.parse(cli('inspect')); assert.equal(stats.usage_count, 0);
    assert.deepEqual(evidence.errors, []);
    check('No browser-native warnings, page errors, scoring activation or AI usage');
  } catch (error) {
    evidence.failure = error.message;
    if (browser) try { await browser.contexts()[0]?.pages()[0]?.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }); } catch {}
    throw error;
  } finally {
    if (browser) await browser.close();
    for (const child of children) {
      if (!child.pid || child.exitCode !== null) continue;
      try { if (process.platform === 'win32') execFileSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' }); else process.kill(-child.pid, 'SIGTERM'); } catch {}
    }
    if (prepared) { cli('cleanup'); evidence.isolatedSchemaRemoved = true; }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(evidence, null, 2));
    console.log('Artifacts: ' + output);
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
