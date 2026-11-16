// Real catalog/category review in the isolated browser database; no AI calls.
const assert = require('node:assert/strict');
const path = require('node:path');
const {expect} = require('../frontend/node_modules/playwright/test');
const {default:AxeBuilder} = require('../frontend/node_modules/@axe-core/playwright');

module.exports = async function({page:p,admin,viewer,session,base,org,check,output}) {
  const platform = await session('platform');
  assert.equal((await admin.request('/platform/control-catalogs/baseline','POST',{})).status,403);
  await platform.page.goto(base+'/platform/controls');
  await platform.page.getByRole('button',{name:'Install verified NIST baseline',exact:true}).click();
  await expect(platform.page.getByRole('button',{name:'Install verified NIST baseline',exact:true})).toBeEnabled();
  const releases = (await admin.request(org+'/control-catalogs')).body;
  assert.equal(releases.available,true); assert.equal(releases.items.length,1);
  const release = releases.items[0], controls = (await admin.request(org+'/control-catalogs/'+release.id)).body.controls;
  assert.equal(controls.length,106); assert.ok(!controls.some(c=>c.reference==='RC.CO-01'));
  assert.equal((await platform.request('/platform/control-catalogs/baseline','POST',{})).status,200);
  for(const width of [320,1440]) {
    await platform.page.setViewportSize({width,height:1000});
    assert.ok(await platform.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    const axe=await new AxeBuilder({page:platform.page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
    assert.deepEqual(axe.violations.map(v=>v.id),[]);
    if(output)await platform.page.screenshot({path:path.join(output,`control-catalog-platform-${width}.png`),fullPage:true});
  }
  check('Platform-only verified NIST install exposes 106 current outcomes, excludes withdrawn entries and repeats without a new release');

  const category = 'PB15 synthetic category', otherCategory = 'PB15 synthetic other category';
  async function create(description,categoryValue=category) {
    const result=await admin.request(org+'/findings','POST',{domain:'identity_access',source:'manual',severity:'high',category:categoryValue,description});
    assert.equal(result.status,201); return result.body.id;
  }
  const first=await create('PB15 synthetic first finding'), second=await create('PB15 synthetic second finding'), other=await create('PB15 synthetic unrelated finding',otherCategory);
  const endpoint=id=>org+'/findings/'+id+'/control-mapping';
  const url=id=>base+'/controls?org='+org.split('/').at(-1)+'&finding_id='+id;
  const originalWorkflow=(await admin.request(org+'/findings/'+first+'/workflow')).body;
  await p.goto(base+'/findings?org='+org.split('/').at(-1)+'&finding_id='+first);
  const row=p.getByRole('row').filter({has:p.getByText('PB15 synthetic first finding',{exact:true})});
  await expect(row).toContainText('Unmapped');
  await row.getByRole('button',{name:'Controls',exact:true}).click();
  await expect(p.getByLabel('Finding ID',{exact:true})).toHaveValue(first);
  await expect(p.getByRole('heading',{name:'Unmapped',exact:true})).toBeVisible();
  await p.getByRole('button',{name:'Propose mapping',exact:true}).click();
  let d=p.getByRole('dialog',{name:'Propose control mapping',exact:true});
  await expect(d.getByRole('button',{name:'Save proposal',exact:true})).toBeDisabled();
  await d.getByLabel('Find a control',{exact:true}).fill(controls[0].reference);
  await d.getByRole('checkbox',{name:controls[0].title,exact:true}).check();
  await d.getByLabel('Review rationale',{exact:true}).fill('Synthetic category relevance review only');
  for(const width of [320,1440]) {
    await p.setViewportSize({width,height:1000});
    assert.ok(await d.evaluate(node=>node.scrollWidth<=node.clientWidth));
    const axe=await new AxeBuilder({page:p}).include('dialog[open]').withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
    assert.deepEqual(axe.violations.map(v=>v.id),[]);
  }
  if(output)await p.screenshot({path:path.join(output,'control-mapping-proposal.png'),fullPage:true});
  await d.getByRole('button',{name:'Save proposal',exact:true}).click(); await expect(d).not.toBeVisible();
  await expect(p.getByRole('region',{name:'Proposal pending administrator review',exact:true})).toBeVisible();
  assert.equal((await admin.request(endpoint(second))).body.status,'unmapped');
  assert.equal((await admin.request(endpoint(other))).body.version,0);
  await p.getByRole('button',{name:'Review proposal',exact:true}).click();
  d=p.getByRole('dialog',{name:'Approve control mapping',exact:true});
  await expect(d).toContainText(controls[0].description);
  await d.getByLabel('Review rationale',{exact:true}).fill('Administrator approves relevance, not compliance');
  await d.getByRole('button',{name:'Approve mapping',exact:true}).click(); await expect(d).not.toBeVisible();
  await expect(p.getByRole('heading',{name:'Approved category mapping',exact:true})).toBeVisible();
  assert.equal((await admin.request(endpoint(first))).body.version,2);
  assert.equal((await admin.request(endpoint(second))).body.status,'mapped');
  assert.equal((await admin.request(endpoint(other))).body.status,'unmapped');
  assert.deepEqual((await admin.request(org+'/findings/'+first+'/workflow')).body,originalWorkflow);
  check('Finding row status and Controls navigation preserve explicit Unmapped; approval applies only to the exact category without changing workflow');

  await p.getByRole('button',{name:'Propose mapping',exact:true}).click();
  d=p.getByRole('dialog',{name:'Propose control mapping',exact:true});
  await d.getByLabel('Review rationale',{exact:true}).fill('Stale synthetic reviewer');
  const payload={source:'manual',domain:'identity_access',category,expected_version:2,catalog_id:release.id,control_ids:[controls[1].control_id],rationale:'Independent synthetic proposal'};
  assert.equal((await admin.request(endpoint(first)+'/proposals','POST',payload)).status,200);
  await d.getByRole('button',{name:'Save proposal',exact:true}).click();
  await expect(d.getByRole('alert')).toContainText('changed');
  await expect(d.getByLabel('Review rationale',{exact:true})).toHaveValue('Stale synthetic reviewer');
  await d.getByRole('button',{name:'Close and reload',exact:true}).click(); await expect(d).not.toBeVisible();
  await p.getByRole('button',{name:'Revise proposal',exact:true}).click();
  d=p.getByRole('dialog',{name:'Propose control mapping',exact:true});
  await expect(d.getByRole('button',{name:'Save proposal',exact:true})).toBeDisabled();
  await d.getByLabel('Review rationale',{exact:true}).fill('Synthetic committed response loss');
  let submissions=0;
  await p.route('**/control-mapping/proposals',async route=>{
    submissions++;const accepted=await route.fetch();assert.equal(accepted.status(),200);
    await route.fulfill({status:503,json:{detail:'Synthetic committed response loss'}});
  });
  try {
    await d.getByRole('button',{name:'Save proposal',exact:true}).click();
    await expect(d.getByRole('alert')).toContainText('Outcome unknown');
    await d.getByRole('button',{name:'Close and reload',exact:true}).click(); await expect(d).not.toBeVisible();
  } finally {await p.unroute('**/control-mapping/proposals');}
  assert.equal(submissions,1);
  let current=(await admin.request(endpoint(first))).body;
  assert.equal(current.version,4); assert.equal(current.effective.version,2); assert.equal(current.proposal.version,4);
  check('Stale review retains the draft; a lost committed response refreshes without retrying, while the prior approval stays effective');
  await p.getByRole('button',{name:'Withdraw mapping',exact:true}).click();
  d=p.getByRole('dialog',{name:'Withdraw control mapping',exact:true});
  await expect(d.getByRole('region',{name:'Effective mapping to withdraw',exact:true})).toContainText(controls[0].title);
  await expect(d.getByRole('region',{name:'Pending proposal to withdraw',exact:true})).toContainText(controls[1].title);
  await d.getByRole('button',{name:'Cancel',exact:true}).click();
  assert.equal((await admin.request(endpoint(first))).body.version,4);
  const retainedEndpoint=org+'/control-rules/'+current.rule_id;
  await p.getByRole('link',{name:'Open retained category rule',exact:true}).click();
  await expect(p.getByLabel('Rule ID',{exact:true})).toHaveValue(current.rule_id);
  async function lifecycle(endpointValue) {
    const job=await admin.request(endpointValue,'POST');assert.ok([200,202].includes(job.status),JSON.stringify(job.body));
    await expect.poll(async()=>{
      const row=(await admin.request(org+'/archive-jobs?tracked=true')).body.find(x=>x.id===job.body.id);
      assert.ok(!row||!['failed','stopped'].includes(row.status),JSON.stringify(row));return row?.status||job.body.status;
    },{timeout:45000}).toBe('completed');
  }
  await lifecycle(org+'/findings/'+first+'/archive');
  const archived=(await admin.request(org+'/archive?type=finding&q='+encodeURIComponent('PB15 synthetic first finding'))).body.items;
  assert.equal(archived.length,1);
  await lifecycle(org+'/archive/'+archived[0].id+'/purge');
  assert.equal((await admin.request(endpoint(first))).status,404);
  assert.equal((await admin.request(retainedEndpoint)).body.status,'mapped');
  await p.getByRole('button',{name:'Withdraw mapping',exact:true}).click();
  d=p.getByRole('dialog',{name:'Withdraw control mapping',exact:true});
  await d.getByLabel('Review rationale',{exact:true}).fill('Withdraw synthetic category mapping and pending proposal');
  await d.getByRole('button',{name:'Withdraw mapping',exact:true}).click(); await expect(d).not.toBeVisible();
  await expect(p.getByRole('heading',{name:'Unmapped',exact:true})).toBeVisible();
  current=(await admin.request(retainedEndpoint)).body;
  assert.equal(current.version,5);assert.equal(current.effective,null);assert.equal(current.proposal,null);
  await viewer.page.goto(base+'/controls?org='+org.split('/').at(-1)+'&rule_id='+current.rule_id);
  await expect(viewer.page.getByRole('heading',{name:'Unmapped',exact:true})).toBeVisible();
  assert.equal(await viewer.page.getByRole('button',{name:'Propose mapping',exact:true}).count(),0);
  await viewer.page.getByRole('button',{name:'Show mapping history',exact:true}).click();
  await expect(viewer.page.getByRole('heading',{name:'Approved mapping',exact:true})).toBeVisible();
  assert.equal((await viewer.request(retainedEndpoint+'/proposals','POST',{...payload,expected_version:5})).status,403);
  check('After archive and source purge, retained-rule review still works; withdrawal previews both scopes, Cancel makes no change and viewers cannot review');

  await p.evaluate(next=>history.pushState(null,'',next),url(other));
  await expect(p.getByLabel('Finding ID',{exact:true})).toHaveValue(other);
  await expect(p.getByText(otherCategory,{exact:true})).toBeVisible();
  for(const width of [320,1440]) {
    await p.setViewportSize({width,height:1000});
    assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    const axe=await new AxeBuilder({page:p}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
    assert.deepEqual(axe.violations.map(v=>v.id),[]);
    if(output)await p.screenshot({path:path.join(output,`control-mapping-${width}.png`),fullPage:true});
  }
  check('Client query navigation opens the correct finding; mapping page and review dialog fit mobile/desktop and pass Axe');
};
