// Test-only extension of the guarded local browser fixture. No real tenant data.
const assert = require('node:assert/strict');
const path = require('node:path');
const { expect } = require('../frontend/node_modules/playwright/test');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const weights = { identity_access: .20, network_config: .15, vulnerability_management: .15,
  backup_recovery: .15, monitoring_detection: .15, incident_response: .10, compliance_alignment: .10 };
// Serializable into the browser's own time zone. Native datetime-local inputs
// normalize :00 seconds away; Playwright rejects a non-canonical fill value.
function browserLocalInput(timestamp) {
  const value = new Date(timestamp);
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
  const local = value.toISOString().slice(0, 19);
  return local.endsWith(':00') ? local.slice(0, 16) : local;
}

module.exports = async function evidencePilot({ base, seed, primary, observer, loadActors, evidence, output, check }) {
  assert.equal(base, 'http://localhost:3014');
  assert.match(evidence.schema, /^phase3_browser_[a-f0-9]{12}$/);
  const org = '/orgs/' + seed.other_org, scoring = org + '/scoring';
  const scope = 'Entire synthetic Beta organization inventory; software acceptance only';
  const details = evidence.pilot = { synthetic: true, startedAt: new Date().toISOString(), jobs: [] };
  const sources = {};
  const panel = primary.panel, page = primary.page;
  const region = () => panel.getByRole('region', { name: 'Organization-wide evidence evaluation', exact: true });
  const toggle = panel.getByRole('checkbox', { name: 'Evidence-qualified scoring', exact: true });
  const cards = who => who.page.locator('section').filter({ has: who.page.getByRole('heading', { name: 'Per-domain scores', exact: true }) }).locator('div[title]');
  async function request(who, endpoint, method = 'GET', body, status = 200) {
    const response = await who.request(endpoint, method, body);
    assert.equal(response.status, status, method + ' ' + endpoint);
    return response.body;
  }
  async function dialogAction(label, title) {
    await panel.getByRole('button', { name: label, exact: true }).click();
    await page.getByRole('dialog', { name: title, exact: true }).getByRole('button', { name: label, exact: true }).click();
  }
  async function open(domain) {
    await page.goto(base + '/settings');
    const picker = panel.getByRole('combobox', { name: /^Domain/ });
    await picker.selectOption(domain);
    await panel.getByRole('button', { name: 'Open / reload domain', exact: true }).click();
    await expect(panel.getByLabel('Scope description')).toBeVisible();
  }
  async function approveDomain(domain, declaredScope = scope, expiryMs = 7 * 86400000) {
    await open(domain);
    let stored = (await request(primary, scoring + '/qualifications')).find(row => row.domain === domain);
    if (stored?.status === 'approved') {
      await panel.getByLabel('Review / revocation note').fill('Synthetic pilot: revise expiry or scope deliberately');
      await dialogAction('Revoke qualification', 'Revoke qualification?');
      await expect(panel.getByText(new RegExp('Saved status: revoked.*Version ' + (stored.version + 1)))).toBeVisible();
      stored = (await request(primary, scoring + '/qualifications')).find(row => row.domain === domain);
    }
    await panel.getByLabel('Scope description').fill(declaredScope);
    await panel.getByLabel('Evidence rationale').fill('Synthetic observations exercising all objectives; not operational audit evidence');
    await panel.getByRole('button', { name: 'Load current inventory', exact: true }).click();
    await expect(panel.getByText('Current inventory loaded. Save the draft to bind it.', { exact: true })).toBeVisible({ timeout: 30000 });
    if (!stored?.observations.length) {
      const objectives = profiles[domain];
      for (const [index, objective] of objectives.entries()) {
        await panel.getByRole('combobox', { name: /^Objective/ }).selectOption(objective);
        await panel.getByLabel('Source UUID', { exact: true }).fill(sources[domain][index % 2]);
        const observed = await page.evaluate(browserLocalInput, Date.now());
        await panel.getByLabel('Observed at', { exact: true }).fill(observed);
        await panel.getByRole('button', { name: 'Validate source and add', exact: true }).click();
        await expect(panel.getByLabel('Source UUID', { exact: true })).toHaveValue('');
      }
    }
    await panel.getByRole('button', { name: 'Save draft', exact: true }).click();
    const version = (stored?.version ?? 0) + 1;
    await expect(panel.getByText(new RegExp('Saved status: draft.*Version ' + version))).toBeVisible();
    await panel.getByLabel('Review / revocation note').fill('Synthetic administrator approval for test coverage only');
    const expiry = await page.evaluate(browserLocalInput, Date.now() + expiryMs);
    await panel.getByLabel('Review expiry').fill(expiry);
    await panel.getByRole('checkbox', { name: /I reviewed operational evidence/ }).check();
    await dialogAction('Approve saved evidence', 'Approve saved evidence?');
    await expect(panel.getByText(new RegExp('Saved status: approved.*Version ' + (version + 1)))).toBeVisible();
    return (await request(primary, scoring + '/qualifications')).find(row => row.domain === domain);
  }
  async function evaluate(expectedCount) {
    await page.goto(base + '/settings');
    const accepted = page.waitForResponse(response => response.url().endsWith(scoring + '/evaluations') && response.request().method() === 'POST');
    await region().getByRole('button', { name: 'Evaluate evidence across all domains', exact: true }).click();
    const response = await accepted; assert.equal(response.status(), 202);
    const queued = await response.json(); details.jobs.push(queued.id);
    let finished;
    await expect.poll(async () => { finished = await request(primary, scoring + '/evaluations/' + queued.id); return finished.status; }, { timeout: 30000 }).toBe('completed');
    assert.equal(finished.is_current, true);
    assert.equal(finished.result.qualified_domain_count, expectedCount);
    await expect(region().getByText(/Coverage assessment:/)).toContainText(expectedCount + ' of 7 domains qualified');
    return finished;
  }
  async function mode(enabled) {
    await page.goto(base + '/settings');
    await expect(toggle).toBeEnabled();
    await expect(toggle).toBeChecked({ checked: !enabled });
    await toggle.click();
    await page.getByRole('dialog', { name: 'Change Dashboard scoring mode?', exact: true }).getByRole('button', {
      name: enabled ? 'Enable evidence-qualified scoring' : 'Use findings-based baseline', exact: true,
    }).click();
    await expect(toggle).toBeChecked({ checked: enabled });
    assert.equal((await request(primary, scoring + '/settings')).evidence_qualified_enabled, enabled);
  }
  const probe = await primary.context.newPage();
  try {
    await probe.setContent('<input type="datetime-local">');
    for (const seconds of [0, 1, 45]) {
      const timestamp = await probe.evaluate(value => new Date(2026, 10, 4, 16, 34, value).getTime(), seconds);
      const formatted = await probe.evaluate(browserLocalInput, timestamp);
      assert.equal(formatted, '2026-11-04T16:34' + (seconds ? ':' + String(seconds).padStart(2, '0') : ''));
      await probe.locator('input').fill(formatted);
      await expect(probe.locator('input')).toHaveValue(formatted);
    }
  } finally { await probe.close(); }
  check('Browser-local native date inputs accept exact-minute and nonzero-second timestamps without normalization errors');
  const profiles = (await request(primary, scoring + '/profiles')).profiles;
  const domains = Object.keys(weights);
  assert.deepEqual([...Object.keys(profiles)].sort(), [...domains].sort());
  assert.equal((await request(primary, scoring + '/settings')).evidence_qualified_enabled, false);
  // Seed all synthetic source findings first: later approvals bind one population.
  for (const domain of domains) {
    sources[domain] = [];
    const count = domain === 'identity_access' ? 7 : 2;
    for (let index = 0; index < count; index++) {
      const finding = await request(primary, org + '/findings', 'POST', {
        domain, severity: domain === 'identity_access' ? 'critical' : 'high', source: 'manual',
        description: 'SYNTHETIC pilot observation ' + domain + ' ' + (index + 1),
      }, 201);
      sources[domain].push(finding.id);
    }
  }
  const baseline = await request(primary, org + '/dashboard');
  const expectedScores = Object.fromEntries(domains.map(domain => [domain, domain === 'identity_access' ? 0 : 86]));
  const expectedOverall = domains.reduce((sum, domain) => sum + expectedScores[domain] * weights[domain], 0);
  assert.ok(Math.abs(baseline.overall_score - expectedOverall) < 1e-9);
  details.expectedScores = expectedScores; details.expectedOverall = expectedOverall;
  const expiringDomain = domains.at(-1);
  let expiring;
  for (const domain of domains) {
    const reviewed = await approveDomain(domain, scope, domain === expiringDomain ? 45000 : 7 * 86400000);
    if (domain === expiringDomain) expiring = reviewed;
  }
  assert.equal((await request(primary, scoring + '/evaluations/current')), null);
  await evaluate(7); await mode(true);
  await observer.page.getByLabel('Organization', { exact: true }).selectOption({ label: 'Phase3 Beta' });
  for (const who of [primary, observer]) {
    await who.page.goto(base + '/');
    await expect(who.page.getByText(/Evidence-qualified scoring · 7 of 7 domains qualified/)).toBeVisible();
    await expect(who.page.getByTestId('overall-score')).toHaveText(String(Math.round(expectedOverall)));
    await expect(cards(who)).toHaveCount(7);
    await expect(cards(who).locator('p:nth-child(2)').filter({ hasText: /^0$/ })).toHaveCount(1);
  }
  const complete = await request(primary, org + '/dashboard');
  assert.equal(complete.assessment_status, 'complete'); assert.equal(complete.overall_tier, 'medium');
  for (const domain of complete.domains) assert.equal(domain.score, expectedScores[domain.domain]);
  await page.screenshot({ path: path.join(output, 'pilot-seven-qualified.png'), fullPage: true });
  check('Synthetic seven-domain UI approvals authorize the existing weighted overall score; real zero remains numeric in both users\' Dashboards');

  // Let a real short-lived review expire: no clock patch, direct DB edit or delay interception.
  details.reviewExpiresAt = expiring.expires_at;
  const expiresAt = Date.parse(expiring.expires_at), expiryStarted = performance.now();
  assert.ok(expiresAt > Date.now(), 'Short-lived review must still be current at complete-score verification');
  while (Date.now() <= expiresAt) {
    console.log('Pilot waiting for real review expiry: ' + Math.ceil((expiresAt - Date.now()) / 1000) + 's');
    await pause(Math.min(10000, expiresAt - Date.now() + 50));
  }
  await expect.poll(async () => (await request(primary, scoring + '/dashboard-state')).evaluation_id).toBe(null);
  await expect(observer.page.getByText('A current evidence evaluation is required.', { exact: false })).toBeVisible({ timeout: 20000 });
  await expect(observer.page.getByTestId('overall-score')).toHaveText('Not assessed');
  await expect(cards(observer).getByText('Insufficient evidence', { exact: true })).toHaveCount(7);
  details.expiryObservedMs = +(performance.now() - expiryStarted).toFixed(1);
  const expired = await evaluate(6);
  assert.equal(expired.result.domains.find(domain => domain.domain === expiringDomain).reason_code, 'review_expired_or_invalid');
  await page.goto(base + '/');
  await expect(page.getByText(/Evidence-qualified scoring · 6 of 7 domains qualified/)).toBeVisible();
  await expect(page.getByTestId('overall-score')).toHaveText('Not assessed');
  assert.equal((await request(primary, org + '/dashboard')).overall_score, null);
  await page.screenshot({ path: path.join(output, 'pilot-review-expired.png'), fullPage: true });
  check('Real elapsed-time expiry withdraws the complete cached score; explicit reevaluation retains six domains without renormalizing an overall');

  await approveDomain(expiringDomain); await evaluate(7);
  await page.goto(base + '/');
  await expect(page.getByTestId('overall-score')).toHaveText(String(Math.round(expectedOverall)));
  check('Revoke, saved-version re-review and explicit reevaluation restore seven-domain scoring without changing deductions or weights');
  await approveDomain(expiringDomain, scope + ' — deliberately different declared scope');
  const mismatch = await evaluate(7);
  assert.equal(mismatch.result.assessment_status, 'partial');
  assert.equal(mismatch.result.overall_reason, 'scope_mismatch');
  await page.goto(base + '/');
  await expect(page.getByText('Qualified domain scopes differ. An overall score cannot be assigned.', { exact: true })).toBeVisible();
  await expect(page.getByTestId('overall-score')).toHaveText('Not assessed');
  const mismatched = await request(primary, org + '/dashboard');
  assert.equal(mismatched.overall_score, null); assert.ok(mismatched.domains.every(domain => domain.score !== null));
  await page.screenshot({ path: path.join(output, 'pilot-scope-mismatch.png'), fullPage: true });
  check('Seven individually qualified but incompatible scopes keep domain scores and suppress the overall score with a visible explanation');
  await approveDomain(expiringDomain); await evaluate(7);

  if (loadActors) {
    await boundedLoad({ actors: loadActors, alpha: '/orgs/' + seed.org, beta: org, request, details });
    check('Bounded local six-user/two-organization mixed reads and repeated worker evaluations complete without HTTP errors or tenant/mode crossover');
  }
  await mode(false);
  await page.goto(base + '/');
  await expect(page.getByText('Findings-based baseline', { exact: true })).toBeVisible();
  assert.equal((await request(observer, '/orgs/' + seed.org + '/scoring/settings')).evidence_qualified_enabled, false);
  assert.equal((await request(primary, scoring + '/qualifications')).length, 7);
  assert.equal((await request(primary, org + '/dashboard')).overall_score, baseline.overall_score);
  details.completedAt = new Date().toISOString();
  check('Both synthetic organizations finish default-off; seven reviewed records remain until the guarded fixture is removed');
};

async function boundedLoad({ actors, alpha, beta, request, details }) {
  const samples = [], jobs = [], started = performance.now(), durationMs = 60000;
  const entries = actors.map((actor, index) => ({ actor, org: index < 4 ? alpha : beta }));
  assert.equal(entries.length, 6);
  const rounds = entries.map(async ({ actor, org }) => {
    let iteration = 0;
    while (performance.now() - started < durationMs) {
      const tick = performance.now();
      const suffix = ['/scoring/dashboard-state', '/dashboard', '/scoring/evaluations/current'][iteration++ % 3];
      const response = await request(actor, org + suffix);
      if (suffix === '/dashboard' || suffix === '/scoring/dashboard-state') {
        assert.equal(response.scoring_mode, org === alpha ? 'findings_based' : 'evidence_qualified');
        if (suffix === '/dashboard') assert.equal(response.asset_count, org === alpha ? 100000 : 0);
      } else if (response) assert.equal(response.org_id, org.slice('/orgs/'.length));
      samples.push({ endpoint: suffix, latencyMs: performance.now() - tick });
      await pause(Math.max(0, 1000 - (performance.now() - tick)));
    }
  });
  const worker = (async () => {
    for (let wave = 0; wave < 4; wave++) {
      const queuedAt = performance.now();
      const queued = await Promise.all([
        request(actors[0], alpha + '/scoring/evaluations', 'POST', undefined, 202),
        request(actors[4], beta + '/scoring/evaluations', 'POST', undefined, 202),
      ]);
      for (const [index, job] of queued.entries()) {
        const org = index === 0 ? alpha : beta, actor = index === 0 ? actors[0] : actors[4];
        let finished;
        await expect.poll(async () => { finished = await request(actor, org + '/scoring/evaluations/' + job.id); return finished.status; }, { timeout: 30000 }).toBe('completed');
        assert.equal(finished.is_current, true);
        assert.equal(finished.progress.processed, finished.progress.total);
        jobs.push({ organization: index === 0 ? 'Alpha' : 'Beta', id: job.id, records: finished.progress.total,
          workerSeconds: finished.progress.elapsed_seconds, waveMs: +(performance.now() - queuedAt).toFixed(1) });
      }
      console.log('Bounded concurrency wave ' + (wave + 1) + '/4 completed');
      await pause(Math.max(0, 15000 - (performance.now() - queuedAt)));
    }
  })();
  // Drain every loop even on failure before the parent removes the fixture.
  const settled = await Promise.allSettled([...rounds, worker]);
  const failure = settled.find(result => result.status === 'rejected');
  if (failure) throw failure.reason;
  const summary = values => {
    const sorted = [...values].sort((a, b) => a - b);
    return { count: sorted.length, p50Ms: +sorted[Math.ceil(sorted.length * .5) - 1].toFixed(1),
      p95Ms: +sorted[Math.ceil(sorted.length * .95) - 1].toFixed(1), maxMs: +sorted.at(-1).toFixed(1) };
  };
  details.boundedConcurrency = { durationMs: +(performance.now() - started).toFixed(1), users: 6, organizations: 2,
    requestSummary: summary(samples.map(sample => sample.latencyMs)),
    endpoints: Object.fromEntries([...new Set(samples.map(sample => sample.endpoint))].map(endpoint => [endpoint, summary(samples.filter(sample => sample.endpoint === endpoint).map(sample => sample.latencyMs))])),
    jobs, limits: 'Local 60-second bounded exercise, warm/uncontrolled caches; not production sustained-load or capacity certification' };
  console.log('Bounded concurrency measurements: ' + JSON.stringify(details.boundedConcurrency));
}
