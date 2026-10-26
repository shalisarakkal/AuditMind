// Real Chrome, synthetic API interception only. No real credentials or writes.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium, expect } = require('../frontend/node_modules/playwright/test');
const AxeBuilder = require('../frontend/node_modules/@axe-core/playwright').default;

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const result = { browser: browser.version(), api: 'intercepted fixtures only', checks: [] };
  const output = path.resolve(__dirname, '../temp/auditmind-demo/browser');
  await fs.mkdir(output, { recursive: true });
  try {
    for (const scenario of ['viewer', 'admin', 'platform']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      let granted = false;
      let consentWrites = 0;
      let uploads = 0;
      let previewFails = false;
      const errors = [];
      const version = { id: 'v1', number: 1, edition: 'Demo', source: 'Synthetic policy', content_kind: 'organization_policy', rights: 'Synthetic training material', content_hash: 'a'.repeat(64), current: false, retired_at: null, purged_at: null, indexes: [{ id: 'i1', status: 'pending', publish_version: true, error_message: null }] };
      const document = { id: 'd1', org_id: scenario === 'platform' ? null : 'sa01', title: 'Synthetic access policy', framework: null, created_at: '2026-10-21T12:00:00Z', versions: [version] };
      const shared = { ...document, id: 'shared', org_id: null, title: 'Shared synthetic reference', versions: [{ ...version, id: 'v-shared', current: true, indexes: [{ ...version.indexes[0], id: 'i-shared', status: 'ready' }] }] };
      await context.route('**/api/v1/**', async route => {
        const req = route.request();
        const endpoint = new URL(req.url()).pathname.replace('/api/v1', '');
        const send = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
        if (endpoint === '/auth/refresh') return send({ access_token: 'fixture-token', must_change_password: false });
        if (endpoint === '/auth/me') return send({ id: 'fixture-user', name: 'Fixture user', email: 'fixture@example.com', is_sysadmin: scenario === 'platform', must_change_password: false });
        if (endpoint === '/orgs') return send([{ id: 'sa01', name: 'SA01', role: scenario === 'viewer' ? 'viewer' : 'admin', archived: false }]);
        if (endpoint === '/worker-status') return send({ running: true });
        if (/\/(scans|archive-jobs)$/.test(endpoint)) return send([]);
        if (endpoint.endsWith('/documents/settings')) return send({ embedding_target: 'local:test', report_target: 'anthropic:fixture:prompt', effective_embedding: 'local', embedding_granted: false, report_granted: granted });
        if (endpoint.endsWith('/documents/settings/consent')) {
          assert.equal(scenario, 'admin'); assert.equal(req.postDataJSON().purpose, 'report');
          consentWrites++; granted = true; return send({ ok: true });
        }
        if (endpoint.endsWith('/documents/search')) return send({ items: [] });
        if (endpoint.endsWith('/documents/facets')) return send({ framework: [] });
        if (endpoint.endsWith('/documents/versions/v1')) return previewFails ? send({detail:'Preview temporarily unavailable'},503) : send({content:'Synthetic preview text '+ 'x'.repeat(5000)});
        if (endpoint.endsWith('/documents/versions/v-shared')) return send({content:'Shared reference preview'});
        if (endpoint.endsWith('/documents') && req.method() === 'POST') {
          uploads++; assert.match(req.postData(), /browser-policy\.txt/); return send({ ok: true });
        }
        if (endpoint.endsWith('/documents')) return send({ items: scenario === 'platform' ? [document] : [document, shared], total: scenario === 'platform' ? 1 : 2 });
        throw new Error(`Unexpected intercepted request: ${req.method()} ${endpoint}`);
      });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`http://localhost:3000/${scenario === 'platform' ? 'platform/documents' : 'documents'}`);
      await page.getByRole('cell').filter({ hasText: 'Synthetic access policy' }).first().waitFor();
      assert.equal(await page.getByRole('checkbox', { name: /Select Synthetic access policy/ }).count(), scenario === 'viewer' ? 0 : 1);
      assert.equal(await page.getByRole('checkbox', { name: /Select Shared synthetic reference/ }).count(), 0);
      assert.equal(await page.getByText('Reactivating…', { exact: true }).count(), 0);
      assert.ok(await page.getByText('Queued', { exact: true }).count());
      const details = page.getByText('Version details v1', { exact: true }).first();
      assert.equal(await details.evaluate(element => element.parentElement.open), false);
      const documentRow=page.getByRole('row').filter({has:page.getByRole('cell').filter({hasText:'Synthetic access policy'})});
      const previewButton=documentRow.getByRole('button',{name:'Preview v1',exact:true});
      await previewButton.click();
      const preview=page.getByRole('region',{name:'Preview of Synthetic access policy · v1',exact:true});
      await expect(preview.locator('pre')).toContainText('Synthetic preview text');
      assert.equal(await preview.locator('..').getAttribute('colspan'),scenario==='viewer'?'5':'6');
      assert.equal(await preview.evaluate(el=>el.closest('tr').previousElementSibling.textContent.includes('Synthetic access policy')),true);
      await expect(documentRow.getByRole('button',{name:'Hide preview v1',exact:true})).toHaveAttribute('aria-expanded','true');
      const previewAudit=await new AxeBuilder({page}).include('main').withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
      assert.deepEqual(previewAudit.violations.map(v=>v.id),[]);
      await page.screenshot({path:path.join(output,`documents-${scenario}-preview.png`),fullPage:true});
      await page.setViewportSize({width:390,height:844});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'Preview must stay inside page width');
      await page.screenshot({path:path.join(output,`documents-${scenario}-preview-mobile.png`),fullPage:true});
      await page.setViewportSize({width:1440,height:1000});
      await preview.getByRole('button',{name:'Close preview',exact:true}).click();
      await expect(previewButton).toBeFocused();
      previewFails=true; await previewButton.click();
      await expect(preview.getByRole('alert')).toContainText('Preview temporarily unavailable');
      previewFails=false; await preview.getByRole('button',{name:'Retry preview',exact:true}).click();
      await expect(preview.locator('pre')).toContainText('Synthetic preview text');
      if(scenario!=='platform') {
        await page.getByRole('row').filter({has:page.getByRole('cell').filter({hasText:'Shared synthetic reference'})}).getByRole('button',{name:'Preview v1',exact:true}).click();
        await expect(page.getByText('Shared reference preview',{exact:true})).toBeVisible();
        await expect(preview).toHaveCount(0);
        await page.getByRole('button',{name:'Hide preview v1',exact:true}).click();
      } else await documentRow.getByRole('button',{name:'Hide preview v1',exact:true}).click();
      result.checks.push(`${scenario}: inline preview placement/column span, toggle, focus restoration, retry, single preview and mobile long-text containment`);
      if (scenario === 'viewer') {
        assert.equal(await page.getByRole('button', { name: 'Upload document', exact: true }).count(), 0);
        assert.equal(await page.getByRole('button', { name: 'Retire', exact: true }).count(), 0);
      } else {
        await page.getByRole('button', { name: 'Upload document', exact: true }).click();
        const form = page.getByRole('form', { name: 'Upload document', exact: true });
        for (const [label, value] of [['Title', 'Browser policy'], ['Edition / version', 'Demo v2'], ['Source reference', 'Synthetic source'], ['Usage rights / authorization', 'Synthetic owned text']]) await form.getByLabel(label, { exact: true }).fill(value);
        await form.getByLabel('UTF-8 text or Markdown, up to 10 MiB').setInputFiles({ name: 'browser-policy.txt', mimeType: 'text/plain', buffer: Buffer.from('Synthetic policy') });
        await form.getByRole('button', { name: 'Queue processing', exact: true }).click();
        await form.waitFor({ state: 'hidden' });
        assert.equal(uploads, 1);
      }
      if (scenario !== 'platform') {
        await page.getByText('Data processing consent', { exact: true }).click();
        await page.getByRole('region', { name: 'AI report processing', exact: true }).waitFor();
        if (scenario === 'admin') {
          await page.getByRole('button', { name: 'Approve external AI reports', exact: true }).click();
          assert.equal(consentWrites, 0);
          await page.getByRole('button', { name: 'Approve processing', exact: true }).click();
          await page.getByRole('button', { name: 'Revoke external AI reports', exact: true }).waitFor();
          assert.equal(consentWrites, 1);
        } else assert.equal(await page.getByRole('button', { name: 'Approve external AI reports', exact: true }).count(), 0);
        await page.getByLabel('Evidence query', { exact: true }).fill('MFA');
        await page.getByRole('button', { name: 'Search', exact: true }).click();
        await page.getByText('No matching permitted evidence found.', { exact: true }).waitFor();
      } else {
        await page.getByText('Platform embedding configuration', { exact: true }).click();
        await page.getByRole('form', { name: 'Embedding configuration', exact: true }).waitFor();
        assert.ok(await page.getByLabel('Model revision', { exact: true }).isVisible());
      }
      const audit = await new AxeBuilder({ page }).include('main').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      assert.deepEqual(audit.violations.map(v => ({ id: v.id, impact: v.impact })), []);
      assert.deepEqual(errors, []);
      await page.screenshot({ path: path.join(output, `documents-${scenario}.png`), fullPage: true });
      result.checks.push(`${scenario}: permissions, lifecycle badges, compact details, relevant forms and zero main-region Axe AA violations`);
      await context.close();
    }
    await fs.writeFile(path.join(output, 'documents-ui.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
