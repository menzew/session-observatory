'use strict';
const $ = (s, root = document) => root.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = value => new Intl.NumberFormat('en-US').format(value || 0);
const compact = value => new Intl.NumberFormat('en-US', {notation:'compact',maximumFractionDigits:2}).format(value || 0);
const when = value => value ? new Date(value).toLocaleString('en-GB',{timeZone:'UTC',year:'numeric',month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}) : 'Unknown';
const short = value => value ? value.slice(0,12) + '…' : 'Unavailable';
const projectName = value => value === 'Unallocated' ? value : value.split(/[\\/]/).filter(Boolean).slice(-2).join('/') || value;
const badge = (label, type='neutral') => `<span class="badge ${type}">${esc(label)}</span>`;
let state = null, ledger = null, route = '', serial = 0, timer = null, activeDetail = null;
let foregroundLoads = 0;
let filters = {range:'7',q:'',project:'',sort:'newest',offset:0,from:'',to:'',granularity:'',by:'project',facets:{}};
let alerted = new Set();
const sorts={costs:['scenario','desc'],ledger:['timestamp','desc'],analysis:['total_tokens','desc'],provider:['start','desc'],activity:['timestamp','desc'],limits:['timestamp','desc'],coverage:[null,'asc']};
const limitFilters={range:'all',q:'',plan:'pro',source:'',offset:0};
function sortQuery(table) {const [key,direction]=sorts[table];return new URLSearchParams(key?{sort_by:key,direction}:{}).toString();}
function limitsQuery() {
  const params=new URLSearchParams({...limitFilters,sort_by:sorts.limits[0],direction:sorts.limits[1]});
  if(limitFilters.range!=='all'){const date=new Date();date.setUTCDate(date.getUTCDate()-Number(limitFilters.range)+1);date.setUTCHours(0,0,0,0);params.set('from',date.toISOString());}
  return params.toString();
}
function installSorting() {
  const columns={costs:['dimension','tokens','baseline','scenario',...(costDetailed?['input','cached','write','output']:[]),'unpriced_records'],ledger:['timestamp','project','actor','model','input_tokens','cached_input_tokens','output_tokens','total_tokens'],
    analysis:['dimension','records','tasks','share','input_tokens','cached_input_tokens','uncached_input_tokens','output_tokens','reasoning_output_tokens','cache_write_input_tokens','total_tokens','cache_share'],
    provider:['start','kind','dimensions','values','imported_at'],activity:['timestamp','actor','action','device','purpose'],
    limits:['timestamp','plan','limit_id','primary','secondary','thread_id','source'],coverage:['surface','working','missing']};
  const table=$(route==='analysis'?'#main .analysis-table':'#main table'),keys=columns[route];if(!table||!keys)return;
  const [selected,direction]=sorts[route];
  const hints={project:'project path',actor:'person',start:'period start',values:'kind, currency, then total tokens or exact cost',imported_at:'import time',primary:'primary used percentage',secondary:'secondary used percentage',source:'source path'};
  table.querySelectorAll('thead th').forEach((th,i)=>{
    const key=keys[i],label=th.textContent;th.setAttribute('aria-sort',key===selected?(direction==='asc'?'ascending':'descending'):'none');
    const next=key===selected&&direction==='asc'?'descending':'ascending';
    th.innerHTML=`<button class="sort-header" id="sort-${route}-${key}" data-sort-table="${route}" data-sort-key="${key}" title="Sort by ${esc(hints[key]||label)}; click for ${next} order">${esc(label)} <span aria-hidden="true">${key===selected?(direction==='asc'?'↑':'↓'):'↕'}</span></button>`;
  });
  if(route==='coverage'&&selected){const index=keys.indexOf(selected),body=table.tBodies[0];[...body.rows].sort((a,b)=>a.cells[index].textContent.localeCompare(b.cells[index].textContent)*(direction==='asc'?1:-1)).forEach(r=>body.append(r));}
}


async function api(path, data) {
  if (globalThis.ObservatoryBrowser) return ObservatoryBrowser.api(path, data);
  const options = data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Observatory-Token':state?.csrf || ''},body:JSON.stringify(data)};
  const response = await fetch(path, options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `Request failed (${response.status}).`);
  return value;
}

function query(table="ledger") {
  const params = new URLSearchParams({q:filters.q,project:filters.project,sort:filters.sort,offset:String(filters.offset),granularity:filters.granularity,by:filters.by});
  if (filters.range === 'custom') {
    if(filters.from)params.set('from',filters.from);
    if(filters.to){const end=new Date(filters.to+'T00:00:00Z');end.setUTCDate(end.getUTCDate()+1);params.set('to',end.toISOString());}
  } else if (filters.range !== 'all') {
    const date = new Date(); date.setUTCDate(date.getUTCDate()-Number(filters.range)+1); date.setUTCHours(0,0,0,0);
    params.set('from',date.toISOString());
  }
  if(Object.keys(filters.facets||{}).length)params.set('facets',JSON.stringify(filters.facets));
  for(const key of ['tokens_min','tokens_max'])if(filters[key]!=null)params.set(key,String(filters[key]));
  if(filters.drillFrom)params.set('from',filters.drillFrom);
  if(filters.drillTo)params.set('to',filters.drillTo);
  for(const [key,value] of new URLSearchParams(sortQuery(table)))params.set(key,value);
  return params.toString();
}

function toast(message) {
  $('#toast').textContent = message; $('#toast').hidden = false;
  clearTimeout(timer); timer = setTimeout(()=>$('#toast').hidden=true,6500);
}

function header(title, description, extra='') {
  return `<div class="page-heading"><div><h1>${title}</h1><p>${description}</p></div>${extra}</div>`;
}

function empty(title, description) {
  return `<div class="empty"><span aria-hidden="true">◎</span><h2>${title}</h2><p>${description}</p></div>`;
}

function filterBar(exportParams=query(),simple=false) {
  return `<div class="filters"><label class="search"><span aria-hidden="true">⌕</span><input id="search" type="search" aria-label="Search the ledger" placeholder="Find a project, task, person, model or purpose…" value="${esc(filters.q)}"></label>
  <label class="select-label">Period<select id="range">${[['7','Last 7 days'],['30','Last 30 days'],['90','Last 90 days'],['all','All recorded time'],['custom','Custom dates']].map(([v,t])=>`<option value="${v}" ${filters.range===v?'selected':''}>${t}</option>`).join('')}</select></label>
  ${filters.range==='custom'?`<label class="date-label">From (UTC)<input id="from" type="date" value="${esc(filters.from)}"></label><label class="date-label">Through (UTC)<input id="to" type="date" value="${esc(filters.to)}"></label>`:''}<label class="select-label">Evidence<select id="granularity">${[['','All metering'],['response','Responses only'],['snapshot delta','Legacy snapshots only']].map(([v,t])=>`<option value="${v}" ${filters.granularity===v?'selected':''}>${t}</option>`).join('')}</select></label>${route==='projects'?`<label class="select-label">Sort<select id="sort">${[['newest','Newest first'],['oldest','Oldest first'],['tokens','Most tokens']].map(([v,t])=>`<option value="${v}" ${filters.sort===v?'selected':''}>${t}</option>`).join('')}</select></label>`: simple?'':'<span class="sort-hint">Click column headings to sort ↕</span>'}
  ${simple?'':`<a class="button" href="/api/export?${exportParams}">Export CSV</a>`}</div>${filters.project?`<div class="filter-chip">Project: ${esc(projectName(filters.project))}<button data-action="clear-project" aria-label="Clear project filter">×</button></div>`:''}${facetChips()}`;
}

function chart(days) {
  if (!days.length) return '';
  const data = days.slice(-30), max = Math.max(...data.map(d=>d.total),1), w=960, h=150, slot=w/data.length;
  const bars = data.map((d,i)=>{
    let y=h; const rects=[];
    for (const [key,cls] of [['cached','cached'],['uncached','uncached'],['output','output']]) {
      const size=d[key]/max*(h-12); y-=size;
      rects.push(`<rect x="${i*slot+slot*.15}" y="${y}" width="${slot*.7}" height="${size}" class="${cls}"/>`);
    }
    return `<g><title>${esc(d.day)}: ${fmt(d.total)} tokens; ${fmt(d.cached)} cached, ${fmt(d.uncached)} uncached input, ${fmt(d.output)} output</title>${rects.join('')}</g>`;
  }).join('');
  return `<section class="chart-section" aria-label="Recorded token history"><div class="section-heading"><h2>Recorded token history</h2><div class="legend"><span><i class="cached"></i>Cached input</span><span><i class="uncached"></i>Uncached input</span><span><i class="output"></i>Output</span></div></div>
    <svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Stacked bars of daily recorded tokens, most recent ${data.length} active days. Exact totals available in the ledger export.">${bars}</svg><div class="chart-axis"><span>${esc(data[0].day)}</span><span>Most recent ${data.length} active days in selection · UTC</span><span>${esc(data.at(-1).day)}</span></div></section>`;
}

function ledgerView() {
  const {summary:s,events}=ledger;
  return header('Usage ledger','Trace recorded tokens to their response, task, project and source.',badge('Source-backed accounting','accent')) + filterBar() +
    `<div class="stats"><div><span>Observed tokens</span><strong title="${fmt(s.total_tokens)}">${compact(s.total_tokens)}</strong><small>${fmt(s.total_tokens)} exact</small></div><div><span>Metering records</span><strong>${fmt(s.records)}</strong><small>${fmt(s.tasks)} distinct tasks</small></div><div><span>Projects / folders</span><strong>${fmt(s.projects)}</strong><small>In this selection</small></div><div><span>Purpose not declared</span><strong>${fmt(s.missing_purpose)}</strong><small>Open a record to attribute it</small></div></div>` + `<p class="note">${fmt(s.response_records)} response records · ${fmt(s.snapshot_records)} legacy snapshot deltas in this selection. ${state.issue_files?`<a href="#coverage">${fmt(state.issue_files)} source files have quality notices.</a>`:''} Totals reflect indexed, included evidence; they may be incomplete. <a href="#limits">View recorded Pro limits and resets.</a></p>` + chart(ledger.days) +
    `<div class="section-heading"><h2>Response details</h2><span>${fmt(s.cached_input_tokens)} cached input · ${fmt(s.output_tokens)} output</span></div>` +
    (events.length ? `<div class="table-wrap" tabindex="0" aria-label="Usage records"><table class="ledger-table"><thead><tr><th>When / record</th><th>Project / task</th><th>Who / what</th><th>Model</th><th class="number">Input</th><th class="number">Cached¹</th><th class="number">Output</th><th class="number">Total</th></tr></thead><tbody>${events.map(e=>`<tr><td><button class="record-link" data-event="${e.id}">${esc(when(e.timestamp))}</button><small>${esc(e.granularity)} · ${esc(short(e.response_id||e.id))}</small></td><td><strong title="${esc(e.effective_project)}">${esc(projectName(e.effective_project))}</strong><small>${esc(short(e.thread_id))}${e.parent_id?' · child task':''}</small></td><td>${esc(e.effective_actor||'Identity unknown')}<small>${esc(e.application)}${e.attributed_at?' · declared attribution':''}</small></td><td class="model-cell">${esc(e.model)}</td><td class="number">${fmt(e.input_tokens)}</td><td class="number muted">${fmt(e.cached_input_tokens)}</td><td class="number">${fmt(e.output_tokens)}</td><td class="number"><strong>${fmt(e.total_tokens)}</strong></td></tr>`).join('')}</tbody></table></div><div class="table-footer"><span>¹ Cached input is included in Input. Total = Input + Output.</span><div><span>${fmt(filters.offset+1)}–${fmt(Math.min(filters.offset+50,s.records))} of ${fmt(s.records)}</span><button data-action="previous" ${filters.offset===0?'disabled':''} aria-label="Previous records">←</button><button data-action="next" ${filters.offset+50>=s.records?'disabled':''} aria-label="Next records">→</button></div></div>` : empty(state.progress.running?'Indexing your records':'No records match','Records appear as sources are indexed. Try a wider period, clear the search, or import accounting evidence.'));
}

function projectsView() {
  const projects=[...ledger.projects].sort((a,b)=>filters.sort==='tokens'?b.total_tokens-a.total_tokens:(filters.sort==='oldest'?1:-1)*a.last_seen.localeCompare(b.last_seen));
  return header('Projects','Compare recorded consumption and set a token budget for each project.') + filterBar() +
    (projects.length ? `<div class="project-list">${projects.map((p,i)=>{const budget=state.budgets.find(b=>b.project===p.project);return `<section class="project-row"><div class="project-name"><span class="project-symbol" aria-hidden="true">▦</span><div><button class="record-link" data-project="${esc(p.project)}">${esc(projectName(p.project))}</button><small class="path">${esc(p.project)}</small><small>${fmt(p.tasks)} tasks · ${fmt(p.records)} records · last ${esc(when(p.last_seen))}</small></div></div><div class="project-tokens"><strong>${fmt(p.total_tokens)}</strong><small>tokens in selection</small></div><form class="budget-form" data-project="${esc(p.project)}"><label>Token budget<input name="tokens" type="number" min="1" max="1000000000000000" required value="${budget?.tokens||''}" placeholder="e.g. 1000000" aria-label="Token budget for ${esc(projectName(p.project))}"></label><label>Period<select name="period"><option value="day" ${budget?.period==='day'?'selected':''}>Per UTC day</option><option value="month" ${budget?.period==='month'?'selected':''}>Per UTC month</option></select></label><button type="submit">Save budget</button></form></section>`}).join('')}</div><p class="note">Budgets generate local alerts at 80% and 100%. They do not stop model requests. Project folders remain separate until records are explicitly attributed to a common project.</p>` : empty('No projects in this selection','Expand the period or import Codex evidence to start accounting.'));
}

function providerView(data) {
  return header('Provider records','Inspect imported provider totals without double-counting local observations.',badge('Import-based','warning'))+
  `<div class="notice"><strong>Provider totals are a separate view.</strong><p>${esc(data.note)} Each row retains its time window, declared account, native dimensions and units. Click column headings to sort; reported values sort by kind, currency, then total tokens or exact cost.</p></div>`+
  (data.buckets.length?`<div class="section-heading"><h2>Usage and cost buckets</h2><span>Showing ${fmt(data.buckets.length)} of ${fmt(data.total)} buckets</span></div><div class="table-wrap" tabindex="0" aria-label="Provider buckets"><table><thead><tr><th>Period / account</th><th>Kind</th><th>Dimensions</th><th>Reported values</th><th>Provenance</th></tr></thead><tbody>${data.buckets.map(b=>`<tr><td><strong>${esc(b.scope)}</strong><small>${esc(when(b.start))} → ${esc(when(b.end))}</small><small>End exclusive · UTC</small></td><td>${badge(b.kind)}</td><td><dl class="compact-dl">${Object.entries(b.dimensions).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v??'not grouped')}</dd>`).join('')}</dl></td><td><dl class="compact-dl">${Object.entries(b.values).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${typeof v==='number'?fmt(v):esc(v)}</dd>`).join('')}</dl></td><td><small>Imported ${esc(when(b.imported_at))}</small><small class="path">${esc(b.source)}</small><small>Account label is declared</small></td></tr>`).join('')}</tbody></table></div>`:empty('Bring in provider evidence','Import an OpenAI completion-usage or Costs API JSON page. Personal, Business, Enterprise/Edu and API scopes remain distinct. No live provider account is connected.'));
}

function activityView(data) {
  return header('Accountability','Who changed an attribution, what changed, when, and the reason recorded.')+
  `<div class="notice"><strong>${state.integrity.valid?'Local audit chain verified':'Audit chain verification failed'}</strong><p>${fmt(state.integrity.entries)} entries. The chain detects inconsistencies; it is not externally signed and cannot prove integrity against someone with full database access. Operator identity is the local service user.</p></div>`+
  `<div class="section-heading"><h2>Attribution and import history</h2><span>Latest ${fmt(data.audit.length)} of ${fmt(data.audit_count)} entries</span></div>`+
  (data.audit.length?`<div class="audit-list">${data.audit.map(a=>`<details class="audit-row"><summary><span>${esc(a.action)}</span><span>${esc(a.actor)} · ${esc(when(a.timestamp))}</span></summary><p>${esc(a.reason)}</p><small class="path">Target: ${esc(a.target)}</small><div class="before-after"><div><h3>Before</h3><pre>${esc(JSON.stringify(JSON.parse(a.before_json),null,2))}</pre></div><div><h3>After</h3><pre>${esc(JSON.stringify(JSON.parse(a.after_json),null,2))}</pre></div></div><small class="path">Entry hash: ${esc(a.hash)}</small></details>`).join('')}</div>`:empty('Changes leave a trail','Declare a response’s owner, project or purpose to create the first attribution entry. Original metering remains intact.'))+
  `<div class="section-heading"><h2>Imported activity</h2><span>${fmt(data.activity_count)} source-declared events · not a live security feed</span></div>`+
  (data.activity.length?`<div class="table-wrap" tabindex="0" aria-label="Evidence table"><table><thead><tr><th>When</th><th>Who</th><th>What</th><th>Where</th><th>Why / project</th></tr></thead><tbody>${data.activity.map(a=>`<tr><td>${esc(when(a.timestamp))}</td><td>${esc(a.actor||'Unknown')}<small>${esc(a.account_ref)}</small></td><td>${esc(a.action)}<details><summary>Evidence</summary><pre>${esc(JSON.stringify(JSON.parse(a.details),null,2))}</pre><small class="path">${esc(a.source)}</small></details></td><td>${esc(a.device||'Unknown device')}<small>${esc(a.ip||'IP unavailable')}</small></td><td>${esc(a.purpose||'Not supplied')}<small>${esc(a.project||'Unallocated')}</small></td></tr>`).join('')}</tbody></table></div>`: '<p class="note">Import normalized activity exports to preserve workspace or third-party evidence. Missing identities and purposes stay unknown.</p>');
}

function alertsView() {
  return header('Alerts','Review budget thresholds, conflicting records, and collection problems.',`<button id="enable-notifications">Enable desktop alerts</button>`)+
  `<div class="notice"><strong>Accounting alerts are active while the local service runs.</strong><p>Imported activity is checked against any access policy you declare below. Remote stolen-session detection is not connected. Desktop notifications require permission and this page to remain open.</p></div>`+
  activityPolicyView()+
  (state.alerts.length?`<div class="alerts-list">${state.alerts.map(a=>`<article class="alert-row"><div>${badge(a.severity,a.severity==='high'?'danger':'warning')} ${badge(a.status)}<h2>${esc(a.title)}</h2><p>${esc(a.detail)}</p><small class="path">${esc(a.target)}</small><small>First observed ${esc(when(a.created_at))} · updated ${esc(when(a.updated_at))}</small></div>${a.id.startsWith('activity-')?`<button data-activity="${esc(a.target)}">Inspect activity evidence</button>`:a.id.startsWith('conflict:')?`<button data-event="${esc(a.target)}">Inspect metering evidence</button>`:''}${a.status==='open'?`<button data-ack="${esc(a.id)}">Acknowledge</button>`:''}</article>`).join('')}</div>`:empty('No accounting alerts','Set a project token budget to receive threshold alerts. No alerts does not imply that remote account activity is safe or fully monitored.'));
}

function activityPolicyView() {
  return `<details class="source-panel"><summary>Declare approved devices and networks for imported activity</summary><p>Use the exact account label and device names in your activity imports. Missing evidence produces an unknown-coverage alert; a mismatch flags the event for review. These rules do not block access or prove theft.</p><form id="policy-form"><label>Account / workspace label<input name="scope" maxlength="200" required></label><label>Approved device names<textarea name="devices" rows="2" placeholder="One device name per line"></textarea></label><label>Approved IP addresses or networks<textarea name="networks" rows="2" placeholder="One IP or CIDR network per line"></textarea></label><label>Reason for this policy<textarea name="reason" rows="2" required maxlength="2000"></textarea></label><p class="note">Saving replaces the policy for this label and checks its historical imports. Existing alerts remain in history. A blank device or network list leaves that check disabled.</p><p id="policy-error" class="form-error" role="alert"></p><button type="submit">Save access policy</button></form>${state.activity_policies.length?`<h3>Current policies</h3>${state.activity_policies.map(p=>`<div class="observation"><strong>${esc(p.scope)}</strong><p>Devices: ${esc(JSON.parse(p.devices).join(', ')||'Not checked')}</p><p>Networks: ${esc(JSON.parse(p.networks).join(', ')||'Not checked')}</p></div>`).join('')}`:''}</details>`;
}

function sourceSettings() {
  const sources=state.sources||[];
  return `<section class="source-settings"><div class="section-heading"><h2>Configured source roots</h2><button id="add-source">Add source folder</button></div><p class="note">Add as many Codex / ChatGPT Work homes or copied session folders as you need. Settings persist across restarts. Disabling or removing a source stops collection and keeps indexed evidence.</p>
  ${sources.length?`<div class="source-list">${sources.map(s=>`<article class="source-row"><div class="source-row-head"><h3>${esc(s.label)}</h3>${badge(s.status,s.status==='unavailable'||s.status==='notices'||s.status==='unrecognized'?'warning':s.status==='ready'?'accent':'neutral')}</div><div class="source-path path">${esc(s.path)}</div>${s.access_path?`<small class="path">Server path: ${esc(s.access_path)}</small>`:s.resolved_path&&s.resolved_path!==s.path?`<small class="path">Accessible as: ${esc(s.resolved_path)}</small>`:''}<small>${s.kind==='codex_home'?'Codex / ChatGPT Work home':'Session folder'} · ${s.origin==='external'?'Files from another computer; identity unverified':'Local collector identity'} · ${fmt(s.file_count)} JSONL files</small><p class="note">${esc(s.detail||'Waiting for collection.')}</p><small>Last checked: ${esc(when(s.last_scan))} UTC</small><div class="source-actions"><button data-source-edit="${esc(s.id)}">Edit</button><button data-source-toggle="${esc(s.id)}">${s.enabled?'Disable':'Enable'}</button><button data-source-remove="${esc(s.id)}">Remove</button></div></article>`).join('')}</div>`:empty('No source folders enabled','Add a source to collect automatically, or import records manually.')}
  <details class="source-help"><summary>Windows, WSL and ChatGPT Work locations</summary><p>The Windows desktop app shares the Codex home at <code>%USERPROFILE%&#92;.codex</code>. For example, a profile named Alex would use <code>C:&#92;Users&#92;alex&#92;.codex</code>. A custom <code>CODEX_HOME</code> can point elsewhere. WSL CLI can use a separate Linux <code>~/.codex</code>.</p><p>This app reads folders reachable by the server (${esc(state.device)}), which may be a different computer from your browser. A Windows path can be saved now; it stays unavailable until Windows access or an explicit server path is available. Standard mounted drives under <code>/mnt/c</code> are recognized automatically.</p><p>Collect the whole home to include both <code>sessions</code> and <code>archived_sessions</code>. Choose “Session folder” for a copied folder of JSONL logs. App caches and ordinary chat exports are not assumed to contain token metering; use Import records for supported provider or activity exports.</p><p><a href="https://learn.chatgpt.com/docs/windows/windows-app" target="_blank" rel="noopener noreferrer">Official Windows app locations</a> · <a href="https://learn.chatgpt.com/docs/config-file/environment-variables" target="_blank" rel="noopener noreferrer">CODEX_HOME documentation</a></p></details></section>`;
}

function editSource(id='') {
  const source=(state.sources||[]).find(s=>s.id===id)||{id:'',label:'',path:'',access_path:'',kind:'codex_home',origin:'external',enabled:true};
  const form=$('#source-form');
  for(const key of ['id','label','path','access_path','kind','origin'])form.elements.namedItem(key).value=source[key];
  form.elements.namedItem('enabled').checked=source.enabled;
  form.elements.namedItem('reason').value=id?'Update source collection settings.':'Include this source in accounting.';
  $('#source-heading').textContent=id?'Edit source folder':'Add source folder';$('#source-error').textContent='';
  $('#source-dialog').showModal();
}

function coverageView() {
  if (globalThis.ObservatoryBrowser) return ObservatoryBrowser.coverage(state);
  const p=state.progress;
  return header('Sources & coverage','See what is observed, what is missing, and how much evidence has been indexed.', '<a class="button" href="/api/evidence-export">Export complete evidence</a>')+
   sourceSettings()+`<section class="source-panel"><div class="section-heading"><h2>Collection service</h2>${badge(p.running?'Indexing':'Local collector','accent')}</div><dl class="fact-grid"><dt>Device observed by collector</dt><dd>${esc(state.device)}</dd><dt>Service user</dt><dd>${esc(state.operator)} — not a verified model-account identity</dd><dt>Enabled sources</dt><dd>${fmt((state.sources||[]).filter(s=>s.enabled).length)}</dd><dt>Indexed files</dt><dd>${fmt(state.files)} · ${fmt(state.events)} counted records</dd><dt>Quota readings</dt><dd><a href="#limits">${fmt(state.limit_snapshots)} historical limit snapshots</a> · separate from token totals</dd><dt>Scan progress</dt><dd>${p.running?`${fmt(p.done)} / ${fmt(p.total)} files`:'Waiting for the next scan'}${p.error?`<p class="form-error">${esc(p.error)}</p>`:''}</dd><dt>Last completed scan</dt><dd>${esc(when(p.last_scan))}</dd><dt>Excluded records</dt><dd>${fmt(state.excluded)} superseded or ambiguous legacy records</dd><dt>Purpose collection</dt><dd>Explicit declarations. Prompts and tool output are not collected.</dd></dl></section>
   <div class="section-heading"><h2>Account coverage</h2><span>Capabilities and connection state are separate</span></div><div class="table-wrap" tabindex="0" aria-label="Evidence table"><table><thead><tr><th>Surface</th><th>Working in this app</th><th>Still unavailable</th></tr></thead><tbody>
   <tr><td>Local Codex</td><td>Automatic response/snapshot indexing, historical quota readings, task lineage, model, tokens, provenance, declarations</td><td>Verified billing identity; unseen computers; cloud-only runs</td></tr>
   <tr><td>API organization</td><td>Completion-usage/cost export import, native dimensions, revisions</td><td>Live polling, verified account ownership, matched usage reconciliation, gateway enforcement</td></tr>
   <tr><td>Enterprise / Edu</td><td>Normalized activity import with actor, event time, source and purpose</td><td>Authenticated compliance/analytics feeds and replay detection</td></tr>
   <tr><td>Business / personal ChatGPT</td><td>Declared attribution and imported evidence where available</td><td>Complete account-wide metering and stolen-token alerts</td></tr>
   <tr><td>Other computers / third-party apps</td><td>Imported logs and normalized activity; unknown device stays unknown</td><td>Authenticated device enrollment and live external audit feeds</td></tr></tbody></table></div>
   <div class="section-heading"><h2>Source quality</h2><span>${fmt(state.issue_files)} files with notices · showing up to 100</span></div>${state.issues.length?state.issues.map(f=>`<details class="audit-row"><summary class="path">${esc(f.source)}</summary><ul>${f.issues.map(i=>`<li>${esc(i)}</li>`).join('')}</ul></details>`).join(''):'<p class="note">No parser notices in indexed files. This is not a guarantee of complete account coverage.</p>'}`;
}

async function load(background=false,preparedCost=null) {
  // A polling tick must not invalidate a pending user action, even when the
  // tick later declines to render because a control still has focus.
  if(background && foregroundLoads)return;
  if(background && location.hash==='#costs' && (costDirty || costBusy || document.activeElement?.closest('#cost-form')))return;
  if(!background)foregroundLoads++;
  const seq=++serial;
  try {
    const [nextState, nextLedger] = await Promise.all([api('/api/state'),location.hash==='#costs'?Promise.resolve(ledger):api('/api/ledger?'+query())]);
    if(seq!==serial)return;
    state=nextState;ledger=nextLedger;
    $('#device-name').textContent=state.device;
    $('.device-block strong').textContent=state.demo?'Synthetic demo':'This computer';
    $('.device-block small:last-child').textContent=state.demo?'Fictional records · read-only':'Local records · no credentials read';
    $('#scan').disabled=!!state.demo;$('#open-import').disabled=!!state.demo;
    const p=state.progress;
    $('#live-state').textContent=p.running?`Indexing ${fmt(p.done)} / ${fmt(p.total)}`:p.error?'Collection needs attention':state.demo?'Demo data · read-only':'Local collection';
    if (globalThis.ObservatoryBrowser) ObservatoryBrowser.status();
    $('#alert-count').textContent=state.alerts.filter(a=>a.status==='open').length||'';
    if('Notification' in window && Notification.permission==='granted') {
      for(const a of state.alerts) if(a.status==='open'&&!alerted.has(a.id+':'+a.severity)) {new Notification(a.title,{body:a.detail,tag:a.id});alerted.add(a.id+':'+a.severity);}
    }
    route=location.hash.slice(1)||'ledger';
    if(!['ledger','projects','analysis','provider','activity','alerts','coverage','limits','costs'].includes(route)) route='ledger';
    const labels={ledger:'Usage ledger',projects:'Projects',analysis:'Consumption analysis',provider:'Provider records',activity:'Accountability',alerts:'Alerts',coverage:'Sources & coverage',limits:'Limits & cycles',costs:'Cost analysis'};
    $('#breadcrumb').textContent='Accounting / '+labels[route];
    document.querySelectorAll('[data-nav]').forEach(el=>{el.classList.toggle('active',el.dataset.nav===route);if(el.dataset.nav===route)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
    // Do not destroy an active form or search selection during background collection.
    if(background && ((route==='costs' && costDirty) || document.querySelector('dialog[open]') || (document.activeElement && ['INPUT','TEXTAREA','SELECT','BUTTON'].includes(document.activeElement.tagName)))) return;
    let view,costResult;
    if(route==='ledger')view=ledgerView();
    if(route==='limits')view=limitsView(await api('/api/limits?'+limitsQuery()));
    if(route==='projects')view=projectsView();
    if(route==='alerts')view=alertsView();
    if(route==='coverage')view=coverageView();
    if(route==='analysis')view=analyticsView(await api('/api/analytics?'+query('analysis')+'&metric='+analysisMetric));
    if(route==='costs')costResult=preparedCost&&preparedCost.key===costSelectionKey()?preparedCost.data:await api('/api/cost-analysis',costRequest());
    if(route==='provider')view=providerView(await api('/api/provider?'+sortQuery('provider')));
    if(route==='activity')view=activityView(await api('/api/activity?'+sortQuery('activity')));
    if(seq!==serial)return;
    if(costResult){if(background&&(costDirty||costBusy))return;view=costView(costResult);}
    const focus=document.activeElement?.id, start=document.activeElement?.selectionStart;
    $('#main').innerHTML=view;
    installSorting();
    if(focus==='search'||focus==='limit-search') {const input=document.getElementById(focus);if(input){input.focus();if(start!=null)input.setSelectionRange(start,start);}}
    else if(focus?.startsWith('sort-')||['trend-split','by','cost-details-toggle'].includes(focus))document.getElementById(focus)?.focus();
  }catch(error){if(seq!==serial)return;if(!state)$('#main').innerHTML=empty('Could not load the ledger',esc(error.message));else toast(error.message);}
  finally{if(!background)foregroundLoads--;}
}

async function openDetail(id) {
  const dialog=$('#detail');
  $('#detail-content').innerHTML='<div class="dialog-head"><h2 id="detail-heading">Loading evidence…</h2><button data-close="detail" aria-label="Close record">×</button></div>';
  if(!dialog.open)dialog.showModal();
  try {
    const data=await api('/api/event?id='+encodeURIComponent(id));
    if(!dialog.open)return;
    activeDetail=data;
    const e=data.event,a=data.attribution;
    const facts=[['Who',`${e.effective_actor||'Unknown'}${a.principal?' (declared attribution)':e.actor?' (collector user)':''}`],['What',`${e.application} · ${e.model} · ${e.granularity}`],['When',`${e.details.source_timestamp||e.timestamp} (source timestamp)`],['Where',`${e.device?'Collector computer: '+e.device:'Execution device unknown'} · source directory: ${e.cwd||'Unavailable'}`],['Why',e.purpose||'Purpose not declared. The app does not infer intent from token counts.'],['Account / workspace',e.account_ref||'Not established by this source'],['Project',e.effective_project]];
    $('#detail-content').innerHTML=`<div class="dialog-head"><div><span class="muted">Metering evidence</span><h2 id="detail-heading">${fmt(e.total_tokens)} tokens</h2></div><button data-close="detail" aria-label="Close record">×</button></div>
    <div class="detail-actions">${badge(e.granularity)}${e.excluded?badge('Excluded from totals','warning'):badge('Counted','accent')}<button data-action="download-evidence">Download evidence JSON</button></div>
    <dl class="fact-grid">${facts.map(([k,v])=>`<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    ${limitContext(data)}
    <h3>Exact metering</h3><dl class="token-list">${Object.entries(e.details.usage).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${e.details.usage_reported_fields&&!e.details.usage_reported_fields.includes(k)?'Not reported':fmt(v)}</dd>`).join('')}</dl>
    <p class="note">Cached input is included in input; reasoning output is included in output. Source details are preserved without adding these subsets again.</p>
    <details open><summary>Execution and lineage</summary><dl class="fact-grid">${[['Response ID',e.response_id],['Task ID',e.thread_id],['Turn ID',e.turn_id],['Root turn ID',e.details.root_turn_id],['Execution session ID',e.details.execution_session_id],['Source task ID',e.details.source_thread_id],['Parent task',e.parent_id],['Session metadata ID',e.details.session_id],['Branch',e.details.branch],['Commit',e.details.commit],['Reasoning effort',e.details.effort],['Speed / service tier',e.details.speed],['Client version',e.details.cli_version],['Model provider',e.details.provider]].map(([k,v])=>`<dt>${k}</dt><dd class="mono">${esc(v||'Unavailable')}</dd>`).join('')}</dl>${e.thread_id?`<button data-thread="${esc(e.thread_id)}">Find records for this task</button>`:''}</details>
    <details><summary>Source observations (${data.observations.length})</summary>${data.observations.map(o=>`<div class="observation"><strong class="path">${esc(o.source)}</strong><small>Line ${o.line} · indexed ${esc(when(o.received_at))} UTC</small><small class="path">Source record SHA-256: ${esc(o.sha256)}</small></div>`).join('')}<p class="note">This is a hash of the source line at ingestion. It is not a provider signature. Original metering is retained; prompt bodies and credentials are not stored.</p></details>
    ${data.conflicts.length?`<details open><summary>Conflicting evidence (${data.conflicts.length})</summary><p class="form-error">Different counts were reported for this response. The first observed counts are retained. Review these records before treating the total as settled.</p>${data.conflicts.map(c=>`<div class="observation"><small class="path">${esc(c.source)} · line ${c.line} · SHA-256 ${esc(c.sha256)}</small><pre>${esc(JSON.stringify(JSON.parse(c.evidence),null,2))}</pre></div>`).join('')}</details>`:''}<details id="attribution-editor"><summary>Declare owner, project and purpose</summary><p>These are your declarations. They supplement the source and leave an audit trail; they do not alter its token counts.</p><form id="attribute-form"><input type="hidden" name="id" value="${e.id}"><label>Apply to<select name="apply_scope"><option value="record">This metering record</option>${e.thread_id?`<option value="task">All ${fmt(data.task_records)} currently indexed records in this task</option>`:''}</select><small>Task attribution replaces existing declarations on those records. Future records must be attributed separately.</small></label><label>Project<input name="project" value="${esc(a.project||e.project)}" maxlength="1000"></label><label>Responsible person or workload<input name="principal" value="${esc(a.principal||'')}" placeholder="e.g. Me / release-automation" maxlength="1000"></label><label>Purpose<textarea name="purpose" rows="3" maxlength="1000" placeholder="What was this work intended to achieve?">${esc(a.purpose||'')}</textarea></label><label>Reason for this attribution<textarea name="reason" rows="2" maxlength="2000" required placeholder="Why are you assigning or changing these details?"></textarea></label><p id="attribute-error" class="form-error" role="alert"></p><button class="primary" type="submit">Save attribution</button></form></details>
    <details><summary>Attribution history (${data.history.length})</summary>${data.history.length?data.history.map(h=>`<div class="observation"><strong>${esc(h.actor)} · ${esc(when(h.timestamp))} UTC</strong><p>${esc(h.reason)}</p><pre>${esc(JSON.stringify(JSON.parse(h.after_json),null,2))}</pre></div>`).join(''):'<p>No declarations have been added to this record.</p>'}</details>`;
  }catch(error){$('#detail-content').innerHTML=`<div class="dialog-head"><h2 id="detail-heading">Could not load evidence</h2><button data-close="detail" aria-label="Close record">×</button></div><p>${esc(error.message)}</p>`;}
}

document.addEventListener('click',async event=>{
  const button=event.target.closest('button,a');if(!button)return;
  try {
    if(button.dataset.sortTable){const table=button.dataset.sortTable,key=button.dataset.sortKey;sorts[table]=[key,sorts[table][0]===key&&sorts[table][1]==='asc'?'desc':'asc'];if(table==='limits')limitFilters.offset=0;else filters.offset=0;await load();}
    if(button.dataset.limitSource){limitFilters.source=button.dataset.limitSource;limitFilters.q='';limitFilters.plan='';limitFilters.range='all';limitFilters.offset=0;$('#detail').close();location.hash='limits';await load();}
    if(button.dataset.action==='limit-source-clear'){limitFilters.source='';limitFilters.offset=0;await load();}
    if(button.dataset.action==='limits-next'){limitFilters.offset+=50;await load();}
    if(button.dataset.action==='limits-previous'){limitFilters.offset=Math.max(0,limitFilters.offset-50);await load();}
    if(button.dataset.close)$('#'+button.dataset.close).close();
    if(button.dataset.event)await openDetail(button.dataset.event);
    if(button.dataset.activity){const evidence=await api('/api/activity-event?id='+encodeURIComponent(button.dataset.activity));evidence.details=JSON.parse(evidence.details);$('#detail-content').innerHTML=`<div class="dialog-head"><h2 id="detail-heading">Activity evidence</h2><button data-close="detail" aria-label="Close record">×</button></div><p class="note">Imported, source-declared evidence. An access-policy mismatch is not proof of theft.</p><dl class="fact-grid">${Object.entries(evidence).filter(([k])=>k!=='details').map(([k,v])=>`<dt>${esc(k)}</dt><dd class="path">${esc(v||'Unknown')}</dd>`).join('')}</dl><h3>Source references</h3><pre>${esc(JSON.stringify(evidence.details,null,2))}</pre>`;$('#detail').showModal();}
    if(button.dataset.project){filters.project=button.dataset.project;filters.offset=0;location.hash='ledger';await load();}
    if(button.dataset.thread){filters.q=button.dataset.thread;filters.offset=0;$('#detail').close();location.hash='ledger';await load();}
    if(button.dataset.ack){await api('/api/acknowledge',{id:button.dataset.ack});toast('Alert acknowledged.');await load();}
    if(button.dataset.action==='clear-project'){filters.project='';filters.offset=0;await load();}
    if(button.dataset.action==='previous'){filters.offset=Math.max(0,filters.offset-50);await load();}
    if(button.dataset.action==='next'){filters.offset+=50;await load();}
    if(button.dataset.action==='download-evidence'&&activeDetail){const blob=new Blob([JSON.stringify(activeDetail,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`evidence-${activeDetail.event.id.slice(0,12)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
    if(button.id==='add-source')editSource();
    if(button.dataset.sourceEdit)editSource(button.dataset.sourceEdit);
    if(button.dataset.sourceToggle){const source=state.sources.find(s=>s.id===button.dataset.sourceToggle);await api('/api/source/save',{...source,enabled:!source.enabled,reason:source.enabled?'Disable collection from this source.':'Enable collection from this source.'});toast('Source collection settings saved.');await load();}
    if(button.dataset.sourceRemove){await api('/api/source/remove',{id:button.dataset.sourceRemove});toast('Source removed. Indexed evidence is retained.');await load();}
    if(button.id==='open-import'){$('#import-error').textContent='';$('#import-dialog').showModal();}
    if(button.id==='scan'){await api('/api/scan',{});toast('Source refresh requested.');await load();}
    if(button.id==='enable-notifications'){if(!('Notification' in window)){toast('This browser does not support desktop notifications.');return;}const permission=await Notification.requestPermission();toast(permission==='granted'?'Desktop alerts enabled while this page is open.':'Desktop notifications were not enabled.');await load();}
  }catch(error){toast(error.message);}
});

let debounce;
document.addEventListener('input',event=>{if(event.target.id==='limit-search'){limitFilters.q=event.target.value;limitFilters.offset=0;clearTimeout(debounce);debounce=setTimeout(()=>load(),250);}if(event.target.id==='search'){filters.q=event.target.value;filters.offset=0;clearTimeout(debounce);debounce=setTimeout(()=>load(),250);}});
document.addEventListener('change',event=>{if(['limit-range','limit-plan'].includes(event.target.id)){limitFilters[event.target.id.replace('limit-','')]=event.target.value;limitFilters.offset=0;load();}if(['range','sort','granularity','from','to','by'].includes(event.target.id)){filters[event.target.id]=event.target.value;filters.offset=0;load();}});
document.addEventListener('submit',async event=>{
  const form=event.target, formId=form.getAttribute('id');
  if(!['attribute-form','import-form','policy-form','source-form'].includes(formId)&&!form.classList.contains('budget-form'))return;
  event.preventDefault();const submit=$('[type="submit"]',form);submit.disabled=true;
  try {
    const values=Object.fromEntries(new FormData(form));
    if(formId==='source-form') {$('#source-error').textContent='';await api('/api/source/save',{...values,enabled:form.elements.namedItem('enabled').checked});$('#source-dialog').close();toast('Source saved. Reachable folders will be checked automatically.');await load();}
    if(formId==='attribute-form') {$('#attribute-error').textContent='';const result=await api('/api/attribute',values);toast(`Attribution saved for ${fmt(result.changed_records)} records, each with an audit entry.`);await openDetail(values.id);await load();}
    if(form.classList.contains('budget-form')){await api('/api/budget',{project:form.dataset.project,tokens:Number(values.tokens),period:values.period});toast('Token budget saved.');await load();}
    if(formId==='policy-form'){ $('#policy-error').textContent=''; await api('/api/activity-policy',{scope:values.scope,reason:values.reason,devices:values.devices.split('\n').map(v=>v.trim()).filter(Boolean),networks:values.networks.split('\n').map(v=>v.trim()).filter(Boolean)});toast('Access policy saved; imported activity checked.');await load(); }
    if(formId==='import-form'){
      $('#import-error').textContent='';const file=values.file;if(!file.size||file.size>30*1024*1024)throw new Error('Choose a non-empty file up to 30 MB.');
      if(/auth|credential|secret|\.env/i.test(file.name))throw new Error('Authentication and credential files must not be imported.');
      const result=await api('/api/import',{scope:values.scope,name:file.name,content:await file.text()});
      $('#import-dialog').close();form.reset();toast(`${result.kind}: ${fmt(result.new_records)} new or revised records.${result.new_limit_snapshots?` ${fmt(result.new_limit_snapshots)} limit readings.`:''}${result.issues?.length?' Review source quality notices.':''}`);await load();
    }
  }catch(error){const el=formId==='attribute-form'?$('#attribute-error'):formId==='import-form'?$('#import-error'):formId==='policy-form'?$('#policy-error'):formId==='source-form'?$('#source-error'):null;if(el)el.textContent=error.message;else toast(error.message);}
  finally{submit.disabled=false;}
});
window.addEventListener('hashchange',()=>{filters.offset=0;load();});
load();if (!globalThis.ObservatoryBrowser) setInterval(()=>load(true),10000);
