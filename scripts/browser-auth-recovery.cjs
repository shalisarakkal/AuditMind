// Real Chrome UI regression with intercepted API responses; no credentials,
// production account changes, or live backend/provider requests.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('../frontend/node_modules/playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const context = await browser.newContext();
    let mode = 'expired';
    let refreshes = 0;
    let refusedAccounts = 0;
    const errors = [];
    const me = { id: 'test-root', email: 'root@example.com', name: 'Test sysadmin',
      is_sysadmin: true, must_change_password: false, password_expires_at: null };
    const defaults = { idle_minutes: 480, max_session_days: 7, lockout_threshold: 5,
      lockout_window_minutes: 15, lock_minutes: 15, password_rule: 'simple', min_length: 12,
      require_upper: true, require_lower: true, require_digit: true, require_symbol: true,
      history_count: 5, expiry_days: 90 };
    await context.route('**/api/v1/**', async route => {
      const request = route.request();
      const endpoint = new URL(request.url()).pathname.replace('/api/v1', '');
      const respond = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      if (endpoint === '/auth/refresh') {
        refreshes++;
        if (mode === 'ended') return respond({ detail: { code: 'session_ended', message: 'Test session ended' } }, 401);
        return respond({ access_token: refreshes === 1 ? 'expired' : 'renewed', expires_in: 900, must_change_password: false });
      }
      if (endpoint === '/auth/me') {
        if (mode === 'unavailable') return respond({ detail: 'Account lookup temporarily unavailable' }, 503);
        if (mode === 'ended' || request.headers().authorization === 'Bearer expired') {
          refusedAccounts++;
          return respond({ detail: 'Expired account token' }, 401);
        }
        return respond(me);
      }
      if (endpoint === '/orgs') return respond([]);
      if (endpoint === '/worker-status') return respond({ running: true });
      if (endpoint === '/platform/security') return respond({ values: defaults, changed: [], below: defaults });
      if (endpoint === '/auth/options') return respond({ public_signup: false });
      throw new Error(`Unexpected intercepted API request: ${request.method()} ${endpoint}`);
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://localhost:3000/platform/security');
    await page.getByRole('form', { name: 'Security settings' }).waitFor();
    assert.ok(refusedAccounts > 0);
    assert.equal(refreshes, 2, 'one initial session hydration plus one shared renewal');
    mode = 'unavailable';
    await page.reload();
    await page.getByRole('alert').filter({ hasText: 'Account lookup temporarily unavailable' }).waitFor();
    mode = 'healthy';
    await page.getByRole('button', { name: 'Retry', exact: true }).click();
    await page.getByRole('form', { name: 'Security settings' }).waitFor();
    assert.deepEqual(errors, []);
    const result = { browser: browser.version(), channel: 'chrome', api: 'intercepted fixtures, not live authentication', checks: [
      'Expired /auth/me token renews once and Security defaults renders without hard refresh',
      'Failed account lookup displays error and Retry',
      'Retry recovers the protected form without reloading',
      'No uncaught browser exceptions',
    ] };
    const output = path.resolve(__dirname, '../temp/auditmind-demo/browser/auth-recovery.json');
    await fs.mkdir(path.dirname(output), { recursive: true });
    await fs.writeFile(output, JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
