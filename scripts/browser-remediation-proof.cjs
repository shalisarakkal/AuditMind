// Real proof submission/rejection/approval; isolated synthetic tenant only.
const assert = require('node:assert/strict');
const path = require('node:path');
const {expect} = require('../frontend/node_modules/playwright/test');
const {default:AxeBuilder} = require('../frontend/node_modules/@axe-core/playwright');

module.exports = async function({page:p,admin,viewer,base,org,check,output}) {
  const description='PB21 synthetic remediation proof';
  const created=await admin.request(org+'/findings','POST',{domain:'network_config',severity:'high',description});
  assert.equal(created.status,201);
  const id=created.body.id, endpoint=org+'/findings/'+id;
  const address=base+'/findings?org='+org.split('/').at(-1)+'&finding_id='+id;
  const workflowBefore=(await admin.request(endpoint+'/workflow')).body;
  const localObserved=async minutes=>p.evaluate(minutes=>{
    const value=new Date(Date.now()-minutes*60000);
    return new Date(value.getTime()-value.getTimezoneOffset()*60000).toISOString().slice(0,16);
  },minutes);
  await p.goto(address);
  await p.getByRole('row').filter({has:p.getByText(description,{exact:true})}).getByRole('button',{name:'Workflow',exact:true}).click();
  const dialog=p.getByRole('dialog');
  await dialog.getByText('Remediation proof',{selector:'summary',exact:true}).click();
  const panel=dialog.getByRole('region',{name:'Remediation proof review'});
  await expect(panel.getByText('No remediation proof submitted.',{exact:true})).toBeVisible();
  await dialog.getByLabel('Rationale or note',{exact:true}).fill('Unsaved synthetic workflow draft');
  await expect(panel.getByRole('button',{name:'Submit remediation proof',exact:true})).toBeDisabled();
  await dialog.getByLabel('Rationale or note',{exact:true}).fill('');
  await panel.getByLabel('Proof evidence reference',{exact:true}).fill('https://example.com/synthetic-remediation-retest');
  await panel.getByLabel('Proof observed at',{exact:true}).fill(await localObserved(60));
  await panel.getByLabel('Proof submission note',{exact:true}).fill('Synthetic post-fix evidence; no real remediation claim');
  const proofRoute='**/findings/'+id+'/remediation-proof';
  await p.route(proofRoute,async route=>{
    if(route.request().method()!=='POST')return route.continue();
    const committed=await route.fetch(); assert.equal(committed.status(),200);
    await route.fulfill({status:503,json:{detail:'Synthetic response loss after commit'}});
  });
  await panel.getByRole('button',{name:'Submit remediation proof',exact:true}).click();
  await expect(panel.getByRole('alert')).toContainText('save outcome is unknown');
  await expect(panel.getByRole('button',{name:'Submit remediation proof',exact:true})).toBeDisabled();
  await expect(panel.getByLabel('Proof submission note',{exact:true})).toHaveValue('Synthetic post-fix evidence; no real remediation claim');
  await p.unroute(proofRoute);
  await panel.getByRole('button',{name:'Reload remediation proof',exact:true}).click();
  await expect(panel.getByText('Verification pending. The workflow remains Open.',{exact:true})).toBeVisible();
  const pending=(await admin.request(endpoint+'/remediation-proof')).body;
  assert.equal(pending.records.length,1); assert.equal(pending.can_review,true);
  check('Open-finding proof submission creates a retained pending review; unsaved workflow drafts disable proof actions');
  check('A genuinely committed proof with a lost response preserves the draft and blocks another write until explicit reload discovers the single retained record');

  await panel.getByLabel('Proof decision',{exact:true}).selectOption('rejected');
  await panel.getByLabel('I reviewed the referenced remediation evidence.',{exact:true}).check();
  await panel.getByLabel('I acknowledge reviewing remediation proof I submitted.',{exact:true}).check();
  await panel.getByLabel('Proof review reason and next action',{exact:true}).fill('Synthetic rejection: patch the service and submit a new retest');
  await panel.getByRole('button',{name:'Save proof decision',exact:true}).click();
  await expect(panel.getByText(/Proof rejected\. The finding remains Open/)).toBeVisible();
  await panel.getByLabel('Proof evidence reference',{exact:true}).fill('https://example.com/synthetic-replacement-retest');
  await panel.getByLabel('Proof observed at',{exact:true}).fill(await localObserved(30));
  await panel.getByLabel('Proof submission note',{exact:true}).fill('Synthetic replacement retest');
  await panel.getByRole('button',{name:'Submit remediation proof',exact:true}).click();
  await expect(panel.getByLabel('Proof decision',{exact:true})).toBeVisible();
  await panel.getByLabel('Proof decision',{exact:true}).selectOption('approved');
  await panel.getByLabel('I reviewed the referenced remediation evidence.',{exact:true}).check();
  await panel.getByLabel('I acknowledge reviewing remediation proof I submitted.',{exact:true}).check();
  await panel.getByLabel('Proof review reason and next action',{exact:true}).fill('Synthetic approval after replacement proof review');
  await panel.getByRole('button',{name:'Save proof decision',exact:true}).click();
  await expect(panel.getByText('Proof approved. Workflow closure still requires an explicit action.',{exact:true})).toBeVisible();
  const approved=(await admin.request(endpoint+'/remediation-proof')).body;
  assert.deepEqual(approved.records.map(r=>r.state),['approved','pending','rejected','pending']);
  assert.deepEqual((await admin.request(endpoint+'/workflow')).body,workflowBefore);
  const scoring=(await admin.request(endpoint+'/risk-verification')).body;
  assert.equal(scoring.version,0); assert.equal(scoring.eligible_for_exclusion,false);
  check('Rejected proof retains the reviewer reason and leaves Open; replacement approval preserves all four records without closing workflow or excluding risk');

  for(const width of [320,1440]) {
    await p.setViewportSize({width,height:1000});
    assert.ok(await dialog.evaluate(node=>node.scrollWidth<=node.clientWidth));
    const axe=await new AxeBuilder({page:p}).include('dialog[open]').withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
    assert.deepEqual(axe.violations.map(v=>v.id),[]);
    if(output)await p.screenshot({path:path.join(output,`remediation-proof-${width}.png`),fullPage:true});
  }
  check('Remediation proof workflow fits 320px/1440px and passes Axe');
  await dialog.getByRole('button',{name:'Close',exact:true}).click();
  await viewer.page.goto(address);
  await viewer.page.getByRole('row').filter({has:viewer.page.getByText(description,{exact:true})}).getByRole('button',{name:'Workflow',exact:true}).click();
  const vd=viewer.page.getByRole('dialog');
  await vd.getByText('Remediation proof',{selector:'summary',exact:true}).click();
  const vp=vd.getByRole('region',{name:'Remediation proof review'});
  await expect(vp.getByText('Proof approved. Workflow closure still requires an explicit action.',{exact:true})).toBeVisible();
  await expect(vp.getByLabel('Proof action',{exact:true})).toHaveCount(0);
  assert.equal((await viewer.request(endpoint+'/remediation-proof/review','POST',{expected_version:4,expected_workflow_version:0,decision:'rejected',note:'Forbidden',evidence_reviewed:true})).status,403);
  await vd.getByRole('button',{name:'Close',exact:true}).click();
  check('Viewer can inspect retained remediation proof but has no write controls or reviewer authority');
};
