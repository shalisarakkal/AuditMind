// Read-only publication UI acceptance on real native sources; no publication writer.
const assert=require('node:assert/strict');
const {expect}=require('../frontend/node_modules/playwright/test');
const {default:AxeBuilder}=require('../frontend/node_modules/@axe-core/playwright');
module.exports=async function({page:p,admin,viewer,base,org,list,check}) {
  const name='Read-only publication source example';
  const tool=await admin.request(org+'/identity-tools','POST',{name:'Read-only provenance scanner',rationale:'Isolated provenance acceptance'});assert.equal(tool.status,201);
  async function imported(severity,filename) {
    const xml=`<?xml version="1.0"?><NessusClientData_v2><Report name="Read only"><ReportHost name="publication-browser-source"><HostProperties><tag name="host-ip">10.77.31.1</tag></HostProperties><ReportItem port="443" protocol="tcp" severity="${severity}" pluginID="993177" pluginName="${name}" pluginFamily="General"><description>Read-only native source ${severity}</description></ReportItem></ReportHost></Report></NessusClientData_v2>`;
    const response=await p.request.post(base+'/api/v1'+list+'/import',{headers:{Authorization:admin.authorization()},multipart:{confirm:'true',file:{name:filename,mimeType:'text/xml',buffer:Buffer.from(xml)}}});
    assert.equal(response.status(),201);return (await response.json()).scan_id;
  }
  const first=await imported(2,'publication-browser-original.nessus');await imported(4,'publication-browser-later.nessus');
  const target=(await admin.request(list+'?q='+encodeURIComponent(name))).body.items.find(row=>row.scan_id===first);assert.ok(target);
  const observations=(await admin.request(list+`/${target.id}/observations`)).body;assert.equal(observations.length,2);
  const selected=observations[0];
  assert.equal((await admin.request(list+`/${target.id}/observations/${selected.id}/identity-binding`,'PUT',{expected_version:0,tool_id:tool.body.id,expected_tool_version:1,canonical_asset_id:target.asset_id,confirm_mapping:true,rationale:'Reviewed same scanner and host'})).status,200);
  const beforeWorkflow=(await admin.request(list+`/${target.id}/workflow`)).body;
  await p.goto(base+`/findings/lookup?org=${org.split('/').at(-1)}&finding_id=${target.id}`);
  await p.getByRole('row').filter({has:p.getByText(name,{exact:true})}).getByRole('button',{name:'Workflow',exact:true}).click();
  const dialog=p.getByRole('dialog',{name:'Finding workflow',exact:true});
  await dialog.getByRole('button',{name:'Show publication history',exact:true}).click();
  await expect(dialog.getByText('No publication recorded',{exact:true})).toBeVisible();
  await dialog.getByRole('button',{name:'Show source observations',exact:true}).click();
  const row=dialog.getByRole('listitem').filter({hasText:'publication-browser-later.nessus'});
  await row.getByRole('button',{name:'Preview scanner-field differences',exact:true}).click();
  const preview=row.getByRole('region',{name:'Read-only scanner-field preview',exact:true});
  await expect(preview.getByText('Critical',{exact:true})).toBeVisible();await expect(preview.getByText('Medium',{exact:true})).toBeVisible();
  await expect(preview.getByText('Original owner import: publication-browser-original.nessus',{exact:true})).toBeVisible();
  await expect(preview.getByText(/This preview cannot authorize Publish or Undo/)).toBeVisible();
  assert.equal(await preview.getByRole('button',{name:/^(Publish|Undo|Apply)$/}).count(),0);
  for(const width of [320,1440]) {await p.setViewportSize({width,height:1000});assert.ok(await dialog.evaluate(node=>node.scrollWidth<=node.clientWidth));}
  const axe=await new AxeBuilder({page:p}).include('dialog[open]').withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();assert.deepEqual(axe.violations.map(row=>row.id),[]);
  await preview.getByRole('button',{name:'Close preview',exact:true}).click();await expect(preview.getByText('Critical',{exact:true})).toHaveCount(0);
  await dialog.getByRole('button',{name:'Close finding workflow',exact:true}).click();
  assert.deepEqual((await admin.request(list+`/${target.id}/workflow`)).body,beforeWorkflow);
  const after=(await admin.request(list+'?q='+encodeURIComponent(name))).body.items.find(row=>row.id===target.id);assert.equal(after.severity,'medium');
  assert.equal((await admin.request(list+`/${target.id}/publication-status`)).body.status,'not_published');
  assert.equal((await viewer.request(list+`/${target.id}/publication-status`)).status,200);
  assert.equal((await viewer.request(list+`/${target.id}/observations/${selected.id}/publication-preview`,'POST',{})).status,403);
  check('Read-only publication history and real native differences preserve scanner/workflow fields, expose no writer, enforce roles and pass mobile/Axe');
};
