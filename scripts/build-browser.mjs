// Build-time Node only. End users open the output HTML without any server.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const read=path=>readFile(join(root,path));
const files=['pyodide.mjs','pyodide.asm.mjs','pyodide.asm.wasm','python_stdlib.zip','pyodide-lock.json'];
const assets={},manifest={runtime:'pyodide@314.0.6',assets:{}};
const pkg=JSON.parse(await read('node_modules/pyodide/package.json'));
if(pkg.version!=='314.0.6')throw new Error('The offline runtime must match the pinned, reviewed version.');
for(const name of files){const bytes=await read('node_modules/pyodide/'+name);assets[name]=bytes.toString('base64');manifest.assets[name]=createHash('sha256').update(bytes).digest('hex');}
for(const name of ['__init__.py','ledger.py','analytics.py','costs.py','limits.py','demo.py']){const path='engine/'+name;assets[path]=(await read(path)).toString('base64');}
assets['bridge.py']=(await read('web/browser/bridge.py')).toString('base64');
const notices=(await Promise.all(['third_party/NOTICE.txt','LICENSE','NOTICE','third_party/licenses/PYODIDE-MPL-2.0.txt','third_party/licenses/PYTHON.txt','third_party/licenses/EMSCRIPTEN.txt'].map(async p=>`\n\n===== ${p} =====\n${await read(p)}`))).join('');
const payload={assets,worker:(await read('web/browser/worker.js')).toString('base64'),notices:Buffer.from(notices).toString('base64')};
let html=(await read('web/index.html')).toString();
html=html.replace(/<script defer src="[^"]+"><\/script>/g,'');
html=html.replace('<link rel="stylesheet" href="/style.css">',`<style>${await read('web/style.css')}\n.browser-actions{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}.browser-intro h2{margin-top:0}.source-panel>p{max-width:90ch;line-height:1.6}.source-panel>summary{cursor:pointer}</style>`);
html=html.replace('href="/favicon.svg"',`href="data:image/svg+xml;base64,${(await read('web/favicon.svg')).toString('base64')}"`);
html=html.replace('<meta charset="utf-8">',`<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' 'wasm-unsafe-eval' blob: data:; worker-src data:; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"><meta name="referrer" content="no-referrer">`);
html=html.replace('Loading the local ledger…','Starting the offline engine… No files are being read.');
html=html.replace('<span id="live-state" role="status">Connecting</span>','<span id="live-state" role="status">Starting offline</span><button id="browser-save" data-browser="save">Save in this browser</button>');
const scripts=['web/browser/browser.js','web/limits.js','web/analytics.js','web/costs.js','web/app.js'];
const safe=value=>value.replace(/<\/script/gi,'<\\/script');
html=html.replace('</body>',`<script id="browser-assets" type="application/json">${JSON.stringify(payload)}</script>\n${(await Promise.all(scripts.map(async p=>`<script>\n${safe((await read(p)).toString())}\n</script>`))).join('\n')}\n</body>`);
const out=join(root,'dist');await mkdir(out,{recursive:true});
const name='session-observatory-browser.html';
await writeFile(join(out,name),html);await writeFile(join(out,'browser-runtime-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
await writeFile(join(out,name+'.sha256'),`${createHash('sha256').update(html).digest('hex')}  ${name}\n`);
console.log(`Built ${name}: ${(Buffer.byteLength(html)/1024/1024).toFixed(1)} MB, self-contained; no user data included.`);
