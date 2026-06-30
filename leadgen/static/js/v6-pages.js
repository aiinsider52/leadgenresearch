/* LeadGen Autopilot v6 — page modules & UX extensions */
(function (global) {
  'use strict';

  const PIPELINE_STAGES = ['queued', 'fetching', 'enriching', 'dedupe', 'analyzing', 'done'];
  const STAGE_I18N = {
    queued: { uk: 'У черзі', ru: 'В очереди', en: 'Queued' },
    fetching: { uk: 'Збір даних', ru: 'Сбор данных', en: 'Fetching' },
    enriching: { uk: 'Збагачення', ru: 'Обогащение', en: 'Enriching' },
    dedupe: { uk: 'Дедуплікація', ru: 'Дедупликация', en: 'Deduplicating' },
    analyzing: { uk: 'Аналіз', ru: 'Анализ', en: 'Analyzing' },
    done: { uk: 'Готово', ru: 'Готово', en: 'Complete' },
    cancelled: { uk: 'Скасовано', ru: 'Отменено', en: 'Cancelled' },
    failed: { uk: 'Помилка', ru: 'Ошибка', en: 'Failed' },
  };

  let searchStartTime = 0;
  let searchTimerId = null;
  let originalPaintBudgetBanner = null;
  let originalPollSearchJob = null;
  let originalOpenLeadDetail = null;
  let originalOpenStats = null;
  let originalPaintTabs = null;
  let dwTab = 'message';

  function $(s) { return document.querySelector(s); }
  function $$(s) { return [...document.querySelectorAll(s)]; }

  function stageLabel(key) {
    const lang = global.getLgLang?.() || 'uk';
    return (STAGE_I18N[key] || STAGE_I18N.queued)[lang] || key;
  }

  function formatElapsed(ms) {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    return `${m}:${String(s % 60).padStart(2, '0')}`;
  }

  function updateSearchPipeline(stage, pct) {
    const box = $('#searchPipeline');
    if (!box) return;
    const idx = PIPELINE_STAGES.indexOf(stage);
    const steps = box.querySelectorAll('.pipeline-step');
    steps.forEach((el, i) => {
      el.classList.toggle('done', i < idx || stage === 'done');
      el.classList.toggle('active', i === idx && stage !== 'done');
    });
    const fill = $('#pipelineBarFill');
    if (fill) fill.style.width = `${pct ?? (idx >= 0 ? ((idx + 1) / PIPELINE_STAGES.length) * 100 : 0)}%`;
    const elapsed = $('#pipelineElapsed');
    if (elapsed && searchStartTime) elapsed.textContent = formatElapsed(Date.now() - searchStartTime);
  }

  function showPipeline(show) {
    const box = $('#searchPipeline');
    if (box) box.classList.toggle('hidden', !show);
    if (show) {
      searchStartTime = Date.now();
      if (searchTimerId) clearInterval(searchTimerId);
      searchTimerId = setInterval(() => updateSearchPipeline(inferStage(), null), 1000);
    } else {
      if (searchTimerId) { clearInterval(searchTimerId); searchTimerId = null; }
    }
  }

  let currentPipelineStage = 'queued';
  function inferStage() { return currentPipelineStage; }

  function mapJobToStage(job, elapsedMs) {
    if (job.status === 'pending') return 'queued';
    if (job.status === 'failed') return 'failed';
    if (job.status === 'cancelled') return 'cancelled';
    if (job.status === 'done') return 'done';
    const meta = job.result?.meta || job.meta || {};
    if (meta.deduped_before_enrichment != null && elapsedMs > 8000) return 'dedupe';
    if (meta.enriching || (global.lastSearchPayload && JSON.parse(global.lastSearchPayload || '{}').enrich && elapsedMs > 5000)) return 'enriching';
    if (elapsedMs > 12000) return 'analyzing';
    return 'fetching';
  }

  function showToast(msg, type) {
    let root = $('#toastRoot');
    if (!root) {
      root = document.createElement('div');
      root.id = 'toastRoot';
      root.className = 'toast-root';
      document.body.appendChild(root);
    }
    const el = document.createElement('div');
    el.className = 'toast-item';
    if (type === 'error') el.style.borderColor = 'rgba(255,90,95,0.4)';
    el.textContent = msg;
    root.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  function providerStatus(row) {
    if (!row) return { label: 'Ready', cls: 'healthy' };
    if (row.blocked) return { label: 'Exhausted', cls: 'exhausted' };
    const pct = row.cap_usd ? (row.spent_usd / row.cap_usd) * 100 : 0;
    if (pct >= 90) return { label: 'Degraded', cls: 'degraded' };
    return { label: 'Healthy', cls: 'healthy' };
  }

  async function renderInfrastructurePage() {
    const body = $('#infraBody');
    if (!body) return;
    body.innerHTML = '<div class="text-muted" style="padding:24px"><span class="spin"></span> Loading…</div>';
    try {
      const [u, storage, db, jobs] = await Promise.all([
        fetch('/api/usage').then(r => r.json()),
        fetch('/api/storage/status').then(r => r.json()).catch(() => ({})),
        fetch('/api/db/status').then(r => r.json()).catch(() => ({})),
        fetch('/api/jobs').then(r => r.json()).catch(() => ({ jobs: [] })),
      ]);
      const bud = u.budget || {};
      global.budgetState = bud;
      const providers = [
        { key: 'openai', name: 'OpenAI', features: 'AI analysis, agent, outreach' },
        { key: 'brave', name: 'Brave', features: 'Intent · Places · Discovery' },
        { key: 'apify', name: 'Apify', features: 'IG · FB · Maps · Jobs' },
        { key: 'hunter', name: 'Hunter', features: 'Email waterfall' },
        { key: 'apollo', name: 'Apollo', features: 'Contact enrichment' },
      ];
      let healthy = 0;
      const cards = providers.map(p => {
        const row = u[p.key] || bud.providers?.[p.key] || { spent_usd: 0, cap_usd: 10, calls: 0, runs: 0 };
        const st = providerStatus(row.blocked != null ? row : { ...row, blocked: (bud.unavailable_sources || []).some(() => false) && row.blocked });
        const blocked = row.blocked || (bud.blocked_providers || []).includes(p.key);
        const status = blocked ? { label: 'Exhausted', cls: 'exhausted' } : providerStatus({ ...row, blocked: false });
        if (status.cls === 'healthy') healthy++;
        const pct = row.cap_usd ? Math.min(100, Math.round((row.spent_usd / row.cap_usd) * 100)) : 0;
        const barCls = pct >= 100 ? 'danger' : pct >= 85 ? 'warn' : '';
        const calls = row.calls ?? row.runs ?? 0;
        return `<div class="provider-card ${status.cls === 'exhausted' ? 'exhausted' : status.cls === 'degraded' ? 'degraded' : ''}">
          <div class="provider-head">
            <span class="provider-name">${p.name}</span>
            <span class="provider-status"><span class="status-dot ${status.cls}"></span>${status.label}</span>
          </div>
          <div class="provider-usage">${calls} calls · $${row.spent_usd ?? 0} / $${row.cap_usd ?? '—'}</div>
          <div class="provider-bar"><div class="provider-bar-fill ${barCls}" style="width:${pct}%"></div></div>
          <div class="provider-features">${p.features}${blocked ? ' ✗' : ' ✓'}</div>
        </div>`;
      }).join('');
      const overall = Math.round((healthy / providers.length) * 100);
      const jobList = (jobs.jobs || jobs || []).slice(0, 8);
      const running = jobList.filter(j => j.status === 'running' || j.status === 'pending').length;
      body.innerHTML = `
        <div class="infra-overall">
          <div><div style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-tertiary)">Infrastructure health</div>
          <div class="infra-overall-val">${overall}%</div></div>
          <div class="provider-bar" style="flex:1;max-width:280px"><div class="provider-bar-fill" style="width:${overall}%"></div></div>
        </div>
        <div style="margin-top:20px">${cards}</div>
        <div class="provider-card" style="margin-top:20px">
          <div class="provider-head"><span class="provider-name">Storage</span><span class="provider-status"><span class="status-dot healthy"></span>${storage.status || 'OK'}</span></div>
          <div class="provider-usage">${storage.leads ?? '—'} leads · ${storage.events ?? '—'} events · SQLite ${db.ok !== false ? 'healthy' : 'degraded'}</div>
        </div>
        <div class="provider-card">
          <div class="provider-head"><span class="provider-name">Jobs</span></div>
          <div class="provider-usage">${running} running · ${jobList.filter(j => j.status === 'done').length} completed (recent)</div>
        </div>`;
      const dot = $('#infraHealthDot');
      if (dot) {
        dot.className = 'status-dot ' + (overall >= 80 ? 'healthy' : overall >= 50 ? 'degraded' : 'exhausted');
      }
      if (typeof global.paintBudgetEnrichToggles === 'function') global.paintBudgetEnrichToggles();
      if (typeof global.paintSources === 'function') global.paintSources();
    } catch (e) {
      body.innerHTML = `<div class="text-muted" style="padding:24px">⚠ ${e.message || e}</div>`;
    }
  }

  function bindCampHandlers(cl) {
    $('#campCreate')?.addEventListener('click', async () => {
      const cities = ($('#city')?.value || '').split(',').map(x => x.trim()).filter(Boolean) || ['Київ'];
      const body = {
        name: $('#campName')?.value || ($('#category')?.value + ' autopilot'),
        category: $('#category')?.value,
        cities,
        source: global.getLgSource?.() || 'osm',
        limit_per_run: +($('#campLimit')?.value || 80),
        cron: $('#campCron')?.value,
        auto_outreach: $('#campOutreach')?.checked,
        expand_niche: $('#campExpand')?.checked,
        lang: global.getLgLang?.() || 'uk',
        discover_websites: $('#discoverWebsites')?.checked,
        brave_people: $('#bravePeople')?.checked,
        brave_news: $('#braveNews')?.checked,
        brave_intent: $('#braveIntent')?.checked,
      };
      await fetch('/api/campaigns', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      showToast(cl.created || 'Campaign created');
      renderCampaignsPage();
      if (typeof global.refreshKpis === 'function') global.refreshKpis();
    }, { once: true });
    $('#campRunDue')?.addEventListener('click', async () => {
      await fetch('/api/campaigns/run_due', { method: 'POST' });
      renderCampaignsPage();
      if (typeof global.refreshKpis === 'function') global.refreshKpis();
    }, { once: true });
    $$('[data-crun]').forEach(b => b.onclick = async () => {
      await fetch('/api/campaigns/' + b.dataset.crun + '/run', { method: 'POST' });
      renderCampaignsPage();
    });
    $$('[data-ctoggle]').forEach(b => b.onclick = async () => {
      const id = b.dataset.ctoggle, paused = b.dataset.st === 'active';
      await fetch('/api/campaigns/' + id + (paused ? '/pause' : '/resume'), { method: 'POST' });
      renderCampaignsPage();
    });
    $$('[data-cdel]').forEach(b => b.onclick = async () => {
      if (!confirm('Delete campaign?')) return;
      await fetch('/api/campaigns/' + b.dataset.cdel, { method: 'DELETE' });
      renderCampaignsPage();
    });
  }

  async function renderCampaignsPage() {
    const body = $('#campaignsBody');
    if (!body) return;
    const campLbl = {
      uk: { title: 'Кампанії', new: 'Нова кампанія', name: 'Назва', active: 'активна', paused: 'пауза', last: 'останній', total: 'всього', none: 'Ще немає кампаній', runDue: '▶ Due now', runs: 'Останні запуски', create: 'Створити', created: 'Кампанію створено' },
      en: { title: 'Campaigns', new: 'New campaign', name: 'Name', active: 'active', paused: 'paused', last: 'last', total: 'total', none: 'No campaigns yet', runDue: '▶ Run due', runs: 'Recent runs', create: 'Create', created: 'Campaign created' },
    };
    const cl = campLbl[global.getLgLang?.() || 'uk'] || campLbl.uk;
    const [campData, runs] = await Promise.all([
      fetch('/api/campaigns').then(r => r.json()),
      fetch('/api/campaigns/runs?limit=12').then(r => r.json()),
    ]);
    const camps = campData.campaigns || [];
    const cronPresets = campData.cron_presets || { daily_7: '0 7 * * *', daily_8: '0 8 * * *' };
    body.innerHTML = `
      <div class="page-header">
        <h3 style="margin:0;font-family:var(--font-display);font-size:var(--fs-h1)">${cl.title}</h3>
        <button id="campRunDue" class="btn btn-secondary">${cl.runDue}</button>
      </div>
      <div class="campaign-card">
        <div style="font-size:12px;font-weight:600;margin-bottom:12px;color:var(--text-tertiary)">${cl.new}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
          <input id="campName" class="input" placeholder="${cl.name}">
          <select id="campCron" class="select-field">${Object.entries(cronPresets).map(([k, v]) => `<option value="${v}">${k}</option>`).join('')}</select>
          <input id="campLimit" type="number" min="10" max="200" value="80" class="input">
          <label style="display:flex;align-items:center;gap:8px;font-size:12px"><input type="checkbox" id="campExpand" checked> AI expand</label>
          <label style="display:flex;align-items:center;gap:8px;font-size:12px"><input type="checkbox" id="campOutreach"> Auto outreach</label>
        </div>
        <button id="campCreate" class="btn btn-primary" style="width:100%">${cl.create}</button>
      </div>
      <div id="campList">${camps.length ? camps.map(c => `
        <div class="campaign-card">
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">
            <div style="min-width:0">
              <div style="font-weight:600;font-size:15px">${global.esc ? global.esc(c.name) : c.name}</div>
              <div class="text-muted" style="font-size:12px;margin-top:4px">${c.category} · ${(c.cities || []).join(', ')} · ${c.source || 'osm'}</div>
              <div class="text-muted" style="font-size:11px;margin-top:6px">● ${c.status === 'active' ? cl.active : cl.paused} · Next: ${c.cron || '—'}</div>
              <div class="text-muted" style="font-size:11px;margin-top:2px">${cl.last}: ${c.last_run ? c.last_run.slice(0, 16).replace('T', ' ') : '—'} · +${(c.totals || {}).leads || 0} leads</div>
            </div>
            <div style="display:flex;gap:4px;flex-shrink:0">
              <button data-crun="${c.id}" class="btn btn-ghost" style="padding:6px 10px;font-size:12px">▶</button>
              <button data-ctoggle="${c.id}" data-st="${c.status}" class="btn btn-ghost" style="padding:6px 10px;font-size:12px">${c.status === 'active' ? '⏸' : '▶'}</button>
              <button data-cdel="${c.id}" class="btn btn-ghost" style="padding:6px 10px;font-size:12px;color:var(--danger)">⋯</button>
            </div>
          </div>
        </div>`).join('') : `<p class="text-muted">${cl.none}</p>`}</div>
      ${runs.length ? `<div class="camp-run-timeline"><div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-tertiary);margin-bottom:10px">${cl.runs}</div>
        ${runs.map(r => `<div class="text-muted" style="font-size:12px;padding:6px 0;border-bottom:1px solid var(--border)">${r.ts?.slice(0, 16).replace('T', ' ') || ''} · +${r.leads_found || 0} · hot ${r.hot || 0}</div>`).join('')}</div>` : ''}`;
    bindCampHandlers(cl);
  }

  async function renderAnalyticsPage() {
    const body = $('#analyticsBody');
    if (!body) return;
    if (typeof global.openStats === 'function') {
      await global.openStats();
      const statsHtml = $('#statsBody')?.innerHTML || '';
      body.innerHTML = `<div class="exec-kpi-grid page-panel">${statsHtml}</div>`;
      $('#stats')?.classList.add('hidden');
      document.body.style.overflow = '';
      bindAnalyticsHandlers();
    }
  }

  function bindAnalyticsHandlers() {
    $('#icpSave')?.addEventListener('click', async () => {
      await fetch('/api/icp', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ icp: $('#icpInput')?.value }) });
      showToast('ICP saved');
    });
    $('#schAdd')?.addEventListener('click', async () => {
      const cities = ($('#city')?.value || '').split(',').map(x => x.trim()).filter(Boolean);
      const search = {
        category: $('#category')?.value, country: $('#country')?.value, limit: +$('#limit')?.value,
        lang: global.getLgLang?.() || 'uk', enrich: $('#enrich')?.checked, discover_websites: $('#discoverWebsites')?.checked,
        brave_people: $('#bravePeople')?.checked, brave_news: $('#braveNews')?.checked,
        brave_intent: $('#braveIntent')?.checked, source: global.sourceMode, ig_mode: global.igMode,
      };
      if (cities.length > 1) search.cities = cities; else search.city = $('#city')?.value;
      await fetch('/api/schedules', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ search }) });
      renderAnalyticsPage();
    });
    $$('.schDel').forEach(b => b.onclick = async () => {
      await fetch('/api/schedules/' + b.dataset.i, { method: 'DELETE' });
      renderAnalyticsPage();
    });
  }

  function showPagePanels() {
    const t = global.getLgTab ? global.getLgTab() : 'search';
    const isData = t === 'search' || t === 'all' || t === 'saved';
    $('#searchPanel')?.classList.toggle('hidden', t === 'agent' || t === 'campaigns' || t === 'analytics' || t === 'infrastructure');
    $('#agentPanel')?.classList.toggle('hidden', t !== 'agent');
    $('#campaignsPanel')?.classList.toggle('hidden', t !== 'campaigns');
    $('#analyticsPanel')?.classList.toggle('hidden', t !== 'analytics');
    $('#infraPanel')?.classList.toggle('hidden', t !== 'infrastructure');
    $('#kpiStrip')?.classList.toggle('hidden', t === 'agent' || t === 'infrastructure');
    if (t === 'campaigns') renderCampaignsPage();
    if (t === 'analytics') renderAnalyticsPage();
    if (t === 'infrastructure') renderInfrastructurePage();
  }

  function initDrawerTabs() {
    const drawer = $('#drawer');
    if (!drawer || drawer.dataset.dwTabs) return;
    drawer.dataset.dwTabs = '1';
    const content = drawer.querySelector('aside > div:last-child');
    if (!content) return;
    const sections = content.querySelectorAll('section');
    if (sections.length < 3) return;
    const tabs = document.createElement('div');
    tabs.className = 'dw-tabs';
    tabs.innerHTML = `
      <button type="button" class="dw-tab on" data-dw="message">Message</button>
      <button type="button" class="dw-tab" data-dw="analysis">Analysis</button>
      <button type="button" class="dw-tab" data-dw="automations">Automations</button>`;
    content.parentElement.insertBefore(tabs, content);
    sections[0].classList.add('dw-pane'); sections[0].dataset.dw = 'analysis';
    sections[1].classList.add('dw-pane'); sections[1].dataset.dw = 'automations';
    sections[2].classList.add('dw-pane'); sections[2].dataset.dw = 'message';
    sections[0].classList.add('hidden');
    sections[1].classList.add('hidden');
    function paintDw() {
      $$('.dw-tab').forEach(b => b.classList.toggle('on', b.dataset.dw === dwTab));
      $$('.dw-pane').forEach(p => p.classList.toggle('hidden', p.dataset.dw !== dwTab));
    }
    tabs.querySelectorAll('.dw-tab').forEach(b => b.onclick = () => { dwTab = b.dataset.dw; paintDw(); });
    paintDw();
  }

  async function loadLeadHistory(id, container) {
    if (!container) return;
    try {
      const rows = await fetch('/api/history?lead_id=' + encodeURIComponent(id)).then(r => r.json());
      const list = Array.isArray(rows) ? rows : rows.events || [];
      container.innerHTML = list.length
        ? list.map(e => `<div class="lm-timeline-item"><time>${global.esc ? global.esc(e.ts || e.created_at || '') : ''}</time><div>${global.esc ? global.esc(e.action || e.type || e.summary || '') : ''}</div></div>`).join('')
        : '<span class="text-muted" style="font-size:12px">—</span>';
    } catch {
      container.innerHTML = '<span class="text-muted" style="font-size:12px">—</span>';
    }
  }

  function patchOpenLeadDetail() { /* two-column layout in index.html */ }

  function patchPollSearchJob() {
    if (!global.pollSearchJob || originalPollSearchJob) return;
    originalPollSearchJob = global.pollSearchJob;
    global.pollSearchJob = async function (jobId, mySeq, signal) {
      showPipeline(true);
      currentPipelineStage = 'queued';
      updateSearchPipeline('queued', 10);
      const u = global.UI?.[global.getLgLang?.() || 'uk'] || {};
      const t0 = Date.now();
      while (true) {
        if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
        if (mySeq !== (global.getSearchSeq?.() ?? mySeq)) throw new DOMException('Aborted', 'AbortError');
        const r = await fetch(`/api/jobs/${jobId}`, { signal });
        const job = await r.json();
        if (job.status === 'done') {
          currentPipelineStage = 'done';
          updateSearchPipeline('done', 100);
          showPipeline(false);
          return job.result;
        }
        if (job.status === 'failed') {
          showPipeline(false);
          throw new Error(job.error || 'Search failed');
        }
        if (job.status === 'cancelled') {
          showPipeline(false);
          throw new DOMException('Aborted', 'AbortError');
        }
        const elapsed = Date.now() - t0;
        currentPipelineStage = mapJobToStage(job, elapsed);
        const idx = PIPELINE_STAGES.indexOf(currentPipelineStage);
        const pct = Math.min(95, ((idx + 1) / PIPELINE_STAGES.length) * 100);
        updateSearchPipeline(currentPipelineStage, pct);
        const label = (STAGE_I18N[currentPipelineStage] || {})[global.getLgLang?.() || 'uk'] || currentPipelineStage;
        const st = document.querySelector('#status');
        if (st) st.innerHTML = `<span class="spin"></span><span>${label}…</span>`;
        await global.sleep?.(1200, signal) ?? new Promise(res => setTimeout(res, 1200));
      }
    };
  }

  function patchBeginSearchUI() {
    const orig = global.beginSearchUI;
    if (!orig) return;
    global.beginSearchUI = function () {
      orig();
      showPipeline(true);
      currentPipelineStage = 'queued';
      updateSearchPipeline('queued', 5);
    };
    const origEnd = global.endSearchUI;
    if (origEnd) {
      global.endSearchUI = function () {
        origEnd();
        showPipeline(false);
      };
    }
  }

  function patchPaintBudgetBanner() {
    if (!global.paintBudgetBanner) return;
    originalPaintBudgetBanner = global.paintBudgetBanner;
    global.paintBudgetBanner = function (u) {
      if (u?.budget) global.budgetState = u.budget;
      const el = $('#budgetBanner');
      if (el) { el.classList.add('hidden'); el.innerHTML = ''; }
      const dot = $('#infraHealthDot');
      if (dot && u?.budget) {
        const blocked = (u.budget.blocked_providers || []).length;
        dot.className = 'status-dot ' + (blocked === 0 ? 'healthy' : blocked >= 2 ? 'exhausted' : 'degraded');
      }
    };
  }

  function extendPaintTabs() {
    if (!global.paintTabs || originalPaintTabs) return;
    originalPaintTabs = global.paintTabs;
    const PAGE_TITLES = {
      search: 'page_search', agent: 'page_agent', all: 'page_all', saved: 'page_saved',
      campaigns: 'page_campaigns', analytics: 'page_analytics', infrastructure: 'page_infra',
    };
    const PAGE_SUBS = {
      search: 'page_sub_search', agent: 'page_sub_agent', all: 'page_sub_all', saved: 'page_sub_saved',
      campaigns: 'page_sub_campaigns', analytics: 'page_sub_analytics', infrastructure: 'page_sub_infra',
    };
    global.paintTabs = function () {
      originalPaintTabs();
      const u = global.UI?.[global.getLgLang?.() || 'uk'] || {};
      const t = global.getLgTab ? global.getLgTab() : 'search';
      if (PAGE_TITLES[t]) {
        const pt = $('#pageTitle'); if (pt && u[PAGE_TITLES[t]]) pt.textContent = u[PAGE_TITLES[t]];
        const ps = $('#pageSub'); if (ps && u[PAGE_SUBS[t]]) ps.textContent = u[PAGE_SUBS[t]];
      }
      $$('.page-nav').forEach(b => b.classList.toggle('tab-active', b.dataset.tab === t));
      showPagePanels();
    };
  }

  function bindPageNav() {
    $$('.page-nav').forEach(b => {
      b.onclick = () => {
        if (global.setLgTab) global.setLgTab(b.dataset.tab);
        const t = global.getLgTab?.() || 'search';
        if (t === 'saved') global.loadSaved?.();
        else if (t === 'all') global.loadAll?.();
        else if (t === 'agent') global.initAgent?.();
        else if (t === 'search') global.renderCurrent?.();
      };
    });
    $('#infraHealthBtn')?.addEventListener('click', () => {
      global.setLgTab?.('infrastructure');
    });
    $('#statsBtnSide')?.addEventListener('click', (e) => {
      e.preventDefault();
      global.tab = 'analytics';
      global.paintTabs?.();
    }, true);
  }

  function patchRender() {
    const orig = global.render;
    if (!orig) return;
    global.render = function (leads, total) {
      orig(leads, total);
      const out = $('#results');
      if (!out) return;
      const capMsg = out.querySelector('[data-render-cap]');
      if (!capMsg && leads.length > (global.RENDER_CAP || 250)) {
        const div = document.createElement('div');
        div.className = 'render-cap-footer';
        div.dataset.renderCap = '1';
        div.textContent = `Showing ${global.RENDER_CAP || 250} of ${leads.length}. Narrow with search.`;
        out.appendChild(div);
      }
    };
  }

  function initV6Redesign() {
    patchPaintBudgetBanner();
    patchPollSearchJob();
    patchBeginSearchUI();
    patchOpenLeadDetail();
    extendPaintTabs();
    bindPageNav();
    patchRender();
    initDrawerTabs();
    const origOpenOutreach = global.openOutreach;
    if (origOpenOutreach) {
      global.openOutreach = function (id) { origOpenOutreach(id); initDrawerTabs(); };
    }
    global.showToast = showToast;
    global.renderInfrastructurePage = renderInfrastructurePage;
    global.renderCampaignsPage = renderCampaignsPage;
    global.renderAnalyticsPage = renderAnalyticsPage;
    if (typeof global.refreshBudget === 'function') global.refreshBudget();
  }

  global.initV6Redesign = initV6Redesign;
})(window);
