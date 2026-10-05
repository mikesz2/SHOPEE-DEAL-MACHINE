let runtime={},sourceDiag={},offerOffset=0,offerTotal=0,offerLimit=60,selected=new Set();
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const money=v=>Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const dt=v=>v?new Date(/(?:Z|[+-]\d{2}:?\d{2})$/.test(v)?v:v+'Z').toLocaleString('pt-BR'):'—';
const pct=v=>Number(v||0).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})+'%';
const statusLabel={queued:'Na fila',published:'Publicada',rejected:'Rejeitada',failed:'Falhou',duplicate:'Duplicada',reserved:'Processando'};
const viewMeta={whatsapp:['WhatsApp','Conexão, grupos e confirmação dos envios.'],dashboard:['Visão geral','Operação, receita e saúde do robô em tempo real.'],deals:['Ofertas','Pesquise, filtre e opere todo o pipeline de ofertas.'],radar:['Radar Telegram','Monitore fontes concorrentes e importe histórico com segurança.'],automation:['Automação','Regras de qualidade, ritmo e proteção da operação.'],analytics:['Performance','Aprenda com conversões, comissão e desempenho de conteúdo.'],system:['Sistema','Observabilidade, integrações e trilha de auditoria.']};

async function api(path,opt={}){
  const cfg={credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt};
  let r; try{r=await fetch(path,cfg)}catch(e){throw Error('Não foi possível alcançar o serviço Web. Verifique o status do Web na Central Windows.')}
  let d={}; try{d=await r.json()}catch{try{d={detail:await r.text()}}catch{}}
  if(r.status===401){location.href='/login';throw Error('Sessão expirada')}
  if(!r.ok)throw Error(Array.isArray(d.detail)?d.detail.map(x=>`${x.loc?.slice(1).join('.')||'Campo'}: ${x.msg}`).join('; '):(d.detail||d.error||`HTTP ${r.status}`));
  return d;
}
function toast(text,bad=false,title=bad?'Ação não concluída':'Concluído'){
  const x=$('#toast'); $('#toastTitle').textContent=title; $('#toastText').textContent=text; x.classList.toggle('bad',bad); x.style.display='block'; clearTimeout(window.__toast); window.__toast=setTimeout(()=>x.style.display='none',5500);
}
function openView(name){
  if(!viewMeta[name])return; history.replaceState(null,'','#'+name);
  $$('.view').forEach(x=>x.classList.toggle('active',x.id===`view-${name}`)); $$('.nav').forEach(x=>x.classList.toggle('active',x.dataset.view===name));
  $('#pageTitle').textContent=viewMeta[name][0]; $$('.nav').forEach(x=>x.setAttribute('aria-current',x.dataset.view===name?'page':'false')); $('#pageSubtitle').textContent=viewMeta[name][1]; $('#sidebar').classList.remove('open'); $('#sidebarBackdrop').hidden=true; $('#menuBtn').setAttribute('aria-expanded','false');
  if(name==='whatsapp')loadWhatsApp();
  if(name==='deals')loadOffers(); if(name==='radar')loadSources(); if(name==='automation'&&!settingsDirty)loadSettings(); if(name==='analytics')loadAnalytics(); if(name==='system'){loadHealth();loadActivity(true)};
}
$$('.nav').forEach(b=>b.addEventListener('click',()=>openView(b.dataset.view))); $('#menuBtn').setAttribute('aria-controls','sidebar');
$('#menuBtn').setAttribute('aria-expanded','false');
$('#menuBtn').onclick=()=>{const open=$('#sidebar').classList.toggle('open');$('#sidebarBackdrop').hidden=!open;$('#menuBtn').setAttribute('aria-expanded',String(open))};
function closeMobileMenu(){$('#sidebar').classList.remove('open');$('#sidebarBackdrop').hidden=true;$('#menuBtn').setAttribute('aria-expanded','false')}
$('#sidebarBackdrop').onclick=closeMobileMenu;
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMobileMenu()});
async function logout(){try{await api('/api/logout',{method:'POST'})}catch{} location.href='/login'}

async function loadDashboard(){
  const d=await api('/api/dashboard?days=7');
  window.dashboardData=d;
  renderDashboard(d);
}
function renderServicePill(s){const offline=Number(!s.worker)+Number(!s.reader);$('#healthBadge').innerHTML=`<span class="${offline?'warn':'ok'}">●</span> ${offline?offline+' serviço'+(offline>1?'s':'')+' offline':'Serviços online'}`;$('#healthBadge').title='Publicador: '+(s.worker?'online':'offline')+' · Radar Telegram: '+(s.reader?'online':'offline')}
async function loadHealth(){
  const h=await api('/api/system/health'); renderServicePill({worker:!!h.worker,reader:!!h.listener}); $('#systemHealth').textContent=JSON.stringify(h,null,2);
  const cards=[['Web',true,'Painel e API'],['Worker',!!h.worker,h.worker?.error_streak?`${h.worker.error_streak} falhas recentes`:'Processador de fila'],['Reader',!!h.listener,'Radar Telegram'],['Shopee',!!h.shopee_configured,'Affiliate Open API'],['Telegram Bot',!!h.telegram_bot_configured,'Publicador']];
  $('#systemCards').innerHTML=cards.map(x=>`<div class="healthCard"><div class="dot ${x[1]?'ok':'bad'}">●</div><b>${x[0]}</b><span>${esc(x[2])}</span></div>`).join('');
}
async function loadActivity(full=false){
  const rows=await api('/api/activity?limit='+(full?60:8)); const html=rows.length?rows.map(a=>`<div class="activityItem"><span class="activityDot ${esc(a.severity)}"></span><div><b>${esc(a.message)}</b><p>${esc(a.type)} · ${dt(a.created_at)}</p></div></div>`).join(''):'<span class="hint">A trilha de auditoria começará a ser preenchida conforme o sistema operar.</span>';
  if(full)$('#activityFull').innerHTML=html; else $('#activityMini').innerHTML=html;
}

function offerQuery(){const q=new URLSearchParams({limit:offerLimit,offset:offerOffset,status:$('#offerStatus')?.value||'all',source_type:$('#offerSourceType')?.value||'all'});const term=$('#offerSearch')?.value?.trim();if(term)q.set('q',term);return q}
async function loadOffers(){
  const d=await api('/api/offers?'+offerQuery()); offerTotal=d.total; const rows=d.items; window.currentOffers=rows; rows.forEach(e=>offerCache.set(e.id,e)); selected.clear(); $('#selectAll').checked=false; updateSelected(); $$('[data-status]').forEach(b=>b.classList.toggle('active',b.dataset.status===$('#offerStatus').value));
  $('#offers').innerHTML=rows.length?rows.map(e=>{let p=e.product;return `<tr><td class="check"><input type="checkbox" data-offer-id="${e.id}"></td><td><div class="productCell">${p.image_url?`<img class="thumb" src="${esc(safeUrl(p.image_url))}" loading="lazy" alt="">`:''}<div><b>${esc(p.name).slice(0,100)}</b><div class="meta">${esc(p.category)} · ${p.price?money(p.price):'sem preço'}${p.discount!=null?' · '+pct(p.discount)+' off':''}${p.commission_rate?' · com. '+pct(p.commission_rate):''}</div>${e.reject_reason?`<div class="reason">${esc(e.reject_reason)}</div>`:''}</div></div></td><td><b>${esc(e.source_ref||e.source_type)}</b><div class="meta">${esc(e.source_type)}</div></td><td class="score">${Number(e.score).toFixed(1)}</td><td>${Number(e.trend_score).toFixed(1)}</td><td><span class="pill ${esc(e.status)}">${esc(statusLabel[e.status]||e.status)}</span></td><td>${dt(e.created_at)}</td><td><button class="btn tiny soft" onclick="previewOffer(${e.id})">Detalhes</button> ${e.status==='queued'?`<button class="btn tiny" onclick="previewOffer(${e.id})">Revisar</button>`:(['failed','rejected','duplicate'].includes(e.status)?`<button class="btn tiny soft" onclick="retryOffer(${e.id})">Reenfileirar</button>`:'')}</td></tr>`}).join(''):'<tr><td colspan="8" class="hint">Nenhuma oferta encontrada com esses filtros.</td></tr>';
  $('#offerCount').textContent=`${offerTotal} oferta${offerTotal===1?'':'s'}`; $('#offerPage').textContent=Math.floor(offerOffset/offerLimit)+1;
  $$('[data-offer-id]').forEach(c=>c.onchange=()=>{c.checked?selected.add(Number(c.dataset.offerId)):selected.delete(Number(c.dataset.offerId));updateSelected()});
}
function updateSelected(){if($('#selectedCount'))$('#selectedCount').textContent=`${selected.size} selecionada${selected.size===1?'':'s'}`}
function pageOffers(dir){const next=offerOffset+dir*offerLimit;if(next<0||next>=offerTotal&&dir>0)return;offerOffset=Math.max(0,next);loadOffers()}
$('#selectAll').onchange=e=>{$$('[data-offer-id]').forEach(c=>{c.checked=e.target.checked;if(c.checked)selected.add(Number(c.dataset.offerId));else selected.delete(Number(c.dataset.offerId))});updateSelected()};
$('#offerSearch').addEventListener('keydown',e=>{if(e.key==='Enter'){offerOffset=0;loadOffers()}});
async function publishNow(id){try{await api(`/api/offers/${id}/publish`,{method:'POST'});toast('Oferta processada para os destinos selecionados.');await refreshAll()}catch(e){toast(e.message,true)}}
async function retryOffer(id){try{await api(`/api/offers/${id}/retry`,{method:'POST'});toast('Oferta devolvida à fila.');loadOffers()}catch(e){toast(e.message,true)}}
async function bulkAction(action){if(!selected.size)return toast('Selecione pelo menos uma oferta.',true);try{const d=await api('/api/offers/bulk',{method:'POST',body:JSON.stringify({offer_ids:[...selected],action})});toast(`${d.changed} ofertas atualizadas.`);loadOffers()}catch(e){toast(e.message,true)}}
function showManual(){ $('#manualDialog').showModal() }
async function manualIngest(){try{let d=await api('/api/manual/ingest',{method:'POST',body:JSON.stringify({url:$('#manualUrl').value,source_ref:$('#manualSource').value})});toast(`Oferta #${d.offer_id}: ${statusLabel[d.status]||d.status} · score ${Number(d.score).toFixed(1)}${d.reason?' · '+d.reason:''}.`);$('#manualDialog').close();$('#manualUrl').value='';await refreshAll()}catch(e){toast(e.message,true)}}
let radarRunning=false;
async function loadRadarPauseState(){
 try{
  const d=await api('/api/radar/status');
  const b=$('#radarPauseBtn');
  if(b){b.textContent=d.paused?'Retomar radar':'Pausar radar';b.classList.toggle('danger',!d.paused);b.classList.toggle('soft',d.paused);}
 }catch{}
}
async function toggleRadarPause(){
 try{
  const d=await api((await api('/api/radar/status')).paused?'/api/radar/resume':'/api/radar/pause',{method:'POST'});
  toast(d.paused?'Radar pausado. A fila atual continua intacta.':'Radar retomado.');
  loadRadarPauseState();
 }catch(e){toast(e.message,true)}
}
async function clearOfferQueue(){
 const d=await api('/api/offers?limit=1&offset=0&status=queued');
 if(!d.total)return toast('A fila já está vazia.');
 if(!confirm('Excluir TODAS as ofertas atualmente na fila? Elas sairão da fila, mas o histórico publicado será preservado.'))return;
 try{
  const r=await api('/api/offers/queue/clear',{method:'POST'});
  selected.clear(); offerOffset=0; if($('#offerStatus')) $('#offerStatus').value='queued'; toast(r.changed+' ofertas removidas da fila.'); await loadOffers(); await loadDashboard();
 }catch(e){toast(e.message,true)}
}
async function runRadar(){
 if(radarRunning)return;
 radarRunning=true;document.querySelectorAll('.radarRun').forEach(b=>b.disabled=true);
 const report=document.getElementById('discoveryReport');
 if(report){report.hidden=false;report.className='';report.textContent='Buscando produtos e comparando relevância, qualidade e variedade de lojas…';}
 try{
  const d=await api('/api/radar/run',{method:'POST'});
  const summary=d.reason||`${d.created||0} novas ofertas na fila · ${d.scanned||0} resultados consultados · ${d.eligible||0} produtos elegíveis.`;
  if(report){report.className=d.ok?'':'warning';report.innerHTML=`<b>${esc(summary)}</b>`+(d.queries!=null?`<br>${d.queries} consultas · ${d.duplicates||0} repetições encontradas. `:'')+(d.limited?'Busca limitada por tempo ou volume; novas rodadas continuam a exploração. ':'')+(d.rejections&&Object.keys(d.rejections).length?'<br>Filtros: '+Object.entries(d.rejections).map(([k,v])=>`${esc(k)} (${v})`).join(' · '):'')+(d.errors?.length?'<br>'+d.errors.map(esc).join(' '):'');}
  toast(summary,!d.ok);await refreshAll();loadRadarPauseState();
 }catch(e){if(report){report.textContent=e.message;report.className='warning';}toast(e.message,true)}
 finally{radarRunning=false;document.querySelectorAll('.radarRun').forEach(b=>b.disabled=false);}
}
async function syncConversions(){try{const d=await api('/api/conversions/sync',{method:'POST'});toast(`${d.matched||0} conversões atribuídas.`);await refreshAll()}catch(e){toast(e.message,true)}}

function sourceDiagHtml(id){let d=sourceDiag[id];if(!d)return '<div class="sourceDiag hint">Ainda não testada</div>';if(d.loading)return '<div class="sourceDiag warn">● '+esc(d.text||'processando…')+'</div>';if(d.error)return '<div class="sourceDiag bad">● '+esc(d.error)+'</div>';let r=d.result||{};let member=r.member?'acesso confirmado':'acesso encontrado';return `<div class="sourceDiag ok">● ${member}<br><span class="hint">${esc(r.title||'')} ${r.username?'@'+esc(r.username):''} · ID ${esc(r.telegram_id||'')}<br>Última: ${esc(dt(r.last_message_at))} · links nas últimas ${r.sample_messages||50}: <b>${r.shopee_links_in_sample||0}</b></span></div>`}
async function loadSources(){let rows=await api('/api/sources');window.__sources=rows;$('#sources').innerHTML=rows.length?rows.map(s=>`<tr><td><b>${esc(s.name)}</b><div class="meta">${esc(s.chat_ref)}${s.last_detected_at?' · captura '+dt(s.last_detected_at):''}</div>${sourceDiagHtml(s.id)}</td><td>${Number(s.weight).toFixed(1)}<div class="meta">aprendido ${Number(s.learned_weight).toFixed(2)}</div></td><td>${s.detected_count}</td><td>${s.published_count}</td><td>${s.converted_count}</td><td>${money(s.commission_total)}</td><td><div class="sourceActions"><button class="btn tiny soft" onclick="testSource(${s.id})">Testar</button><select class="miniSelect" id="hist-${s.id}"><option value="20">20 msgs</option><option value="100" selected>100 msgs</option><option value="500">500 msgs</option></select><button class="btn tiny" onclick="importHistory(${s.id})">Importar</button><button class="btn tiny soft" onclick="showSourceMessages(${s.id})">Mensagens</button><button class="btn tiny ${s.active?'danger':'soft'}" onclick="toggleSource(${s.id})">${s.active?'Pausar':'Ativar'}</button></div></td></tr>`).join(''):'<tr><td colspan="7" class="hint">Nenhuma fonte cadastrada.</td></tr>'}
async function pollTelegramJob(job,id,kind){for(let i=0;i<360;i++){await new Promise(r=>setTimeout(r,1000));let d=await api('/api/telegram/jobs/'+job);if(d.status==='pending')continue;if(d.status==='error'||d.ok===false){sourceDiag[id]={error:d.error||'Falha no Reader'};loadSources();throw Error(d.error||'Falha no Reader')}if(kind==='test'){sourceDiag[id]={result:d.result};loadSources();toast('Fonte validada com sucesso.')}else{loadSources();let r=d.result||{};toast(`${r.scanned_messages||0} mensagens · ${r.links_found||0} links · ${r.ingested||0} analisadas.`,'', 'Histórico importado')}return d}throw Error('O Reader demorou demais para responder')}
async function testSource(id){try{sourceDiag[id]={loading:true,text:'testando acesso e amostra…'};loadSources();let d=await api(`/api/sources/${id}/test`,{method:'POST'});await pollTelegramJob(d.job_id,id,'test')}catch(e){sourceDiag[id]={error:e.message};loadSources();toast(e.message,true)}}
async function importHistory(id){try{let n=Number($(`#hist-${id}`).value||100);sourceDiag[id]={loading:true,text:`importando ${n} mensagens…`};loadSources();let d=await api(`/api/sources/${id}/import-history`,{method:'POST',body:JSON.stringify({message_limit:n})});await pollTelegramJob(d.job_id,id,'import');refreshAll()}catch(e){sourceDiag[id]={error:e.message};loadSources();toast(e.message,true)}}
async function addSource(){try{await api('/api/sources',{method:'POST',body:JSON.stringify({name:$('#sourceName').value,chat_ref:$('#sourceRef').value,weight:Number($('#sourceWeight').value),active:true})});$('#sourceName').value='';$('#sourceRef').value='';toast('Fonte adicionada. Use Testar para confirmar o acesso.');loadSources()}catch(e){toast(e.message,true)}}
async function toggleSource(id){const s=(window.__sources||[]).find(x=>x.id===id);if(!s)return;try{await api('/api/sources/'+id,{method:'PUT',body:JSON.stringify({name:s.name,chat_ref:s.chat_ref,weight:s.weight,active:!s.active})});toast(`Fonte ${s.active?'pausada':'ativada'}.`);loadSources()}catch(e){toast(e.message,true)}}

const groups=[
  ['Publicação','Ritmo, score e Breaking Deals',[['auto_publish','Publicação automática','checkbox'],['post_interval_minutes','Intervalo normal (min)','number'],['min_score','Score mínimo','number'],['breaking_enabled','Breaking Deal','checkbox'],['breaking_min_score','Score Breaking','number'],['breaking_min_trend','Trend mínimo Breaking','number'],['breaking_min_interval_minutes','Intervalo Breaking (min)','number']]],
  ['Qualidade','Filtros mínimos por produto',[['require_quality_data','Exigir avaliação, vendas e comissão','checkbox'],['max_offer_age_hours','Validade da fila (horas)','number'],['min_discount','Desconto anunciado mínimo %','number'],['min_rating','Avaliação mínima','number'],['min_sales','Vendas mínimas','number'],['min_commission_rate','Comissão mínima %','number'],['max_price_increase_pct','Máx. aumento de preço %','number'],['cooldown_days','Cooldown mesmo item (dias)','number'],['similarity_cooldown_hours','Cooldown similares (h)','number'],['similarity_threshold','Similaridade 0-1','number']]],
  ['Radar','Descoberta e priorização',[['discovery_expand_keywords','Explorar termos relacionados','checkbox'],['discovery_max_candidates','Limite de candidatos por rodada','number'],['discovery_shop_limit','Máximo por loja em cada rodada','number'],['radar_interval_minutes','Radar Shopee (min)','number'],['radar_pages','Páginas por palavra (1 a 5)','number'],['max_products_per_keyword','Produtos por página','number'],['radar_keywords','Categorias do radar','categories'],['priority_keywords','Palavras prioritárias','textarea'],['blocked_keywords','Palavras bloqueadas','textarea'],['blocked_shop_ids','Shop IDs bloqueados','textarea']]],
  ['Inteligência','Aprendizado operacional',[['template_learning','Aprender templates','checkbox'],['source_learning','Aprender fontes','checkbox'],['smart_schedule','Horário inteligente','checkbox'],['max_same_category_consecutive','Máx. mesma categoria seguida','number']]],
  ['Horários','Controle de janela de postagem',[['quiet_hours_enabled','Horário silencioso','checkbox'],['quiet_start_hour','Silêncio começa','number'],['quiet_end_hour','Silêncio termina','number']]],
  ['Confiabilidade','Backpressure, retry e circuit breaker',[['max_publish_attempts','Máx. tentativas','number'],['retry_base_seconds','Retry base (s)','number'],['max_queue_depth','Máx. fila antes de pausar radar','number'],['alert_queue_depth','Alertar fila acima de','number'],['circuit_breaker_failures','Falhas para circuit breaker','number'],['circuit_breaker_cooldown_minutes','Cooldown circuit breaker (min)','number']]],
  ['Dados','Retenção e manutenção',[['event_retention_days','Eventos (dias)','number'],['snapshot_retention_days','Histórico de preço (dias)','number'],['failed_publication_retention_days','Falhas (dias)','number'],['audit_retention_days','Auditoria (dias)','number']]]
];
async function loadSettings(){runtime=await api('/api/settings');$('#settingsForm').innerHTML=groups.map(([title,desc,fields])=>`<div class="settingsGroup"><h3>${title}</h3><p>${desc}</p><div class="fields">${fields.map(([k,l,t])=>t==='checkbox'?`<div class="toggleRow"><span>${l}</span><input class="switch" data-k="${k}" type="checkbox" ${runtime[k]?'checked':''}></div>`:`<div class="field"><label>${l}</label>${t==='categories'?`<div class="categoryPicker" data-category-picker="${k}">${['eletronicos','casa','cozinha','beleza','gamer','celular','ferramentas','moda'].map(c=>{const labels={eletronicos:'Eletrônicos',casa:'Casa',cozinha:'Cozinha',beleza:'Beleza',gamer:'Gamer',celular:'Celular',ferramentas:'Ferramentas',moda:'Moda'};const on=(runtime[k]||'').split(',').map(x=>x.trim().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase()).includes(c);return `<button type="button" class="categoryChip ${on?'selected':''}" data-category="${c}">${on?'✓ ':''}${labels[c]}</button>`}).join('')}<input type="hidden" data-k="${k}" value="${esc(runtime[k]??'')}"><small class="hint">Selecione as categorias. O motor V9 expande cada uma em dezenas de buscas inteligentes.</small></div>`:t==='textarea'?`<textarea data-k="${k}">${esc(runtime[k]??'')}</textarea>`:`<input data-k="${k}" type="number" step="any" value="${runtime[k]??''}">`}</div>`).join('')}</div></div>`).join('')}
function initCategoryPicker(){
  $('[data-category-picker]').forEach(box=>{const hidden=box.querySelector('[data-k="radar_keywords"]');box.querySelectorAll('.categoryChip').forEach(btn=>btn.onclick=()=>{btn.classList.toggle('selected');const cats=[...box.querySelectorAll('.categoryChip.selected')].map(x=>x.dataset.category);hidden.value=cats.join(',');btn.textContent=(btn.classList.contains('selected')?'✓ ':'')+btn.textContent.replace(/^✓\\s*/,'')})})
}

async function saveSettings(){initCategoryPicker();let p={...runtime};$$('[data-k]').forEach(x=>{let k=x.dataset.k;p[k]=x.type==='checkbox'?x.checked:(x.type==='number'?Number(x.value):x.value)});try{runtime=await api('/api/settings',{method:'PUT',body:JSON.stringify(p)});settingsDirty=false;toast('Políticas de automação atualizadas.');loadDashboard()}catch(e){toast(e.message,true)}}

function perfHtml(rows){if(!rows?.length)return '<span class="hint">Ainda sem dados suficientes.</span>';const max=Math.max(1,...rows.map(x=>x.commission));return rows.slice(0,10).map(x=>`<div class="perfRow"><div><b>${esc(x.key)}</b><div class="perfBar"><span style="width:${Math.max(2,x.commission/max*100)}%"></span></div></div><span>${x.posts} posts</span><span>${pct(x.conversion_post_rate)}</span><b>${money(x.commission)}</b></div>`).join('')}
async function loadAnalytics(){try{const days=Number($('#analyticsDays').value||30),d=await api('/api/analytics/performance?days='+days);$('#analyticsSources').innerHTML=perfHtml(d.sources);$('#analyticsTemplates').innerHTML=perfHtml(d.templates);$('#analyticsCategories').innerHTML=perfHtml(d.categories);await loadConversions()}catch(e){toast(e.message,true)}}
async function loadConversions(){let days=Number($('#analyticsDays').value||30);let c=await api('/api/conversions/summary?days='+days);$('#conversionBox').innerHTML=`<div class="kpi" style="margin-top:12px"><div class="label">COMISSÃO ${days} DIAS</div><div class="value">${money(c.commission)}</div><div class="sub">${c.conversions} conversões · ${c.completed_orders}/${c.orders} pedidos concluídos</div></div>`}


let waSelected = new Set();
async function loadWhatsApp(){
  try {
    const ch=await api('/api/channels');
    waSelected=new Set(ch.whatsapp_groups);
    $('#waTelegram').checked=ch.telegram_publish_enabled;
    $('#waEnabled').checked=ch.whatsapp_enabled;
    $('#waInterval').value=ch.whatsapp_interval_seconds;
    const results=await Promise.allSettled([api('/api/whatsapp/status'),loadDeliveries(),loadInbox()]);
    const st=results[0];
    $('#waState').textContent=st.status==='fulfilled'?({open:'Conectado',close:'Desconectado',connecting:'Conectando…',not_configured:'Configure a instância Evolution no servidor'}[st.value.state]||st.value.state):st.reason.message;
    for(const r of results.slice(1))if(r.status==='rejected')toast(r.reason.message,true);
    $('#waGroups').textContent=waSelected.size?`${waSelected.size} grupo(s) salvo(s). Carregue a lista para alterar.`:'Nenhum grupo selecionado.';
  } catch(e){toast(e.message,true)}
}
async function connectWhatsApp(){
  try{
    const d=await api('/api/whatsapp/connect',{method:'POST'});
    const area=$('#waQR'); area.replaceChildren();
    if(d.base64 && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(d.base64)){
      const img=document.createElement('img');img.src=d.base64;img.alt='QR Code para conectar WhatsApp';img.style.cssText='max-width:260px;width:100%;margin-top:20px';area.append(img);
    }else area.textContent='QR indisponível. Confira a conexão ou crie a instância no gerenciador Evolution.';
  }catch(e){toast(e.message,true)}
}
async function loadWhatsAppGroups(){
  try{
    const groups=await api('/api/whatsapp/groups');
    $('#waGroups').innerHTML=groups.length?groups.map(g=>`<div class="toggleRow"><label><input type="checkbox" data-wa-group="${esc(g.id)}" ${waSelected.has(g.id)?'checked':''}> ${esc(g.name)} <small>${g.size!=null?esc(g.size)+' membros':''}</small></label></div>`).join(''):'A conta não retornou grupos disponíveis.';
    $$('[data-wa-group]').forEach(el=>el.onchange=()=>el.checked?waSelected.add(el.dataset.waGroup):waSelected.delete(el.dataset.waGroup));
  }catch(e){toast(e.message,true)}
}
async function saveChannels(){
  try{
    await api('/api/channels',{method:'PUT',body:JSON.stringify({telegram_publish_enabled:$('#waTelegram').checked,whatsapp_enabled:$('#waEnabled').checked,whatsapp_groups:[...waSelected],whatsapp_interval_seconds:Number($('#waInterval').value)})});
    toast('Destinos salvos. A publicação segue as regras do piloto automático.');
  }catch(e){toast(e.message,true)}
}
async function loadDeliveries(){
  const rows=await api('/api/deliveries');
  const labels={published:'Enviado',sending:'Em envio / conferir se interrompido',uncertain:'Precisa de conferência',pending:'Preparando',failed:'Não entregue'};
  $('#waDeliveries').innerHTML=rows.length?rows.map(r=>`<tr><td>#${r.offer_id}</td><td>${esc(r.destination)}</td><td>${esc(labels[r.status]||r.status)}</td><td>${['sending','uncertain'].includes(r.status)?`<button class="btn tiny soft" onclick="reconcileDelivery(${r.id},true)">Recebido no grupo</button> <button class="btn tiny soft" onclick="reconcileDelivery(${r.id},false)">Não recebido</button>`:esc(r.error||'—')}</td></tr>`).join(''):'<tr><td colspan="4">Nenhuma publicação ainda.</td></tr>';
}
async function reconcileDelivery(id,delivered){
  if(!confirm(delivered?'Você conferiu e encontrou essa oferta no destino?':'Você conferiu o destino e confirmou que a oferta NÃO chegou? Isso libera nova tentativa.'))return;
  try{await api(`/api/deliveries/${id}/reconcile`,{method:'POST',body:JSON.stringify({delivered})});await loadDeliveries();toast('Conferência registrada.')}catch(e){toast(e.message,true)}
}
async function loadInbox(){
  const d=await api('/api/radar/quality');
  $('#radarInbox').innerHTML=`<p>Pendentes: <b>${d.inbox.pending||0}</b> · Processados: <b>${d.inbox.done||0}</b> · Falhas: <b>${d.inbox.failed||0}</b> · Expirados: <b>${d.inbox.expired||0}</b></p>`+d.sources.map(s=>`<p>${esc(s.source)} · última mensagem #${s.last_message_id} · ${dt(s.updated_at)}</p>`).join('');
}

loadRadarPauseState();
