// Verify the static web edition without exposing or reading any personal data.
import {chromium,expect} from '@playwright/test';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const app='session-observatory-browser.html';
const allowed=new Set(['index.html',app,app+'.sha256','browser-runtime-manifest.json']);
const server=createServer(async(req,res)=>{
  const name=req.url==='/'?'index.html':req.url.slice(1);
  if(req.method!=='GET'||!allowed.has(name)){res.writeHead(404);res.end();return;}
  try{
    const data=await readFile(join(root,'dist/site',name));
    res.setHeader('Content-Type',name.endsWith('.html')?'text/html; charset=utf-8':'text/plain');
    res.end(data);
  }catch{res.writeHead(404);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
  browser=await chromium.launch({...(process.env.OBSERVATORY_BROWSER?{executablePath:process.env.OBSERVATORY_BROWSER}:{}),headless:true});
  const context=await browser.newContext({acceptDownloads:true});
  const page=await context.newPage(),requests=[],errors=[];
  page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push({url:r.url(),method:r.method()});});
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>d.accept());
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await expect(page.getByRole('heading',{name:'Sources & privacy'})).toBeVisible({timeout:60000});
  await expect(page.getByText('You are using the web edition.',{exact:false})).toBeVisible();
  const initialRequests=requests.length;
  await context.setOffline(true);
  await page.getByRole('button',{name:'Try fictional demo'}).click();
  await expect.poll(()=>page.evaluate(async()=>(await ObservatoryBrowser.api('/api/state')).events)).toBe(72);
  await page.locator('[data-nav="costs"]').click();
  await expect(page.locator('[data-cost-total="baseline"]')).toHaveText('$29.40');
  await page.locator('#browser-save').click();
  await expect(page.locator('#live-state')).toHaveText('Saved in this browser');
  expect(requests.length).toBe(initialRequests);
  await context.setOffline(false);
  await page.reload();
  await expect(page.locator('#live-state')).toHaveText('Saved in this browser',{timeout:60000});
  expect(await page.evaluate(async()=>(await ObservatoryBrowser.api('/api/state')).events)).toBe(72);
  await page.locator('[data-nav="coverage"]').click();
  const [download]=await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link',{name:'Download the offline app'}).click(),
  ]);
  expect(download.suggestedFilename()).toBe(app);
  expect(await readFile(await download.path())).toEqual(await readFile(join(root,'dist',app)));
  await page.getByRole('button',{name:'Forget this workspace'}).click();
  await expect.poll(()=>page.evaluate(async()=>(await ObservatoryBrowser.api('/api/state')).events)).toBe(0);
  expect(requests.every(r=>r.method==='GET')).toBe(true);
  expect(errors).toEqual([]);
  console.log('Hosted browser passed: static launch, offline demo/calculation/save, persisted reload, exact offline download, forget, and no uploads.');
}finally{
  if(browser)await browser.close();
  await new Promise(resolve=>server.close(resolve));
}
