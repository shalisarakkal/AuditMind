// Real isolated API + installed Chrome acceptance. Imported by workflow harness.
const assert=require('node:assert/strict');
const {expect}=require('../frontend/node_modules/playwright/test');
const {default:AxeBuilder}=require('../frontend/node_modules/@axe-core/playwright');
module.exports=async function({page:p,admin,viewer,base,org,list,check}) {
  const name='Consolidation browser retest',root=org+'/finding-consolidations';
  await p.goto(base+'/findings');
  const tool=await admin.request(org+'/identity-tools','POST',{name:'Consolidation acceptance scanner',rationale:'Isolated acceptance'});
  assert.equal(tool.status,201);
  async function imported(host,ip,filename){
    const xml=`<?xml version="1.0"?><NessusClientData_v2><Report name="Group"><ReportHost name="${host}"><HostProperties><tag name="host-ip">${ip}</tag></HostProperties><ReportItem port="443" protocol="tcp" severity="3" pluginID="903211" pluginName="${name}" pluginFamily="General" /></ReportHost></Report></NessusClientData_v2>`;
    const response=await p.request.post(base+'/api/v1'+list+'/import',{headers:{Authorization:admin.authorization()},multipart:{confirm:'true',file:{name:filename,mimeType:'text/xml',buffer:Buffer.from(xml)}}});
    assert.equal(response.status(),201);const scan=(await response.json()).scan_id;
    const rows=(await admin.request(list+'?q='+encodeURIComponent(name))).body.items;
    const finding=rows.find(row=>row.scan_id===scan);assert.ok(finding);
    const observation=(await admin.request(list+`/${finding.id}/observations`)).body[0];
    return {finding,observation,scan};
  }
  const first=await imported('consolidation-browser-source','10.77.20.1','consolidation-source.nessus');
  const second=await imported('consolidation-browser-alias','10.77.20.2','consolidation-alias.nessus');
  for(const item of [first,second]){
    const bound=await admin.request(list+`/${item.finding.id}/observations/${item.observation.id}/identity-binding`,'PUT',{
      expected_version:0,tool_id:tool.body.id,expected_tool_version:1,canonical_asset_id:first.finding.asset_id,
      confirm_mapping:true,rationale:'Independently reviewed scanner and canonical asset'});
    assert.equal(bound.status,200,JSON.stringify(bound.body));
  }
  const canonicalPath=list+`/${second.finding.id}/observations/${second.observation.id}/identity-binding/canonical`;
  const preview=(await admin.request(canonicalPath+'/preview','POST',{source_observation_id:first.observation.id})).body;
  const selected=await admin.request(canonicalPath,'POST',{source_observation_id:first.observation.id,
    expected_version:preview.expected_version,review_token:preview.review_token,canonical_finding_id:first.finding.id,
    confirm_histories:true,rationale:'Reviewed both independent histories for consolidation'});
  assert.equal(selected.status,200,JSON.stringify(selected.body));
  const before=(await admin.request(list)).body.total;
  assert.equal((await admin.request(root+'/settings')).body.enabled,false);
  await p.goto(base+'/settings');
  const settings=p.getByRole('region',{name:'Reviewed finding consolidation',exact:true});
  await settings.getByLabel('Allow reviewed native pair consolidation',{exact:true}).check();
  await settings.getByRole('button',{name:'Save consolidation setting',exact:true}).click();
  await expect.poll(async()=>(await admin.request(root+'/settings')).body.enabled).toBe(true);
  check('Consolidation has a separate default-off organization opt-in and real admin setting');
  const workflow=()=>p.getByRole('dialog',{name:'Finding workflow',exact:true});
  async function open(){await p.goto(base+`/findings/lookup?org=${org.split('/').at(-1)}&finding_id=${first.finding.id}`);
    await p.getByRole('row').filter({has:p.getByText(name,{exact:true})}).getByRole('button',{name:'Workflow',exact:true}).click();
    await expect(workflow().getByText('Current status',{exact:true})).toBeVisible();}
  await open();await workflow().getByRole('button',{name:'Show consolidation review',exact:true}).click();
  await workflow().getByLabel('Rationale or note',{exact:true}).fill('Preserve an unsaved workflow draft');
  await expect(workflow().getByRole('button',{name:`Preview consolidation for ${first.finding.id}`,exact:true})).toBeDisabled();
  await workflow().getByLabel('Rationale or note',{exact:true}).fill('');
  await workflow().getByRole('button',{name:`Preview consolidation for ${first.finding.id}`,exact:true}).click();
  const apply=()=>p.getByRole('dialog',{name:'Consolidate reviewed pair',exact:true});
  await expect(apply().getByRole('button',{name:'Cancel',exact:true})).toBeFocused();
  await expect(apply().getByRole('button',{name:'Consolidate pair',exact:true})).toBeDisabled();
  for(const width of [320,1440]){await p.setViewportSize({width,height:1000});assert.ok(await apply().evaluate(node=>node.scrollWidth<=node.clientWidth));}
  const axe=await new AxeBuilder({page:p}).include('dialog[open]').withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
  assert.deepEqual(axe.violations.map(row=>row.id),[]);
  await apply().getByLabel('Review rationale',{exact:true}).fill('Review both native members and source ownership');await apply().getByRole('checkbox').check();
  const bodies=[];
  await p.route('**/finding-consolidations/apply',async route=>{bodies.push(route.request().postData());
    if(bodies.length===1){await new Promise(resolve=>setTimeout(resolve,350));await route.fetch();await route.abort('failed');}
    else await route.continue();});
  await apply().getByRole('button',{name:'Consolidate pair',exact:true}).click();
  await expect(apply().getByRole('button',{name:'Cancel',exact:true})).toBeDisabled();
  await p.keyboard.press('Escape');await expect(apply()).toBeVisible();
  await expect(apply().getByText(/Outcome unknown/)).toBeVisible();
  assert.equal((await admin.request(list)).body.total,before-1);
  await apply().getByRole('button',{name:'Retry same request',exact:true}).click();await expect(workflow()).toHaveCount(0);
  assert.equal(bodies.length,2);assert.equal(bodies[0],bodies[1]);await p.unroute('**/finding-consolidations/apply');
  const group=(await admin.request(root+`/for-finding/${first.finding.id}`)).body.items[0];
  assert.equal(group.version,1);assert.equal(group.published,true);
  assert.equal((await admin.request(root+`/${group.id}/history`)).body.items.length,1);
  assert.equal((await admin.request(list+`/${second.finding.id}/workflow`,'PATCH',{expected_version:0,rationale:'Forbidden alias edit'})).status,404);
  const blocked=await admin.request(org+`/scans/${second.scan}/archive`,'POST');assert.equal(blocked.status,409);
  const viewerData=await viewer.request(root+`/for-finding/${first.finding.id}`);assert.equal(viewerData.status,200);
  const unauthorized=await viewer.request(root+`/${group.id}/undo-preview`,'POST',{});assert.equal(unauthorized.status,403);
  check('Real Chrome apply freezes targets, passes mobile/Axe, retries a lost committed response once, and blocks alias/source mutations');
  await open();await workflow().getByRole('button',{name:'Show consolidation review',exact:true}).click();
  await workflow().getByText(`Retained member source and workflow history: ${second.finding.id}`,{exact:true}).click();
  await expect(workflow().getByText('Read-only retained source record. Group review does not transfer its workflow or notes.',{exact:true})).toBeVisible();
  await workflow().getByRole('button',{name:'Close finding workflow',exact:true}).click();
  const resolved=await admin.request(list+`/${first.finding.id}/workflow`,'PATCH',{expected_version:0,status:'resolved',rationale:'Both members retested',verification:'Both native sources reviewed'});assert.equal(resolved.status,200);
  const proof=list+`/${first.finding.id}/risk-verification`,instant=Date.now();
  assert.equal((await admin.request(proof,'POST',{expected_version:0,expected_workflow_version:1,source_reference:'https://evidence.example/group-retest',observed_at:new Date(instant-3600000).toISOString(),note:'Retest both retained members'})).status,200);
  const approved=await admin.request(proof+'/review','POST',{expected_version:1,expected_workflow_version:1,decision:'approved',expires_at:new Date(instant+86400000).toISOString(),note:'Reviewed both source sets',evidence_reviewed:true,self_review_acknowledged:true});
  assert.equal(approved.status,200,JSON.stringify(approved.body));assert.equal(approved.body.eligible_for_exclusion,true);
  await open();await workflow().getByText('Scoring evidence review',{exact:true}).click();
  await expect(workflow().getByText(/This evidence review covers the entire consolidated pair/)).toBeVisible();
  await workflow().getByRole('button',{name:'Show consolidation review',exact:true}).click();
  await workflow().getByRole('button',{name:'Preview undo consolidation',exact:true}).click();
  const undo=()=>p.getByRole('dialog',{name:'Undo finding consolidation',exact:true});
  await expect(undo().getByRole('alert')).toContainText('revoke approved');await undo().getByRole('button',{name:'Cancel',exact:true}).click();
  await workflow().getByLabel('Action',{exact:true}).selectOption('review');
  await workflow().getByLabel('Review rationale',{exact:true}).fill('Explicitly revoke group approval before undo');
  await workflow().getByRole('button',{name:'Save evidence decision',exact:true}).click();
  await expect.poll(async()=>(await admin.request(proof)).body.state).toBe('revoked');
  await workflow().getByRole('button',{name:'Preview undo consolidation',exact:true}).click();
  await undo().getByLabel('Review rationale',{exact:true}).fill('Preserve this stale undo draft');await undo().getByRole('checkbox').check();
  assert.equal((await admin.request(list+`/${first.finding.id}/workflow`,'PATCH',{expected_version:1,rationale:'Concurrent canonical note'})).status,200);
  await undo().getByRole('button',{name:'Undo consolidation',exact:true}).click();await expect(undo().getByRole('alert')).toContainText('changed');
  await undo().getByRole('button',{name:'Reload and review current targets',exact:true}).click();
  await expect(undo().getByLabel('Review rationale',{exact:true})).toHaveValue('Preserve this stale undo draft');await undo().getByRole('checkbox').check();
  await undo().getByRole('button',{name:'Undo consolidation',exact:true}).click();await expect(workflow()).toHaveCount(0);
  assert.equal((await admin.request(list)).body.total,before);
  assert.equal((await admin.request(list+`/${first.finding.id}/workflow`)).body.status,'resolved');
  assert.equal((await admin.request(list+`/${second.finding.id}/workflow`)).body.status,'open');
  check('Group evidence scope is visible; undo requires explicit revocation, fences stale previews, retains draft and preserves both workflows');
  const policy=(await admin.request(root+'/settings')).body;
  assert.equal((await admin.request(root+'/settings','PATCH',{expected_version:policy.version,enabled:false})).status,200);
};
