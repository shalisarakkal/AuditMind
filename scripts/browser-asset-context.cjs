// Real managed-context workflow on synthetic assets in the isolated browser DB.
const assert=require('node:assert/strict');
const {expect}=require('../frontend/node_modules/playwright/test');
const {default:AxeBuilder}=require('../frontend/node_modules/@axe-core/playwright');
module.exports=async function({page:p,admin,viewer,base,org,check}){
 const name='PB14 managed-context synthetic host';
 const created=await admin.request(org+'/assets','POST',{type:'server',hostname:name,environment:'scanner-production',criticality:'source-high'});assert.equal(created.status,201);
 const id=created.body.id,endpoint=org+'/assets/'+id+'/context',url=base+'/assets?org='+org.split('/').at(-1)+'&hostname='+encodeURIComponent(name);
 const me=(await admin.request('/auth/me')).body;
 async function open(page=p){await page.goto(url);const row=page.getByRole('row').filter({has:page.getByText(name,{exact:true})});await row.getByRole('button',{name:page===p?'Edit context':'View context',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Asset context',exact:true});return dialog;}
 let d=await open();await expect(d.getByLabel('Change rationale',{exact:true})).toBeVisible();
 await expect(d.getByRole('button',{name:'Cancel',exact:true})).toBeFocused();
 await expect(d.getByRole('button',{name:'Save context',exact:true})).toBeDisabled();
 await d.getByLabel('Find asset owner',{exact:true}).fill(me.email.split('@')[0]);
 assert.equal((await admin.request(endpoint)).body.version,0);
 await d.getByLabel('Owner',{exact:true}).selectOption(me.id);
 await d.getByLabel('Organization-managed environment',{exact:true}).fill('Production');await d.getByLabel('Business criticality',{exact:true}).selectOption('critical');
 await expect(d.getByRole('button',{name:'Save context',exact:true})).toBeDisabled();await d.getByLabel('Change rationale',{exact:true}).fill('Synthetic owner reviewed this business context');
 for(const width of [320,1440]){await p.setViewportSize({width,height:1000});assert.ok(await d.evaluate(node=>node.scrollWidth<=node.clientWidth));}
 const axe=await new AxeBuilder({page:p}).include('dialog[open]').withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();assert.deepEqual(axe.violations.map(x=>x.id),[]);
 await d.getByRole('button',{name:'Save context',exact:true}).click();await expect(d).not.toBeVisible();
 let saved=(await admin.request(endpoint)).body;assert.equal(saved.version,1);assert.equal(saved.environment,'Production');assert.equal(saved.owner_id,me.id);
 let asset=(await admin.request(org+'/assets?hostname='+encodeURIComponent(name))).body.items[0];assert.equal(asset.environment,'scanner-production');assert.equal(asset.criticality,'source-high');
 for(const query of ['managed_owner='+me.id,'managed_environment=Production','business_criticality=critical'])assert.ok((await admin.request(org+'/assets?'+query)).body.items.some(x=>x.id===id));
 check('Managed asset context saves independently of scanner fields, owner search makes no mutation, filters work and desktop/mobile Axe pass');
 d=await open();await d.getByLabel('Organization-managed environment',{exact:true}).fill('Unsaved draft');await d.getByLabel('Change rationale',{exact:true}).fill('Stale reviewer draft');
 assert.equal((await admin.request(endpoint,'PATCH',{expected_version:1,environment:'Other reviewer',rationale:'Independent synthetic reviewer'})).status,200);
 await d.getByRole('button',{name:'Save context',exact:true}).click();await expect(d.getByRole('alert')).toContainText('changed');await expect(d.getByLabel('Organization-managed environment',{exact:true})).toHaveValue('Unsaved draft');
 await d.getByRole('button',{name:'Reload saved context',exact:true}).click();await d.getByRole('button',{name:'Keep editing',exact:true}).click();await expect(d.getByLabel('Change rationale',{exact:true})).toHaveValue('Stale reviewer draft');
 await d.getByRole('button',{name:'Reload saved context',exact:true}).click();await d.getByRole('button',{name:'Reload and discard edits',exact:true}).click();await expect(d.getByLabel('Organization-managed environment',{exact:true})).toHaveValue('Other reviewer');await d.getByRole('button',{name:'Cancel',exact:true}).click();
 check('Stale asset context saves preserve edits and require an application-level reload/discard decision');
 d=await open();await d.getByLabel('Organization-managed environment',{exact:true}).fill('Committed with lost response');await d.getByLabel('Change rationale',{exact:true}).fill('Synthetic response loss');
 let intercepted=0;const pattern='**/api/v1'+endpoint;
 await p.route(pattern,async route=>{if(route.request().method()==='PATCH'){intercepted++;const response=await route.fetch();assert.equal(response.status(),200);await route.abort('failed');}else await route.continue();});
 try{await d.getByRole('button',{name:'Save context',exact:true}).click();await expect(d.getByRole('alert')).toContainText('Outcome unknown');await d.getByRole('button',{name:'Close and refresh',exact:true}).click();await expect(d).not.toBeVisible();}finally{await p.unroute(pattern);}
 assert.equal(intercepted,1);saved=(await admin.request(endpoint)).body;assert.equal(saved.version,3);assert.equal(saved.environment,'Committed with lost response');
 const history=(await admin.request(endpoint+'/history')).body;assert.deepEqual(history.map(x=>x.version),[3,2,1]);
 const vd=await open(viewer.page);await expect(vd.getByText('Committed with lost response',{exact:true})).toBeVisible();assert.equal(await vd.getByRole('button',{name:'Save context',exact:true}).count(),0);await vd.getByRole('button',{name:'Show context history',exact:true}).click();await expect(vd.getByText('Rationale: Synthetic response loss',{exact:true})).toBeVisible();await vd.getByRole('button',{name:'Close',exact:true}).click();
 assert.equal((await viewer.request(endpoint,'PATCH',{expected_version:3,environment:'Forbidden',rationale:'Viewer cannot write'})).status,403);
 check('Lost committed response causes explicit refresh without duplicate writes; members can read context/history while viewers cannot edit');
 async function lifecycle(path){const job=await admin.request(path,'POST');assert.ok([200,202].includes(job.status),JSON.stringify(job.body));await expect.poll(async()=>{const row=(await admin.request(org+'/archive-jobs?tracked=true')).body.find(x=>x.id===job.body.id);assert.ok(!row||!['failed','stopped'].includes(row.status),JSON.stringify(row));return row?.status||job.body.status;},{timeout:45000}).toBe('completed');return job.body;}
 await lifecycle(org+'/assets/'+id+'/archive');
 assert.equal((await admin.request(endpoint)).body.asset_archived,true);
 const archived=(await admin.request(org+'/archive?type=asset&q='+encodeURIComponent(name))).body.items;assert.equal(archived.length,1);
 await lifecycle(org+'/archive/'+archived[0].id+'/restore');
 saved=(await admin.request(endpoint)).body;assert.equal(saved.version,3);assert.equal(saved.environment,'Committed with lost response');assert.equal(saved.asset_archived,false);
 check('Asset archive/restore preserves managed context generation and audit history');
};
