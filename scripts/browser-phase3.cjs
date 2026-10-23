// Real Chrome/frontend/API/worker/PostgreSQL. Only inference/embedding are mocked.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn, execFileSync} = require('node:child_process');
const {chromium, expect} = require('../frontend/node_modules/playwright/test');
const root = path.resolve(__dirname, '..');
const python = path.join(root, 'backend/.venv/Scripts/python.exe');
const fixture = path.join(root, 'backend/scripts/phase3_browser_fixture.py');
const schema = `phase3_browser_${require('node:crypto').randomBytes(6).toString('hex')}`;
const output = path.join(root, 'temp/auditmind-demo/browser/phase3', schema);
const base = 'http://localhost:3000', api = 'http://127.0.0.1:8012';
const evidence = {schema, checks: [], errors: [], mocked: ['embeddings', 'Anthropic SDK response only'], real: ['Chrome', 'frontend', 'API', 'worker', 'PostgreSQL']};
const children = [];
const cli = action => execFileSync(python, [fixture, action, '--schema', schema], {cwd: path.join(root, 'backend'), windowsHide: true, encoding: 'utf8'});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  fs.mkdirSync(output, {recursive:true});
  let browser, prepared = false;
  try {
    await new Promise((resolve,reject) => {const s=require('node:net').createServer();s.once('error',reject);s.listen(8012,'127.0.0.1',()=>s.close(resolve));});
    const seed = JSON.parse(cli('prepare')); prepared = true;
    for (const action of ['api','worker']) {
      const log=fs.openSync(path.join(output,`${action}.log`),'w');
      children.push(spawn(python,[fixture,action,'--schema',schema],{cwd:path.join(root,'backend'),env:{...process.env,REPORT_EVIDENCE_V3_ENABLED:process.env.AUDITMIND_BROWSER_EVIDENCE_V3==='1'?'true':'false',REPORT_EVIDENCE_QUALIFICATIONS_FILE:''},windowsHide:true,stdio:['ignore',log,log]}));fs.closeSync(log);
    }
    await expect.poll(async()=>{try{return (await fetch(api+'/health')).status;}catch{return 0;}},{timeout:30000}).toBe(200);
    browser=await chromium.launch({channel:'chrome',headless:true}); evidence.browser=browser.version();
    async function session(role) {
      const ctx=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
      await ctx.route('**/api/v1/**',async route=>{
        const response=await route.fetch({url:route.request().url().replace(base,api)});
        await route.fulfill({response});
      });
      const page=await ctx.newPage();let token;
      page.on('pageerror',e=>evidence.errors.push(e.message));
      page.on('request',r=>{if(r.url().startsWith(base+'/api/'))token=r.headers().authorization||token;});
      await page.goto(base+'/login');
      await page.getByLabel('Email',{exact:true}).fill(`${role}@phase3.example`);
      await page.getByLabel('Password',{exact:true}).fill(seed.password);
      await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(base+'/');
      await expect.poll(()=>token).toBeTruthy();
      const request=async(endpoint,method='GET',body)=>{
        const response=await fetch(api+'/api/v1'+endpoint,{method,headers:{Authorization:token,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
        return {status:response.status,body:await response.json()};
      };
      return {ctx,page,request};
    }
    const check=name=>{evidence.checks.push(name);console.log('PASS '+name);};
    const admin=await session('admin'), p=admin.page, org=`/orgs/${seed.org}`;
    await p.goto(base+'/reports');await p.getByRole('button',{name:'+ Generate report',exact:true}).click();
    let dialog=p.getByRole('dialog',{name:'Generate AI audit report'});
    await expect(dialog.getByRole('button',{name:'Generate Report',exact:true})).toBeDisabled();
    await p.keyboard.press('Escape');check('Unapproved real organization cannot submit AI generation');
    await p.goto(base+'/documents');await p.getByRole('button',{name:'Upload document',exact:true}).click();
    const form=p.getByRole('form',{name:'Upload document',exact:true});
    for(const [label,value] of [['Title','Phase3 synthetic policy'],['Edition / version','v1'],['Source reference','Owned synthetic fixture'],['Usage rights / authorization','Synthetic test text']])await form.getByLabel(label,{exact:true}).fill(value);
    await form.locator('select[name="framework"]').selectOption('NIST');
    await form.locator('select[name="content_kind"]').selectOption('organization_policy');
    await form.getByLabel('UTF-8 text or Markdown, up to 10 MiB').setInputFiles({name:'policy.txt',mimeType:'text/plain',buffer:Buffer.from('Synthetic MFA policy: verify administrator access and restore tests independently.')});
    await form.getByRole('button',{name:'Queue processing',exact:true}).click();await form.waitFor({state:'hidden'});
    let doc;
    await expect.poll(async()=>{const r=await admin.request(org+'/documents');doc=r.body.items.find(d=>d.title==='Phase3 synthetic policy');return doc?.versions[0]?.current;},{timeout:30000}).toBe(true);
    const version=doc.versions[0].id;
    await p.reload();await expect(p.getByText('Current',{exact:true}).first()).toBeVisible();
    check('UI upload queues real worker indexing/publication with mocked embeddings');
    const found=await admin.request(org+'/documents/search','POST',{query:'MFA',frameworks:['NIST']});
    assert.equal(found.status,200);assert.ok(found.body.items.length);check('Published policy retrievable from real tenant-filtered vector storage');
    await p.getByText('Data processing consent',{exact:true}).click();
    await p.getByRole('button',{name:'Approve external AI reports',exact:true}).click();
    await p.getByRole('button',{name:'Approve processing',exact:true}).click();
    await expect(p.getByRole('button',{name:'Revoke external AI reports',exact:true})).toBeVisible();
    check('Organization admin explicitly approves the current processing target through UI');
    const viewer=await session('viewer');await viewer.page.goto(base+'/documents');
    await expect(viewer.page.getByRole('heading',{name:'Documents',exact:true})).toBeVisible();
    assert.equal(await viewer.page.getByRole('button',{name:'Upload document',exact:true}).count(),0);
    assert.equal((await viewer.request(org+'/documents/settings/consent','PUT',{purpose:'report',granted:false,target:'fixture'})).status,403);
    assert.equal((await viewer.request(org+'/reports/generate','POST',{title:'Forbidden viewer'})).status,403);
    check('Viewer UI is read-only and real API rejects consent/report writes');
    const other=await session('other');
    assert.equal((await other.request(org+'/documents')).status,403);
    const isolated=await other.request(`/orgs/${seed.other_org}/documents/search`,'POST',{query:'MFA',frameworks:['NIST']});
    assert.equal(isolated.status,200);assert.deepEqual(isolated.body.items,[]);
    check('Foreign organization cannot list/retrieve another tenant policy');
    async function generate(title){
      await p.goto(base+'/reports');await p.getByRole('button',{name:'+ Generate report',exact:true}).click();
      dialog=p.getByRole('dialog',{name:'Generate AI audit report'});
      await dialog.getByLabel('Report title',{exact:true}).fill(title);
      await expect(dialog.getByRole('button',{name:'Generate Report',exact:true})).toBeEnabled();
      const response=p.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/reports/generate'));
      await dialog.getByRole('button',{name:'Generate Report',exact:true}).click();
      const result=await response;assert.equal(result.status(),202);return (await result.json()).id;
    }
    async function terminal(id,status){let result;await expect.poll(async()=>{result=await admin.request(org+'/reports/'+id);return result.body.status;},{timeout:45000}).toBe(status);return result.body;}
    const success=await generate('Fixture success');const snapshot=await terminal(success,'completed');
    assert.equal(snapshot.data.domains.length,7);assert.equal(snapshot.data.remediations[0].confidence,.5);
    assert.equal(snapshot.data.provenance.rule_based.overall_score,100);
    assert.equal(snapshot.data.provenance.model,'claude-browser-fixture');
    assert.ok(snapshot.data.compliance_citations.length);
    if(process.env.AUDITMIND_BROWSER_EVIDENCE_V3==='1') {
      assert.equal(snapshot.data.assessment_status,'partial');assert.equal(snapshot.data.overall_score,null);
      assert.equal(snapshot.data.provenance.schema_version,3);
    }
    check('UI queues real asynchronous report; worker validates mock AI domains/remediation and captures provenance');
    await p.goto(base+'/reports');const row=p.getByRole('row').filter({hasText:'Fixture success'});
    if(process.env.AUDITMIND_BROWSER_EVIDENCE_V3==='1') {
      await p.getByLabel('Assessment completeness',{exact:true}).selectOption('partial');
      await expect(row.getByText('Partial AI assessment — overall score unavailable',{exact:true})).toBeVisible();
      await p.getByLabel('Assessment completeness',{exact:true}).selectOption('complete');
      await expect(row).toHaveCount(0);
      await p.getByLabel('Assessment completeness',{exact:true}).selectOption('');
      await expect(row).toHaveCount(1);
      check('Assessment completeness filter includes partial reports without inventing a numeric score');
    }
    await row.getByRole('button',{name:'View',exact:true}).click();
    await expect(p.getByText('Mock inference; synthetic evidence only.',{exact:true})).toBeVisible();
    await expect(p.getByText('AI resilience score (advisory)',{exact:true})).toBeVisible();
    if(process.env.AUDITMIND_BROWSER_EVIDENCE_V3==='1') await expect(p.getByText('Partial AI assessment — overall score unavailable',{exact:true})).toBeVisible();
    await expect(p.getByText(/Captured deterministic baseline: 100\/100/)).toBeVisible();
    await expect(p.getByText(/not a calibrated probability of compliance/)).toBeVisible();
    const sourceLink=p.getByRole('link',{name:snapshot.data.compliance_citations[0].citation_id,exact:true}).first();
    await expect(sourceLink).toBeVisible();await sourceLink.focus();await p.keyboard.press('Enter');
    assert.match(p.url(),/#report-evidence-/);
    await p.setViewportSize({width:390,height:844});
    await expect(p.getByText('AI resilience score (advisory)',{exact:true})).toBeVisible();
    await p.emulateMedia({media:'print'});
    await expect(p.getByText(/AI variation is not a measured change/)).toBeVisible();
    await p.emulateMedia({media:'screen'});await p.setViewportSize({width:1440,height:1000});
    check('Advisory labels, baseline and confidence visible; keyboard citation navigation, mobile and print presentation');
    await p.screenshot({path:path.join(output,'report.png'),fullPage:true});
    for(const format of ['HTML','PDF']){
      await p.goto(base+'/reports');const download=p.waitForEvent('download');
      await p.getByRole('row').filter({hasText:'Fixture success'}).getByRole('button',{name:'Download '+format,exact:true}).click();
      const item=await download;assert.equal(await item.failure(),null);
      const destination=path.join(output,'report.'+format.toLowerCase());await item.saveAs(destination);
      const bytes=fs.readFileSync(destination);if(format==='PDF')assert.equal(bytes.subarray(0,4).toString(),'%PDF');else assert.match(bytes.toString(),/Fixture success/);
    }
    check('Report viewer and real browser HTML/PDF downloads render saved snapshot');
    await viewer.page.goto(base+'/reports');
    const viewerDownload=viewer.page.waitForEvent('download');
    await viewer.page.getByRole('row').filter({hasText:'Fixture success'}).getByRole('button',{name:'Download HTML',exact:true}).click();
    assert.equal(await (await viewerDownload).failure(),null);
    check('Viewer can download an authorized completed report through UI');
    const auditor=await session('auditor');await auditor.page.goto(base+'/reports');
    await auditor.page.getByRole('button',{name:'+ Generate report',exact:true}).click();
    await expect(auditor.page.getByRole('dialog').getByRole('button',{name:'Generate Report',exact:true})).toBeEnabled();
    await auditor.page.keyboard.press('Escape');
    assert.equal((await auditor.request(org+'/documents/settings/consent','PUT',{purpose:'report',granted:false,target:'fixture'})).status,403);
    check('Auditor can open approved generation but cannot change consent');
    assert.equal((await other.request(org+'/reports/'+success)).status,403);
    check('Foreign organization cannot read completed report');
    const retry=await generate('Fixture retry');await terminal(retry,'completed');check('Mock 429 retries through real worker/accounting and completes');
    const invalid=await generate('Fixture invalid');const failed=await terminal(invalid,'failed');assert.equal(failed.data,null);
    await p.goto(base+'/reports');await expect(p.getByRole('row').filter({hasText:'Fixture invalid'})).toContainText(/failed/i);
    check('Malformed model output becomes visible failure, never an audit snapshot');
    const cancel=await generate('Fixture cancel');await expect.poll(async()=> (await admin.request(org+'/reports/'+cancel)).body.status,{timeout:15000}).toBe('running');
    await expect.poll(()=>JSON.parse(cli('inspect')).usage_count,{timeout:15000}).toBe(5);
    await p.goto(base+'/reports');await p.getByRole('row').filter({hasText:'Fixture cancel'}).getByRole('button',{name:'Cancel',exact:true}).click();
    await p.getByRole('group',{name:'Cancel report generation',exact:true}).getByRole('button',{name:'Cancel generation',exact:true}).click();
    const cancelled=await terminal(cancel,'failed');assert.match(cancelled.error_message,/cancelled/i);
    await delay(6000);const stats=JSON.parse(cli('inspect'));
    assert.equal(stats.usage_count,5); // success 1 + retry 2 + invalid 1 + cancelled 1
    check('UI cancellation survives in-flight timeout; no second reservation or saved result');
    await p.goto(base+'/documents');await p.getByRole('button',{name:'Retire',exact:true}).click();
    await expect.poll(async()=> (await admin.request(org+'/documents/search','POST',{query:'MFA',frameworks:['NIST']})).body.items.length).toBe(0);
    assert.deepEqual((await admin.request(org+'/reports/'+success)).body.data,snapshot.data);
    check('Retirement excludes future retrieval without mutating completed snapshot');
    await p.getByText('Data processing consent',{exact:true}).click();
    await p.getByRole('button',{name:'Revoke external AI reports',exact:true}).click();
    await p.getByRole('button',{name:'Revoke processing',exact:true}).click();
    assert.equal((await admin.request(org+'/reports/generate','POST',{title:'Consent revoked'})).status,409);
    check('Revocation blocks new generation through real API');
    assert.deepEqual(evidence.errors,[]);evidence.passed=true;
  }catch(error){evidence.passed=false;evidence.failure=error.stack;process.exitCode=1;console.error(error.message);
    try{await browser?.contexts()[0]?.pages()[0]?.screenshot({path:path.join(output,'failure.png'),fullPage:true});}catch{}}
  finally{
    if(browser)await browser.close();
    for(const child of children)if(child.exitCode===null&&child.signalCode===null){try{execFileSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});}catch{}}
    if(prepared){try{cli('cleanup');evidence.cleanedUp=true;}catch(error){evidence.cleanupError=error.message;process.exitCode=1;}}
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(evidence,null,2));
    console.log(JSON.stringify({passed:evidence.passed,checks:evidence.checks.length,cleanedUp:evidence.cleanedUp,evidence:path.relative(root,output)}));
  }
})();
