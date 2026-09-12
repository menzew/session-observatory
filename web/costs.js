'use strict';

// Scenarios are local estimates. Original usage is never changed by these controls.
const costDefaults = {
  target:'recorded', tier:'standard', volume:'1', input_percent:'100', output_percent:'100',
  cache:'observed', cache_percent:'80', context:'auto',
  custom:{input:'0', cached:'0', write:'0', output:'0'},
};
const costComponentLabels = {input:'Fresh input', cached:'Reused input', write:'Cache creation', output:'Output & reasoning'};
let costScenario=structuredClone(costDefaults), costData=null, costDirty=false, costDraft=null;
let costDetailed=false, costBusy=false, costRevision=0;
const costOpen = new Set();
const dollars = value => value==null ? 'Not priced' : new Intl.NumberFormat('en-US', {
  style:'currency', currency:'USD', maximumFractionDigits:2,
}).format(Number(value));
const costModelName = name => name==='recorded' ? 'Current model mix' : name==='custom' ? 'Custom prices' : name.replace(/^gpt-/, 'GPT-').replace(/-(astra|sol|terra|luna)$/, (_,v)=>' '+v[0].toUpperCase()+v.slice(1));
const costOptions = (options,current) => options.map(([key,label])=>`<option value="${esc(key)}" ${current===key?'selected':''}>${esc(label)}</option>`).join('');
const costSelectionKey = () => JSON.stringify({filters,sort:sorts.costs,scenario:costScenario});
function costRequest() {
  const params=new URLSearchParams(query('costs'));
  params.set('by',filters.by);
  return {filters:Object.fromEntries(params), scenario:costScenario};
}
function costIsChanged(config) {
  return ['target','tier','volume','input_percent','output_percent','cache','context'].some(key=>String(config[key])!==costDefaults[key]);
}
function costAssumptions(config) {
  const parts=[costModelName(config.target)];
  if(config.target!=='custom')parts.push({standard:'standard prices',batch:'Batch prices',flex:'Flex prices',fast:'Fast prices'}[config.tier]);
  parts.push(config.cache==='none'?'no caching':config.cache==='percent'?`${config.cache_percent}% reused input`:'reported caching');
  if(Number(config.volume)!==1)parts.push(`${config.volume}× workload`);
  if(Number(config.input_percent)!==100)parts.push(`${config.input_percent}% input`);
  if(Number(config.output_percent)!==100)parts.push(`${config.output_percent}% output`);
  if(config.context!=='auto')parts.push(`assumed ${config.context}-context prices`);
  return parts.join(' · ');
}
function savedCosts() {
  try {
    const values=JSON.parse((globalThis.ObservatoryBrowser?.preferences || localStorage).getItem('observatory-cost-scenarios-v1')||'[]');
    return Array.isArray(values)?values.filter(v=>v&&typeof v.name==='string'&&v.scenario&&typeof v.scenario==='object').slice(0,20):[];
  } catch {return [];}
}
function costCoverage(data) {
  const rows=[['Current model mix',data.baseline],['Your what-if',data.scenario]];
  const acc=costIsChanged(data.scenario_config)?data.scenario:data.baseline;
  const excluded=data.records-acc.priced_records;
  if(!data.records)return '';
  return `<details class="cost-coverage ${excluded?'incomplete':''}" data-cost-details="coverage" ${costOpen.has('coverage')?'open':''}>
    <summary>${excluded?`Partial estimate · ${percent(data.tokens?acc.priced_tokens/data.tokens:null)} of tokens priced`:'All selected usage is priced'} <span>${excluded?`${fmt(excluded)} usage entries need more information`:'View coverage and assumptions'}</span></summary>
    <p>A usage entry is one recorded response or a change in a legacy token counter. One task can contain many entries. Unpriced usage is excluded from dollar totals.</p>
    ${rows.map(([label,item])=>`<p><strong>${label}:</strong> ${fmt(item.priced_records)} of ${fmt(data.records)} entries priced.${Object.entries(item.reasons).map(([reason,n])=>` ${fmt(n)}: ${esc(data.catalog.reason_labels[reason]||reason)}.`).join('')}</p>`).join('')}
    <p>${fmt(data.missing_cache_fields)} entries omit at least one cache counter; missing amounts are assumed zero. Estimates include text tokens only.</p>
  </details>`;
}
function costSummary(data) {
  const b=data.baseline,s=data.scenario,c=data.comparison,changed=costIsChanged(data.scenario_config);
  let difference='No comparable estimate';
  if(c.change!=null) {
    const n=Number(c.change);
    difference=n===0?'Same estimated cost':`${n<0?'Save':'Add'} ${dollars(Math.abs(n))}${c.percent==null?'':` (${percent(Math.abs(Number(c.percent))/100)})`}`;
  }
  return `<section class="cost-overview" aria-label="Cost estimate comparison">
    <div class="cost-current"><h2>Current model mix</h2><p class="cost-amount" data-cost-total="baseline">${dollars(b.total)}</p><p>At standard API prices, using the models and caching in your records.</p></div>
    <div class="cost-result ${changed?'is-comparison':''}">
      ${changed?`<h2>Your what-if <span>${esc(costModelName(data.scenario_config.target))}</span></h2><p class="cost-amount" data-cost-total="scenario">${dollars(s.total)}</p><p class="cost-difference">${difference}</p><p class="cost-comparable">${c.records?`Compared on the same ${fmt(c.records)} entries: ${dollars(c.baseline)} → ${dollars(c.scenario)}.`:'Choose a model or supply prices to compare the same usage.'}</p>`:
      '<h2>What would you change?</h2><p>Try another model, remove caching, or repeat this workload. Your comparison will appear here.</p>'}
    </div>
  </section>${costCoverage(data)}`;
}
function costControls(data) {
  const config=costDraft||costScenario;
  const fields=Object.keys(costComponentLabels);
  return `<section class="cost-controls" aria-labelledby="cost-controls-title">
    <div class="panel-heading"><h2 id="cost-controls-title">Try a what-if</h2><button data-cost-preset="reset" class="quiet">Reset assumptions</button></div>
    <div class="cost-presets" aria-label="Quick scenarios"><span>Try:</span><button data-cost-preset="no-cache">No caching</button><button data-cost-preset="double">Twice the workload</button><button data-cost-preset="shorter">Half the output</button><button data-cost-preset="terra">Use Terra</button></div>
    <form id="cost-form">
      <div class="cost-form-grid cost-basics">
        <label>Model<select name="target">${costOptions([['recorded','Keep the current model mix'],...Object.keys(data.catalog.prices).map(m=>[m,costModelName(m)]),['custom','Enter my own prices']],config.target)}</select></label>
        <label>Workload multiplier<input name="volume" type="number" min="0" max="1000" step="any" required value="${esc(config.volume)}"><small>1 = this workload. 2 = twice as many requests.</small></label>
        <label>Caching<select name="cache">${costOptions([['observed','Keep the recorded caching'],['none','No caching'],['percent','Choose how much input is reused']],config.cache)}</select></label>
        <label id="cost-cache-share" ${config.cache==='percent'?'':'hidden'}>Reused input (%)<input name="cache_percent" type="number" min="0" max="100" step="any" required value="${esc(config.cache_percent)}"></label>
      </div>
      <details class="cost-advanced" data-cost-details="advanced" ${costOpen.has('advanced')?'open':''}>
        <summary>Advanced assumptions <span>Processing speed, token sizes and context</span></summary>
        <div class="cost-form-grid">
          <label>Processing tier<select name="tier">${costOptions([['standard','Standard'],['batch','Batch — assume eligible'],['flex','Flex — assume eligible'],['fast','Fast']],config.tier)}</select><small>Applies to preset model prices.</small></label>
          <label>Input size per request (%)<input name="input_percent" type="number" min="0" max="1000" step="any" required value="${esc(config.input_percent)}"><small>100 keeps the recorded size.</small></label>
          <label>Output size per request (%)<input name="output_percent" type="number" min="0" max="1000" step="any" required value="${esc(config.output_percent)}"><small>Includes reasoning tokens.</small></label>
          <label>Context pricing<select name="context">${costOptions([['auto','Use each response’s size'],['short','Assume short-context prices'],['long','Assume long-context prices']],config.context)}</select><small>Forced assumptions can include legacy counters whose request size is unknown.</small></label>
        </div>
      </details>
      <section id="cost-custom" class="cost-custom" ${config.target==='custom'?'':'hidden'}>
        <h3>Your prices · USD per million tokens</h3><p>Enter all four rates. Zero means free. Processing and context price multipliers do not apply.</p>
        <div class="cost-form-grid">${fields.map(key=>`<label>${costComponentLabels[key]}<input name="custom_${key}" type="number" min="0" max="100000" step="any" required value="${esc(config.custom?.[key]??'0')}"></label>`).join('')}</div>
      </section>
      <p id="cost-error" class="form-error" role="alert"></p>
      <div class="cost-apply"><button class="primary" type="submit" ${costBusy?'disabled':''}>${costBusy?'Calculating…':'Update estimate'}</button><span id="cost-draft-status" role="status">${costDirty?'Changes not applied yet.':'Change assumptions, then update the estimate.'}</span></div>
    </form>
    <p class="cost-applied">Showing: ${esc(costAssumptions(data.scenario_config))}.</p>
  </section>`;
}
function costComposition(data) {
  const acc=data.scenario,total=Number(acc.total||0);
  let offset=0;
  const arcs=Object.keys(costComponentLabels).map((key,i)=>{
    const share=total?Number(acc.components[key])/total*100:0,start=offset;offset+=share;
    return share?`<circle class="pie-segment palette-${i}" cx="100" cy="100" r="72" pathLength="100" fill="none" stroke-width="28" stroke-dasharray="${share} ${100-share}" stroke-dashoffset="${-start}" transform="rotate(-90 100 100)"><title>${costComponentLabels[key]}: ${dollars(acc.components[key])}</title></circle>`:'';
  }).join('');
  return `<section class="analytics-panel cost-mix"><h2>What makes up the cost?</h2><div class="cost-mix-layout">
    ${total?`<svg class="donut" viewBox="0 0 200 200" role="img" aria-label="Estimated cost shares by token type">${arcs}<text x="100" y="104" text-anchor="middle" class="donut-caption">Token cost</text></svg>`:''}
    <dl class="cost-components">${Object.keys(costComponentLabels).map((key,i)=>`<dt><i class="swatch palette-${i}" aria-hidden="true"></i>${costComponentLabels[key]}</dt><dd title="${esc(acc.components[key])} USD">${acc.total==null?'—':dollars(acc.components[key])}<small>${total?percent(Number(acc.components[key])/total):'—'}</small></dd>`).join('')}</dl>
    </div><p class="chart-footnote">Reused input is the cached part of input. Reasoning is already part of output. Each token is counted once.</p></section>`;
}
function costAlternatives(data) {
  return `<section class="analytics-panel"><div class="panel-heading"><h2>Compare model prices</h2></div>
    ${data.alternatives.map(alt=>`<button class="cost-alternative" data-cost-target="${esc(alt.model)}"><span>${esc(costModelName(alt.model))}<small>${percent(data.tokens?alt.priced_tokens/data.tokens:null)} of tokens priced</small></span><strong>${dollars(alt.total)} <small>Try this model →</small></strong></button>`).join('')}
    <p class="chart-footnote">Each estimate puts the selected workload on one model using your applied assumptions. Actual token use, caching and quality may change.</p>
  </section>`;
}
function costGroupLabel(data,value) {
  return data.by==='project'||data.by==='directory'?projectName(value):readableDimension(data.by,value);
}
function costBreakdown(data) {
  const rows=data.groups.slice(filters.offset,filters.offset+50),fields=Object.keys(costComponentLabels);
  const priced=data.ranking.filter(r=>r.scenario!=null),max=Math.max(...priced.map(r=>Number(r.scenario)),0)||1;
  return `<section class="cost-breakdown"><div class="panel-heading"><h2>Where does it go?</h2><label class="trend-split">Group by <select id="by">${costOptions(Object.entries(dimensionLabels),filters.by)}</select></label></div>
    <div class="cost-ranking">${priced.slice(0,8).map(r=>`<button class="rank-row" data-cost-group="${esc(r.dimension)}" title="Explore ${esc(r.dimension)}"><span class="rank-label">${esc(costGroupLabel(data,r.dimension))}</span><strong>${dollars(r.scenario)}</strong><svg viewBox="0 0 400 6" preserveAspectRatio="none" aria-hidden="true"><rect width="400" height="6" class="bar-track"/><rect width="${Number(r.scenario)/max*400}" height="6" class="bar-value"/></svg></button>`).join('')}</div>
    <div class="cost-table-toolbar"><p>Choose a row to explore its usage. Sort with any column heading.</p><label><input id="cost-details-toggle" type="checkbox" ${costDetailed?'checked':''}> Show token cost columns</label></div>
    <div class="table-wrap" tabindex="0" aria-label="Cost breakdown"><table class="cost-table ${costDetailed?'is-detailed':''}"><thead><tr><th>${esc(dimensionLabels[data.by])}</th><th class="number">Recorded tokens</th><th class="number">Current mix · USD</th><th class="number">What-if · USD</th>${costDetailed?fields.map(key=>`<th class="number">${costComponentLabels[key]} · USD</th>`).join(''):''}<th class="number">Unpriced entries</th></tr></thead><tbody>
    ${rows.map(r=>`<tr><td class="path"><button class="record-link" data-cost-group="${esc(r.dimension)}" title="${esc(r.dimension)}">${esc(costGroupLabel(data,r.dimension))}</button></td><td class="number">${fmt(r.tokens)}</td><td class="number" title="${esc(r.baseline)} USD">${dollars(r.baseline)}</td><td class="number" title="${esc(r.scenario)} USD">${dollars(r.scenario)}</td>${costDetailed?fields.map(key=>`<td class="number" title="${esc(r[key])} USD">${r.scenario==null?'—':dollars(r[key])}</td>`).join(''):''}<td class="number">${fmt(r.unpriced_records)}</td></tr>`).join('')}
    </tbody></table></div>
    <div class="table-footer"><a href="#ledger">Inspect matching usage →</a><div><span>${fmt(filters.offset+1)}–${fmt(Math.min(filters.offset+50,data.groups.length))} of ${fmt(data.groups.length)}</span><button data-cost-action="previous" ${filters.offset===0?'disabled':''} aria-label="Previous cost groups">←</button><button data-cost-action="next" ${filters.offset+50>=data.groups.length?'disabled':''} aria-label="Next cost groups">→</button></div></div></section>`;
}
function costSavedView() {
  return `<details class="cost-saved" data-cost-details="saved" ${costOpen.has('saved')?'open':''}><summary>Save or export this estimate</summary>
    <p>${globalThis.ObservatoryBrowser?'Assumptions are added to this workspace. Click Save in this browser or download a backup to keep them.':'Saved assumptions stay in this browser.'} Exports include the complete filtered breakdown.</p>
    <div class="cost-save-row"><input id="cost-scenario-name" aria-label="Scenario name" maxlength="80" placeholder="Name these assumptions"><button data-cost-action="save">Save assumptions</button></div>
    <div class="cost-saved-list">${savedCosts().map((item,i)=>`<span><button data-cost-load="${i}">${esc(item.name)}</button><button data-cost-delete="${i}" aria-label="Delete saved scenario ${esc(item.name)}">×</button></span>`).join('')||'<small>No saved scenarios yet.</small>'}</div>
    <div class="cost-downloads"><button data-cost-action="csv">Download cost CSV</button><button data-cost-action="json">Download full calculation</button></div>
    <small>CSV contains all groups and token cost columns. The full calculation also includes prices, assumptions, coverage and filters.</small>
  </details>`;
}
function costView(data) {
  costData=data;
  return header('Cost analysis','What would your recorded usage cost through the API?',badge('Estimate · USD','warning'))+filterBar(query(),true)+
    '<p class="cost-intro">A price estimate for recorded text tokens. Your ChatGPT subscription and actual provider bills are separate.</p>'+
    (data.records?costSummary(data)+costControls(data)+`<div class="analytics-grid cost-charts">${costComposition(data)}${costAlternatives(data)}</div>`+costBreakdown(data)+costSavedView():empty('No usage in this selection','Choose a wider period or clear your filters. To get started, add a Codex folder in Sources & coverage or import the included synthetic example.'))+
    costMethod(data)+`<p class="cost-source">Prices checked ${esc(data.catalog.checked_at)} · <a href="${esc(data.catalog.source)}" target="_blank" rel="noopener noreferrer">Official rate source</a> · <a href="#provider">Imported provider costs</a></p>`;
}

function costMethod(data) {
  const fields=Object.keys(costComponentLabels);
  return `    <details class="analytics-method cost-method" data-cost-details="method" ${costOpen.has('method')?'open':''}><summary>How this is calculated</summary><p>Verified rate snapshot: ${esc(data.catalog.checked_at)}. Current prices are applied hypothetically to historical usage; this does not reconstruct old invoices. GPT-5.6 Sol has promotional pricing documented through at least 21 November 2026. Unknown model names are not guessed; only the documented gpt-5.6 alias maps to Sol.</p><div class="rate-cards">${Object.entries(data.catalog.prices).map(([model,rates])=>`<article><h3>${esc(model)}</h3><p>${fields.map(k=>`${esc(costComponentLabels[k])}: $${esc(rates[k])}`).join(' · ')} per million tokens.</p></article>`).join('')}</div><p>For the preset models, input above 272,000 tokens selects long-context rates: input, cached reads and cache writes ×2, output ×1.5. Batch and Flex use half Standard rates; Fast uses double. These are assumptions about processing, not the tier observed in the original logs. Auto mode requires native response evidence and excludes requests exceeding the preset 1.05M combined context or 128k output limits.</p><p>Forced short/long context modes treat counts as token volumes at the chosen rates, including legacy deltas, and do not establish request eligibility. Custom prices are flat rates: processing-tier and context multipliers are ignored, although auto mode still requires native records.</p><p>${fmt(data.missing_cache_fields)} selected entries lack one or both cache-field declarations; missing amounts are assumed zero. When a cached-read target is set, the observed write share of noncached input is preserved. Disabling caching removes both reads and writes. Overlapping cache categories are left unpriced. Workload repetitions multiply costs after per-request input/output and context decisions.</p><p>Formula: (ordinary input × input rate + cached reads × cached rate + cache writes × write rate + output × output rate) ÷ 1,000,000, then processing and workload multipliers. Savings or increases compare only source entries priced in both scenarios. No tools, storage, media-specific charges, regional uplifts, taxes, credits, discounts or subscription charges are included. <a href="${data.catalog.source}" target="_blank" rel="noopener noreferrer">Review the official pricing source</a>.</p></details>`;
}

function costDownload(name,body,type) {
  const url=URL.createObjectURL(new Blob([body],{type}));
  const link=document.createElement('a');link.href=url;link.download=name;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function costFormValues(form) {
  const values=Object.fromEntries(new FormData(form));
  return Object.fromEntries(Object.keys(costDefaults).map(key=>[key,key==='custom'?
    Object.fromEntries(Object.keys(costComponentLabels).map(k=>[k,values['custom_'+k]])):values[key]]));
}
function costKeepDraft(event) {
  const form=event.target.closest('#cost-form');
  if(!form)return;
  costDraft=costFormValues(form);costDirty=true;
  $('#cost-draft-status').textContent='Changes not applied yet.';
  $('#cost-custom').hidden=costDraft.target!=='custom';
  $('#cost-cache-share').hidden=costDraft.cache!=='percent';
}
function costRenderLocal() {
  if(!costData||location.hash!=='#costs')return;
  const focus=document.activeElement?.id;
  $('#main').innerHTML=costView(costData);installSorting();
  if(focus)document.getElementById(focus)?.focus();
}
async function costCalculate(next) {
  const revision=++costRevision,previous=costScenario,submitted=JSON.stringify(next);
  costScenario=next;costBusy=true;filters.offset=0;
  const key=costSelectionKey();
  const form=$('#cost-form'),button=form?.querySelector('[type="submit"]');
  if(button){button.disabled=true;button.textContent='Calculating…';}
  if($('#cost-error'))$('#cost-error').textContent='';
  try {
    const data=await api('/api/cost-analysis',costRequest());
    if(revision!==costRevision)return;
    // An intervening filter change needs a new calculation; an untouched result can be rendered directly.
    const sameSelection=key===costSelectionKey();
    costScenario=data.scenario_config;
    if(!costDraft||JSON.stringify(costDraft)===submitted){costDraft=null;costDirty=false;}
    costBusy=false;
    if(location.hash==='#costs')await load(false,sameSelection?{data,key:costSelectionKey()}:null);
  } catch(error) {
    if(revision!==costRevision)return;
    costScenario=previous;costBusy=false;
    if($('#cost-error'))$('#cost-error').textContent=error.message;else toast(error.message);
  } finally {
    if(revision===costRevision)costBusy=false;
    if(button?.isConnected){button.disabled=false;button.textContent='Update estimate';}
  }
}
document.addEventListener('input',costKeepDraft);
document.addEventListener('change',event=>{
  costKeepDraft(event);
  if(event.target.id==='cost-details-toggle'){
    costDetailed=event.target.checked;
    if(!costDetailed&&Object.keys(costComponentLabels).includes(sorts.costs[0]))sorts.costs=['scenario','desc'];
    // Apply the selected global ordering when hiding a formerly sorted detail column.
    load();
  }
});
document.addEventListener('toggle',event=>{
  if(!event.target.matches('details[data-cost-details]')||!event.target.isConnected)return;
  const key=event.target.dataset.costDetails;
  if(event.target.open)costOpen.add(key);else costOpen.delete(key);
},true);
document.addEventListener('submit',event=>{
  if(event.target.id!=='cost-form')return;
  event.preventDefault();costCalculate(costFormValues(event.target));
});
document.addEventListener('click',async event=>{
  const el=event.target.closest('[data-cost-preset],[data-cost-target],[data-cost-group],[data-cost-action],[data-cost-load],[data-cost-delete]');
  if(!el)return;
  try {
    if(el.dataset.costPreset||el.dataset.costTarget||el.hasAttribute('data-cost-load')){
      let next;
      if(el.hasAttribute('data-cost-load'))next={...structuredClone(costDefaults),...structuredClone(savedCosts()[Number(el.dataset.costLoad)].scenario)};
      else if(el.dataset.costTarget)next={...costScenario,target:el.dataset.costTarget};
      else {
        next=structuredClone(costDefaults);
        const key=el.dataset.costPreset;
        if(key==='no-cache')next.cache='none';
        if(key==='double')next.volume='2';
        if(key==='shorter')next.output_percent='50';
        if(key==='terra')next.target='gpt-5.6-terra';
      }
      costDraft=null;costDirty=false;
      return await costCalculate(next);
    }
    if(el.hasAttribute('data-cost-group')){
      filters.facets={...(filters.facets||{}),[costData.by]:el.dataset.costGroup};
      filters.by=({project:'model',model:'task',task:'day'})[costData.by]||'task';
      filters.offset=0;return await load();
    }
    if(el.hasAttribute('data-cost-delete')){
      const saved=savedCosts();saved.splice(Number(el.dataset.costDelete),1);
      (globalThis.ObservatoryBrowser?.preferences || localStorage).setItem('observatory-cost-scenarios-v1',JSON.stringify(saved));return costRenderLocal();
    }
    const action=el.dataset.costAction;
    if(action==='save'){
      const name=$('#cost-scenario-name').value.trim();
      if(!name){toast('Name the scenario first.');$('#cost-scenario-name').focus();return;}
      const saved=savedCosts().filter(s=>s.name!==name);
      saved.unshift({name,scenario:costData.scenario_config,price_snapshot:costData.catalog.checked_at});
      (globalThis.ObservatoryBrowser?.preferences || localStorage).setItem('observatory-cost-scenarios-v1',JSON.stringify(saved.slice(0,20)));
      costRenderLocal();toast(globalThis.ObservatoryBrowser?'Assumptions added to this workspace. Save or download a backup to keep them.':'Applied assumptions saved in this browser.');return;
    }
    if(action==='json')return costDownload('observatory-cost-scenario.json',JSON.stringify(costData,null,2),'application/json');
    if(action==='csv'){
      const fields=['dimension','records','tokens','baseline','scenario','input','cached','write','output','unpriced_records'];
      const cell=value=>'"'+String(typeof value==='string'&&['=','+','-','@'].includes(value.trimStart()[0])?"'"+value:value??'').replaceAll('"','""')+'"';
      const lines=[['currency',...fields],...costData.groups.map(r=>['USD',...fields.map(k=>r[k])])].map(row=>row.map(cell).join(',')).join('\r\n');
      return costDownload('observatory-cost-breakdown.csv',lines,'text/csv');
    }
    if(action==='previous')filters.offset=Math.max(0,filters.offset-50);
    if(action==='next')filters.offset+=50;
    await load();
  } catch(error){toast(error.message);}
});
