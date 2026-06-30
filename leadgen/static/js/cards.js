// ---- card ----
function chip(html,cls){return `<span class="chip ${cls||''}">${html}</span>`;}
const PL_STATUSES={new:{l:{uk:'Новий',ru:'Новый',en:'New'},c:'#71717A'},contacted:{l:{uk:'Написав',ru:'Написал',en:'Contacted'},c:'#38BDF8'},replied:{l:{uk:'Відповів',ru:'Ответил',en:'Replied'},c:'#F59E0B'},client:{l:{uk:'Клієнт',ru:'Клиент',en:'Client'},c:'#22C55E'},rejected:{l:{uk:'Відмова',ru:'Отказ',en:'Rejected'},c:'#F43F5E'}};
function pipelineBlock(l){const st=l.status||'new',tags=l.tags||[];
  const opts=Object.keys(PL_STATUSES).map(k=>`<option value="${k}" ${k===st?'selected':''}>${PL_STATUSES[k].l[lang]}</option>`).join('');
  return `<div class="pipeline-box">
    <div style="display:flex;align-items:center;gap:8px;font-size:12px">
      <span style="width:8px;height:8px;border-radius:50%;background:${PL_STATUSES[st].c};flex-shrink:0"></span>
      <select class="pl-status" style="flex:1;margin:0">${opts}</select>
    </div>
    <input class="pl-tags" placeholder="теги, через кому" value="${esc(tags.join(', '))}">
    <textarea class="pl-notes" rows="2" placeholder="нотатки…">${esc(l.notes||'')}</textarea>
  </div>`;}
async function savePipeline(id,fields){const lead=savedLeads.find(l=>l._id===id);if(lead)Object.assign(lead,fields);
  await fetch('/api/update_saved',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,...fields})});}
function initials(name){return (name||'?').split(/\s+/).filter(Boolean).slice(0,2).map(w=>(w[0]||'').toUpperCase()).join('')||'?';}
function scoreRingSvg(score,tier,size=50){
 const pct=Math.min(100,Math.max(0,Number(score)||0)),r=(size/2)-5,c=2*Math.PI*r,off=c*(1-pct/100);
 const col={hot:'#FB923C',warm:'#FBBF24',cold:'#A1A1AA'}[tier]||'#A1A1AA';
 return `<svg class="score-ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true"><circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="rgba(255,255,255,.14)" stroke-width="3"/><circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="${col}" stroke-width="3" stroke-linecap="round" stroke-dasharray="${c.toFixed(2)}" stroke-dashoffset="${off.toFixed(2)}" transform="rotate(-90 ${size/2} ${size/2})"/></svg>`;}
function card(l){const u=UI[lang],c=l.company||{},en=l.enrichment||{};
 const emails=en.emails||[],phones=en.phones||[],extraEmails=emails.length>1?emails.length-1:0;
 const socials=Object.entries(en.socials||{}).map(([k,v])=>`<a href="${esc(v)}" target="_blank" rel="noopener" class="chip chip-sky">${esc(k)}</a>`).join('');
 const tg=(en.telegram||[]).map(h=>chip(svg('send','w-3 h-3')+'@'+esc(h),'chip-sky')).join('');
 const dm=(en.decision_makers||[]).slice(0,3).map(p=>{
   const li=p.linkedin?`<a href="${esc(p.linkedin)}" target="_blank" rel="noopener" class="dm-link" title="LinkedIn">${svg('linkedin','w-3.5 h-3.5')}</a>`
     :(p.linkedin_search?`<a href="${esc(p.linkedin_search)}" target="_blank" rel="noopener" class="dm-link" title="LinkedIn search">${svg('linkedin','w-3.5 h-3.5')}</a>`:'');
   return `<div class="dm-row"><span class="dm-avatar" aria-hidden="true">${esc(initials(p.name))}</span><div class="dm-info"><span class="dm-name">${esc(p.name)}</span><span class="dm-role">${esc(p.role||'')}</span></div>${li}</div>`;}).join('');
 const autos=(l.automations||[]).map(a=>`
   <div class="lead-auto-item">
     <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
       <b style="font-size:13px;color:var(--accent-hover)">${esc(a.name)}</b>
       <span class="chip chip-violet" style="font-size:10px;font-weight:700">${a.score}</span>
     </div>
     <div class="text-muted" style="font-size:12px;margin-top:6px;line-height:1.45">${esc(a.pitch)}</div>
   </div>`).join('');
 const p=en.profile||{};
 const sizeBand=p.size_band||c.size_band;
 const sig=en.signals||{};
 const profChips=[
   c.rating?chip(svg('star','w-3 h-3')+c.rating+(c.reviews?` · ${c.reviews>999?(c.reviews/1000).toFixed(1)+'K':c.reviews}`:''),'chip-amber'):'',
   (p.employees||sizeBand)?chip(svg('user','w-3 h-3')+(p.employees?esc(p.employees)+' '+u.emp:esc(sizeBand)),'chip-violet'):'',
   sig.hiring?chip(svg('briefcase','w-3 h-3')+((sig.hiring_for&&sig.hiring_for.length)?esc(sig.hiring_for[0].slice(0,28)):(lang==='en'?'hiring':lang==='ru'?'наём':'наймає')),'chip-green'):'',
   p.founded?chip(esc(u.founded)+' '+esc(p.founded),''):'',
   (en.staff||[]).length?chip(svg('user','w-3 h-3')+(en.staff.length)+' '+esc(u.staff.toLowerCase()),''):'',
 ].filter(Boolean).join('');
 const templates=(l.templates||[]).slice(0,4).map(t=>`
   <a href="${esc(t.url)}" target="_blank" rel="noopener" class="lead-auto-item" style="display:block;text-decoration:none">
     <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px">
       <b style="font-size:13px;color:var(--accent-hover)">${esc(t.name)}</b>${svg('ext','w-3.5 h-3.5')}
     </div>
     <div class="text-muted" style="font-size:11px;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${(t.nodes||[]).slice(0,4).map(esc).join(' · ')}</div>
   </a>`).join('');
 const liked=l._saved;
 const sc=l.score||{}; const tierCls={hot:'hot',warm:'warm',cold:'cold'}[sc.tier]||'cold';
 const tierBar={hot:'tier-hot',warm:'tier-warm',cold:'tier-cold'}[sc.tier]||'tier-cold';
 const tierLabel={hot:{uk:'гарячий',ru:'горячий',en:'hot'},warm:{uk:'теплий',ru:'тёплый',en:'warm'},cold:{uk:'холодний',ru:'холодный',en:'cold'}}[sc.tier]?.[lang]||'';
 const scoreBadge=sc.score!=null?`<div class="score-pill ${tierCls}" title="${esc((sc.reasons||[]).join(', '))}">${scoreRingSvg(sc.score,sc.tier)}<span class="sc-num">${sc.score}</span><span class="sc-tier">${esc(tierLabel)}</span></div>`:'';
 const emailBlock=emails.length?`<div class="email-row"><a href="mailto:${esc(emails[0])}" class="email-main">${svg('mail','w-3.5 h-3.5')}${esc(emails[0])}</a>${extraEmails?`<button type="button" class="email-more" data-expand-emails="${esc(l._id)}">+${extraEmails}</button>`:''}</div>
   <div class="email-extra hidden" data-emails-for="${esc(l._id)}">${emails.slice(1).map(e=>`<a href="mailto:${esc(e)}" class="lead-contact">${svg('mail','w-3.5 h-3.5')}<span class="truncate">${esc(e)}</span></a>`).join('')}</div>`:'';
 const phoneBlock=phones.length?`<div class="phones-row">${svg('phone','w-3.5 h-3.5')}<span>${esc(phones.slice(0,2).join(' · '))}</span></div>`:'';
 const contacts=[emailBlock,phoneBlock,dm].filter(Boolean).join('');
 const foot=[socials,tg,c.website?`<a href="${esc(c.website)}" target="_blank" rel="noopener" class="chip">${svg('ext','w-3 h-3')}site</a>`:''].filter(Boolean).join('');
 return `<article class="lead-card ${tierBar}" data-id="${esc(l._id)}" data-hydrated="true">
   <div class="lead-card-head">
     ${scoreBadge}
     <div style="min-width:0;flex:1">
       <h3 class="lead-name">${esc(c.name)}</h3>
       <div class="lead-loc">${svg('pin','w-3 h-3')}<span>${esc(c.address||c.city||'')}</span></div>
     </div>
     <div class="lead-actions">
       <input type="checkbox" class="bulk-cb" style="width:16px;height:16px;accent-color:var(--accent);cursor:pointer" ${selectedIds.has(l._id)?'checked':''} title="Виділити">
       <button class="msg btn-icon" title="${u.write_msg}">${svg('pen','w-4 h-4')}</button>
       <button class="heart btn-icon" style="${liked?'color:#F43F5E;border-color:rgba(244,63,94,.4);background:rgba(244,63,94,.1)':''}" title="${liked?u.saved:u.save}">
         <svg class="w-4 h-4" viewBox="0 0 24 24" fill="${liked?'currentColor':'none'}" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${ICONS.heart}</svg></button>
     </div>
   </div>
   ${tab==='saved'?pipelineBlock(l):''}
   <div class="lead-card-body">
     ${profChips?`<div class="lead-chips">${profChips}</div>`:''}
     ${contacts?`<div style="margin-top:8px">${contacts}</div>`:''}
     ${autos?`<details class="lead-expand"><summary>${svg('sparkle','w-3.5 h-3.5')} ${u.autos} <span class="chip chip-violet" style="font-size:10px">${(l.automations||[]).length}</span></summary><div style="margin-top:8px">${autos}</div></details>`:''}
     ${templates?`<details class="lead-expand"><summary>${svg('sparkle','w-3.5 h-3.5')} ${u.templates} <span class="text-muted" style="font-weight:400;text-transform:none">n8n.io</span> <span class="chip chip-violet" style="font-size:10px">${(l.templates||[]).length}</span></summary><div style="margin-top:8px">${templates}</div></details>`:''}
   </div>
   ${foot?`<div class="lead-card-foot">${foot}</div>`:''}
 </article>`;}

const RENDER_CAP=250;  // avoid freezing on huge DBs — narrow with the search box
let searchLoading=false;
let searchInFlight=false;
let searchAbort=null;
let searchSeq=0;
window.getSearchSeq=()=>searchSeq;
let lastSearchPayload='';

function isHydratedLeadCard(el){
  return el&&el.classList.contains('lead-card')&&el.dataset.hydrated==='true'&&!!el.dataset.id;
}

function setSearchBusy(busy){
  searchLoading=busy;
  if(busy)searchInFlight=true;
  else searchInFlight=false;
  const run=$('#runCity'),map=$('#runMap'),cancel=$('#cancelSearch'),form=$('#searchForm');
  if(run){run.disabled=busy;run.setAttribute('aria-disabled',busy?'true':'false');}
  if(map){map.disabled=busy;map.setAttribute('aria-disabled',busy?'true':'false');}
  if(cancel){cancel.classList.toggle('hidden',!busy);}
  if(form){form.toggleAttribute('aria-busy',busy);}
  const prog=$('#searchProgress');
  if(prog){prog.classList.toggle('hidden',!busy);prog.setAttribute('aria-valuenow',busy?'50':'0');}
}

function beginSearchUI(){
  const u=UI[lang];
  setSearchBusy(true);
  $('#status').innerHTML=`<span class="spin"></span><span>${u.search_progress}</span>`;
  loadingCards();
}

function endSearchUI(){
  setSearchBusy(false);
  searchAbort=null;
}

function cancelSearch(){
  if(!searchInFlight)return;
  if(activeSearchJobId)fetch(`/api/jobs/${activeSearchJobId}/cancel`,{method:'POST'}).catch(()=>{});
  if(searchAbort)searchAbort.abort();
}

function normalizeSearchPayload(data){
  if(Array.isArray(data))return {leads:data,meta:null};
  return {leads:data.leads||[],meta:data.meta||null};
}

function formatSearchStatus(visibleCount){
  const u=UI[lang],m=lastSearchMeta;
  if(!m)return u.found(visibleCount,lastLeads.length);
  const req=m.requested_limit,ret=m.after_filters??m.returned??lastLeads.length;
  if(m.capped){
    const reason=m.cap_reason==='source_exhausted'?u.cap_source_exhausted:m.cap_reason==='dedupe_filter'?u.cap_dedupe:u.cap_pipeline;
    return u.limit_capped(ret,req,m.discovered_raw,m.deduped_before_enrichment,reason);
  }
  return u.limit_exact(ret,req);
}

const SEARCH_ENDPOINTS={'/api/find':'find','/api/find_around':'find_around','/api/find_multi':'find_multi','/api/find_expanded':'find_expanded'};
let activeSearchJobId=null;

function sleep(ms,signal){return new Promise((res,rej)=>{if(signal?.aborted)return rej(new DOMException('Aborted','AbortError'));const t=setTimeout(res,ms);signal?.addEventListener('abort',()=>{clearTimeout(t);rej(new DOMException('Aborted','AbortError'));},{once:true});});}

async function pollSearchJob(jobId,mySeq,signal){
  const u=UI[lang];
  while(true){
    if(signal?.aborted)throw new DOMException('Aborted','AbortError');
    if(mySeq!==searchSeq)throw new DOMException('Aborted','AbortError');
    const r=await fetch(`/api/jobs/${jobId}`,{signal});
    const job=await r.json();
    if(job.status==='done')return job.result;
    if(job.status==='failed')throw new Error(job.error||'Search failed');
    if(job.status==='cancelled')throw new DOMException('Aborted','AbortError');
    const label=job.status==='pending'?u.search_queued:u.search_running;
    $('#status').innerHTML=`<span class="spin"></span><span>${label}</span>`;
    await sleep(1200,signal);
  }
}

function loadingCards(){
  searchLoading=true;
  const out=$('#results');
  out.setAttribute('aria-busy','true');
  out.innerHTML=Array.from({length:4}).map(()=>`<article class="lead-card-skeleton" aria-hidden="true" tabindex="-1">
    <div class="skel" style="height:20px;width:66%;margin-bottom:12px"></div>
    <div class="skel" style="height:12px;width:50%;margin-bottom:8px"></div>
    <div class="skel" style="height:12px;width:75%;margin-bottom:16px"></div>
    <div class="skel" style="height:56px;width:100%"></div>
  </article>`).join('');
}

function clearSearchLoading(){
  searchLoading=false;
  const out=$('#results');
  if(out)out.removeAttribute('aria-busy');
}

function handleSearchCancelled(mySeq){
  if(mySeq!==searchSeq)return;
  clearSearchLoading();
  const u=UI[lang];
  $('#status').innerHTML=`<span class="text-muted">${u.search_cancelled}</span>`;
  if(lastLeads.length&&tab==='search')renderCurrent();
  else if(tab==='search')$('#results').innerHTML=emptyState(u.none);
}

function render(leads,total){const u=UI[lang],out=$('#results');
 clearSearchLoading();
 if(tab==='saved'&&!savedLeads.length){out.innerHTML=emptyState(u.empty_saved);return;}
 const shown=leads.slice(0,RENDER_CAP);
 if(!leads.length){out.innerHTML=emptyState(u.none);}
 else out.innerHTML=shown.map(card).join('')+(leads.length>RENDER_CAP?`<div class="render-cap-footer" data-render-cap="1">Показано ${RENDER_CAP} з ${leads.length}. Звузьте пошуком.</div>`:'');
 out.querySelectorAll('.lead-card[data-hydrated="true"]').forEach(el=>{
   const mb=el.querySelector('.msg'); if(mb)mb.onclick=e=>{e.stopPropagation();openOutreach(el.dataset.id);};
   const hb=el.querySelector('.heart'); if(hb)hb.onclick=e=>{e.stopPropagation();toggleSave(el.dataset.id);};
   const ss=el.querySelector('.pl-status');if(ss)ss.onchange=()=>savePipeline(el.dataset.id,{status:ss.value});
   const tg=el.querySelector('.pl-tags');if(tg)tg.onchange=()=>savePipeline(el.dataset.id,{tags:tg.value.split(',').map(s=>s.trim()).filter(Boolean)});
   const nt=el.querySelector('.pl-notes');if(nt)nt.onblur=()=>savePipeline(el.dataset.id,{notes:nt.value});
   const cb=el.querySelector('.bulk-cb');if(cb)cb.onchange=()=>{cb.checked?selectedIds.add(el.dataset.id):selectedIds.delete(el.dataset.id);updateBulkBar();};
   el.querySelectorAll('[data-expand-emails]').forEach(btn=>btn.onclick=e=>{e.stopPropagation();const box=el.querySelector(`[data-emails-for="${el.dataset.id}"]`);if(box){box.classList.toggle('hidden');btn.textContent=box.classList.contains('hidden')?('+'+(box.querySelectorAll('a').length)):'−';}});
   el.style.cursor='pointer';
 });
 updateBulkBar();
 if(tab==='search'&&lastLeads.length)$('#status').textContent=formatSearchStatus(leads.length);
 else if(tab==='all')$('#status').textContent=u.found(leads.length,allLeads.length);
 else if(tab!=='saved')$('#status').textContent='';
}
function emptyState(msg){return `<div class="empty-state" style="grid-column:1/-1">
 <div class="empty-icon">${svg('empty','w-7 h-7')}</div>
 <p>${esc(msg)}</p></div>`;}
function esc(s){return (s||'').toString().replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
window.esc=esc;

