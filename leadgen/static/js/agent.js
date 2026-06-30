// ---- Agent chat ----
let agentSessionId=localStorage.getItem('lg_agent_session')||'';
const AGENT_SG=[
 {ic:'search',key:'sg_1',prompts:{
   uk:'Знайди 25 marketing agency у Києві',
   ru:'Найди 25 marketing agency в Киеве',
   en:'Find 25 marketing agencies in Kyiv'}},
 {ic:'briefcase',key:'sg_2',prompts:{
   uk:'Знайди agency з email у Львові (глибокий пошук)',
   ru:'Найди agency с email во Львове (глубокий поиск)',
   en:'Find agencies with email in Lviv (deep search)'}},
 {ic:'trend',key:'sg_3',prompts:{
   uk:'Покажи гарячі ліди з бази',
   ru:'Покажи горячие лиды из базы',
   en:'Show hot leads from database'}},
 {ic:'send',key:'sg_4',prompts:{
   uk:'Створи автокампанію: marketing agency, Київ+Львів, щодня о 7:00',
   ru:'Создай автокампанию: marketing agency, Киев+Львов, каждый день в 7:00',
   en:'Create autopilot campaign: marketing agency, Kyiv+Lviv, daily 7am'}},
];
function agentMd(text){return esc(text).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code style="font-size:11px">$1</code>').replace(/\n/g,'<br>');}
function chatLeadMini(l){
 const tier=l.tier||'cold';
 return `<div class="chat-lead-mini"><div class="lm-score ${tier}">${l.score??'—'}</div><div style="min-width:0"><div style="font-weight:600;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(l.name||'—')}</div><div class="text-muted" style="font-size:11px">${esc(l.city||'')}${(l.emails&&l.emails[0])?' · '+esc(l.emails[0]):''}</div></div></div>`;}
function agentBubble(role,text){
  const isUser=role==='user';
  const html=isUser?esc(text).replace(/\n/g,'<br>'):agentMd(text);
  return `<div class="flex ${isUser?'justify-end':''} animate-fadeup">
    <div class="max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${isUser?'chat-user':'chat-bot'}">${html}</div></div>`;}
function renderAgentWelcome(){
  const u=UI[lang];
  return `<div class="agent-welcome" id="agentWelcome">
    <div class="agent-orb" aria-hidden="true"></div>
    <h2>${esc(u.agent_welcome_h)}</h2>
    <p>${esc(u.agent_welcome_p)}</p>
    <div class="agent-suggestions">
      ${AGENT_SG.map((s,i)=>`<button type="button" class="suggestion-card" data-sg="${i}"><span class="sg-ic">${svg(s.ic,'w-4 h-4')}</span><span>${esc(u[s.key])}</span></button>`).join('')}
    </div></div>`;}
function bindAgentSuggestions(root){
  root?.querySelectorAll('.suggestion-card').forEach(btn=>btn.onclick=()=>{
    const sg=AGENT_SG[+btn.dataset.sg];
    if(!sg)return;
    $('#agentInput').value=sg.prompts[lang]||sg.prompts.uk;
    $('#agentInput').focus();
  });}
function typeAgentReply(chat,text){
  const wrapId='ab'+Date.now();
  chat.insertAdjacentHTML('beforeend',`<div class="flex animate-fadeup" id="${wrapId}"><div class="max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed chat-bot"><span class="agent-reply-body"></span><span class="typing-cursor" style="opacity:.6">▍</span></div></div>`);
  const body=chat.querySelector(`#${wrapId} .agent-reply-body`);
  const cursor=chat.querySelector(`#${wrapId} .typing-cursor`);
  if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){body.innerHTML=agentMd(text);cursor?.remove();chat.scrollTop=chat.scrollHeight;return;}
  let i=0;(function tick(){if(i>=text.length){cursor?.remove();chat.scrollTop=chat.scrollHeight;return;}
    body.innerHTML=agentMd(text.slice(0,++i));chat.scrollTop=chat.scrollHeight;setTimeout(tick,8);})();}
function initAgent(){
  const chat=$('#agentChat');
  const hasChat=chat.querySelector('.chat-user,.chat-bot');
  if(!hasChat)chat.innerHTML=renderAgentWelcome();
  bindAgentSuggestions(chat);
  $('#agentSession').textContent=agentSessionId?('session: '+agentSessionId.slice(0,8)):'';}
$('#agentForm').onsubmit=async e=>{
  e.preventDefault();
  const u=UI[lang],msg=$('#agentInput').value.trim();
  if(!msg)return;
  $('#agentWelcome')?.remove();
  $('#agentInput').value='';
  const chat=$('#agentChat');
  chat.insertAdjacentHTML('beforeend',agentBubble('user',msg));
  chat.insertAdjacentHTML('beforeend',`<div id="agentTyping" class="flex"><div class="chat-bot" style="padding:12px 16px;border-radius:var(--radius-lg)"><span class="typing-dots"><span></span><span></span><span></span></span></div></div>`);
  chat.scrollTop=chat.scrollHeight;
  $('#agentProgress').classList.remove('hidden');
  $('#agentProgressText').textContent=u.agent_thinking;
  try{
    const r=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:msg,session_id:agentSessionId||null,lang})});
    const sid=r.headers.get('X-Session-Id');
    if(sid){agentSessionId=sid;localStorage.setItem('lg_agent_session',sid);$('#agentSession').textContent='session: '+sid.slice(0,8);}
    const reader=r.body.getReader();const dec=new TextDecoder();let buf='',reply='';
    while(true){
      const {done,value}=await reader.read();if(done)break;
      buf+=dec.decode(value,{stream:true});
      const lines=buf.split('\n');buf=lines.pop()||'';
      for(const line of lines){
        if(!line.startsWith('data: '))continue;
        try{
          const ev=JSON.parse(line.slice(6));
          if(ev.event==='progress'){$('#agentProgressText').textContent=ev.data;}
          if(ev.event==='tool_start'){
            $('#agentProgressText').textContent='🔧 '+ev.data.tool;
            chat.insertAdjacentHTML('beforeend',`<div class="chat-tool"><span class="spin"></span><span>${esc(ev.data.tool)}</span></div>`);
            chat.scrollTop=chat.scrollHeight;
          }
          if(ev.event==='leads'&&Array.isArray(ev.data)&&ev.data.length){
            chat.insertAdjacentHTML('beforeend',`<div style="display:flex;flex-direction:column;gap:6px;margin:8px 0">${ev.data.map(chatLeadMini).join('')}</div>`);
            chat.scrollTop=chat.scrollHeight;
            refreshKpis();loadAll().catch(()=>{});
          }
          if(ev.event==='done'){reply=ev.data;}
          if(ev.event==='error'){reply='⚠ '+ev.data;}
        }catch(x){}
      }
    }
    $('#agentTyping')?.remove();
    if(reply)typeAgentReply(chat,reply);
  }catch(err){
    $('#agentTyping')?.remove();
    chat.insertAdjacentHTML('beforeend',agentBubble('assistant','⚠ '+esc(err.message||err)));
  }
  $('#agentProgress').classList.add('hidden');
  chat.scrollTop=chat.scrollHeight;
};

