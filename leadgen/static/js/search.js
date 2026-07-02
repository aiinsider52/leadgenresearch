// ---- save ----
 async function toggleSave(id){const pool=tab==='saved'?savedLeads:lastLeads;const lead=pool.find(l=>l._id===id);if(!lead)return;
 if(lead._saved){await fetch('/api/unsave',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});}
 else{await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lead})});}
 const v=!lead._saved;[...lastLeads,...savedLeads].filter(l=>l._id===id).forEach(l=>l._saved=v);
 if(tab==='saved'){savedLeads=savedLeads.filter(l=>l._saved);renderCurrent();} else renderCurrent();
 refreshSavedCount();refreshKpis();}
async function loadSaved(){savedLeads=await (await fetch('/api/saved')).json();renderCurrent();}
async function refreshSavedCount(){const d=await (await fetch('/api/saved')).json();$('#savedCount').textContent=d.length?d.length:'';}

// ---- search ----
function sparkFromSeed(seed,n){const out=[];let v=Math.max(1,seed*.7);for(let i=0;i<n;i++){v=Math.max(0,v+(Math.sin(seed*12.7+i*1.3)*.08+.03)*Math.max(seed,1));out.push(v);}return out;}
function drawSpark(svgId,values,color,hero){
  const el=document.getElementById(svgId);if(!el)return;
  const w=100,h=36,p=2,max=Math.max(...values,1),min=Math.min(...values,0),r=max-min||1;
  const pts=values.map((v,i)=>{const x=p+(i/(values.length-1||1))*(w-p*2);const y=h-p-((v-min)/r)*(h-p*2);return [x,y];});
  const line=pts.map(pt=>pt.join(',')).join(' ');
  const area=pts.length?`${p},${h} ${line} ${w-p},${h}`:'';
  const stroke=hero?'rgba(196,181,253,.95)':color;
  const last=pts[pts.length-1];
  const gradId='g'+svgId.replace(/[^a-z]/gi,'');
  el.innerHTML=`<defs><linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${hero?'rgba(255,255,255,.35)':color}" stop-opacity=".45"/><stop offset="100%" stop-opacity="0"/></linearGradient></defs>
  ${area?`<polygon points="${area}" fill="url(#${gradId})"/>`:''}
  <polyline points="${line}" fill="none" stroke="${stroke}" stroke-width="${hero?2.2:1.8}" stroke-linecap="round" stroke-linejoin="round"/>
  ${last?`<circle cx="${last[0]}" cy="${last[1]}" r="3.2" fill="${stroke}" style="filter:drop-shadow(0 0 4px ${stroke})"/>`:''}`;}
const kpiAnim={};
function countUp(el,target,dur=900){
 if(!el)return;
 const start=parseInt(el.dataset.val||el.textContent,10)||0;
 if(kpiAnim[el.id])cancelAnimationFrame(kpiAnim[el.id]);
 if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){el.textContent=target;el.dataset.val=target;return;}
 const t0=performance.now();
 (function frame(t){
  const p=Math.min(1,(t-t0)/dur),ease=1-Math.pow(1-p,3),v=Math.round(start+(target-start)*ease);
  el.textContent=v;el.dataset.val=v;
  if(p<1)kpiAnim[el.id]=requestAnimationFrame(frame);
 })(t0);}
async function refreshKpis(){
  try{const s=await (await fetch('/api/stats')).json();
    const hot=(s.by_tier||{}).hot||0,total=s.total_leads??0,email=s.with_email??0,saved=s.saved??0;
    countUp($('#kpiTotal'),total);countUp($('#kpiEmail'),email);countUp($('#kpiHot'),hot);countUp($('#kpiSaved'),saved);
    const emailRate=total?Math.round(email/total*100):0;
    const trendEl=$('#kpiTotalTrend');if(trendEl)trendEl.textContent=emailRate?`↑ ${emailRate}% email`:'—';
    drawSpark('sparkTotal',sparkFromSeed(total,12),'#7C5CFF',true);
    drawSpark('sparkEmail',sparkFromSeed(email,12),'#34D399',false);
    drawSpark('sparkHot',sparkFromSeed(hot,12),'#F97316',false);
    drawSpark('sparkSaved',sparkFromSeed(saved,12),'#38BDF8',false);
  }catch(e){}}
async function runSearch(url,body){
 const u=UI[lang];
 const payloadKey=url+'\0'+JSON.stringify(body);
 if(searchInFlight&&payloadKey===lastSearchPayload)return;
 if(searchInFlight&&searchAbort)searchAbort.abort();
 searchInFlight=true;
 lastSearchPayload=payloadKey;
 searchSeq++;
 const mySeq=searchSeq;
 tab='search';paintTabs();
 searchAbort=new AbortController();
 beginSearchUI();
 const reqBody={...body,search_seq:mySeq};
 const endpoint=SEARCH_ENDPOINTS[url]||'find';
 try{
  const start=await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({endpoint,params:reqBody,filters:{},search_seq:mySeq}),signal:searchAbort.signal});
  if(mySeq!==searchSeq)return;
  const started=await start.json();
  if(!start.ok)throw new Error(started&&started.error?started.error:'HTTP '+start.status);
  activeSearchJobId=started.job_id;
  const data=await pollSearchJob(started.job_id,mySeq,searchAbort.signal);
  if(mySeq!==searchSeq)return;
  const packed=normalizeSearchPayload(data);
  lastLeads=packed.leads;
  lastSearchMeta=packed.meta;
  renderCurrent();
  refreshKpis();
  refreshBudget();
 }catch(e){
  if(e&&e.name==='AbortError'){handleSearchCancelled(mySeq);return;}
  if(mySeq!==searchSeq)return;
  clearSearchLoading();
  $('#status').innerHTML=`<span class="text-rose-500">⚠ ${esc(e.message||e)}</span>`;
  $('#results').innerHTML=emptyState(u.none||'Помилка');
 }finally{
  if(mySeq===searchSeq){activeSearchJobId=null;endSearchUI();}
 }}
// segmented source control
const SOURCES=[
  {v:'all_sources',ic:'sparkle',label:'All',hint:{uk:'усі джерела · раннє об’єднання',ru:'все источники · раннее объединение',en:'all sources · early merge'}},
  {v:'brave_places',ic:'search',label:'Brave',hint:{uk:'200M+ місць · Brave Places',ru:'200M+ мест · Brave Places',en:'200M+ places · Brave Places'}},
  {v:'brave_intent',ic:'target',label:'Intent',hint:{uk:'тендери · найм · expansion',ru:'тендеры · найм · expansion',en:'tenders · hiring · expansion'}},
  {v:'osm',ic:'map',label:'OSM',hint:{uk:'швидко, безкоштовно · фіз. місця',ru:'быстро, бесплатно · физ. места',en:'fast, free · physical places'}},
  {v:'gmaps',ic:'pin',label:'Maps',hint:{uk:'рейтинги, відгуки, сайти',ru:'рейтинги, отзывы, сайты',en:'ratings, reviews, sites'}},
  {v:'instagram',ic:'instagram',label:'IG',hint:{uk:'засновники + email (Apify)',ru:'основатели + email (Apify)',en:'founders + email (Apify)'}},
  {v:'facebook',ic:'facebook',label:'FB',hint:{uk:'Facebook сторінки · email, сайт (Apify)',ru:'Facebook страницы · email, сайт (Apify)',en:'Facebook pages · email, site (Apify)'}},
  {v:'jobs',ic:'briefcase',label:'Jobs',hint:{uk:'сигнали найму · вакансія + контакт (LinkedIn)',ru:'сигналы найма · вакансия + контакт',en:'hiring signals · job + contact'}},
  {v:'dou',ic:'briefcase',label:'DOU',hint:{uk:'укр. вакансії DOU.ua · компанія + роль',ru:'укр. вакансии DOU.ua',en:'UA jobs DOU.ua'}},
  {v:'djinni',ic:'briefcase',label:'Djinni',hint:{uk:'IT вакансії Djinni.co',ru:'IT вакансии Djinni',en:'Djinni tech jobs'}},
  {v:'workua',ic:'briefcase',label:'Work',hint:{uk:'Work.ua вакансії',ru:'Work.ua',en:'Work.ua jobs'}},
  {v:'robota',ic:'briefcase',label:'Robota',hint:{uk:'Robota.ua вакансії',ru:'Robota.ua',en:'Robota.ua jobs'}},
  {v:'linkedin_people',ic:'linkedin',label:'LI',hint:{uk:'LinkedIn люди (Apify)',ru:'LinkedIn люди',en:'LinkedIn people (Apify)'}},
  {v:'web_discovery',ic:'globe',label:'Web',hint:{uk:'Brave + AI — весь інтернет',ru:'Brave + AI поиск',en:'Brave + AI web discovery'}},
  {v:'apify_gmaps',ic:'database',label:'DB',hint:{uk:'готова Maps база · підтримувані країни',ru:'готовая Maps база · поддерживаемые страны',en:'prebuilt Maps DB · supported countries'}},
];
let sourceMode=localStorage.getItem('lg_src')||'all_sources';
let budgetState=null;
const SOURCE_QUICK=['all_sources','brave_places','osm','gmaps','jobs','web_discovery'];

function isSourceBlocked(src){
  if(!budgetState)return false;
  if(src==='all_sources')return false;
  return (budgetState.unavailable_sources||[]).includes(src);
}

function fmtBudget(tpl,row){
  return tpl.replace('%s',row.spent_usd).replace('%s',row.cap_usd);
}

function paintBudgetBanner(u){
  const el=$('#budgetBanner'),t=UI[lang];
  if(!el||!u.budget)return;
  budgetState=u.budget;
  const blocked=u.budget.blocked_providers||[];
  if(!blocked.length&&!u.budget.degraded_all_sources){el.classList.add('hidden');el.innerHTML='';return;}
  const p=u.budget.providers||{};
  const lines=[`<div class="budget-banner-title">⚠ ${esc(t.budget_banner_title)}</div>`];
  if(p.apify?.blocked)lines.push(esc(fmtBudget(t.budget_apify,p.apify)));
  if(p.brave?.blocked)lines.push(esc(fmtBudget(t.budget_brave,p.brave)));
  if(p.openai?.blocked)lines.push(esc(fmtBudget(t.budget_openai,p.openai)));
  if(sourceMode==='all_sources'&&u.budget.degraded_all_sources)lines.push(esc(t.budget_all_degraded));
  lines.push(`<div class="budget-banner-hint">${esc(t.budget_free_hint)}</div>`);
  el.innerHTML=lines.join('');
  el.classList.remove('hidden');
  el.classList.toggle('warn',blocked.length===1);
}

function paintBudgetEnrichToggles(){
  if(!budgetState)return;
  const dis=budgetState.enrich_brave_disabled;
  ['bravePeople','braveNews','braveIntent'].forEach(id=>{
    const el=$('#'+id);if(!el)return;
    el.disabled=!!dis;
    if(dis)el.checked=false;
    const lbl=el.closest('label');if(lbl)lbl.style.opacity=dis?'.45':'';
  });
}

function maybeFallbackSource(){
  if(!isSourceBlocked(sourceMode))return;
  const fallback=SOURCE_QUICK.find(s=>!isSourceBlocked(s))||'osm';
  setSource(fallback,true);
}

async function refreshBudget(){
  try{
    const u=await (await fetch('/api/usage')).json();
    paintBudgetBanner(u);
    paintBudgetEnrichToggles();
    paintSources();
    maybeFallbackSource();
  }catch(e){}
}

function setSource(v,silent){
  if(isSourceBlocked(v)){
    if(!silent)$('#status').innerHTML=`<span class="text-rose-500">⚠ ${esc(UI[lang].budget_source_blocked)}</span>`;
    return;
  }
  sourceMode=v;$('#source').value=v;localStorage.setItem('lg_src',v);
  if(sourceMode==='instagram')$('#adv').classList.remove('hidden');
  paintSources();updateSrcHint();paintIgMode();}
function paintSources(){
  const sel=$('#sourceSelect');
  if(sel){sel.innerHTML=SOURCES.map(s=>{
    const off=isSourceBlocked(s.v);
    return `<option value="${s.v}" ${s.v===sourceMode?'selected':''} ${off?'disabled':''}>${s.label}${off?' 🚫':''}</option>`;}).join('');
    if(!sel._bound){sel._bound=true;sel.onchange=e=>setSource(e.target.value);}}
  const chips=$('#sourceSeg');
  if(chips){chips.innerHTML=SOURCE_QUICK.map(v=>{
    const s=SOURCES.find(x=>x.v===v);if(!s)return '';
    const off=isSourceBlocked(v);
    return `<button type="button" data-src="${v}" class="src-chip ${v===sourceMode?'on':''} ${off?'disabled':''}" ${off?'disabled':''} title="${off?UI[lang].budget_source_blocked:''}">${svg(s.ic,'w-3.5 h-3.5')}${s.label}</button>`;}).join('');
    chips.querySelectorAll('.src-chip:not(.disabled)').forEach(b=>b.onclick=()=>setSource(b.dataset.src));}
  $('#source').value=sourceMode;}
function updateSrcHint(){const s=SOURCES.find(x=>x.v===sourceMode);$('#srcHint').textContent=s?s.hint[lang]:'';}
let igMode='business';
function paintIgMode(){$('#igModeWrap').classList.toggle('hidden',sourceMode!=='instagram');
  $$('#igModeSeg .igmbtn').forEach(b=>b.classList.toggle('on',b.dataset.m===igMode));}
$$('#igModeSeg .igmbtn').forEach(b=>b.onclick=()=>{igMode=b.dataset.m;paintIgMode();});
$('#advBtn').onclick=()=>{$('#adv').classList.toggle('hidden');updateSrcHint();};
$('#allCities').onclick=()=>{$('#city').value='Київ, Львів, Одеса, Дніпро, Харків, Запоріжжя';};
$('#searchForm').onsubmit=e=>{e.preventDefault();
  const cities=city.value.split(',').map(s=>s.trim()).filter(Boolean);
  const base={category:category.value,country:country.value,limit:+limit.value,lang,enrich:enrich.checked,discover_websites:discoverWebsites.checked,brave_people:bravePeople.checked,brave_news:braveNews.checked,brave_intent:braveIntent.checked,source:sourceMode,ig_mode:igMode};
  if($('#expandNiche').checked)runSearch('/api/find_expanded',{...base,city:cities.length>1?'':city.value,cities:cities.length>1?cities:[]});
  else if(cities.length>1)runSearch('/api/find_multi',{...base,cities});
  else runSearch('/api/find',{...base,city:city.value});};
$('#runMap').onclick=()=>{const pt=picked||map.getCenter();   // fall back to map centre
  runSearch('/api/find_around',{category:category.value,lat:pt.lat,lon:pt.lng,radius_m:+radius.value,limit:+limit.value,lang,enrich:enrich.checked});};
$('#cancelSearch').onclick=cancelSearch;

