// Opens a local HTML with offline networking. No Python, HTTP server or live data.
import {chromium,expect} from '@playwright/test';
import {readFile,mkdtemp,rm,mkdir,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const scratch=await mkdtemp(join(tmpdir(),'observatory-offline-'));
const browser=await chromium.launch({...(process.env.OBSERVATORY_BROWSER?{executablePath:process.env.OBSERVATORY_BROWSER}:{}),headless:true});
try{
  const context=await browser.newContext({offline:true,acceptDownloads:true,viewport:{width:1440,height:1000}});
  const requests=[],errors=[];
  context.on('request',request=>{if(/^https?:/.test(request.url()))requests.push(request.url());});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text().slice(0,300));});
  page.on('dialog',d=>d.accept());
  const open=async()=>{await page.goto(pathToFileURL(join(root,'dist/session-observatory-browser.html')).href);await expect(page.getByRole('heading',{name:'Sources & privacy'})).toBeVisible({timeout:60000});};
  await open();
  const call=(path,data)=>page.evaluate(([p,d])=>ObservatoryBrowser.api(p,d),[path,data]);
  expect((await call('/api/state')).events).toBe(0);
  await page.getByRole('button',{name:'Try fictional demo'}).click();
  await expect.poll(async()=>(await call('/api/state')).events).toBe(72);
  expect((await call('/api/evidence-export')).integrity.valid).toBe(true);
  await page.locator('[data-nav="costs"]').click();
  await expect(page.getByRole('heading',{name:'Current model mix'})).toBeVisible();
  await expect(page.locator('[data-cost-total="baseline"]')).toHaveText('$29.40');
  await page.locator('[data-cost-preset="double"]').click();
  await expect(page.locator('[data-cost-total="scenario"]')).toHaveText('$58.79');
  await page.locator('.cost-saved summary').click();
  await page.locator('#cost-scenario-name').fill('Double workload');
  await page.getByRole('button',{name:'Save assumptions',exact:true}).click();
  expect(await page.evaluate(()=>localStorage.length)).toBe(0);
  expect(await page.evaluate(()=>savedCosts().length)).toBe(1);
  for(const route of ['ledger','analysis','limits','projects','provider','activity','alerts','coverage']){
    await page.locator(`[data-nav="${route}"]`).click();
    await expect(page.locator(`[data-nav="${route}"]`)).toHaveAttribute('aria-current','page');
    await expect(page.locator('#main h1')).toBeVisible();
  }
  await page.reload();await expect(page.getByRole('heading',{name:'Sources & privacy'})).toBeVisible({timeout:60000});
  expect((await call('/api/state')).events).toBe(0); // Default is memory only.
  expect(await page.evaluate(()=>savedCosts().length)).toBe(0);
  await page.getByRole('button',{name:'Try fictional demo'}).click();
  await expect.poll(async()=>(await call('/api/state')).events).toBe(72);
  const evidence=await call('/api/evidence-export');
  await page.locator('#browser-save').first().click();
  await expect(page.locator('#live-state')).toHaveText('Saved in this browser');
  await page.reload();await expect(page.getByRole('heading',{name:'Sources & privacy'})).toBeVisible({timeout:60000});
  expect((await call('/api/state')).events).toBe(72);
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download complete backup'}).click();
  const backup=await download;await backup.saveAs(join(scratch,'backup.json'));
  const restored=JSON.parse(await readFile(join(scratch,'backup.json'),'utf8'));
  expect(restored.tables.events).toEqual(evidence.tables.events);
  await page.getByRole('button',{name:'Forget this workspace'}).click();
  await expect.poll(async()=>(await call('/api/state')).events).toBe(0);
  await page.reload();await expect(page.getByRole('heading',{name:'Sources & privacy'})).toBeVisible({timeout:60000});
  expect((await call('/api/state')).events).toBe(0);
  await page.locator('#browser-restore').setInputFiles(join(scratch,'backup.json'));
  await expect.poll(async()=>(await call('/api/state')).events).toBe(72);
  expect((await call('/api/evidence-export')).integrity).toEqual(evidence.integrity);
  // Save conflicts must preserve the newer tab's copy, even after deletion.
  await page.locator('#browser-save').click();
  await expect(page.locator('#live-state')).toHaveText('Saved in this browser');
  const second=await context.newPage();second.on('dialog',d=>d.accept());
  await second.goto(page.url());await expect(second.getByRole('heading',{name:'Sources & privacy'})).toBeVisible({timeout:60000});
  await page.getByRole('button',{name:'Forget this workspace'}).click();
  await expect.poll(async()=>(await call('/api/state')).events).toBe(0);
  await second.locator('#browser-save').click();
  await expect(second.locator('#toast')).toContainText('Another tab changed');
  await second.close();

  // Import a folder containing valid logs, a copied log, unrelated and secret files.
  const selected=join(scratch,'codex-sessions');await mkdir(selected);
  const stamp=new Date().toISOString();
  const line=(type,payload)=>JSON.stringify({type,timestamp:stamp,payload})+'\n';
  const log=line('session_meta',{id:'offline-task',cwd:'/demo/browser-project',originator:'Test CLI',model_provider:'openai'})+
    line('turn_context',{model:'gpt-5.6-sol'})+
    line('event_msg',{type:'token_count',info:null,rate_limits:{plan_type:'pro',limit_id:'codex',primary:{used_percent:49,window_minutes:300,resets_at:Math.floor(Date.now()/1000)+3600},secondary:null}})+
    line('token_usage_record',{response_id:'offline-response',usage:{input_tokens:100000,cached_input_tokens:50000,cache_write_input_tokens:0,output_tokens:10000,reasoning_output_tokens:5000}})+
    line('event_msg',{type:'user_message',message:'PRIVATE_PROMPT_SENTINEL'});
  await writeFile(join(selected,'rollout.jsonl'),log);await writeFile(join(selected,'copy.jsonl'),log);
  await writeFile(join(selected,'auth.jsonl'),log.replaceAll('offline-response','NEVER_IMPORT_SECRET'));
  await writeFile(join(selected,'config.json'),'PRIVATE_CONFIG_SENTINEL');
  await writeFile(join(selected,'invalid.jsonl'),'not json');
  await page.locator('#browser-folder').setInputFiles(selected);
  await expect(page.locator('#browser-import-result')).toContainText('2 files imported');
  await expect(page.locator('#browser-import-result')).toContainText('2 other files skipped · 1 logs not imported');
  expect((await call('/api/state')).events).toBe(1);
  const folderEvidence=await call('/api/evidence-export');
  expect(folderEvidence.tables.events[0].actor).toBe('');expect(folderEvidence.tables.events[0].device).toBe('');
  expect(folderEvidence.tables.observations.some(o=>o.source.endsWith('/codex-sessions/rollout.jsonl'))).toBe(true);
  expect(JSON.stringify(folderEvidence)).not.toContain('PRIVATE_PROMPT_SENTINEL');
  expect(JSON.stringify(folderEvidence)).not.toContain('PRIVATE_CONFIG_SENTINEL');
  expect(JSON.stringify(folderEvidence)).not.toContain('NEVER_IMPORT_SECRET');
  expect(folderEvidence.tables.limit_snapshots.length).toBeGreaterThan(0);
  await page.locator('#browser-folder').setInputFiles(selected);
  await expect(page.locator('#browser-import-result')).toContainText('0 new entries');
  expect((await call('/api/state')).events).toBe(1);
  await page.locator('[data-nav="ledger"]').click();
  await expect(page.locator('[data-event]')).toHaveCount(1);
  await page.locator('[data-event]').click();
  await page.getByText('Declare owner, project and purpose',{exact:true}).click();
  await page.locator('#attribute-form [name="principal"]').fill('Demo owner');
  await page.locator('#attribute-form [name="purpose"]').fill('<img src=x onerror=alert(1)> review');
  await page.locator('#attribute-form [name="reason"]').fill('Verify offline attribution');
  await page.getByRole('button',{name:'Save attribution',exact:true}).click();
  await expect(page.locator('#detail-content')).toContainText('Demo owner (declared attribution)');
  await expect(page.locator('#detail-content img')).toHaveCount(0);
  await page.getByRole('button',{name:'Close record'}).click();
  const csv=page.waitForEvent('download');await page.getByRole('link',{name:'Export CSV',exact:true}).click();
  expect((await csv).suggestedFilename()).toBe('observatory-ledger.csv');
  await page.locator('[data-nav="costs"]').click();
  // Previous what-if is still a UI choice; the current baseline remains exact.
  await expect(page.locator('[data-cost-total="baseline"]')).toHaveText('$0.42');
  await mkdir(join(root,'test-results'),{recursive:true});
  await page.screenshot({path:join(root,'test-results/browser-only-costs.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:join(root,'test-results/browser-only-mobile.png'),fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('[data-nav="coverage"]').click();
  await page.screenshot({path:join(root,'test-results/browser-only-privacy.png'),fullPage:true});
  // Invalid restore is atomic, including attempts to introduce a schema table.
  const before=await call('/api/evidence-export');
  const broken=structuredClone(before);broken.tables.audit[0].reason='tampered';
  const invalid=await page.evaluate(async value=>{try{await ObservatoryBrowser.api('/browser/restore',value);return false;}catch{return true;}},broken);
  expect(invalid).toBe(true);expect((await call('/api/evidence-export')).tables).toEqual(before.tables);
  // A realistic metering volume must remain usable in the WebAssembly engine.
  const count=13000;
  const bulk=line('session_meta',{id:'scale-task',cwd:'/demo/scale',model_provider:'openai'})+line('turn_context',{model:'gpt-5.6-sol'})+
    Array.from({length:count},(_,i)=>line('token_usage_record',{response_id:'scale-'+i,usage:{input_tokens:1000,cached_input_tokens:500,cache_write_input_tokens:0,output_tokens:100,reasoning_output_tokens:50}})).join('');
  const start=Date.now();
  await call('/api/import',{name:'scale.jsonl',content:bulk,scope:''});
  const scale=await call('/api/cost-analysis',{filters:{q:'/demo/scale'}});
  expect(scale.records).toBe(count);expect(Number(scale.baseline.total)).toBeCloseTo(54.6,8);
  const largeBackup=await call('/api/evidence-export');
  await call('/browser/restore',largeBackup);
  expect((await call('/api/state')).events).toBe(count+1);
  console.log(`13,000-entry import, pricing and backup restore: ${((Date.now()-start)/1000).toFixed(1)} seconds.`);
  expect(requests).toEqual([]);expect(errors).toEqual([]);
  console.log('Offline browser passed: costs/what-ifs, all routes, folder deduplication/secret skipping, attribution, quotas, CSV, memory-only reload, save/reload, backup, forget, migration, stale-tab save rejection, atomic restore, mobile layout, zero HTTP requests.');
}finally{await browser.close();await rm(scratch,{recursive:true,force:true});}
