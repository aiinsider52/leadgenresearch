// ---- analytics / settings modal ----
const STATUS_LABELS={new:{uk:'Новий',ru:'Новый',en:'New'},contacted:{uk:'Написав',ru:'Написал',en:'Contacted'},replied:{uk:'Відповів',ru:'Ответил',en:'Replied'},client:{uk:'Клієнт',ru:'Клиент',en:'Client'},rejected:{uk:'Відмова',ru:'Отказ',en:'Rejected'}};
function statBars(obj){
  const m=Math.max(1,...Object.values(obj));
  return `<div class="stat-bars">${Object.entries(obj).map(([k,v])=>`
    <div class="bar-row"><span class="bar-label">${esc(k)}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.round(v/m*100)}%"></div></div>
      <span class="bar-val">${v}</span></div>`).join('')}</div>`;}
function lineChart(values){
  const w=400,h=140,p=26,max=Math.max(...values,1);
  const pts=values.map((v,i)=>{const x=p+(i/(values.length-1||1))*(w-p*2);const y=h-p-(v/max)*(h-p*2);return `${x},${y}`;}).join(' ');
  const area=`${p},${h-p} ${pts} ${w-p},${h-p}`;
  return `<svg class="chart-svg" viewBox="0 0 ${w} ${h}">
    <defs>
      <linearGradient id="chartGrad" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#7C5CFF"/><stop offset="100%" stop-color="#9B82FF"/></linearGradient>
      <linearGradient id="chartAreaGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#7C5CFF" stop-opacity=".4"/><stop offset="100%" stop-opacity="0"/></linearGradient>
    </defs>
    <g class="chart-grid">${[0,.25,.5,.75,1].map(t=>`<line x1="${p}" y1="${h-p-t*(h-p*2)}" x2="${w-p}" y2="${h-p-t*(h-p*2)}"/>`).join('')}</g>
    <polygon class="chart-area" points="${area}"/>
    <polyline class="chart-line" points="${pts}"/>
  </svg>`;}
function gaugeChart(pct,label){
  const w=220,h=130,cx=110,cy=110,r=86,pctClamped=Math.max(0,Math.min(100,pct));
  const startA=Math.PI*0.85,endA=Math.PI*2.15,totalA=endA-startA;
  const a=startA+(pctClamped/100)*totalA;
  const arcPath=(s,e)=>{const x1=cx+r*Math.cos(s),y1=cy+r*Math.sin(s),x2=cx+r*Math.cos(e),y2=cy+r*Math.sin(e);const large=e-s>Math.PI?1:0;return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;};
  return `<div class="gauge-wrap"><svg class="gauge-svg" viewBox="0 0 ${w} ${h}">
    <defs><linearGradient id="gaugeGrad" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#7C5CFF"/><stop offset="100%" stop-color="#9B82FF"/></linearGradient></defs>
    <path class="gauge-arc-bg" d="${arcPath(startA,endA)}"/>
    <path class="gauge-arc-fg" d="${arcPath(startA,a)}"/>
    <text class="gauge-val" x="${cx}" y="${cy-4}">${pct}%</text>
    <text class="gauge-lbl" x="${cx}" y="${cy+16}">${label}</text>
  </svg></div>`;
}
function donutChart(obj){
  const total=Object.values(obj).reduce((a,b)=>a+b,0)||1;
  const colors=['#7C5CFF','#38BDF8','#34D399','#FBBF24','#94A3B8'];
  let angle=0;const cx=60,cy=60,r=42;
  const segs=Object.entries(obj).map(([k,v],i)=>{
    const a=(v/total)*Math.PI*2;
    const x1=cx+r*Math.cos(angle-Math.PI/2),y1=cy+r*Math.sin(angle-Math.PI/2);
    angle+=a;
    const x2=cx+r*Math.cos(angle-Math.PI/2),y2=cy+r*Math.sin(angle-Math.PI/2);
    const large=a>Math.PI?1:0;
    return `<path class="donut-segment" fill="${colors[i%colors.length]}" opacity=".88" d="M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z"/>`;
  }).join('');
  return `<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
    <svg width="120" height="120" viewBox="0 0 120 120">${segs}<circle cx="${cx}" cy="${cy}" r="26" fill="var(--bg-1)"/><text x="${cx}" y="${cy+4}" text-anchor="middle" fill="var(--text)" font-size="11" font-weight="600">${total}</text></svg>
    <div style="font-size:12px;color:var(--text-secondary)">${Object.entries(obj).map(([k,v],i)=>`<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px"><span style="width:8px;height:8px;border-radius:50%;background:${colors[i%colors.length]}"></span>${esc(k)} <span class="text-muted">${v}</span></div>`).join('')}</div>
  </div>`;}
function bars(obj){return statBars(obj);}
async function openStats(){
  const campLbl={uk:{title:'Автокампанії',new:'Нова кампанія',name:'Назва',cron:'Розклад (cron)',limit:'Ліміт/запуск',outreach:'Auto outreach',expand:'AI веер',create:'Створити',runDue:'▶ Due now',runs:'Останні запуски',active:'активна',paused:'пауза',last:'останній',total:'всього',none:'Ще немає кампаній',cronHint:'Cron UTC · запускайте <code>python3 run_scheduled.py</code> щогодини або о 7:00'},ru:{title:'Автокампании',new:'Новая кампания',name:'Название',cron:'Расписание (cron)',limit:'Лимит/запуск',outreach:'Auto outreach',expand:'AI веер',create:'Создать',runDue:'▶ Due now',runs:'Последние запуски',active:'активна',paused:'пауза',last:'последний',total:'всего',none:'Пока нет кампаний',cronHint:'Cron UTC · запускайте <code>python3 run_scheduled.py</code> каждый час или в 7:00'},en:{title:'Autopilot campaigns',new:'New campaign',name:'Name',cron:'Schedule (cron)',limit:'Limit/run',outreach:'Auto outreach',expand:'AI niche fan',create:'Create',runDue:'▶ Run due',runs:'Recent runs',active:'active',paused:'paused',last:'last',total:'total',none:'No campaigns yet',cronHint:'Cron UTC · run <code>python3 run_scheduled.py</code> hourly or at 7:00'}};
  const cl=campLbl[lang]||campLbl.uk;
  const [s,u,icp,sch,campData,runs]=await Promise.all([fetch('/api/stats').then(r=>r.json()),fetch('/api/usage').then(r=>r.json()),fetch('/api/icp').then(r=>r.json()),fetch('/api/schedules').then(r=>r.json()),fetch('/api/campaigns').then(r=>r.json()),fetch('/api/campaigns/runs?limit=8').then(r=>r.json())]);
  const camps=campData.campaigns||[];
  const cronPresets=campData.cron_presets||{daily_7:'0 7 * * *',daily_8:'0 8 * * *',weekdays_8:'0 8 * * 1-5',every_6h:'0 */6 * * *'};
  const funnel=Object.fromEntries(Object.entries(s.funnel||{}).map(([k,v])=>[STATUS_LABELS[k]?.[lang]||k,v]));
  const trendVals=sparkFromSeed(s.total_leads||0,8);
  const budBar=(o,color)=>`<div class="bar-track" style="height:8px"><div class="bar-fill" style="width:${Math.min(100,Math.round(o.usd/o.cap*100))}%;background:${color}"></div></div>`;
  $('#statsBody').innerHTML=`
    <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
      ${[['Лідів',s.total_leads],['З сайтом',s.with_website],['З email',s.with_email],['Перевірені email',s.verified_email],['Buying intent',s.with_intent],['З керівником',s.with_dm],['Збережено',s.saved]].map(([t,v])=>`<div class="glass-card kpi-card" style="padding:16px;text-align:center"><div style="font-weight:700;font-size:22px">${v??0}</div><div class="text-muted" style="font-size:11px;margin-top:4px">${t}</div></div>`).join('')}
    </div>
    <div class="glass-card chart-panel">
      <div class="chart-title">Lead growth trend</div>
      ${lineChart(trendVals)}
    </div>
    <div class="grid sm:grid-cols-2 gap-4">
      <div class="glass-card chart-panel"><div class="chart-title">Воронка</div>${statBars(funnel)}</div>
      <div class="glass-card chart-panel"><div class="chart-title">Email coverage</div>${gaugeChart(s.total_leads?Math.round((s.with_email||0)/s.total_leads*100):0,'verified reach')}</div>
    </div>
    <div class="grid sm:grid-cols-2 gap-4">
      <div class="glass-card chart-panel"><div class="chart-title">За тиром</div>${donutChart(s.by_tier||{})}</div>
      <div class="glass-card chart-panel"><div class="chart-title">Джерела</div>${statBars(s.by_source||{})}</div>
    </div>
    <div class="glass-card chart-panel"><div class="chart-title">Топ міста</div>${statBars(s.by_city||{})}</div>
    <div class="glass-card chart-panel"><div class="chart-title">Конверсія джерел</div>
      <div class="grid sm:grid-cols-2 gap-2">${Object.entries(s.source_conversion||{}).map(([src,x])=>`<div class="glass-card" style="padding:12px;font-size:13px"><div style="font-weight:600">${esc(src)}</div><div class="text-muted" style="font-size:12px;margin-top:4px">reply ${x.reply_rate}% · client ${x.client_rate}%</div></div>`).join('')||'<span class="text-muted" style="font-size:12px">Потрібні статуси contacted/replied/client.</span>'}</div>
    </div>
    <div class="border-t border-black/5 dark:border-white/5 pt-4">
      <div class="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">Бюджет (${esc(u.month)})</div>
      <div class="space-y-2 text-sm">
        <div><div class="flex justify-between mb-1"><span>Apify · ${u.apify.runs} прогонів</span><span class="tabular-nums">$${u.apify.usd} / $${u.apify.cap}</span></div>${budBar(u.apify,'#22C55E')}</div>
        <div><div class="flex justify-between mb-1"><span>OpenAI · ${u.openai.calls} викликів</span><span class="tabular-nums">$${u.openai.usd} / $${u.openai.cap}</span></div>${budBar(u.openai,'#8B5CF6')}</div>
        <div><div class="flex justify-between mb-1"><span>Brave · ${u.brave.calls} запитів</span><span class="tabular-nums">$${u.brave.usd} / $${u.brave.cap}</span></div>${budBar(u.brave,'#F97316')}</div>
      </div>
    </div>
    <div class="border-t border-black/5 dark:border-white/5 pt-4">
      <div class="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">${svg('target','w-3.5 h-3.5 text-brand-500')}ICP — ідеальний клієнт</div>
      <textarea id="icpInput" rows="3" class="w-full bg-white dark:bg-zinc-900/70 border border-black/10 dark:border-white/10 rounded-xl px-3 py-2.5 text-sm" placeholder="Опишіть ідеального клієнта…">${esc(icp.icp||'')}</textarea>
      <button id="icpSave" class="mt-2 bg-brand-600 hover:bg-brand-500 text-white rounded-lg px-4 py-2 text-sm font-medium">Зберегти ICP</button>
      <span id="icpMsg" class="ml-2 text-xs text-emerald-500"></span>
    </div>
    <div class="border-t border-black/5 dark:border-white/5 pt-4">
      <div class="flex items-center justify-between mb-2">
        <div class="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">Розклад · збережені пошуки</div>
        <div class="flex gap-1.5"><button id="schAdd" class="text-xs bg-black/5 dark:bg-white/10 hover:bg-black/10 rounded-lg px-2.5 py-1">+ поточний</button>
          <button id="schRun" class="text-xs bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-2.5 py-1">▶ Запустити</button></div>
      </div>
      <div id="schList" class="space-y-1.5">${sch.length?sch.map((x,i)=>`<div class="flex items-center justify-between text-sm rounded-lg bg-black/[.03] dark:bg-white/[.04] px-2.5 py-1.5"><span>${esc(x.category||'')} · ${esc((x.cities||[x.city]).join(', '))} <span class="text-zinc-400">[${esc(x.source||'osm')}]</span></span><button data-i="${i}" class="schDel text-zinc-400 hover:text-rose-500">✕</button></div>`).join(''):'<span class="text-xs text-zinc-400">Поки порожньо. «+ поточний» додасть пошук із верхньої панелі.</span>'}</div>
      <div class="text-[11px] text-zinc-400 mt-2">Авто-запуск: cron → <code>python3 run_scheduled.py</code> (напр. щоранку о 8:00).</div>
    </div>
    <div class="border-t border-black/5 dark:border-white/5 pt-4">
      <div class="flex items-center justify-between mb-3">
        <div class="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">${svg('sparkle','w-3.5 h-3.5')} ${cl.title}</div>
        <button id="campRunDue" class="text-xs bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-2.5 py-1">${cl.runDue}</button>
      </div>
      <div class="glass-card" style="padding:14px;margin-bottom:12px">
        <div class="text-xs font-semibold text-muted mb-2">${cl.new}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
          <input id="campName" class="input" placeholder="${cl.name}" style="font-size:12px">
          <select id="campCron" class="select-field" style="font-size:12px">${Object.entries(cronPresets).map(([k,v])=>`<option value="${v}">${k} · ${v}</option>`).join('')}</select>
          <input id="campLimit" type="number" min="10" max="200" value="80" class="input" style="font-size:12px" title="${cl.limit}">
          <span class="text-muted" style="font-size:11px;display:flex;align-items:center">${cl.limit}: 80</span>
        </div>
        <label class="flex items-center gap-2 text-xs text-muted" style="margin-bottom:6px"><input type="checkbox" id="campExpand" checked> ${cl.expand}</label>
        <label class="flex items-center gap-2 text-xs text-muted" style="margin-bottom:10px"><input type="checkbox" id="campOutreach"> ${cl.outreach}</label>
        <button id="campCreate" class="btn btn-primary" style="width:100%;font-size:12px;padding:10px">${cl.create} · ${esc($('#category')?.value||'agency')}</button>
        <div class="text-muted" style="font-size:10px;margin-top:8px;line-height:1.4">${cl.cronHint}</div>
      </div>
      <div id="campList" class="space-y-1.5">${camps.length?camps.map(c=>`<div class="flex items-center justify-between gap-2 text-sm rounded-lg bg-black/[.03] dark:bg-white/[.04] px-2.5 py-2">
        <div style="min-width:0"><div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(c.name)}</div>
        <div class="text-muted" style="font-size:11px;margin-top:2px">${esc(c.category)} · ${esc((c.cities||[]).join(', '))} · <code style="font-size:10px">${esc(c.cron||'')}</code></div>
        <div class="text-muted" style="font-size:10px;margin-top:2px">${c.status==='active'?cl.active:cl.paused} · ${cl.last}: ${c.last_run?esc(c.last_run.slice(0,16).replace('T',' ')):'—'} · ${cl.total}: ${(c.totals||{}).leads||0} leads</div></div>
        <div style="display:flex;gap:4px;flex-shrink:0">
          <button data-crun="${c.id}" class="btn btn-ghost" style="padding:4px 8px;font-size:11px" title="Run">▶</button>
          <button data-ctoggle="${c.id}" data-st="${c.status}" class="btn btn-ghost" style="padding:4px 8px;font-size:11px">${c.status==='active'?'⏸':'▶'}</button>
          <button data-cdel="${c.id}" class="btn btn-ghost" style="padding:4px 8px;font-size:11px;color:var(--danger,#F43F5E)">✕</button>
        </div></div>`).join(''):`<span class="text-xs text-zinc-400">${cl.none}</span>`}</div>
      ${runs.length?`<div style="margin-top:12px"><div class="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">${cl.runs}</div>
        <div class="space-y-1">${runs.map(r=>`<div class="text-xs text-muted rounded-lg px-2 py-1.5 bg-black/[.02] dark:bg-white/[.03]">${esc(r.ts?.slice(0,16).replace('T',' ')||'')} · +${r.leads_found||0} · hot ${r.hot||0}</div>`).join('')}</div></div>`:''}
    </div>`;
  $('#icpSave').onclick=async()=>{await fetch('/api/icp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({icp:$('#icpInput').value})});$('#icpMsg').textContent='✓';setTimeout(()=>$('#icpMsg').textContent='',1500);};
  $('#schAdd').onclick=async()=>{const cities=$('#city').value.split(',').map(x=>x.trim()).filter(Boolean);
    const search={category:$('#category').value,country:$('#country').value,limit:+$('#limit').value,lang,enrich:$('#enrich').checked,discover_websites:$('#discoverWebsites').checked,brave_people:$('#bravePeople').checked,brave_news:$('#braveNews').checked,brave_intent:$('#braveIntent').checked,source:sourceMode,ig_mode:igMode};
    if(cities.length>1)search.cities=cities;else search.city=$('#city').value;
    await fetch('/api/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({search})});openStats();};
  $('#schRun').onclick=async()=>{$('#schRun').textContent='…';await fetch('/api/run_schedules',{method:'POST'});openStats();};
  $$('.schDel').forEach(b=>b.onclick=async()=>{await fetch('/api/schedules/'+b.dataset.i,{method:'DELETE'});openStats();});
  $('#campCreate').onclick=async()=>{
    const cities=$('#city').value.split(',').map(x=>x.trim()).filter(Boolean)||['Київ'];
    const body={name:$('#campName').value||($('#category').value+' autopilot'),category:$('#category').value,cities,
      source:sourceMode,limit_per_run:+($('#campLimit').value||80),cron:$('#campCron').value,
      auto_outreach:$('#campOutreach').checked,expand_niche:$('#campExpand').checked,lang,
      discover_websites:$('#discoverWebsites').checked,brave_people:$('#bravePeople').checked,
      brave_news:$('#braveNews').checked,brave_intent:$('#braveIntent').checked};
    await fetch('/api/campaigns',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    openStats();refreshKpis();};
  $('#campRunDue').onclick=async()=>{$('#campRunDue').textContent='…';await fetch('/api/campaigns/run_due',{method:'POST'});openStats();refreshKpis();};
  $$('[data-crun]').forEach(b=>b.onclick=async()=>{await fetch('/api/campaigns/'+b.dataset.crun+'/run',{method:'POST'});openStats();refreshKpis();});
  $$('[data-ctoggle]').forEach(b=>b.onclick=async()=>{
    const id=b.dataset.ctoggle,paused=b.dataset.st==='active';
    await fetch('/api/campaigns/'+id+(paused?'/pause':'/resume'),{method:'POST'});
    openStats();});
  $$('[data-cdel]').forEach(b=>b.onclick=async()=>{if(!confirm('Delete campaign?'))return;await fetch('/api/campaigns/'+b.dataset.cdel,{method:'DELETE'});openStats();});
  if(getLgTab()==='analytics'){
    const ab=$('#analyticsBody');if(ab)ab.innerHTML=$('#statsBody').innerHTML;
    $('#stats').classList.add('hidden');document.body.style.overflow='';return;
  }
  $('#stats').classList.remove('hidden');document.body.style.overflow='hidden';
}
$('#statsBtn').onclick=()=>{setLgTab('analytics');};
$('#statsBtnBottom').onclick=(e)=>{e.preventDefault();setLgTab('analytics');};
$('#statsClose').onclick=$('#statsBg').onclick=()=>{$('#stats').classList.add('hidden');document.body.style.overflow='';};

function axT(key) {
  const lang = localStorage.getItem('lg_lang') || 'uk';
  const u = (typeof UI !== 'undefined' && UI[lang]) || {};
  return u[key] || key;
}

function axBudgetBar(o, color) {
  const pct = Math.min(100, Math.round((o.usd / o.cap) * 100));
  return `<div class="bar-track" style="height:6px"><div class="bar-fill" style="width:${pct}%;background:${color}"></div></div>`;
}

async function buildAnalyticsDashboard() {
  const lang = localStorage.getItem('lg_lang') || 'uk';
  const headers = typeof authHeaders === 'function' ? authHeaders() : { 'Content-Type': 'application/json' };
  const [s, u, icp, intentLeads] = await Promise.all([
    fetch('/api/stats', { credentials: 'same-origin', headers }).then(r => r.json()).catch(() => ({})),
    fetch('/api/usage', { credentials: 'same-origin', headers }).then(r => r.json()).catch(() => ({})),
    fetch('/api/icp', { credentials: 'same-origin', headers }).then(r => r.json()).catch(() => ({})),
    fetch('/api/intent/leads?limit=10', { credentials: 'same-origin', headers }).then(r => r.json()).catch(() => []),
  ]);
  const roi = await fetch('/api/playbook/roi', {
    method: 'POST',
    credentials: 'same-origin',
    headers,
    body: JSON.stringify({
      leads: s.total_leads || 100,
      conversion_pct: 2.5,
      deal_usd: 1500,
      hourly_cost: 35,
    }),
  }).then(r => r.json()).catch(() => ({}));

  const funnel = Object.fromEntries(
    Object.entries(s.funnel || {}).map(([k, v]) => [STATUS_LABELS[k]?.[lang] || k, v])
  );
  const trendVals = sparkFromSeed(s.total_leads || 0, 8);
  const emailPct = s.total_leads ? Math.round((s.with_email || 0) / s.total_leads * 100) : 0;
  const conv = s.source_conversion || {};
  const convHtml = Object.keys(conv).length
    ? `<div class="ax-conv-grid">${Object.entries(conv).map(([src, x]) =>
      `<div class="ax-conv-card"><b>${esc(src)}</b><span>reply ${x.reply_rate}% · client ${x.client_rate}%</span></div>`
    ).join('')}</div>`
    : `<p class="text-muted" style="font-size:12px;margin:0">${lang === 'ru' ? 'Нужны статусы contacted/replied/client.' : lang === 'en' ? 'Needs contacted/replied/client statuses.' : 'Потрібні статуси contacted/replied/client.'}</p>`;

  const intentHtml = (intentLeads || []).length
    ? `<div class="ax-intent-list">${(intentLeads || []).slice(0, 8).map(l => {
      const c = l.company || l;
      return `<div class="ax-intent-row"><div><div class="ax-intent-name">${esc(c.name || '—')}</div><div class="ax-intent-city">${esc(c.city || '')}</div></div></div>`;
    }).join('')}</div>`
    : `<p class="text-muted" style="font-size:12px;margin:0">—</p>`;

  const usage = u.apify ? u : { month: '—', apify: { usd: 0, cap: 1, runs: 0 }, openai: { usd: 0, cap: 1, calls: 0 }, brave: { usd: 0, cap: 1, calls: 0 } };

  return `<div class="analytics-hub">
    <header class="ax-header">
      <div>
        <h2 class="ax-title">${axT('page_analytics')}</h2>
        <p class="ax-sub">${axT('page_sub_analytics')}</p>
      </div>
      <button type="button" id="axRefresh" class="btn btn-ghost" style="font-size:13px">${axT('ax_refresh')}</button>
    </header>

    <div class="ax-kpis">
      <div class="ax-kpi">
        <div class="ax-kpi-val">${s.total_leads ?? 0}</div>
        <div class="ax-kpi-label">${axT('ax_total')}</div>
        <div class="ax-kpi-meta">${s.with_website ?? 0} ${axT('ax_website')}</div>
      </div>
      <div class="ax-kpi">
        <div class="ax-kpi-val">${s.with_email ?? 0}</div>
        <div class="ax-kpi-label">${axT('ax_email')}</div>
        <div class="ax-kpi-meta">${emailPct}% · ${s.verified_email ?? 0} ${axT('ax_verified')}</div>
      </div>
      <div class="ax-kpi ax-kpi--hot">
        <div class="ax-kpi-val">${(s.by_tier || {}).hot ?? 0}</div>
        <div class="ax-kpi-label">${axT('ax_hot')}</div>
        <div class="ax-kpi-meta">${s.with_intent ?? 0} intent</div>
      </div>
      <div class="ax-kpi ax-kpi--saved">
        <div class="ax-kpi-val">${s.saved ?? 0}</div>
        <div class="ax-kpi-label">${axT('ax_saved')}</div>
        <div class="ax-kpi-meta">${s.with_dm ?? 0} ${axT('ax_dm')}</div>
      </div>
    </div>

    <div class="ax-bento">
      <section class="ax-block ax-block--wide">
        <div class="ax-block-head"><span class="ax-block-title">${axT('ax_trend')}</span></div>
        ${lineChart(trendVals)}
      </section>
      <section class="ax-block ax-block--side">
        <div class="ax-block-head"><span class="ax-block-title">${axT('ax_coverage')}</span></div>
        ${gaugeChart(emailPct, 'reach')}
        <div class="ax-mini-stats">
          <div class="ax-mini-stat"><b>${s.verified_email ?? 0}</b><span>${axT('ax_verified')}</span></div>
          <div class="ax-mini-stat"><b>${s.with_intent ?? 0}</b><span>intent</span></div>
        </div>
      </section>

      <section class="ax-block">
        <div class="ax-block-head"><span class="ax-block-title">${axT('ax_funnel')}</span></div>
        ${statBars(funnel)}
      </section>
      <section class="ax-block">
        <div class="ax-block-head"><span class="ax-block-title">${axT('ax_tier')}</span></div>
        ${donutChart(s.by_tier || {})}
      </section>

      <section class="ax-block">
        <div class="ax-block-head"><span class="ax-block-title">${axT('ax_sources')}</span></div>
        ${statBars(s.by_source || {})}
      </section>
      <section class="ax-block">
        <div class="ax-block-head"><span class="ax-block-title">${axT('ax_cities')}</span></div>
        ${statBars(s.by_city || {})}
      </section>

      <section class="ax-block ax-block--third">
        <div class="ax-block-head"><span class="ax-block-title">${axT('ax_roi')}</span></div>
        <div class="ax-roi-grid">
          <div class="ax-roi-item"><div class="ax-roi-lbl">${axT('ax_roi_pipeline')}</div><div class="ax-roi-val">$${roi.pipeline_value_usd ?? '—'}</div></div>
          <div class="ax-roi-item"><div class="ax-roi-lbl">${axT('ax_roi_time')}</div><div class="ax-roi-val">${roi.hours_saved ?? '—'}h</div></div>
          <div class="ax-roi-item"><div class="ax-roi-lbl">${axT('ax_roi_mult')}</div><div class="ax-roi-val">${roi.roi_multiple ?? '—'}×</div></div>
        </div>
      </section>
      <section class="ax-block ax-block--third">
        <div class="ax-block-head"><span class="ax-block-title">${axT('ax_intent')}</span></div>
        ${intentHtml}
      </section>
      <section class="ax-block ax-block--third">
        <div class="ax-block-head"><span class="ax-block-title">${axT('ax_budget')} · ${esc(usage.month || '')}</span></div>
        <div class="ax-budget-row">
          <div class="ax-budget-head"><b>Apify</b><span>$${usage.apify?.usd ?? 0} / $${usage.apify?.cap ?? 0}</span></div>
          ${axBudgetBar(usage.apify || { usd: 0, cap: 1 }, '#22C55E')}
        </div>
        <div class="ax-budget-row">
          <div class="ax-budget-head"><b>OpenAI</b><span>$${usage.openai?.usd ?? 0} / $${usage.openai?.cap ?? 0}</span></div>
          ${axBudgetBar(usage.openai || { usd: 0, cap: 1 }, '#8B5CF6')}
        </div>
        <div class="ax-budget-row">
          <div class="ax-budget-head"><b>Brave</b><span>$${usage.brave?.usd ?? 0} / $${usage.brave?.cap ?? 0}</span></div>
          ${axBudgetBar(usage.brave || { usd: 0, cap: 1 }, '#F97316')}
        </div>
      </section>

      <section class="ax-block ax-block--full ax-icp">
        <div class="ax-block-head"><span class="ax-block-title">${axT('ax_icp')}</span></div>
        <textarea id="icpInput" placeholder="${lang === 'ru' ? 'Опишите идеального клиента…' : lang === 'en' ? 'Describe your ideal customer…' : 'Опишіть ідеального клієнта…'}">${esc(icp.icp || '')}</textarea>
        <div class="ax-icp-actions">
          <button type="button" id="icpSave" class="btn btn-primary" style="font-size:13px">${axT('ax_icp_save')}</button>
          <span id="icpMsg" class="text-muted" style="font-size:12px"></span>
        </div>
      </section>

      <section class="ax-block ax-block--full">
        <div class="ax-block-head"><span class="ax-block-title">${axT('ax_conv')}</span></div>
        ${convHtml}
      </section>
    </div>
  </div>`;
}

window.buildAnalyticsDashboard = buildAnalyticsDashboard;

