'use strict';
function windowDuration(minutes) {
  if(minutes==null)return 'Duration unavailable';
  if(minutes===10080)return 'Weekly · 7 days';
  if(minutes%1440===0)return `${fmt(minutes/1440)} days`;
  if(minutes%60===0)return `${fmt(minutes/60)} hours`;
  return `${fmt(minutes)} minutes`;
}
function limitWindow(window, observed, reference, expanded=false) {
  if(!window)return '<span class="muted">Not reported</span>';
  const percent=window.used_percent,reset=window.resets_at;
  const passed=reset&&new Date(reset)<=new Date(reference);
  return `<div class="limit-window"><strong>${percent==null?'Usage unavailable':`${fmt(percent)}% used`}</strong>
    ${expanded&&percent!=null?`<progress max="100" value="${percent}" aria-label="${esc(windowDuration(window.window_minutes))}: ${percent}% used at observation"></progress><span>${fmt(100-percent)}% remaining at observation</span>`:''}
    <small>${esc(windowDuration(window.window_minutes))}</small><small>Reset: ${reset?esc(when(reset))+' UTC':'not reported'}</small>
    ${passed?`<small class="limit-expired">${expanded?'Reset time has passed; remaining now unknown.':'Reset time passed'}</small>`:''}
    ${expanded?`<small>Observed ${esc(when(observed))} UTC</small>`:''}</div>`;
}
function limitsView(data) {
  const latest=data.latest;
  return header('Limits & cycles','See the quota position recorded during your Codex / ChatGPT Work tasks.',badge('Historical readings','warning'))+
    `<div class="notice"><strong>Recorded headroom, with its reset window.</strong><p>Percentages describe a provider quota window, not a monthly bill or a percentage of tokens. Readings can cover usage outside the indexed projects. Account identity is not verified, so sources and tasks are not combined into an account balance.</p></div>
    <div class="filters"><label class="search"><span aria-hidden="true">⌕</span><input id="limit-search" type="search" aria-label="Search limit readings" placeholder="Find a task, source path or limit pool…" value="${esc(limitFilters.q)}"></label>
    <label class="select-label">Plan<select id="limit-plan">${[['pro','Pro'],['','All reported plans']].map(([v,t])=>`<option value="${v}" ${limitFilters.plan===v?'selected':''}>${t}</option>`).join('')}</select></label>
    <label class="select-label">Observed<select id="limit-range">${[['all','All recorded time'],['7','Last 7 days'],['30','Last 30 days']].map(([v,t])=>`<option value="${v}" ${limitFilters.range===v?'selected':''}>${t}</option>`).join('')}</select></label><span class="sort-hint">Click column headings to sort ↕</span></div>
    ${limitFilters.source?`<div class="filter-chip path">Source: ${esc(limitFilters.source)}<button data-action="limit-source-clear" aria-label="Clear limit source filter">×</button></div>`:''}`+
    (latest?`<section class="source-panel"><div class="section-heading"><h2>Latest recorded reading in this selection</h2>${badge(latest.plan||'Plan not reported','accent')}</div><p class="note">Observed ${esc(when(latest.timestamp))} UTC · ${esc(latest.limit_name||latest.limit_id||'Limit pool not reported')}. This is not a live balance.</p>
    <div class="limit-cards">${['primary','secondary'].map(slot=>`<article><h3>${slot==='primary'?'Primary':'Secondary'} window</h3>${limitWindow(latest.windows[slot],latest.timestamp,data.checked_at,true)}</article>`).join('')}</div>
    <p class="path"><strong>Source:</strong> ${esc(latest.source)} · line ${fmt(latest.line)}</p><p class="path"><strong>Task:</strong> ${esc(latest.thread_id||'Not reported')}</p></section>
    <div class="section-heading"><h2>Limit history</h2><span>${fmt(data.total)} readings in this selection</span></div>
    <p class="note">Primary and secondary are source labels. Their durations are reported individually; a missing window stays unknown. Copied logs retain separate provenance. Window columns sort by used percentage.</p>
    <div class="table-wrap" tabindex="0" aria-label="Limit history"><table class="limits-table"><thead><tr><th>Observed (UTC)</th><th>Plan</th><th>Limit pool</th><th>Primary window</th><th>Secondary window</th><th>Task</th><th>Source</th></tr></thead><tbody>${data.snapshots.map(r=>`<tr><td>${esc(when(r.timestamp))}<small>Historical reading</small></td><td>${esc(r.plan||'Not reported')}</td><td>${esc(r.limit_name||r.limit_id||'Not reported')}</td><td>${limitWindow(r.windows.primary,r.timestamp,data.checked_at)}</td><td>${limitWindow(r.windows.secondary,r.timestamp,data.checked_at)}</td><td class="path">${esc(r.thread_id||'Not reported')}</td><td class="path"><details><summary>${esc(r.source.split(/[\\/]/).at(-1))} · line ${fmt(r.line)}</summary><p>${esc(r.source)}</p><small>SHA-256: ${esc(r.sha256)}</small><small>Indexed ${esc(when(r.received_at))} UTC</small></details></td></tr>`).join('')}</tbody></table></div>
    <div class="table-footer"><span>Original limit readings are included in the complete evidence export.</span><div><span>${fmt(Math.min(data.offset+1,data.total))}–${fmt(Math.min(data.offset+50,data.total))} of ${fmt(data.total)}</span><button data-action="limits-previous" ${data.offset===0?'disabled':''} aria-label="Previous limit readings">←</button><button data-action="limits-next" ${data.offset+50>=data.total?'disabled':''} aria-label="Next limit readings">→</button></div></div>`:
    empty('No limit readings in this selection',state.progress.running?'The collector is checking existing logs for quota snapshots. Readings appear as files are indexed.':'Try all reported plans, clear the search, or connect a source containing Codex token_count rate_limits records. Missing limits cannot be reconstructed from token totals.'))+
    `<p class="note">Observation gaps and provider changes remain unknown. <a href="https://learn.chatgpt.com/docs/app-server" target="_blank" rel="noopener noreferrer">OpenAI documents usage percentage, window duration and reset time.</a></p>`;
}
function limitContext(data) {
  const rows=data.limit_context||[];
  return `<details ${rows.length?'open':''}><summary>Quota position near this record</summary><p class="note">The last reading at or before this record in the same source task and file. It is historical context; it does not measure this response’s share of the quota.</p>${rows.length?rows.map(r=>{
    const seconds=Math.max(0,(new Date(data.event.details.source_timestamp||data.event.timestamp)-new Date(r.timestamp))/1000);
    return `<div class="observation"><strong>${esc(r.plan||'Plan not reported')} · ${esc(r.limit_name||r.limit_id||'Pool not reported')}</strong><small>Observed ${esc(when(r.timestamp))} UTC · ${fmt(seconds)} seconds before this record</small><div class="limit-cards">${['primary','secondary'].map(slot=>`<article><h4>${slot==='primary'?'Primary':'Secondary'} window</h4>${limitWindow(r.windows[slot],r.timestamp,data.event.timestamp)}${r.windows[slot]?.resets_at&&new Date(r.windows[slot].resets_at)<=new Date(data.event.timestamp)?'<small class="limit-expired">Reset preceded this record; quota at this record is unknown.</small>':''}</article>`).join('')}</div><small class="path">${esc(r.source)} · line ${fmt(r.line)} · SHA-256 ${esc(r.sha256)}</small><button data-limit-source="${esc(r.source)}">View this source’s limit history</button></div>`;
  }).join(''):'<p>No earlier reading is available in this source task. Later readings are not assigned retrospectively.</p>'}</details>`;
}
