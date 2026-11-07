// Real Chrome, intercepted synthetic data only; no credentials or database writes.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium, expect} = require('../frontend/node_modules/playwright/test');
const AxeBuilder = require('../frontend/node_modules/@axe-core/playwright').default;
const base = process.env.AUDITMIND_DASHBOARD_BASE_URL || 'http://localhost:3000';
if (!/^http:\/\/(localhost|127\.0\.0\.1):\d+$/.test(base)) throw new Error('Dashboard presentation checks require a local server');

(async () => {
  const browser = await chromium.launch({...(process.env.AUDITMIND_BROWSER_CHANNEL==='chromium'?{}:{channel:'chrome'}), headless:true});
  const output = path.resolve(__dirname, '../temp/testing/dashboard-tabs');
  await fs.mkdir(output, {recursive:true});
  const result = {checks:[], data:'intercepted synthetic API fixtures; no real writes'};
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    let enabled = true, reads = 0;
    const mutations = [], errors = [];
    const domains = ['identity_access','network_config','vulnerability_management','backup_recovery','monitoring_detection','incident_response','compliance_alignment'];
    await context.route('**/api/v1/**', async route => {
      const request = route.request(), endpoint = new URL(request.url()).pathname.replace('/api/v1','');
      const send = body => route.fulfill({json:body});
      if (endpoint === '/auth/refresh') return send({access_token:'fixture',must_change_password:false});
      if (request.method() !== 'GET') { mutations.push(endpoint); return route.fulfill({status:400,json:{detail:'Unexpected write'}}); }
      if (endpoint === '/auth/me') return send({id:'fixture',name:'Synthetic reviewer',email:'fixture@example.com',is_sysadmin:false,must_change_password:false});
      if (endpoint === '/orgs') return send([{id:'fixture-org',name:'Synthetic organization',role:'viewer',archived:false}]);
      if (endpoint === '/worker-status') return send({running:true});
      if (/\/(scans|archive-jobs)$/.test(endpoint)) return send([]);
      if (endpoint.endsWith('/scoring/dashboard-state')) return send({scoring_mode:enabled?'evidence_qualified':'findings_based',settings_version:0,evidence_revision:0,evaluation_id:null});
      if (endpoint.endsWith('/dashboard/security-summary')) return send({window_start:'2026-11-01T00:00:00Z',window_end:'2026-11-06T00:00:00Z',counts:{member_added:0,role_changed:0,purge:0}});
      if (endpoint.endsWith('/dashboard')) {
        reads++;
        return send({overall_score:enabled?null:15,overall_tier:enabled?null:'critical',
          scoring_mode:enabled?'evidence_qualified':'findings_based',settings_version:0,evidence_revision:0,evaluation_id:null,
          evaluation_state:'not_current',qualified_domain_count:0,snapshot_generated_at:'2026-11-06T12:00:00Z',
          domains:domains.map(domain=>({domain,score:null,tier:null,justification:'Current evidence required',evidence_status:'limited',evidence_reason:'evaluation_required'})),
          findings_baseline:{overall_score:15,overall_tier:'critical',method:'rule-v1',domains:domains.map(domain=>({domain,score:0,tier:'critical',justification:'Synthetic recorded risk'}))},
          asset_count:100,findings_by_severity:{critical:10,high:20,medium:30,low:40},
          status_scoring:{enabled:true,current_risk_findings:100,excluded_findings:0,recorded_findings:100},
          top_findings:[{id:'fixture-finding',domain:'network_config',severity:'critical',description:'Synthetic critical issue'}],
          recent_scans:[{id:'fixture-scan',filename:'synthetic.csv',scan_type:'generic_findings',status:'completed',started_at:'2026-11-06T12:00:00Z'}]});
      }
      return route.fulfill({status:404,json:{detail:'Optional fixture resource unavailable'}});
    });
    const page = await context.newPage();
    page.on('pageerror', error=>errors.push(error.message));
    await page.goto(base+'/');
    const findings = page.getByRole('tab',{name:'Findings-based',exact:true});
    const evidence = page.getByRole('tab',{name:'Evidence-based',exact:true});
    await expect(findings).toHaveAttribute('aria-selected','true');
    await expect(page.getByText('All times are displayed in your browser time zone.',{exact:true})).toHaveCount(0);
    await expect(page.getByTestId('overall-score')).toHaveText('15');
    const inventory = await page.getByRole('region',{name:'Inventory and finding risk',exact:true}).textContent();
    const initialReads = reads;
    await findings.focus(); await page.keyboard.press('ArrowRight');
    await expect(evidence).toBeFocused(); await expect(evidence).toHaveAttribute('aria-selected','true');
    await expect(page.getByRole('region',{name:'Inventory and finding risk',exact:true})).toHaveText(inventory);
    await expect(page.getByRole('region',{name:'Evidence-qualified assessment'})).toContainText('Not assessed');
    await expect(page.getByRole('heading',{name:'Top issues',exact:true})).toBeVisible();
    await expect(page.getByText('Synthetic critical issue',{exact:true})).toBeVisible();
    await expect(page.getByText('Known finding risks, independent of evidence qualification.',{exact:true})).toBeVisible();
    assert.equal(reads,initialReads);
    result.checks.push('Default Findings-based, keyboard activation, separately gated evidence scores; tab switch does not reload or mutate');
    await page.getByRole('button',{name:'Refresh dashboard',exact:true}).click();
    await expect.poll(()=>reads).toBe(initialReads+1);
    await expect(evidence).toHaveAttribute('aria-selected','true');
    const tileSizes = {};
    for (const width of [320,1440]) {
      await page.setViewportSize({width,height:width===1440?900:1000});
      for (const tab of [findings,evidence]) {
        await tab.click();
        if (width === 1440 && await tab.textContent() === 'Findings-based') {
          await page.evaluate(()=>window.scrollTo(0,0));
          const header = await page.getByRole('heading',{name:'Resilience dashboard',exact:true}).locator('../..').boundingBox();
          assert(header.height<=64,'Dashboard title, timestamp and refresh should share a compact desktop row');
          const domainCards = page.getByTitle('Synthetic recorded risk',{exact:true});
          await expect(domainCards).toHaveCount(7);
          for (const card of await domainCards.all()) await expect(card).toBeInViewport({ratio:1});
        }
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
        if (width === 1440) {
          const activeView = await tab.textContent();
          const inventoryTile = await page.getByRole('region',{name:'Inventory and finding risk',exact:true}).boundingBox();
          const scoreTile = await (activeView === 'Findings-based' ? page.getByTestId('overall-score').locator('..') : page.getByRole('region',{name:'Evidence-qualified assessment',exact:true})).boundingBox();
          assert(Math.abs(inventoryTile.width-scoreTile.width)<1 && Math.abs(inventoryTile.height-scoreTile.height)<1,'Paired summary tiles must have matching dimensions');
          tileSizes[activeView] = inventoryTile;
          const issues = page.getByRole('heading',{name:'Top issues',exact:true});
          const uploads = page.getByRole('heading',{name:'Recent uploads',exact:true});
          const headings = await Promise.all([issues.boundingBox(),uploads.boundingBox()]);
          const lists = await Promise.all([issues.locator('..').getByRole('list').boundingBox(),uploads.locator('..').getByRole('list').boundingBox()]);
          assert(Math.abs(headings[0].y-headings[1].y)<1,'Shared headings must align');
          assert(Math.abs(lists[0].y-lists[1].y)<1,'Shared lists must align in both tabs');
        }
        const audit = await new AxeBuilder({page}).include('main').withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
        assert.deepEqual(audit.violations.map(item=>({id:item.id,nodes:item.nodes.map(node=>node.html)})),[]);
        await page.screenshot({path:path.join(output,`${width}-${await tab.textContent()}.png`),fullPage:true});
      }
    }
    assert(Math.abs(tileSizes['Findings-based'].width-tileSizes['Evidence-based'].width)<1 && Math.abs(tileSizes['Findings-based'].height-tileSizes['Evidence-based'].height)<1,'Inventory tile dimensions must match across tabs');
    result.checks.push('Refresh preserves selected tab; shared headings and list tops align in both views; all baseline domain cards fit desktop without scrolling; both views pass mobile/desktop Axe AA');
    enabled=false; await page.reload(); await evidence.click();
    await expect(page.getByRole('heading',{name:'Evidence-based assessment is disabled'})).toBeVisible();
    await expect(page.getByRole('region',{name:'Inventory and finding risk',exact:true})).toHaveText(inventory);
    await expect(page.getByRole('link',{name:'Open Settings',exact:true})).toBeVisible();
    assert.deepEqual(mutations,[]); assert.deepEqual(errors,[]);
    result.checks.push('Disabled evidence mode explains admin enablement; no organization writes or page errors');
    await fs.writeFile(path.join(output,'results.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify(result,null,2));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
