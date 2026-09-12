/* Browser-only adapter. All assets are embedded at build time. */
(() => {
  const embedded = JSON.parse(document.getElementById('browser-assets').textContent);
  const pending = new Map();
  let generation = 0;
  let id = 0, dirty = false, saved = false, busy = false, revision = null, preferences = {};
  let storageWarning = '', fatal = '';
  // Data URLs work for module workers on file:// without special browser flags.
  const worker = new Worker('data:text/javascript;base64,' + embedded.worker, {type:'module'});
  function rpc(path, data, assets) {
    return new Promise((resolve,reject) => {
      const requestId = ++id;
      pending.set(requestId,{resolve,reject});
      worker.postMessage({id:requestId,path,data,assets});
    });
  }
  worker.onmessage = ({data}) => {
    const item=pending.get(data.id);if(!item)return;
    pending.delete(data.id);data.error?item.reject(new Error(data.error)):item.resolve(data.value);
  };
  worker.onerror = () => {
    fatal='The offline engine could not start. Open this file in a recent desktop Chrome or Edge browser.';
    for(const item of pending.values())item.reject(new Error(fatal));pending.clear();status();
  };
  const dbName = 'session-observatory-browser-v1';
  async function database() {
    return new Promise((resolve,reject) => {
      const request=indexedDB.open(dbName,1);
      request.onupgradeneeded=()=>request.result.createObjectStore('workspace');
      request.onsuccess=()=>resolve(request.result);
      request.onerror=()=>reject(new Error('Browser storage is unavailable. Download a backup before closing.'));
    });
  }
  async function readSaved() {
    const db=await database();
    try {return await new Promise((resolve,reject)=>{
      const tx=db.transaction('workspace','readonly'),req=tx.objectStore('workspace').get('current');
      tx.oncomplete=()=>resolve(req.result);tx.onerror=()=>reject(new Error('Saved workspace could not be read.'));
    });}finally{db.close();}
  }
  async function writeSaved(evidence, forget=false) {
    const db=await database();
    try {return await new Promise((resolve,reject)=>{
      const tx=db.transaction('workspace','readwrite'),store=tx.objectStore('workspace'),req=store.get('current');
      let conflict=false,next;
      req.onsuccess=()=>{
        if((req.result?.revision??null)!==revision){conflict=true;tx.abort();return;}
        // Keep a revision tombstone on deletion to stop another tab restoring old data.
        next=crypto.randomUUID();store.put({revision:next,evidence:forget?null:evidence},'current');
      };
      tx.oncomplete=()=>{revision=next;resolve();};
      tx.onabort=tx.onerror=()=>reject(new Error(conflict?'Another tab changed the saved workspace. Download a backup of this tab, then reload before saving.':'Could not save to browser storage. Download a backup before closing.'));
    });}finally{db.close();}
  }
  const ready = (async()=>{
    let timeout;
    try {await Promise.race([rpc(null,null,embedded.assets),new Promise((_,reject)=>{timeout=setTimeout(()=>{worker.terminate();fatal='The offline engine took too long to start. Close other large tabs and reopen in a recent desktop Chrome or Edge browser.';reject(new Error(fatal));},60000);})]);}
    finally {clearTimeout(timeout);}
    // Remove the large encoded copy after initializing; no imported data enters HTML.
    document.getElementById('browser-assets').remove();
    try {
      const stored=await readSaved();revision=stored?.revision??null;
      if(stored?.evidence){await rpc('/browser/restore',stored.evidence);preferences=stored.evidence.browser_preferences||{};saved=true;}
    } catch {storageWarning='Saved data could not be loaded. Your saved copy has not been replaced; use a backup if needed.';}
    status();
  })();
  // Suppress an unhandled rejection; API calls surface startup failures in the page.
  ready.catch(()=>{});
  const mutations=new Set(['/api/import','/api/attribute','/api/budget','/api/activity-policy','/api/acknowledge','/browser/demo']);
  function changed(){generation++;dirty=true;status();}
  async function api(path,data){
    await ready;if(fatal)throw new Error(fatal);
    const result=await rpc(path,data);
    if(mutations.has(path))changed();
    return result;
  }
  function status() {
    const label=document.getElementById('live-state');if(!label)return;
    label.textContent=fatal?'Offline engine unavailable':busy?'Reading selected files…':dirty?'Unsaved changes':saved?'Saved in this browser':'Memory only';
    document.querySelector('.device-block strong').textContent='Browser only';
    document.getElementById('device-name').textContent='No server · no account connection';
    document.querySelector('.device-block small:last-child').textContent=dirty?'Save or download before closing':saved?'Saved locally · manual refresh':'Nothing saved automatically';
    const button=document.getElementById('scan');button.textContent='Choose log folder';button.disabled=busy||!!fatal;
    const save=document.getElementById('browser-save');if(save){save.disabled=busy||!!fatal;save.textContent=saved?'Save changes in browser':'Save in this browser';}
  }
  function coverage(s) {
    return header('Sources & privacy','Open local evidence, explore it offline, and choose whether to keep a copy.',badge('Browser only','accent'))+
    `<section class="source-panel browser-intro"><h2>Your files stay on this computer</h2><p>No server, account connection, telemetry or runtime downloads. Only files you select are read. Conversation text is parsed in memory; the ledger keeps accounting metadata, source hashes and your declarations.</p>
    <div class="browser-actions"><button data-browser="folder" class="primary">Choose Codex log folder</button><button data-browser="import">Import one evidence file</button><button data-browser="demo">Try fictional demo</button></div>
    <p class="note">On Windows, choose <code>C:\\Users\\&lt;you&gt;\\.codex\\sessions</code>, <code>archived_sessions</code>, or the corresponding Work folder. You can select several locations in succession. Re-select a folder to refresh; duplicate responses are reconciled.</p>
    <p class="note">Folder import reads only <code>.jsonl</code> files, skips credential filenames, and accepts up to 30 MB per file. Provider and activity JSON exports use “Import one evidence file.” Prompts and tool output are not retained.</p></section>
    <section class="source-panel"><div class="section-heading"><h2>Keep control of your data</h2>${badge(dirty?'Unsaved changes':saved?'Saved in browser':'Memory only',dirty?'warning':'accent')}</div>
    <p>${saved?'A copy is stored in this browser profile. Changes are saved only when you click Save.':'Accounting stays in memory until you choose to save or download it. Closing or reloading discards unsaved changes.'}</p>
    <div class="browser-actions"><button data-browser="save">${saved?'Save changes in browser':'Save in this browser'}</button><button data-browser="backup">Download complete backup</button><button data-browser="restore">Restore / migrate evidence</button><button data-browser="forget">Forget this workspace</button></div>
    <p class="note">Browser storage is not encrypted by this app or guaranteed permanent. Browser cleanup, private mode, another profile or moving this HTML file may make it unavailable. Keep a downloaded backup. Backups include private paths, attribution, audit history and saved cost assumptions.</p>
    ${storageWarning?`<p class="form-error" role="alert">${esc(storageWarning)}</p>`:''}
    <p class="note">Restore accepts complete evidence JSON up to 512 MB, subject to available memory. To migrate from the earlier local app, export complete evidence from Sources &amp; coverage, then restore that JSON here. Restoration replaces this tab’s workspace; it does not overwrite the saved browser copy until you Save.</p></section>
    <section class="source-panel"><h2>What this workspace covers</h2><dl class="fact-grid"><dt>Imported files</dt><dd>${fmt(s.files)}</dd><dt>Counted usage entries</dt><dd>${fmt(s.events)}</dd><dt>Excluded legacy entries</dt><dd>${fmt(s.excluded)}</dd><dt>Historical quota readings</dt><dd>${fmt(s.limit_snapshots)}</dd><dt>Collection</dt><dd>Only the evidence you import; no automatic folder watcher</dd><dt>Identity</dt><dd>Source-declared or explicitly attributed; no verified login identity</dd><dt>Alerts</dt><dd>Policy mismatches in imported evidence, while this page is open</dd></dl>
    <p class="note">This app cannot detect account-wide stolen-session use, inspect other devices or monitor while closed. Historical Pro limit snapshots are not a live quota feed.</p></section>
    <section class="source-panel"><h2>Source quality</h2>${s.issues.length?s.issues.map(f=>`<details><summary class="path">${esc(f.source)}</summary><ul>${f.issues.map(v=>`<li>${esc(v)}</li>`).join('')}</ul></details>`).join(''):'<p>No parser notices in imported files. This does not guarantee complete coverage.</p>'}</section>
    <details class="source-panel"><summary>About, licenses and runtime sources</summary><p>Session Observatory is Apache-2.0. The unchanged Pyodide 314.0.6 runtime is MPL-2.0 and includes Python and other components under their respective licenses.</p><button data-browser="licenses">Download license notices</button><p><a href="https://github.com/pyodide/pyodide/tree/314.0.6" target="_blank" rel="noreferrer noopener">Pyodide source code</a> · External links open only when you click.</p></details>`;
  }
  function download(name,content,type='application/json') {
    const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
  }
  async function evidence(){const value=await api('/api/evidence-export');value.browser_preferences=preferences;return value;}
  const folder=document.createElement('input');folder.type='file';folder.multiple=true;folder.webkitdirectory=true;folder.hidden=true;folder.id='browser-folder';document.body.append(folder);
  const backup=document.createElement('input');backup.type='file';backup.accept='.json';backup.hidden=true;backup.id='browser-restore';document.body.append(backup);
  folder.addEventListener('change',async()=>{
    if(busy){folder.value='';toast('Wait for the current import to finish.');return;}
    const files=Array.from(folder.files);folder.value='';
    const eligible=files.filter(f=>/\.jsonl$/i.test(f.name)&&!/(auth|credential|secret|\.env)/i.test(f.name));
    busy=true;status();let imported=0,failed=0,records=0,limits=0;const problems=[];
    try {
      for(const file of eligible){
        try {
          if(!file.size||file.size>30*1024*1024)throw new Error('File is empty or above 30 MB.');
          const result=await api('/api/import',{name:file.webkitRelativePath||file.name,content:await file.text(),scope:''});
          imported++;records+=result.new_records;limits+=result.new_limit_snapshots||0;
        } catch {failed++;if(problems.length<20)problems.push(file.webkitRelativePath||file.name);}
        document.getElementById('live-state').textContent=`Read ${imported+failed} / ${eligible.length} logs`;
      }
      const message=`${imported} files imported · ${records} new entries · ${limits} limit readings · ${files.length-eligible.length} other files skipped · ${failed} logs not imported.`;
      await load();toast(message);
      const result=document.getElementById('browser-import-result');if(result)result.remove();
      const note=document.createElement('section');note.id='browser-import-result';note.className='source-panel';note.setAttribute('role','status');note.textContent=message+(problems.length?' Check these files for supported usage/limit records: '+problems.join(', ')+(failed>20?' (first 20 shown)':''):'');document.getElementById('main').prepend(note);
    } finally{busy=false;status();}
  });
  backup.addEventListener('change',async()=>{
    const file=backup.files[0];backup.value='';if(!file)return;
    try {
      if(file.size>512*1024*1024)throw new Error('Backups must be below 512 MB.');
      const value=JSON.parse(await file.text());
      if(!confirm('Replace the evidence in this tab with this backup? Download a backup first if you need to keep current changes.'))return;
      await api('/browser/restore',value);preferences=value.browser_preferences&&typeof value.browser_preferences==='object'?value.browser_preferences:{};
      changed();await load();toast('Evidence restored in this tab. Save if you want to keep it in this browser.');
    }catch {toast('Backup could not be restored. Check the format and app version. Existing evidence has been kept.');}
  });
  document.addEventListener('click',async event=>{
    const anchor=event.target.closest('a[href^="/api/"]');
    const button=event.target.closest('[data-browser],#scan');
    if(!anchor&&!button)return;event.preventDefault();event.stopImmediatePropagation();
    try {
      if(busy)throw new Error('Wait for the current import to finish.');
      if(anchor){const path=anchor.getAttribute('href'),value=await api(path);download(path.startsWith('/api/export')?'observatory-ledger.csv':'observatory-evidence.json',typeof value==='string'?value:JSON.stringify(value,null,2),typeof value==='string'?'text/csv':'application/json');return;}
      const action=button.id==='scan'?'folder':button.dataset.browser;
      if(action==='folder'){folder.click();return;}
      if(action==='restore'){backup.click();return;}
      if(action==='import'){document.getElementById('import-dialog').showModal();return;}
      if(action==='licenses'){download('observatory-third-party-notices.txt',atob(embedded.notices),'text/plain');return;}
      if(busy)throw new Error('Wait for the current import to finish.');
      if(action==='demo'){await api('/browser/demo',{});await load();toast('Fictional demo loaded. Forget this workspace before importing your own usage.');}
      if(action==='backup'){download('observatory-backup.json',JSON.stringify(await evidence()));toast('Backup download prepared. Unsaved changes remain until you Save or close this tab.');}
      if(action==='save'){
        const epoch=generation,value=await evidence();await writeSaved(value);saved=true;dirty=generation!==epoch;storageWarning='';await load();toast('Workspace saved in this browser.');
      }
      if(action==='forget'){
        if(!confirm('Delete this app’s saved workspace and clear all evidence and saved cost assumptions in this tab? Original files and downloaded backups are kept.'))return;
        await ready;await writeSaved(null,true);await rpc('/browser/reset',{});preferences={};saved=false;dirty=false;storageWarning='';
        costScenario=structuredClone(costDefaults);costDraft=null;costDirty=false;costData=null;filters.facets={};filters.project='';filters.q='';await load();toast('Workspace forgotten. Original files and downloaded backups were not changed.');
      }
    }catch(error){storageWarning=error.message;toast(error.message);status();}
  },true);
  window.addEventListener('beforeunload',event=>{if(dirty||busy){event.preventDefault();event.returnValue='';}});
  globalThis.ObservatoryBrowser={api,coverage,status,ready,preferences:{
    getItem:key=>preferences[key]??null,
    setItem:(key,value)=>{preferences[key]=value;changed();}
  }};
  if(!location.hash)location.hash='#coverage';
})();
