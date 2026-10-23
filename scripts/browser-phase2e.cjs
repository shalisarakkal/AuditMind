// Real Chrome + real isolated backend. No demo credentials, provider calls or downloads.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');
const { chromium, expect } = require('../frontend/node_modules/playwright/test');
const root = path.resolve(__dirname, '..');
const python = path.join(root, 'backend/.venv/Scripts/python.exe');
const fixture = path.join(root, 'backend/scripts/phase2e_browser_fixture.py');
const schema = `phase2e_browser_${require('node:crypto').randomBytes(6).toString('hex')}`;
const output = path.join(root, 'temp/auditmind-demo/browser/phase2e');
const base = 'http://localhost:3000';
const secret = 'Browser-Only-New-Passphrase-2026!';
const children = [];
const evidence = { schema, checks: [], errors: [], backend: 'real isolated PostgreSQL schema', mockedAPI: false };
const cli = (action, email) => execFileSync(python, [fixture, action, '--schema', schema, ...(email ? ['--email', email] : [])], { cwd: path.join(root, 'backend'), windowsHide: true, encoding: 'utf8' });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  fs.mkdirSync(output, { recursive: true });
  let browser, prepared = false;
  try {
    // Do not attach to an existing server on the fixture port.
    const net = require('node:net');
    await new Promise((resolve, reject) => {
      const probe = net.createServer();
      probe.once('error', reject);
      probe.listen(8011, '127.0.0.1', () => probe.close(resolve));
    });
    const seed = JSON.parse(cli('prepare')); prepared = true;
    for (const action of ['api', 'worker']) {
      const log = fs.openSync(path.join(output, `${action}.log`), 'w');
      children.push(spawn(python, [fixture, action, '--schema', schema], { cwd: path.join(root, 'backend'), windowsHide: true, stdio: ['ignore', log, log] }));
      fs.closeSync(log);
    }
    let ready = false;
    for (let i = 0; i < 60; i++) {
      try { if ((await fetch('http://127.0.0.1:8011/health')).ok) { ready = true; break; } } catch {}
      await delay(500);
    }
    assert.ok(ready, 'Isolated API did not start');
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    evidence.browser = browser.version();
    async function context() {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      // Transport-only redirect: bodies/status/auth/cookies all come from the real API.
      await ctx.route('**/api/v1/**', async route => {
        const response = await route.fetch({ url: route.request().url().replace(base, 'http://127.0.0.1:8011') });
        await route.fulfill({ response });
      });
      ctx.on('page', page => page.on('pageerror', err => evidence.errors.push(err.message)));
      return ctx;
    }
    async function login(ctx, email, password, forced = false) {
      const page = await ctx.newPage();
      await page.goto(`${base}/login`);
      await page.getByLabel('Email', { exact: true }).fill(email);
      await page.getByLabel('Password', { exact: true }).fill(password);
      await page.getByRole('button', { name: 'Sign in', exact: true }).click();
      await page.waitForURL(forced ? '**/change-password' : `${base}/`);
      return page;
    }
    async function goto(page, url, heading) {
      await page.goto(base + url);
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    }
    async function changePassword(page, current, next = secret) {
      await page.getByLabel(/^Current/).fill(current);
      await page.getByLabel('New password', { exact: true }).fill(next);
      await page.getByLabel('New password again', { exact: true }).fill(next);
      await page.getByRole('button', { name: 'Change password', exact: true }).click();
      await page.waitForURL(`${base}/`);
    }
    async function confirm(page, label) {
      await page.getByRole('group', { name: 'Confirm', exact: true }).getByRole('button', { name: label, exact: true }).click();
    }
    async function temporary(page) {
      const panel = page.getByRole('group', { name: 'Temporary password', exact: true });
      await expect(panel).toBeVisible();
      const value = await panel.locator('code').innerText();
      await panel.getByRole('button', { name: 'Done', exact: true }).click();
      return value;
    }
    function check(name) { evidence.checks.push(name); console.log(`PASS ${name}`); }
    const anonymous = await context(); const anon = await anonymous.newPage();
    const loginResponse = await anon.goto(`${base}/login`);
    await expect(anon.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
    assert.equal(await anon.getByRole('link', { name: 'Create an account', exact: true }).count(), 0);
    assert.match(loginResponse.headers()['content-security-policy'], /nonce-/);
    assert.equal(loginResponse.headers()['x-frame-options'], 'DENY');
    await goto(anon, '/register', 'Sign-up is closed');
    check('Public registration closed; login hides sign-up; real frontend CSP and anti-framing headers');
    const rootCtx = await context();
    const rp = await login(rootCtx, seed.root_email, seed.root_password);
    await goto(rp, '/platform/organizations', 'Organizations');
    assert.equal(await rp.getByRole('link', { name: 'Create an account', exact: true }).count(), 0);
    const cookie = (await rootCtx.cookies()).find(c => c.name === 'auditmind_session');
    assert.ok(cookie?.httpOnly); assert.equal(cookie.sameSite, 'Strict'); assert.equal(cookie.path, '/api/v1/auth');
    assert.equal(await rp.evaluate(() => localStorage.getItem('auditmind_token')), null);
    await rp.reload(); await expect(rp.getByRole('heading', { name: 'Organizations', exact: true })).toBeVisible();
    check('Memory-only token; HttpOnly/Strict scoped renewal cookie; authenticated reload');
    await goto(rp, '/people', 'People');
    await expect(rp.getByText('Sysadmin: read-only', { exact: true })).toBeVisible();
    assert.equal(await rp.getByRole('button', { name: 'Add person', exact: true }).count(), 0);
    await goto(rp, '/platform/organizations', 'Organizations');
    check('Sysadmin browses organization data read-only without membership');
    async function createOrg(name, email) {
      await rp.getByRole('button', { name: 'Create organization', exact: true }).click();
      const form = rp.getByRole('form', { name: 'Create organization', exact: true });
      await form.getByLabel('Name', { exact: true }).fill(name);
      await form.getByLabel("Admin's email", { exact: true }).fill(email);
      await form.getByLabel("Admin's name", { exact: true }).fill('Organization Admin');
      await form.getByRole('button', { name: 'Create', exact: true }).click();
      return temporary(rp);
    }
    const adminEmail = 'admin@phase2e.example';
    const adminTemp = await createOrg('Browser Bravo', adminEmail);
    check('Sysadmin creates organization and first admin with one-time temporary password');
    const adminCtx = await context();
    const ap = await login(adminCtx, adminEmail, adminTemp, true);
    await ap.goto(`${base}/people`); await ap.waitForURL('**/change-password');
    await changePassword(ap, adminTemp);
    await goto(ap, '/people', 'People');
    const ownRow = ap.getByRole('row').filter({ hasText: adminEmail });
    assert.equal(await ownRow.getByRole('combobox').count(), 0);
    assert.equal(await ownRow.getByRole('button', { name: 'Remove', exact: true }).count(), 0);
    assert.equal(await ownRow.getByRole('button', { name: 'Reset password', exact: true }).count(), 0);
    check('First-login password change is mandatory and completes through UI');
    async function addPerson(email, name, role) {
      await ap.getByRole('button', { name: 'Add person', exact: true }).click();
      const form = ap.getByRole('form', { name: 'Add person', exact: true });
      await form.getByLabel('Email', { exact: true }).fill(email);
      await form.getByLabel('Name', { exact: true }).fill(name);
      await form.getByRole('combobox').selectOption(role);
      await form.getByRole('button', { name: 'Add', exact: true }).click();
    }
    const personEmail = 'person@phase2e.example';
    await addPerson(personEmail, 'Browser Person', 'viewer');
    let personTemp = await temporary(ap);
    const personCtx = await context();
    const pp = await login(personCtx, personEmail, personTemp, true);
    await changePassword(pp, personTemp);
    await goto(pp, '/people', 'People');
    await expect(pp.getByRole('cell', { name: personEmail, exact: true })).toBeVisible();
    assert.equal(await pp.getByRole('button', { name: 'Add person', exact: true }).count(), 0);
    await goto(pp, '/platform/organizations', 'Organizations').catch(async () => {
      await expect(pp.getByText('This page is for the Sysadmin.', { exact: true })).toBeVisible();
    });
    check('Viewer reads People but cannot manage people or use platform tools');
    let row = ap.getByRole('row').filter({ hasText: personEmail });
    await row.getByRole('combobox').selectOption('auditor'); await confirm(ap, 'Change role');
    await expect(row.getByRole('combobox')).toHaveValue('auditor');
    await pp.goto(`${base}/people`); await pp.waitForURL('**/login');
    check('Role change persists and immediately revokes existing sessions');
    await row.getByRole('button', { name: 'Rename', exact: true }).click();
    const rename = ap.getByRole('form', { name: /Rename/ });
    await rename.getByLabel(`Name of ${personEmail}`, { exact: true }).fill('Renamed Person');
    await rename.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(ap.getByRole('cell', { name: 'Renamed Person', exact: true })).toBeVisible();
    await row.getByRole('button', { name: 'Reset password', exact: true }).click(); await confirm(ap, 'Reset password');
    personTemp = await temporary(ap);
    const resetCtx = await context(); const resetPage = await login(resetCtx, personEmail, personTemp, true);
    await changePassword(resetPage, personTemp);
    check('Admin renames single-org person; password reset forces a new password');
    // Add the existing person to a second organization using its first-admin flow.
    await goto(rp, '/platform/organizations', 'Organizations');
    await rp.getByRole('button', { name: 'Create organization', exact: true }).click();
    let form = rp.getByRole('form', { name: 'Create organization', exact: true });
    await form.getByLabel('Name', { exact: true }).fill('Browser Charlie');
    await form.getByLabel("Admin's email", { exact: true }).fill(personEmail);
    await form.getByRole('button', { name: 'Create', exact: true }).click();
    await expect(rp.getByText(/already had an account and signs in with it/)).toBeVisible();
    await ap.reload(); await expect(row.getByRole('button', { name: 'Remove', exact: true })).toBeVisible();
    assert.equal(await row.getByRole('button', { name: 'Reset password', exact: true }).count(), 0);
    assert.equal(await row.getByRole('button', { name: 'Rename', exact: true }).count(), 0);
    check('Existing account reused without temporary password; multi-org reset/rename restricted');
    await goto(rp, '/platform/accounts', 'Accounts');
    let personRow = rp.getByRole('row').filter({ hasText: personEmail });
    await personRow.getByRole('button', { name: 'Deactivate', exact: true }).click(); await confirm(rp, 'Deactivate');
    await expect(rp.getByRole('alert').filter({ hasText: /only admin/ })).toBeVisible();
    check('Sysadmin cannot deactivate the only active admin of an organization');
    await rp.getByRole('group', { name: 'Confirm', exact: true }).getByRole('button', { name: 'Cancel', exact: true }).click();
    // Platform can rename/change sign-in even for a multi-org account.
    await personRow.getByRole('button', { name: 'Edit', exact: true }).click();
    form = rp.getByRole('form', { name: `Edit ${personEmail}`, exact: true });
    await form.getByLabel('Name', { exact: true }).fill('Platform Renamed Person');
    await form.getByLabel('Email (the sign-in)', { exact: true }).fill('renamed@phase2e.example');
    await form.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(rp.getByRole('cell', { name: 'renamed@phase2e.example', exact: true })).toBeVisible();
    check('Sysadmin edits multi-org account name and sign-in email');
    // Organization security settings: validation, save, default restoration.
    await goto(ap, '/settings', 'Settings');
    const idle = ap.getByLabel('Signed out after idle (minutes)', { exact: true });
    await idle.fill('1');
    const securityForm = idle.locator('xpath=ancestor::form');
    await expect(securityForm.getByRole('button', { name: 'Save', exact: true })).toBeDisabled();
    await idle.fill('30');
    let saved = ap.waitForResponse(r => r.url().includes('/security') && r.request().method() === 'PATCH');
    await securityForm.getByRole('button', { name: 'Save', exact: true }).click();
    assert.equal((await saved).status(), 200);
    await ap.reload(); await expect(idle).toHaveValue('30');
    await idle.locator('xpath=ancestor::tr').getByRole('button', { name: 'Use default', exact: true }).click();
    saved = ap.waitForResponse(r => r.url().includes('/security') && r.request().method() === 'PATCH');
    await securityForm.getByRole('button', { name: 'Save', exact: true }).click();
    assert.equal((await saved).status(), 200);
    await ap.reload(); await expect(idle).toHaveValue('480');
    await goto(rp, '/platform/security', 'Security defaults');
    const platformIdle = rp.getByLabel('Signed out after idle (minutes)', { exact: true });
    await expect(platformIdle).toBeVisible();
    const platformForm = platformIdle.locator('xpath=ancestor::form');
    await platformIdle.fill('450');
    saved = rp.waitForResponse(r => r.url().includes('/platform/security') && r.request().method() === 'PATCH');
    await platformForm.getByRole('button', { name: 'Save', exact: true }).click();
    assert.equal((await saved).status(), 200);
    await ap.reload(); await expect(idle).toHaveValue('450');
    await rp.reload();
    await platformIdle.locator('xpath=ancestor::tr').getByRole('button', { name: 'Use default', exact: true }).click();
    saved = rp.waitForResponse(r => r.url().includes('/platform/security') && r.request().method() === 'PATCH');
    await platformForm.getByRole('button', { name: 'Save', exact: true }).click();
    assert.equal((await saved).status(), 200);
    await ap.reload(); await expect(idle).toHaveValue('480');
    check('Security settings validate ranges, save overrides and restore defaults; platform defaults load');
    await securityForm.getByRole('combobox').selectOption('complex');
    saved = ap.waitForResponse(r => r.url().includes('/security') && r.request().method() === 'PATCH');
    await securityForm.getByRole('button', { name: 'Save', exact: true }).click();
    assert.equal((await saved).status(), 200);
    check('Platform defaults propagate to organization; complex password policy enabled through UI');
    // Archive/read-only/restore/purge all use genuine UI and worker.
    await goto(rp, '/platform/organizations', 'Organizations');
    let orgRow = rp.getByRole('row').filter({ hasText: 'Browser Bravo' });
    for (const kind of ['active-report', 'active-index']) {
      cli(kind, adminEmail);
      await orgRow.getByRole('button', { name: 'Archive', exact: true }).click(); await confirm(rp, 'Archive');
      await expect(rp.getByRole('alert').filter({ hasText: /background job/ })).toBeVisible();
      await expect(orgRow.getByRole('button', { name: 'Archive', exact: true })).toBeVisible();
      await rp.getByRole('group', { name: 'Confirm', exact: true }).getByRole('button', { name: 'Cancel', exact: true }).click();
      cli('finish-jobs', adminEmail);
    }
    check('Archive refused in UI while a report or document index is running');
    await orgRow.getByRole('button', { name: 'Archive', exact: true }).click(); await confirm(rp, 'Archive');
    await expect(orgRow.getByRole('button', { name: 'Restore', exact: true })).toBeVisible();
    await goto(ap, '/people', 'People');
    await expect(ap.getByRole('status').filter({ hasText: /archived.*read-only/ })).toBeVisible();
    assert.equal(await ap.getByRole('button', { name: 'Add person', exact: true }).count(), 0);
    await orgRow.getByRole('button', { name: 'Restore', exact: true }).click(); await confirm(rp, 'Restore');
    await goto(ap, '/people', 'People'); await expect(ap.getByRole('button', { name: 'Add person', exact: true })).toBeVisible();
    check('Organization archive enforces read-only UI and restore re-enables admin actions');
    // Create disposable account for deactivation, removal, lockout, session tests.
    await addPerson('disposable@phase2e.example', 'Disposable Person', 'viewer');
    const disposableTemp = await temporary(ap);
    const dc = await context(); const dp = await login(dc, 'disposable@phase2e.example', disposableTemp, true);
    await changePassword(dp, disposableTemp);
    await goto(rp, '/platform/accounts', 'Accounts');
    let dr = rp.getByRole('row').filter({ hasText: 'disposable@phase2e.example' });
    await dr.getByRole('button', { name: 'Deactivate', exact: true }).click(); await confirm(rp, 'Deactivate');
    await dp.goto(`${base}/people`); await dp.waitForURL('**/login');
    await dr.getByRole('button', { name: 'Reactivate', exact: true }).click(); await confirm(rp, 'Reactivate');
    check('Deactivation revokes sessions; reactivation restores account availability');
    // Lock through real UI failures, not direct flag mutation.
    const lc = await context(); const lp = await lc.newPage(); await lp.goto(`${base}/login`);
    for (let i = 0; i < 5; i++) {
      await lp.getByLabel('Email', { exact: true }).fill('disposable@phase2e.example');
      await lp.getByLabel('Password', { exact: true }).fill('Incorrect-password-123!');
      const response = lp.waitForResponse(r => r.url().endsWith('/auth/login') && r.request().method() === 'POST');
      await lp.getByRole('button', { name: 'Sign in', exact: true }).click(); assert.equal((await response).status(), 401);
      await expect(lp.getByRole('button', { name: 'Sign in', exact: true })).toBeEnabled();
    }
    await lp.getByLabel('Password', { exact: true }).fill(secret);
    await lp.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(lp.getByRole('alert').filter({ hasText: 'locked' })).toBeVisible();
    await goto(ap, '/people', 'People');
    const disposableRow = ap.getByRole('row').filter({ hasText: 'disposable@phase2e.example' });
    await disposableRow.getByRole('button', { name: 'Unlock', exact: true }).click(); await confirm(ap, 'Unlock');
    check('Failed sign-ins lock account; correct password reveals lock; org admin unlocks');
    const sc1 = await context(), sc2 = await context();
    const sp1 = await login(sc1, 'disposable@phase2e.example', secret);
    const sp2 = await login(sc2, 'disposable@phase2e.example', secret);
    await goto(sp1, '/account', 'Your account');
    await sp1.getByLabel('Name', { exact: true }).fill('Self Renamed Person');
    await sp1.getByRole('button', { name: 'Save', exact: true }).click();
    await sp1.reload(); await expect(sp1.getByLabel('Name', { exact: true })).toHaveValue('Self Renamed Person');
    await sp1.getByRole('button', { name: 'Sign out everywhere else', exact: true }).click();
    await sp2.goto(`${base}/people`); await sp2.waitForURL('**/login');
    check('Your account lists sessions and signs out other browsers');
    const sc3 = await context(); const sp3 = await login(sc3, 'disposable@phase2e.example', secret);
    await goto(sp1, '/change-password', 'Change password');
    await sp1.getByLabel('Current password', { exact: true }).fill(secret);
    await sp1.getByLabel('New password', { exact: true }).fill('short');
    await sp1.getByLabel('New password again', { exact: true }).fill('short');
    await sp1.getByRole('button', { name: 'Change password', exact: true }).click();
    await expect(sp1.getByRole('alert').filter({ hasText: /at least/ })).toBeVisible();
    const changedSecret = secret + 'Changed';
    await changePassword(sp1, secret, changedSecret);
    await sp3.goto(`${base}/people`); await sp3.waitForURL('**/login');
    await goto(sp1, '/change-password', 'Change password');
    await sp1.getByLabel('Current password', { exact: true }).fill(changedSecret);
    await sp1.getByLabel('New password', { exact: true }).fill(secret);
    await sp1.getByLabel('New password again', { exact: true }).fill(secret);
    await sp1.getByRole('button', { name: 'Change password', exact: true }).click();
    await expect(sp1.getByRole('alert').filter({ hasText: /reuse/ })).toBeVisible();
    check('Self rename persists; weak/reused passwords refused; password change revokes other sessions');
    cli('expire-idle', 'disposable@phase2e.example');
    await sp1.goto(`${base}/people`); await sp1.waitForURL('**/login');
    const ec = await context(); const ep = await login(ec, 'disposable@phase2e.example', changedSecret);
    cli('expire-session', 'disposable@phase2e.example');
    await ep.goto(`${base}/people`); await ep.waitForURL('**/login');
    check('Idle and maximum session expiry redirect to login (isolated clock fixtures)');
    await goto(ap, '/people', 'People');
    await disposableRow.getByRole('button', { name: 'Remove', exact: true }).click(); await confirm(ap, 'Remove');
    await expect(disposableRow).toHaveCount(0);
    await goto(rp, '/platform/accounts', 'Accounts');
    await expect(rp.getByRole('cell', { name: 'disposable@phase2e.example', exact: true })).toBeVisible();
    check('Membership removal preserves the account');
    await addPerson('expired@phase2e.example', 'Expired Temporary', 'viewer');
    const expiredTemp = await temporary(ap);
    cli('expire-temp', 'expired@phase2e.example');
    const tc = await context(); const tp = await tc.newPage(); await tp.goto(`${base}/login`);
    await tp.getByLabel('Email', { exact: true }).fill('expired@phase2e.example');
    await tp.getByLabel('Password', { exact: true }).fill(expiredTemp);
    await tp.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(tp.getByRole('alert').filter({ hasText: /temporary password has expired/ })).toBeVisible();
    check('Expired temporary password rejected in browser (isolated clock fixture)');
    await goto(ap, '/activity', 'Activity');
    await expect(ap.getByRole('cell', { name: /Role changed/ }).first()).toBeVisible();
    await goto(rp, '/platform/activity', 'Platform activity');
    await expect(rp.getByRole('cell', { name: /Organization created/ }).first()).toBeVisible();
    check('Organization and platform activity record administration');
    await goto(rp, '/platform/organizations', 'Organizations');
    orgRow = rp.getByRole('row').filter({ hasText: 'Browser Bravo' });
    await orgRow.getByRole('button', { name: 'Archive', exact: true }).click(); await confirm(rp, 'Archive');
    await orgRow.getByRole('button', { name: 'Purge', exact: true }).click();
    form = rp.getByRole('form', { name: 'Purge Browser Bravo', exact: true });
    await form.getByLabel(/to confirm/).fill('wrong');
    await expect(form.getByRole('button', { name: 'Purge', exact: true })).toBeDisabled();
    await form.getByLabel(/to confirm/).fill('Browser Bravo');
    await form.getByRole('button', { name: 'Purge', exact: true }).click();
    await expect(rp.getByRole('status').filter({ hasText: /gone for everyone/ })).toBeVisible();
    await expect(async () => {
      await rp.reload();
      await expect(rp.getByRole('row').filter({ hasText: 'Browser Bravo' })).toHaveCount(0);
    }).toPass({ timeout: 20000 });
    await goto(rp, '/platform/accounts', 'Accounts');
    await expect(rp.getByRole('cell', { name: adminEmail, exact: true })).toBeVisible();
    check('Exact-name purge confirmation; real worker deletes organization; accounts survive');
    await rp.screenshot({ path: path.join(output, 'accounts-after-purge.png'), fullPage: true });
    const ownRoot = rp.getByRole('row').filter({ hasText: seed.root_email });
    assert.deepEqual(await ownRoot.getByRole('button').allTextContents(), ['Edit']);
    await rp.locator('button[aria-haspopup="menu"]').click();
    await rp.getByRole('menuitem', { name: 'Sign out', exact: true }).click();
    await rp.waitForURL('**/login');
    assert.equal((await rootCtx.cookies()).filter(c => c.name === 'auditmind_session').length, 0);
    check('Sysadmin self-protection; explicit logout removes renewal cookie and ends UI session');
    assert.deepEqual(evidence.errors, []);
    evidence.passed = true;
  } catch (error) {
    evidence.passed = false; evidence.failure = error.stack; process.exitCode = 1;
    console.error(error.message);
  } finally {
    if (browser) await browser.close();
    for (const child of children) {
      if (child.exitCode !== null || child.signalCode !== null) continue;
      try { execFileSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' }); } catch {}
    }
    if (prepared) {
      try { cli('cleanup'); evidence.cleanedUp = true; } catch (err) { evidence.cleanupError = err.message; process.exitCode = 1; }
    }
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(evidence, null, 2));
    console.log(JSON.stringify({ passed: evidence.passed, checks: evidence.checks.length, cleanedUp: evidence.cleanedUp }));
  }
})();
