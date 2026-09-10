'use strict';
const token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
history.replaceState(null, '', '/review');
const el = id => document.getElementById(id);
const names = {OFF:'Kapalı',SHADOW:'Gözlem',CANARY:'Sınırlı kullanım',ACTIVE:'Etkin',SUCCESS:'Hazır',DEGRADED:'Eksik bilgi',STALE_INPUT:'Yenilenmeli'};
const reasons = {MODEL_PROPOSAL:'Yerel model önerisi',LOW_EVIDENCE_COMMITMENT:'Karar netleştirilmeli',LIFECYCLE_TARGET_UNKNOWN:'Değiştirilecek karar seçilmeli',REVIEW_REQUIRED:'İnceleme gerekli',HUMAN_APPROVAL_REQUIRED:'İnsan onayı gerekli'};
async function api(path, body) {
  const response = await fetch(path, {method:body?'POST':'GET', headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'}, ...(body?{body:JSON.stringify(body)}:{})});
  const result = await response.json();
  if (!response.ok) throw new Error(response.status===401?'Bu ekranı “review” komutuyla yeniden aç.':(result.detail || result.error || 'İşlem tamamlanamadı.'));
  return result;
}
function node(tag, text, cls) { const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n; }
async function refresh() {
  el('refresh').disabled=true;
  try {
    const [status, list] = await Promise.all([api('/api/runtime/status'),api('/api/review/candidates')]);
    const pending=list.candidates.filter(x=>x.status==='PENDING');
    el('mode').textContent=names[status.mode] || status.mode;el('count').textContent=pending.length;
    el('queue').textContent=status.queue.queued;el('context').textContent=status.context?(names[status.context.status] || status.context.status):'Henüz yok';
    el('details').textContent=JSON.stringify(status,null,2);el('candidates').replaceChildren();
    if(status.mode==='SHADOW') el('candidates').append(node('p','Gözlem modu açık. Öneriler burada birikir; ortak hafızaya yazma sınırlı kullanım açıldıktan sonra başlar.','empty'));
    if(!pending.length) el('candidates').append(node('p','Henüz inceleme bekleyen öneri yok. Yeni öneriler burada görünecek.','empty'));
    for(const item of pending) {
      const card=node('article',null,'candidate');
      card.append(node('div',(item.source.client || 'yerel')+' · '+item.candidate.project_id,'meta'));
      card.append(node('span',reasons[item.reason] || item.reason,'reason'));
      const label=node('label','Kaydedilecek bilgi');label.htmlFor=item.id;
      const input=node('textarea');input.id=item.id;input.value=item.candidate.content || item.candidate.text || '';input.maxLength=8000;
      card.append(label,input);
      const target=node('select');target.setAttribute('aria-label','Değiştirilecek mevcut kayıt');
      const empty=node('option','Yeni kayıt olarak ekle');empty.value='';target.append(empty);
      for(const t of item.targets || []) {const option=node('option',t.text);option.value=t.id;target.append(option);}
      if(item.targets?.length)card.append(target);
      const actions=node('div',null,'actions');const reject=node('button','Reddet','secondary');const accept=node('button','Kabul et');
      accept.disabled=!['CANARY','ACTIVE'].includes(status.mode);
      async function submit(action) {
        accept.disabled=reject.disabled=true;
        try {const result=await api('/api/review/candidates/'+item.id+'/'+action,{content:input.value,expected_revision:item.expected_revision,target_id:target.value || null});
          el('message').textContent=result.status==='ACCEPTED'?'Bilgi ortak hafızaya kaydedildi.':result.status==='REJECTED'?'Öneri reddedildi.':('İşlem tamamlanmadı: '+result.status+'. Kaydı yeniden gözden geçir.');await refresh();
        } catch(e) {el('message').textContent=e.message;} finally {accept.disabled=reject.disabled=false;}
      }
      reject.addEventListener('click',()=>submit('reject'));accept.addEventListener('click',()=>submit('accept'));actions.append(reject,accept);card.append(actions);el('candidates').append(card);
    }
  } catch(e) {el('message').textContent=e.message;} finally {el('refresh').disabled=false;}
}
el('refresh').addEventListener('click',refresh);refresh();
