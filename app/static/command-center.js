/* V6: all metrics come from the application's authenticated API. */
const icons={
 dashboard:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
 tag:'<path d="M20 13l-7 7a2 2 0 0 1-3 0l-7-7V3h10l7 7a2 2 0 0 1 0 3Z"/><circle cx="7.5" cy="7.5" r="1"/>',
 radar:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12l7-7"/><circle cx="12" cy="12" r="1"/>',
 sliders:'<path d="M4 7h7m5 0h4M4 17h2m5 0h9"/><circle cx="13" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
 chart:'<path d="M3 3v18h18M7 14l5-5 4 3 5-8"/>',
 system:'<rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01M16 7h2M16 17h2"/>',
 bolt:'<path d="M13 2L4 14h7l-1 8 10-13h-7l1-7Z"/>',
 search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="M16 16l5 5"/>',
 refresh:'<path d="M20 7a9 9 0 1 0 1 7M20 3v5h-5"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 logout:'<path d="M10 4H4v16h6m5-12 4 4-4 4m-6-4h10"/>',
 wallet:'<path d="M20 8V5H4v15h16V8H4"/><path d="M20 11h-6v5h6"/><path d="M17 13.5h.01"/>',
 send:'<path d="m21 3-7 18-4-7-7-4L21 3ZM10 14 21 3"/>',
 layers:'<path d="m12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5"/>',
 box:'<path d="m12 3 9 5v9l-9 5-9-5V8l9-5ZM3 8l9 5 9-5M12 13v9M8 5l9 5"/>',
 download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
 check:'<path d="m5 12 4 4L19 6"/>',
 alert:'<path d="m12 3 10 18H2L12 3ZM12 9v5m0 3h.01"/>',
 pause:'<path d="M8 5v14M16 5v14"/>',
 play:'<path d="m7 4 14 8-14 8V4Z"/>'
};
function icon(name){return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${icons[name]||icons.box}</svg>`}
function hydrateIcons(){ $$('[data-icon]').forEach(x=>x.innerHTML=icon(x.dataset.icon)) }
function safeUrl(v){try{const u=new URL(v);return ['https:','http:'].includes(u.protocol)?u.href:''}catch{return ''}}
const offerCache=new Map();
let settingsDirty=false,refreshing=false;
$('#settingsForm').addEventListener('input',()=>settingsDirty=true);
window.addEventListener('beforeunload',e=>{if(settingsDirty){e.preventDefault();e.returnValue=''}});
function empty(title,desc,action=''){return `<div class="emptyState">${icon('layers')}<b>${esc(title)}</b><p>${esc(desc)}</p>${action}</div>`}
function renderDashboard(d){
 const k=d.kpis;
 const cards=[['Comissão sincronizada',money(k.commission),'Últimos 7 dias · por sincronização','wallet','revenue'],['Ofertas detectadas',k.detected_24h,'Últimas 24 horas · todas as fontes','radar',''],['Ofertas publicadas',k.published_24h,`Últimas 24h · ${pct(k.publish_success_rate)} sucesso em 7d`,'send',''],['Na fila de publicação',k.queue,'Aguardando as regras de publicação','layers','']];
 $('#kpis').innerHTML=cards.map(([label,value,sub,i,c])=>`<div class="kpi ${c}"><div class="label">${label}${icon(i)}</div><div class="value">${esc(value)}</div><div class="sub">${esc(sub)}</div></div>`).join('');
 const total=d.daily.reduce((t,x)=>t+x.detected,0),published=d.daily.reduce((t,x)=>t+x.published,0);
 $('#chartSummary').innerHTML=`<strong>${total.toLocaleString('pt-BR')}<small>detectadas</small></strong><strong>${published.toLocaleString('pt-BR')}<small>publicadas</small></strong>`;
 renderChart(d.daily);
 $('#chartFootnote').textContent=total?`Score médio ${Number(k.avg_score).toFixed(1)} · Posts com conversão ${pct(k.conversion_post_rate)}`:'O gráfico será preenchido conforme as ofertas chegarem.';
 $('#automationState').innerHTML=`<div class="stateList"><div class="stateRow"><span>Publicação</span><b class="${d.automation.enabled?'ok':'warn'}">● ${d.automation.enabled?'Ativada':'Pausada'}</b></div><div class="stateRow"><span>Intervalo base</span><b>${d.automation.interval} minutos</b></div><div class="stateRow"><span>Score mínimo</span><b>${d.automation.min_score} / 100</b></div></div>`;
 const b=$('#automationToggle'); b.disabled=false;b.innerHTML=icon(d.automation.enabled?'pause':'play')+(d.automation.enabled?'Pausar publicação':'Ativar publicação');
 $('#topSources').innerHTML=d.top_sources.length?d.top_sources.map((s,i)=>`<div class="leader"><div class="leaderRank">${String(i+1).padStart(2,'0')}</div><div class="leaderMain"><b>${esc(s.name)}</b><span>${s.published} publicadas · ${s.converted} conversões</span></div><div class="leaderValue">${money(s.commission)}</div></div>`).join(''):empty('Suas fontes começam aqui','Cadastre um canal ou grupo para acompanhar os resultados.','<button class="btn soft" onclick="openView(\'radar\')">Adicionar fonte →</button>');
 const notes=[];
 if(!d.services.shopee||!d.services.telegram)notes.push(['alert','Conecte Shopee e Telegram para concluir a preparação.','Configurar','system',true]);
 else if(!d.services.worker)notes.push(['alert','Publicador sem sinal. Confira o serviço na Central Windows.','Diagnosticar','system',true]);
 else if(k.failed)notes.push(['alert',`${k.failed} oferta(s) com falha precisam de revisão.`,'Revisar','failed',true]);
 else notes.push(['check','Serviços de publicação disponíveis. Acompanhe as regras e a fila.','Ver regras','automation',false]);
 if(!d.top_sources.length)notes.push(['radar','Amplie sua descoberta com fontes do Telegram.','Adicionar','radar',false]);
 else if(!d.services.reader)notes.push(['radar','Radar Telegram sem sinal. Novas mensagens podem não ser capturadas.','Ver radar','system',true]);
 else notes.push(['chart',`Score médio de ${Number(k.avg_score).toFixed(1)} nas ofertas dos últimos 7 dias.`,'Analisar','analytics',false]);
 $('#insights').innerHTML=notes.map(([i,msg,cta,view,warn])=>`<div class="insight ${warn?'attention':''}">${icon(i)}<span>${esc(msg)}</span><button onclick="${view==='failed'?"filterOffers('failed')":`openView('${view}')`}">${cta} ↗</button></div>`).join('');
 renderServicePill(d.services);
}
function renderChart(rows){
 const w=700,h=190,left=32,right=14,top=14,bottom=27,pw=w-left-right,ph=h-top-bottom;
 const max=Math.max(4,Math.ceil(Math.max(...rows.flatMap(x=>[x.detected,x.published]),1)/4)*4);
 const x=i=>left+i*pw/Math.max(rows.length-1,1),y=n=>top+ph-n/max*ph;
 const path=key=>rows.map((r,i)=>`${i?'L':'M'}${x(i).toFixed(2)},${y(r[key]).toFixed(2)}`).join(' ');
 const ticks=Array.from({length:5},(_,i)=>{const n=max*i/4;return `<line x1="${left}" y1="${y(n)}" x2="${w-right}" y2="${y(n)}" stroke="#e6dfd4" stroke-dasharray="3 5"/><text x="${left-9}" y="${y(n)+3}" text-anchor="end">${Math.round(n)}</text>`}).join('');
 const labels=rows.map((r,i)=>`<text x="${x(i)}" y="${h-5}" text-anchor="middle">${r.date.slice(8,10)}/${r.date.slice(5,7)}</text>`).join('');
 const points=rows.map((r,i)=>`<g tabindex="0" aria-label="${esc(r.date)}: ${r.detected} detectadas, ${r.published} publicadas"><title>${r.date}: ${r.detected} detectadas · ${r.published} publicadas</title><circle cx="${x(i)}" cy="${y(r.detected)}" r="3" fill="#cbbb9e"/><circle cx="${x(i)}" cy="${y(r.published)}" r="3" fill="#d94724"/><rect x="${x(i)-18}" y="${top}" width="36" height="${ph}" fill="transparent"/></g>`).join('');
 $('#timeline').innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Gráfico de ofertas detectadas e publicadas nos últimos sete dias"><defs><linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#cbbb9e" stop-opacity=".22"/><stop offset="100%" stop-color="#cbbb9e" stop-opacity="0"/></linearGradient></defs>${ticks}<path d="${path('detected')} L${x(rows.length-1)},${y(0)} L${left},${y(0)} Z" fill="url(#chartFill)"/><path d="${path('detected')}" fill="none" stroke="#cbbb9e" stroke-width="2"/><path d="${path('published')}" fill="none" stroke="#d94724" stroke-width="2.3"/>${points}${labels}</svg>`;
}
function art(p,score){const u=safeUrl(p.image_url);return `<div class="dealArt"><span class="scoreBadge">✦ ${Number(score).toFixed(0)} score</span>${p.discount>0?`<span class="discountBadge">−${Number(p.discount).toFixed(0)}%</span>`:''}${u?`<img src="${esc(u)}" loading="lazy" alt="${esc(p.name)}">`:icon('box')}</div>`}
async function loadSpotlight(){
 const d=await api('/api/offers?status=queued&limit=60');
 d.items.forEach(e=>offerCache.set(e.id,e));
 const rows=[...d.items].sort((a,b)=>b.score-a.score).slice(0,3);
 $('#spotlight').innerHTML=rows.length?rows.map(e=>{const p=e.product;return `<button class="dealCard" onclick="previewOffer(${e.id})" aria-label="Revisar ${esc(p.name)}">${art(p,e.score)}<div class="dealCategory">${esc(p.category||'Oferta')}</div><h3>${esc(p.name)}</h3><div class="dealPrice">${p.price!=null?money(p.price):'Preço indisponível'}${p.original_price>p.price?`<del>${money(p.original_price)}</del>`:''}</div><div class="dealFoot"><span>${esc(e.source_ref||e.source_type)}</span><b>Revisar oferta ↗</b></div></button>`}).join(''):empty('Espaço para a próxima boa oferta','Busque produtos ou adicione um link Shopee para começar sua curadoria.','<button class="btn soft" onclick="runRadar()">'+icon('radar')+' Buscar ofertas</button>');
}
function previewOffer(id){
 const e=offerCache.get(id);if(!e)return toast('Atualize a lista para revisar esta oferta.',true);const p=e.product,u=safeUrl(p.product_url);
 $('#previewContent').innerHTML=`<div class="previewHeader"><div><span class="eyebrow">REVISÃO DE OFERTA #${e.id}</span><h2 id="previewTitle">Antes de publicar</h2></div><button class="iconBtn" onclick="$('#previewDialog').close()" aria-label="Fechar prévia">×</button></div><div class="previewBody">${art(p,e.score)}<h3>${esc(p.name)}</h3><div class="dealPrice">${p.price!=null?money(p.price):'Preço indisponível'}</div><div class="detailGrid"><div><span>Status</span><b>${esc(statusLabel[e.status]||e.status)}</b></div><div><span>Comissão informada</span><b>${p.commission_rate!=null?pct(p.commission_rate):'Não informada'}</b></div><div><span>Avaliação</span><b>${p.rating??'—'} / 5</b></div><div><span>Vendas do produto</span><b>${p.sales??'—'}</b></div><div><span>Origem</span><b>${esc(e.source_ref||e.source_type)}</b></div><div><span>Tentativas de publicação</span><b>${e.attempts||0}</b></div></div>${e.reject_reason?`<p class="reason">${esc(e.reject_reason)}</p>`:''}<p id="priceEvidence" class="hint">Carregando histórico de preço…</p><p class="hint">Preço e disponibilidade serão revalidados antes do envio. O link de afiliado é gerado pelo publicador.</p></div><div class="previewActions">${u?`<a class="btn soft" href="${esc(u)}" target="_blank" rel="noopener noreferrer">Ver produto ↗</a>`:''}${e.status==='queued'?`<button class="btn" onclick="publishFromPreview(${e.id},this)">${icon('send')} Publicar nos destinos</button>`:(['failed','rejected','duplicate'].includes(e.status)?`<button class="btn" onclick="retryOffer(${e.id});$('#previewDialog').close()">Voltar para a fila</button>`:'')}</div>`;
 $('#previewDialog').showModal();
 api(`/api/offers/${id}/quality`).then(q=>{const el=$('#priceEvidence');if(!el||!$('#previewTitle')||!$('#previewContent').textContent.includes('#'+id))return;el.textContent=q.reference!=null?`Referência observada: ${money(q.reference)} · variação: ${pct(q.drop_pct)} abaixo da referência · ${q.days} dias. Não inclui frete nem diferenças entre variações.`:q.reason}).catch(()=>{const el=$('#priceEvidence');if(el)el.textContent='Histórico indisponível.'});
}
async function publishFromPreview(id,button){button.disabled=true;try{await api(`/api/offers/${id}/publish`,{method:'POST'});$('#previewDialog').close();toast('Oferta publicada nos destinos selecionados.');await refreshAll()}catch(e){toast(e.message,true)}finally{button.disabled=false}}
async function toggleAutomation(){
 const button=$('#automationToggle');button.disabled=true;
 try{const current=await api('/api/settings');current.auto_publish=!current.auto_publish;await api('/api/settings',{method:'PUT',body:JSON.stringify(current)});toast(current.auto_publish?'Publicação automática ativada.':'Publicação pausada. Um envio já iniciado pode ser concluído.');await loadDashboard();if(!settingsDirty)await loadSettings()}catch(e){toast(e.message,true)}finally{button.disabled=false}
}
function filterOffers(status){$('#offerStatus').value=status;offerOffset=0;openView('deals')}
$('#offerStatus').addEventListener('change',()=>{offerOffset=0;loadOffers()});
$('#offerSourceType').addEventListener('change',()=>{offerOffset=0;loadOffers()});
function exportOffers(){
 const rows=window.currentOffers||[];if(!rows.length)return toast('Não há ofertas nesta página para exportar.',true);
 const cell=v=>'"'+String(v??'').replace(/^[=+@\-\t\r]/,"'$&").replaceAll('"','""')+'"';
 const data=[['ID','Produto','Preço','Score','Status','Origem','Detectada'],...rows.map(e=>[e.id,e.product.name,e.product.price,e.score,statusLabel[e.status]||e.status,e.source_ref,dt(e.created_at)])].map(r=>r.map(cell).join(';')).join('\r\n');
 const url=URL.createObjectURL(new Blob(['\ufeff'+data],{type:'text/csv;charset=utf-8;'}));const a=document.createElement('a');a.href=url;a.download='ofertas-pagina.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Página atual exportada em CSV.');
}
const commands=[['Visão geral','dashboard','dashboard'],['Ofertas e fila','deals','tag'],['Radar Telegram','radar','radar'],['Automação e filtros','automation','sliders'],['Performance e conversões','analytics','chart'],['Saúde do sistema','system','system'],['Adicionar oferta manual','manual','plus']];
function showCommands(){$('#commandSearch').value='';renderCommands();$('#commandDialog').showModal();$('#commandSearch').focus()}
function renderCommands(){const q=$('#commandSearch').value.toLocaleLowerCase('pt-BR');$('#commandResults').innerHTML=commands.filter(c=>c[0].toLocaleLowerCase('pt-BR').includes(q)).map(c=>`<button class="commandItem" onclick="$('#commandDialog').close();${c[1]==='manual'?'showManual()':`openView('${c[1]}')`}">${icon(c[2])}<span>${c[0]}</span><span>↗</span></button>`).join('')||'<p class="hint">Nenhum comando encontrado.</p>'}
$('#commandSearch').addEventListener('input',renderCommands);
$('#commandSearch').addEventListener('keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();$('.commandItem')?.focus()}if(e.key==='Enter'){e.preventDefault();$('.commandItem')?.click()}});
$('#commandResults').addEventListener('keydown',e=>{const items=$$('.commandItem'),i=items.indexOf(document.activeElement);if(e.key==='ArrowDown'){e.preventDefault();items[(i+1)%items.length]?.focus()}if(e.key==='ArrowUp'){e.preventDefault();if(i<=0)$('#commandSearch').focus();else items[i-1]?.focus()}});
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(!document.querySelector('dialog[open]'))showCommands()}if(e.key==='Escape')$('#sidebar').classList.remove('open')});
document.addEventListener('click',e=>{if(innerWidth<=780&&!e.target.closest('#sidebar')&&!e.target.closest('#menuBtn'))$('#sidebar').classList.remove('open')});
function showSourceMessages(id){const r=sourceDiag[id]?.result;if(!r)return toast('Teste a fonte primeiro para carregar as mensagens.',true);$('#previewContent').innerHTML=`<div class="previewHeader"><h2 id="previewTitle">Mensagens da fonte</h2><button class="iconBtn" onclick="$('#previewDialog').close()" aria-label="Fechar">×</button></div><div class="previewBody">${(r.recent_messages||[]).map(m=>`<div class="activityItem"><div></div><div><b>${esc(m.text||'(sem texto)')}</b><p>${esc(dt(m.date))} · ${Number(m.shopee_links||0)} link(s)</p></div></div>`).join('')||'<p class="hint">Nenhuma mensagem recente.</p>'}</div>`;$('#previewDialog').showModal()}
// Surface errors from navigation as well as background refreshes.
for(const name of ['loadOffers','loadSources','loadSettings','loadHealth','loadActivity']){
 const original=window[name];window[name]=async(...args)=>{try{return await original(...args)}catch(e){toast(e.message,true);return null}};
}
async function refreshAll(showToast=false){
 if(refreshing)return;refreshing=true;
 try{
  const results=await Promise.allSettled([loadDashboard(),loadSpotlight(),loadActivity(false)]);
  const failures=results.filter(r=>r.status==='rejected');
  if(failures.length)throw failures[0].reason;
  $('#connectionNotice').hidden=true;
  $('#lastUpdated').textContent='Atualizado às '+new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
  if($('#view-deals').classList.contains('active')&&!selected.size)await loadOffers();
  if($('#view-radar').classList.contains('active'))await loadSources();
  if($('#view-system').classList.contains('active'))await Promise.all([loadHealth(),loadActivity(true)]);
  if(showToast)toast('Dados atualizados.');
 }catch(e){$('#connectionNotice').hidden=false;$('#connectionNotice').textContent='Atualização indisponível. Os dados exibidos podem estar desatualizados. '+e.message;if(showToast)toast(e.message,true)}finally{refreshing=false}
}
hydrateIcons();
(async()=>{
 await refreshAll();
 const view=location.hash.slice(1);if(view&&view!=='dashboard'&&viewMeta[view])openView(view);
 setInterval(()=>{if(!document.hidden)refreshAll()},15000);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshAll()});
})();
