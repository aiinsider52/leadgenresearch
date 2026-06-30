// ---- theme ----
function setTheme(dark){document.documentElement.classList.toggle('dark',dark);localStorage.setItem('lg_theme',dark?'dark':'light');
 $('#theme').querySelector('svg')?.remove(); $('#theme').insertAdjacentHTML('beforeend',svg(dark?'moon':'sun','w-5 h-5'));
 if(tiles){tiles.remove();tiles=L.tileLayer(dark?darkTiles:lightTiles,{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(map);}}
$('#theme').onclick=()=>setTheme(!document.documentElement.classList.contains('dark'));

// ---- tabs ----
const PAGE_TITLES={search:'page_search',agent:'page_agent',all:'page_all',saved:'page_saved'};
const PAGE_SUBS={search:'page_sub_search',agent:'page_sub_agent',all:'page_sub_all',saved:'page_sub_saved'};
function paintTabs(){
  $$('.tabbtn').forEach(b=>b.classList.toggle('tab-active',b.dataset.tab===tab));
  $$('.bn-item').forEach(b=>b.classList.toggle('tab-active',b.dataset.tab===tab));
  const u=UI[lang];
  const pt=$('#pageTitle');if(pt)pt.textContent=u[PAGE_TITLES[tab]]||u.tab_search;
  const ps=$('#pageSub');if(ps)ps.textContent=u[PAGE_SUBS[tab]]||'';
  $('#kpiStrip')?.classList.toggle('hidden',tab==='agent');
}
let statusFilter='all';
$('#statusFilter').onchange=e=>{statusFilter=e.target.value;renderCurrent();};
$('#textSearch').oninput=e=>{textFilter=e.target.value.trim();renderCurrent();};
$$('.tabbtn').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;paintTabs();
  $('#statusFilter').classList.toggle('hidden',tab!=='saved');
  $('#textSearch').classList.toggle('hidden',tab==='search');
  if(tab==='saved')loadSaved();else if(tab==='all')loadAll();else if(tab==='agent')initAgent();else if(tab==='search')renderCurrent();});
async function loadAll(){const r=await fetch('/api/leads?limit=3000');allLeads=await r.json();refreshAllCount();renderCurrent();}
async function refreshAllCount(){try{const d=await (await fetch('/api/leads?limit=3000')).json();$('#allCount').textContent=d.length?d.length:'';allLeads=d;}catch(e){}}

// ---- filters ----
function paintChips(){$$('.filterchip').forEach(c=>{
  const on=filters[c.dataset.f];
  c.classList.toggle('active',on);
  c.classList.toggle('chip',true);
});}
$$('.filterchip').forEach(c=>{c.insertAdjacentHTML('afterbegin',svg(c.dataset.ic,'w-3.5 h-3.5'));
 c.onclick=()=>{filters[c.dataset.f]=!filters[c.dataset.f];paintChips();renderCurrent();};});
$('#sort').onchange=e=>{sortMode=e.target.value;renderCurrent();};

function leadPasses(l){const en=l.enrichment||{},s=en.socials||{};
 if(filters.email&&!(en.emails||[]).length)return false;
 if(filters.phone&&!(en.phones||[]).length)return false;
 if(filters.linkedin&&!s.linkedin)return false;
 if(filters.telegram&&!(en.telegram||[]).length)return false;
 if(filters.dm&&!(en.decision_makers||[]).length)return false;
 return true;}

function renderCurrent(){const base=tab==='saved'?savedLeads:tab==='all'?allLeads:lastLeads;let vis=base.filter(leadPasses);
 if(tab==='saved'&&statusFilter!=='all')vis=vis.filter(l=>(l.status||'new')===statusFilter);
 if((tab==='all'||tab==='saved')&&textFilter){const q=textFilter.toLowerCase();
   vis=vis.filter(l=>((l.company||{}).name||'').toLowerCase().includes(q)||((l.company||{}).city||'').toLowerCase().includes(q));}
 if(sortMode==='score')vis=[...vis].sort((a,b)=>((b.score||{}).score||0)-((a.score||{}).score||0));
 else if(sortMode==='reviews')vis=[...vis].sort((a,b)=>((b.company||{}).reviews||0)-((a.company||{}).reviews||0));
 render(vis,base.length);}

// ---- bulk actions ----
function selectedLeads(){const pool=[...lastLeads,...savedLeads,...allLeads];return [...selectedIds].map(id=>pool.find(l=>l._id===id)).filter(Boolean);}
function updateBulkBar(){const n=selectedIds.size;$('#bulkBar').classList.toggle('hidden',n===0);
  $('#bulkCount').textContent=(lang==='en'?`${n} selected`:lang==='ru'?`${n} выбрано`:`${n} виділено`);}
$('#bulkSave').onclick=async()=>{const leads=selectedLeads();if(!leads.length)return;
  await fetch('/api/save_bulk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({leads})});
  leads.forEach(l=>l._saved=true);selectedIds.clear();refreshSavedCount();renderCurrent();};
$('#bulkExport').onclick=()=>{const leads=selectedLeads();if(!leads.length)return;
  const head=['name','city','website','rating','size','score','tier','emails','phones','decision_makers'];
  const rows=leads.map(l=>{const c=l.company||{},en=l.enrichment||{},s=l.score||{};
    return [c.name,c.city,c.website,c.rating,c.size_band||(en.profile||{}).size_band,s.score,s.tier,(en.emails||[]).join(' '),(en.phones||[]).join(' '),(en.decision_makers||[]).map(p=>p.name).join(' ')].map(v=>`"${String(v??'').replace(/"/g,'""')}"`).join(',');});
  const csv=head.join(',')+'\n'+rows.join('\n');const blob=new Blob([csv],{type:'text/csv'});const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);a.download='leadgen_selected.csv';a.click();};
$('#bulkClear').onclick=()=>{selectedIds.clear();renderCurrent();};

// ---- export + AI status ----
$('#exportBtn').onclick=()=>window.open('/api/export.csv?scope='+(tab==='saved'?'saved':'recent'),'_blank');
async function refreshAi(){const u=UI[lang];try{const d=await (await fetch('/api/ai_status')).json();const p=$('#aiPill');
  const wf=d.waterfall?' 💧':'';
  p.textContent=d.ai?('🟢 '+(d.model||u.ai_on)+wf):('⚪ '+u.ai_off);
  p.className='hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border '+(d.ai?'border-purple-500/30 text-purple-300':'');
  if(d.ai)p.style.background='rgba(139,92,246,.12)';else p.style.background='var(--bg-2)';
  const wh=$('#waterfallHint');if(wh)wh.classList.toggle('hidden',!!d.waterfall);
}catch(e){}}

// ---- map ----
const darkTiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
const lightTiles='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
const map=L.map('map',{zoomControl:true,attributionControl:false}).setView([49.842,24.0316],12);
tiles=L.tileLayer(document.documentElement.classList.contains('dark')?darkTiles:lightTiles,{maxZoom:19}).addTo(map);
// Always-visible radius circle marking the search area (centre by default).
circle=L.circle(map.getCenter(),{radius:+radius.value,color:'#E8B84B',weight:2,fillColor:'#8B5CF6',fillOpacity:.14}).addTo(map);
function radiusLabel(){const km=(+radius.value/1000);$('#radiusLabel').textContent='R '+km.toFixed(1)+' · ⌀'+(km*2).toFixed(0)+' km';}
function searchPoint(){return picked||map.getCenter();}
$('#radius').oninput=()=>{radiusLabel();circle.setRadius(+radius.value);};
// Circle follows the map centre while panning (until a point is pinned).
map.on('move',()=>{if(!picked)circle.setLatLng(map.getCenter());});
map.on('click',e=>{picked=e.latlng;circle.setLatLng(e.latlng);
 if(marker)marker.setLatLng(e.latlng);else marker=L.marker(e.latlng).addTo(map);});
radiusLabel();

// ---- command palette (⌘K) ----
function openCmdPalette(){
  const pal=$('#cmdPalette');if(!pal)return;
  pal.classList.remove('hidden');document.body.style.overflow='hidden';
  const inp=$('#cmdPaletteInput');if(inp){inp.value='';setTimeout(()=>inp.focus(),30);}}
function closeCmdPalette(){
  const pal=$('#cmdPalette');if(!pal)return;
  pal.classList.add('hidden');if($('#drawer').classList.contains('hidden')&&$('#leadModal').classList.contains('hidden')&&$('#stats').classList.contains('hidden'))document.body.style.overflow='';}
function runCmdSearch(q){
  if(!q)return;
  const parts=q.split(/\s+/);
  const cityMatch=q.match(/(?:у|в|in)\s+([а-яіїєґa-z\-]+(?:\s+[а-яіїєґa-z\-]+)?)/i);
  if(cityMatch)$('#city').value=cityMatch[1];
  const cat=q.replace(/(?:у|в|in)\s+[а-яіїєґa-z\-]+(?:\s+[а-яіїєґa-z\-]+)?/gi,'').trim();
  if(cat)$('#category').value=cat;
  closeCmdPalette();
  tab='search';paintTabs();
  $('#agentPanel').classList.add('hidden');
  $('#searchPanel').classList.remove('hidden');
  $('#searchForm').requestSubmit();}
$('#sidebarSearch')?.addEventListener('click',openCmdPalette);
$('#cmdPaletteBg')?.addEventListener('click',closeCmdPalette);
$('#cmdPaletteInput')?.addEventListener('keydown',e=>{
  if(e.key==='Enter'){e.preventDefault();runCmdSearch(e.target.value.trim());}
  if(e.key==='Escape'){e.preventDefault();closeCmdPalette();}});
$('#upgradeAgentBtn')?.addEventListener('click',()=>{document.querySelector('.tabbtn[data-tab="agent"]')?.click();});

$('#results').addEventListener('click',ev=>{
  if(searchLoading)return;
  const card=ev.target.closest('.lead-card[data-id][data-hydrated="true"]');
  if(!card||!isHydratedLeadCard(card))return;
  if(ev.target.closest('button,a,input,select,textarea,summary,details,label'))return;
  openLeadDetail(card.dataset.id);
});

// ---- init ----
(async function(){
 setTheme((localStorage.getItem('lg_theme')||'dark')==='dark');
 const cats=await (await fetch('/api/categories')).json();
 $('#cats').innerHTML=cats.map(c=>`<option value="${c}">`).join('');
 paintSources();paintIgMode();paintChips();refreshSavedCount();refreshAllCount();refreshKpis();refreshBudget();applyLang();
 if(tab==='agent')initAgent();
 $('#mapToggle')?.addEventListener('click',()=>{
   const aside=$('#mapAside');const open=aside?.classList.toggle('collapsed');
   $('#mapToggle')?.setAttribute('aria-expanded',open?'false':'true');
   setTimeout(()=>map.invalidateSize(),200);
 });
 setTimeout(()=>map.invalidateSize(),200);
})();
window.UI=UI;
window.sleep=sleep;
window.loadSaved=loadSaved;
window.loadAll=loadAll;
window.initAgent=initAgent;
window.renderCurrent=renderCurrent;
window.refreshKpis=refreshKpis;
window.paintTabs=paintTabs;
window.openStats=openStats;
window.RENDER_CAP=RENDER_CAP;
window.getLgLang=()=>lang;
window.getLgSource=()=>sourceMode;
