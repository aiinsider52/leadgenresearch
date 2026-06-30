// ---- lead detail popup ----
function lmChip(html,cls){return `<span class="chip ${cls||''}">${html}</span>`;}
function lmSection(title,inner){return inner?`<div><div class="lm-section-title">${title}</div>${inner}</div>`:'';}
function scoreRadarHtml(score,lang){
 const dims=(score||{}).dimensions||{};
 const keys=['contactability','intent','fit','data_confidence'];
 const labels={
  contactability:{uk:'Контакти',ru:'Контакты',en:'Contacts'},
  intent:{uk:'Intent',ru:'Intent',en:'Intent'},
  fit:{uk:'Fit',ru:'Fit',en:'Fit'},
  data_confidence:{uk:'Дані',ru:'Данные',en:'Data'}};
 return `<div class="score-radar">${keys.map(k=>{
  const v=Math.min(100,Math.max(0,Math.round(dims[k]||0)));
  const r=18,c=2*Math.PI*r,off=c*(1-v/100);
  const stroke=v>=65?'#F97316':v>=40?'#F59E0B':'#8B5CF6';
  return `<div class="score-ring-mini"><svg viewBox="0 0 44 44" aria-hidden="true"><circle class="rm-bg" cx="22" cy="22" r="${r}"/><circle class="rm-fg" cx="22" cy="22" r="${r}" stroke="${stroke}" stroke-dasharray="${c.toFixed(2)}" stroke-dashoffset="${off.toFixed(2)}" transform="rotate(-90 22 22)"/></svg><div><div class="rm-label">${labels[k][lang]||k}</div><div class="rm-val">${v}</div></div></div>`;
 }).join('')}</div>`;}
function openLeadDetail(id){
  if(searchLoading||!id)return;
  const u=UI[lang],l=findLead(id);
  if(!l||!(l.company&&l.company.name))return;
  const c=l.company||{},en=l.enrichment||{},s=l.score||{},sig=en.signals||{},p=en.profile||{},cq=en.contact_quality||{};
  const tierCls={hot:'hot',warm:'warm',cold:'cold'}[s.tier]||'cold';
  $('#lmHead').innerHTML=`${s.score!=null?`<div class="lm-score ${tierCls}">${s.score}</div>`:''}
    <div style="min-width:0"><div style="font-weight:700;font-size:16px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(c.name||'')}</div>
    <div class="text-muted" style="font-size:12px;margin-top:4px;display:flex;align-items:center;gap:4px">${svg('pin','w-3 h-3')}<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(c.address||c.city||'')}</span><span class="chip" style="margin-left:6px;font-size:10px">${esc((c.sources&&c.sources.length?c.sources.join(' + '):c.source)||'')}</span></div></div>`;

  const emp=c.employees||p.employees, band=p.size_band||c.size_band;
  const facts=[ (emp||band)?lmChip(svg('user','w-3 h-3')+(emp?esc(emp)+' '+u.emp:esc(band)),'chip-violet'):'',
    c.rating?lmChip(svg('star','w-3 h-3')+c.rating+(c.reviews?` · ${c.reviews}`:''),'chip-amber'):'',
    p.founded?lmChip(u.founded+' '+esc(p.founded),''):'',
    (c.gmaps_category||c.category)?lmChip(esc(c.gmaps_category||c.category),'chip-violet'):'' ].filter(Boolean).join(' ');

  // Vacancy (jobs source)
  let vacancy='';
  if(c.source==='jobs'||(sig.hiring_for&&sig.hiring_for.length)){
    const roles=(sig.hiring_for||[]).map(r=>lmChip(svg('briefcase','w-3 h-3')+esc(r),'chip-green')).join(' ');
    const posted=sig.posted_at?`<div class="text-muted" style="font-size:12px;margin-top:4px">Опубліковано: ${esc(sig.posted_at)}</div>`:'';
    const jobLink=sig.job_url?`<a href="${esc(sig.job_url)}" target="_blank" rel="noopener" class="text-accent" style="font-size:12px;margin-top:8px;display:inline-flex;align-items:center;gap:4px">${svg('ext','w-3 h-3')}Вакансія на LinkedIn</a>`:'';
    vacancy=lmSection('Вакансія (сигнал найму)',`<div>${roles}${posted}${jobLink}</div>`);
  }
  const news=(sig.news||[]).map(n=>`<a href="${esc(n.url||'#')}" target="_blank" rel="noopener" class="block rounded-lg bg-orange-500/10 text-orange-600 dark:text-orange-400 px-2.5 py-2 text-xs hover:bg-orange-500/15">${esc(n.title||'News')}<span class="block text-[10px] opacity-70 mt-0.5">${esc((n.signals||[]).join(' · '))}</span></a>`).join('');
  const newsBlock=lmSection('Brave News · buying signals',news?`<div class="space-y-1.5">${news}</div>`:'');
  const intent=(sig.intent_evidence||[]).map(n=>`<a href="${esc(n.url||'#')}" target="_blank" rel="noopener" class="block rounded-lg bg-rose-500/10 text-rose-600 dark:text-rose-400 px-2.5 py-2 text-xs hover:bg-rose-500/15">${esc(n.title||'Intent')}<span class="block text-[10px] opacity-70 mt-0.5">${esc((n.signals||[]).join(' · '))}</span></a>`).join('');
  const intentBlock=lmSection('Buying intent',intent?`<div class="space-y-1.5">${intent}</div>`:'');

  // Instagram
  let insta='';const igUrl=c.instagram||en.socials?.instagram;
  if(igUrl){insta=lmSection('Instagram',`<div class="flex items-center gap-2 flex-wrap">
    <a href="${esc(igUrl)}" target="_blank" rel="noopener" class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-pink-500/10 text-pink-500 text-sm hover:bg-pink-500/20">${svg('instagram','w-4 h-4')}${esc(igUrl.replace(/^https?:\/\/(www\.)?instagram\.com\//,'@').replace(/\/$/,''))}</a>
    ${c.followers?lmChip(esc(String(c.followers))+' підписників',''):''}</div>`);}

  const emails=(en.emails||[]).map(e=>{const q=(cq.emails||[]).find(x=>x.email===e)||{};return `<a href="mailto:${esc(e)}" class="lead-contact">${svg('mail','w-3.5 h-3.5')}${esc(e)}${q.confidence?`<span class="chip" style="font-size:9px">${esc(q.confidence)}</span>`:''}</a>`;}).join('');
  const phones=(en.phones||[]).map(p=>`<div class="lead-contact">${svg('phone','w-3.5 h-3.5')}${esc(p)}</div>`).join('');
  const tg=(en.telegram||[]).map(h=>`<a href="https://t.me/${esc(h)}" target="_blank" class="lead-contact text-accent">${svg('send','w-3.5 h-3.5')}@${esc(h)}</a>`).join('');
  const socials=Object.entries(en.socials||{}).map(([k,v])=>`<a href="${esc(v)}" target="_blank" rel="noopener" class="chip chip-sky">${esc(k)}</a>`).join('');
  const site=c.website?`<a href="${esc(c.website)}" target="_blank" rel="noopener" class="lead-contact text-accent">${svg('ext','w-3.5 h-3.5')}${esc(c.website.replace(/^https?:\/\//,'').slice(0,40))}</a>`:'';
  const contactsLabel=lang==='en'?'Contacts':lang==='ru'?'Контакты':'Контакти';
  const contacts=lmSection(contactsLabel,`<div style="display:flex;flex-direction:column;gap:6px">${emails}${phones}${tg}${site?`<div>${site}</div>`:''}<div style="display:flex;flex-wrap:wrap;gap:6px;padding-top:4px">${socials}</div></div>`);

  const scoreTitle=lang==='en'?'Lead score breakdown':lang==='ru'?'Разбор скора':'Розбір скору';
  const scoreBlock=s.score!=null?lmSection(scoreTitle,scoreRadarHtml(s,lang)):'';

  const dm=(en.decision_makers||[]).map(pp=>{const li=pp.linkedin||pp.linkedin_search;
    return `<div class="lead-contact"><span>${svg('user','w-4 h-4')}</span><span style="font-weight:500;color:var(--text)">${esc(pp.name||'')}</span><span class="text-muted">${esc(pp.role||'')}</span>${li?`<a href="${esc(li)}" target="_blank" rel="noopener" class="text-accent">${svg('linkedin','w-4 h-4')}</a>`:''}</div>`;}).join('');
  const people=lmSection(u.dm,dm?`<div style="display:flex;flex-direction:column;gap:6px">${dm}</div>`:'');

  const leftCol=`
    ${facts?`<div style="display:flex;flex-wrap:wrap;gap:6px">${facts}</div>`:''}
    ${vacancy}${newsBlock}${intentBlock}${insta}${people}${contacts}`;

  const rightCol=`
    ${scoreBlock}
    <div><div class="lm-section-title">AI Analysis</div><div class="dw-box" id="lmAiSummary"><span class="spin"></span></div></div>
    <div id="lmRightHistory"><div class="lm-section-title">Timeline</div><div id="lmHistoryList"><span class="text-muted" style="font-size:12px">—</span></div></div>
    <div class="lm-actions">
      <button type="button" id="lmBrave" class="lm-btn-brave">${svg('search','w-5 h-5')}Brave deep enrich</button>
      <button type="button" id="lmWrite" class="lm-btn-write">${svg('pen','w-5 h-5')}${u.write_msg}</button>
    </div>`;

  $('#lmLeft').innerHTML=leftCol;
  $('#lmRight').innerHTML=rightCol;
  fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lead:l,lang})})
    .then(r=>r.json()).then(d=>{const el=$('#lmAiSummary');if(el)el.textContent=d.summary||'—';}).catch(()=>{});
  fetch('/api/history?lead_id='+encodeURIComponent(id)).then(r=>r.json()).then(rows=>{
    const list=Array.isArray(rows)?rows:(rows.events||[]);
    const el=$('#lmHistoryList');
    if(!el)return;
    el.innerHTML=list.length?list.map(e=>`<div class="lm-timeline-item"><time>${esc(e.ts||e.created_at||'')}</time><div>${esc(e.action||e.type||e.summary||'')}</div></div>`).join(''):'<span class="text-muted" style="font-size:12px">—</span>';
  }).catch(()=>{});
  $('#lmBrave').onclick=async()=>{const b=$('#lmBrave');b.disabled=true;b.textContent='…';
    const r=await fetch('/api/brave/enrich',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lead:l,people:true,news:true,intent:true})});
    const d=await r.json();if(r.ok){Object.assign(l,d);closeLeadDetail();openLeadDetail(l._id);}else{b.disabled=false;b.textContent=d.error||'Brave error';}};
  const openOut=()=>{closeLeadDetail();openOutreach(id);};
  $('#lmWrite').onclick=openOut;
  $('#lmWriteHead').onclick=openOut;
  $('#leadModal').classList.remove('hidden');document.body.style.overflow='hidden';
}
function closeLeadDetail(){$('#leadModal').classList.add('hidden');document.body.style.overflow='';}
$('#lmClose').onclick=$('#leadModalBg').onclick=closeLeadDetail;

