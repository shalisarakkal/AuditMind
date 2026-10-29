// Real API + two-slot pool, isolated local schema, small files, no providers.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn,execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const python=process.env.AUDITMIND_BROWSER_PYTHON||path.join(root,process.platform==='win32'?'backend/.venv/Scripts/python.exe':'backend/.venv/bin/python');
const fixture=path.join(root,'backend/scripts/phase3_browser_fixture.py');
const schema='phase3_browser_'+require('node:crypto').randomBytes(6).toString('hex');
const output=path.join(root,'temp/testing/worker-pool',schema);
const folder=path.join(root,'temp',schema);
const base='http://127.0.0.1:8012/api/v1';
const children=[];
const evidence={schema,checks:[],externalInference:false};
const cli=action=>execFileSync(python,[fixture,action,'--schema',schema,'--workflow','--pool'],{cwd:path.join(root,'backend'),windowsHide:true,encoding:'utf8'});
function start(action,name=action){
  const log=fs.openSync(path.join(output,name+'.log'),'w');
  const child=spawn(python,[fixture,action,'--schema',schema,'--workflow','--pool'],{cwd:path.join(root,'backend'),env:process.env,
    windowsHide:true,detached:process.platform!=='win32',stdio:['ignore',log,log]});
  fs.closeSync(log);children.push(child);return child;
}
function stop(child){
  if(!child.pid||child.exitCode!==null)return;
  if(process.platform==='win32')execFileSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
  else process.kill(-child.pid,'SIGTERM');
}
async function until(check,message,timeout=25000){
  const end=Date.now()+timeout;
  while(Date.now()<end){try{if(await check())return;}catch{}await new Promise(r=>setTimeout(r,100));}
  throw new Error(message);
}
function pass(message){evidence.checks.push(message);console.log('PASS '+message);}
(async()=>{
  let prepared=false;
  fs.mkdirSync(output,{recursive:true});
  try{
    await new Promise((resolve,reject)=>{const server=require('node:net').createServer();server.once('error',reject);server.listen(8012,'127.0.0.1',()=>server.close(resolve));});
    const seed=JSON.parse(cli('prepare'));prepared=true;
    start('api');
    await until(async()=> (await fetch(base+'/auth/options')).status===200,'Isolated API did not start');
    const login=await fetch(base+'/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'admin@phase3.example',password:seed.password})});
    assert.equal(login.status,200);
    const token=(await login.json()).access_token;
    async function request(endpoint,init={}){
      const response=await fetch(base+endpoint,{...init,headers:{...init.headers,Authorization:'Bearer '+token}});
      assert(response.ok,`Unexpected HTTP ${response.status} for ${endpoint}`);
      return response.json();
    }
    async function enqueue(org,name,environment){
      const data=new FormData();
      data.append('file',new Blob([`type,hostname,environment\nserver,pool-shared-host,${environment}\n`],{type:'text/csv'}),name+'.csv');
      const result=await request(`/orgs/${org}/assets/import`,{method:'POST',body:data});
      assert.equal(result.status,'pending');return result.scan_id;
    }
    const a1=await enqueue(seed.org,'pool-a-first','production');
    const a2=await enqueue(seed.org,'pool-a-next','staging');
    const b1=await enqueue(seed.other_org,'pool-b-first','production');
    const status=(org,id)=>request(`/orgs/${org}/scans/${id}`);
    let worker=start('worker');
    const probe=()=>JSON.parse(fs.readFileSync(path.join(folder,'pool-probe.json'),'utf8'));
    await until(()=>probe().orgs.length===2,'Pool did not execute two publishers concurrently');
    const initialProbe=probe();
    assert.deepEqual([...initialProbe.orgs].sort(),[seed.org,seed.other_org].sort());
    assert.equal((await status(seed.org,a1)).status,'running');
    assert.equal((await status(seed.other_org,b1)).status,'running');
    assert.equal((await status(seed.org,a2)).status,'pending');
    pass('Actual two-slot CLI pool runs different organizations concurrently and leaves same-organization backlog queued');
    const duplicate=start('worker','duplicate-worker');
    await until(()=>duplicate.exitCode!==null,'Duplicate installation worker did not exit',8000);
    assert.notEqual(duplicate.exitCode,0);
    pass('Duplicate healthy installation pool is refused without admitting extra jobs');
    stop(worker);
    cli('expire-pool-jobs'); // simulate elapsed stale time only in the guarded test schema
    worker=start('worker','recovered-worker');
    await until(()=>probe().run!==initialProbe.run&&probe().orgs.length===2,'Restarted pool did not recover both interrupted jobs');
    assert.equal((await status(seed.org,a2)).status,'pending');
    const recovering=JSON.parse(cli('inspect')).pool_scans;
    assert.equal(recovering.find(s=>s.filename==='pool-a-first.csv').retry_count,1);
    assert.equal(recovering.find(s=>s.filename==='pool-b-first.csv').retry_count,1);
    pass('Killed pool releases leadership/job locks; stale recovery resumes both imports once without admitting same-org backlog');
    fs.writeFileSync(path.join(folder,'pool-release.flag'),'release');
    await until(async()=>{
      const states=await Promise.all([status(seed.org,a1),status(seed.org,a2),status(seed.other_org,b1)]);
      return states.every(scan=>scan.status==='completed');
    },'Recovered pool did not complete its three small imports');
    const [alpha,beta,next]=await Promise.all([request(`/orgs/${seed.org}/assets?q=pool-shared-host`),request(`/orgs/${seed.other_org}/assets?q=pool-shared-host`),status(seed.org,a2)]);
    assert.equal(alpha.total,1);assert.equal(beta.total,1);
    assert.equal(alpha.items[0].environment,'staging');assert.equal(beta.items[0].environment,'production');
    assert.notEqual(alpha.items[0].id,beta.items[0].id);assert.equal(next.summary.updated,1);
    pass('Recovery and later same-org import preserve one asset per tenant, distinct identities and final update values');
    assert.equal(JSON.parse(cli('inspect')).usage_count,0);
    pass('No AI usage; only tiny isolated synthetic CSVs processed');
  }catch(error){evidence.failure=error.message;throw error;}
  finally{
    for(const child of children)try{stop(child);}catch{}
    if(prepared){cli('cleanup');evidence.fixtureRemoved=true;}
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(evidence,null,2));
    console.log(`${evidence.checks.length} checks; artifacts: ${output}`);
  }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
