// ---- outreach drawer ----
let dwLead=null, dwChannel='email', dwPersonIdx=0;
const hdr=()=>(typeof authHeaders==='function'?authHeaders():{'Content-Type':'application/json'});
function toast(msg,type){if(typeof showToast==='function')showToast(msg,type);else console.log(msg);}
function findLead(id){return [...lastLeads,...savedLeads,...allLeads].find(l=>l._id===id);}
function paintChannels(){$$('#dwChannels .chtab').forEach(b=>b.classList.toggle('on',b.dataset.ch===dwChannel));}
function openOutreach(id){const u=UI[lang];dwLead=findLead(id);if(!dwLead)return;
  const c=dwLead.company||{},dms=(dwLead.enrichment||{}).decision_makers||[];
  $('#dwName').textContent=c.name||'—';$('#dwSub').textContent=(c.gmaps_category||c.category||'')+' · '+(c.city||'');
  dwChannel='email';dwPersonIdx=0;paintChannels();
  const ps=$('#dwPerson');
  ps.innerHTML=dms.length?dms.map((p,i)=>`<option value="${i}">${esc(p.name)} · ${esc(p.role||'')}</option>`).join(''):`<option value="0">${esc(u.contact)}</option>`;
  $('#drawer').classList.remove('hidden');document.body.style.overflow='hidden';
  $('#dwAnalysis').innerHTML='<span class="spin"></span> '+u.agent_thinking;
  $('#dwMsg').value='';$('#dwRecs').innerHTML='<span class="spin"></span>';
  $('#dwFit').classList.add('hidden');
  runAnalysis();runRecs();genMessage();runQualify();}
async function runQualify(){
  try{const d=await apiJson('/api/qualify',{method:'POST',body:JSON.stringify({lead:dwLead,lang})});
  const f=$('#dwFit');if(d&&d.fit!=null){f.className='chip chip-gold';f.style.fontSize='10px';f.style.fontWeight='700';
    f.textContent='ICP '+d.fit+'%';f.title=d.reason||'';f.classList.remove('hidden');}
  else f.classList.add('hidden');}catch(e){toast(e.message||'Qualify failed','error');}}
async function runRecs(){
  try{const d=await apiJson('/api/recommend',{method:'POST',body:JSON.stringify({lead:dwLead,lang})});
  const recs=d.recommendations||[];
  $('#dwRecs').innerHTML=recs.length?recs.map(a=>`
    <div class="dw-rec-item">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px">
        <b style="font-size:13px;color:var(--gold-soft)">${esc(a.name)}</b>
        ${a.ai?'<span class="chip chip-violet" style="font-size:9px">AI</span>':''}
      </div>
      ${a.pitch?`<div class="text-muted" style="font-size:12px;margin-top:6px;line-height:1.5">${esc(a.pitch)}</div>`:''}
      ${a.template?`<a href="${esc(a.template.url)}" target="_blank" rel="noopener" class="text-accent" style="font-size:11px;margin-top:8px;display:inline-flex;align-items:center;gap:4px">${svg('ext','w-3 h-3')}n8n: ${esc((a.template.name||'').slice(0,42))}</a>`:''}
    </div>`).join(''):'<span class="text-muted" style="font-size:12px">—</span>';
  }catch(e){$('#dwRecs').innerHTML='<span class="text-muted" style="font-size:12px">⚠ '+esc(e.message||e)+'</span>';toast(e.message||'Recommend failed','error');}}
function closeDrawer(){$('#drawer').classList.add('hidden');document.body.style.overflow='';}
$('#dwClose').onclick=closeDrawer;$('#drawerBg').onclick=closeDrawer;
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){
    if(searchInFlight){e.preventDefault();cancelSearch();return;}
    closeDrawer();closeCmdPalette();if(!$('#leadModal').classList.contains('hidden'))closeLeadDetail();if(!$('#stats').classList.contains('hidden')){$('#stats').classList.add('hidden');document.body.style.overflow='';}
  }
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openCmdPalette();}
});
$$('#dwChannels .chtab').forEach(b=>b.onclick=()=>{dwChannel=b.dataset.ch;paintChannels();genMessage();});
$('#dwPerson').onchange=e=>{dwPersonIdx=+e.target.value;genMessage();};
async function runAnalysis(){try{
  const d=await apiJson('/api/analyze',{method:'POST',body:JSON.stringify({lead:dwLead,lang})});
  $('#dwAnalysis').textContent=d.summary||'—';
}catch(e){$('#dwAnalysis').textContent='⚠ '+(e.message||e);toast(e.message||'Analysis failed','error');}}
async function genMessage(){$('#dwMsg').value='…';
  try{const d=await apiJson('/api/outreach',{method:'POST',body:JSON.stringify({lead:dwLead,person_index:dwPersonIdx,channel:dwChannel,lang})});
  $('#dwMsg').value=d.message||d.error||'—';
  if(d.error)toast(d.error,'error');
  }catch(e){$('#dwMsg').value='⚠ '+(e.message||e);toast(e.message||'Message failed','error');}}
$('#dwGen').onclick=genMessage;
$('#dwCopy').onclick=()=>{const u=UI[lang];navigator.clipboard.writeText($('#dwMsg').value);toast(u.copied||'Copied');};
$('#dwQueue')?.addEventListener('click',async()=>{
  if(!dwLead)return;
  const emails=(dwLead.enrichment||{}).emails||[];
  const body=$('#dwMsg').value.trim();
  if(!body||body==='…'){toast('Generate message first','error');return;}
  try{
    const d=await apiJson('/api/outreach/enqueue',{method:'POST',body:JSON.stringify({
      lead_id:dwLead._id,channel:dwChannel,subject:'',body,to_email:emails[0]||null})});
    toast('Queued · '+d.queue_id);
    if(!dwLead._saved){await apiJson('/api/save',{method:'POST',body:JSON.stringify({lead:dwLead})});dwLead._saved=true;refreshSavedCount();}
  }catch(e){toast(e.message||'Queue failed','error');}
});
