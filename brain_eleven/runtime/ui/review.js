'use strict';
const token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
history.replaceState(null, '', '/review');
const el = id => document.getElementById(id);
const names = {OFF:'Kapalı',SHADOW:'Gözlem',CANARY:'Sınırlı kullanım',ACTIVE:'Etkin',SUCCESS:'Hazır',DEGRADED:'Eksik bilgi',STALE_INPUT:'Yenilenmeli'};
const commitments = {COMMITTED:'Kesin ifade',OBSERVED:'Gözlem',UNCERTAIN:'Belirsiz',QUOTED:'Alıntı',QUESTION:'Soru',HYPOTHETICAL:'Varsayım',NEGATED:'Olumsuz',PROPOSED:'Öneri'};
const types = {decision:'Karar',preference:'Tercih',lesson:'Ders',observation:'Gözlem'};
const when = v => { const d=v?new Date(v):null; return d&&!isNaN(d)?d.toLocaleString('tr-TR',{dateStyle:'medium',timeStyle:'short'}):'tarih yok'; };
const reasons = {SEMANTIC_REVIEW_REQUIRED:'Model özeti — doğrula',DEGRADED:'Eksik bilgiyle çıkarıldı',MODEL_PROPOSAL:'Yerel model önerisi',LOW_EVIDENCE_COMMITMENT:'Karar netleştirilmeli',LIFECYCLE_TARGET_UNKNOWN:'Değiştirilecek karar seçilmeli',REVIEW_REQUIRED:'İnceleme gerekli',HUMAN_APPROVAL_REQUIRED:'İnsan onayı gerekli'};
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
    fillBulk(pending);
    el('mode').textContent=names[status.mode] || status.mode;el('count').textContent=pending.length;
    el('queue').textContent=status.queue.queued;el('context').textContent=status.context?(names[status.context.status] || status.context.status):'Henüz yok';
    el('details').textContent=JSON.stringify(status,null,2);el('candidates').replaceChildren();
    const canAccept=['CANARY','ACTIVE'].includes(status.mode) || (status.mode==='SHADOW' && status.shadow_accept===true);
    if(status.mode==='SHADOW') el('candidates').append(node('p',status.shadow_accept===true?'Gözlem modu açık. Öneriler burada birikir; sen onayladığında ortak hafızaya yazılır.':'Gözlem modu açık. Öneriler burada birikir; ortak hafızaya yazma sınırlı kullanım açıldıktan sonra başlar.','empty'));
    if(!pending.length) el('candidates').append(node('p','Henüz inceleme bekleyen öneri yok. Yeni öneriler burada görünecek.','empty'));
    for(const item of pending) {
      const card=node('article',null,'candidate');
      const c=item.candidate;
      card.append(node('div',[item.project_name || c.project_id, item.source.client || 'yerel',
        'söylendi: '+when(c.occurred_at || item.created_at), 'son gün: '+when(item.expires_at)].join(' · '),'meta'));
      const tags=node('div',null,'tags');
      tags.append(node('span',reasons[item.reason] || item.reason,'reason'));
      if(c.memory_type) tags.append(node('span',types[c.memory_type] || c.memory_type,'tag'));
      if(c.commitment) tags.append(node('span',commitments[c.commitment] || c.commitment,'tag'));
      card.append(tags);
      if(item.similar?.length) {
        const box=node('div',null,'similar');
        const top=item.similar[0].similarity;
        box.append(node('strong',top>=0.6?'Muhtemel tekrar — benzer kayıt zaten var:':'Benzer mevcut kayıtlar:'));
        const list=node('ul');
        for(const s of item.similar){const li=node('li',Math.round(s.similarity*100)+'% · '+s.text);list.append(li);}
        box.append(list);card.append(box);
      }
      const label=node('label','Kaydedilecek bilgi');label.htmlFor=item.id;
      const input=node('textarea');input.id=item.id;input.value=item.candidate.content || item.candidate.text || '';input.maxLength=8000;
      card.append(label,input);
      const target=node('select');target.setAttribute('aria-label','Değiştirilecek mevcut kayıt');
      const empty=node('option','Yeni kayıt olarak ekle');empty.value='';target.append(empty);
      for(const t of item.targets || []) {const option=node('option',t.text);option.value=t.id;target.append(option);}
      if(item.targets?.length)card.append(target);
      const keyLabel=node('label','Konu anahtarı (isteğe bağlı, ör. srt-00.ship-status)');keyLabel.htmlFor=item.id+'-key';
      const key=node('input');key.id=item.id+'-key';key.maxLength=80;key.setAttribute('list',item.id+'-keys');
      const keys=node('datalist');keys.id=item.id+'-keys';
      for(const k of [...(item.suggested_claim_keys || []), ...(item.claim_keys || [])]) {const option=node('option');option.value=k;keys.append(option);}
      const keyHint=node('p',null,'hint');
      if(item.suggested_claim_keys?.length){
        keyHint.append('Önerilen: ');
        for(const k of item.suggested_claim_keys){const b=node('button',k,'chip');b.type='button';b.addEventListener('click',()=>{key.value=k;checkKey();});keyHint.append(b);}
      }
      const keyWarn=node('p',null,'warn');keyWarn.hidden=true;
      if(item.candidate?.candidate_type==='NEW_MEMORY')card.append(keyLabel,key,keys,keyHint,keyWarn);
      const noteLabel=node('label','Karar gerekçesi (isteğe bağlı, en fazla 280 karakter)');noteLabel.htmlFor=item.id+'-note';
      const note=node('input');note.id=item.id+'-note';note.maxLength=280;
      card.append(noteLabel,note);
      const actions=node('div',null,'actions');const reject=node('button','Reddet','secondary');const accept=node('button','Kabul et');
      accept.disabled=!canAccept;
      // Explicit supersede: the button says what will happen to the existing record.
      const setAcceptLabel=()=>{accept.textContent=target.value?'Yerine geçir':'Kabul et';};
      target.addEventListener('change',setAcceptLabel);
      function checkKey(){
        const k=key.value.trim().toLowerCase();
        const holder=(item.targets || []).find(t=>t.claim_key && t.claim_key===k);
        keyWarn.hidden=!holder;
        if(holder){keyWarn.textContent='“'+k+'” anahtarıyla aktif bir kayıt var: “'+holder.text+'”. Kabul edersen bu yeni bilgi onun yerine geçer.';target.value=holder.id;}
        setAcceptLabel();
      }
      key.addEventListener('input',checkKey);
      const top=item.similar?.[0];
      if(top && top.similarity>=0.6){
        const dup=node('button','Tekrar olarak reddet','secondary');
        dup.addEventListener('click',()=>{note.value=('Tekrar: '+top.id).slice(0,280);submit('reject');});
        actions.append(dup);
      }
      async function submit(action) {
        accept.disabled=reject.disabled=true;
        try {const body={content:input.value,expected_revision:item.expected_revision,target_id:target.value || null};
          if(key.value.trim())body.claim_key=key.value;
          if(note.value.trim())body.note=note.value;
          const result=await api('/api/review/candidates/'+item.id+'/'+action,body);
          if(result.conflict) {
            el('message').textContent='Bu konu anahtarıyla aktif bir kayıt var ('+(result.conflict.occurred_at || result.conflict.timestamp || 'tarih yok')+'): “'+(result.conflict.content || result.conflict.memory_id)+'”. Yeni bilgi onun yerine geçecekse, “Değiştirilecek mevcut kayıt” listesinde seçili olarak bırakıp tekrar Kabul et.';
            await refresh();
            const again=el(item.id)?.closest('article')?.querySelector('select');
            if(again)again.value=result.conflict.memory_id;
            const againKey=el(item.id+'-key');if(againKey)againKey.value=key.value;
            return;
          }
          el('message').textContent=result.status==='ACCEPTED'?'Bilgi ortak hafızaya kaydedildi.':result.status==='REJECTED'?'Öneri reddedildi.':('İşlem tamamlanmadı: '+result.status+'. Kaydı yeniden gözden geçir.');await refresh();
        } catch(e) {el('message').textContent=e.message;} finally {accept.disabled=reject.disabled=false;}
      }
      reject.addEventListener('click',()=>submit('reject'));accept.addEventListener('click',()=>submit('accept'));actions.append(reject,accept);card.append(actions);el('candidates').append(card);
    }
  } catch(e) {el('message').textContent=e.message;} finally {el('refresh').disabled=false;}
}
async function refreshStale() {
  try {
    const result=await api('/api/staleness');el('stale').replaceChildren();
    if(!result.stale_candidates.length){el('stale').append(node('p','Kaynağı değişmiş kayıt yok ('+result.references_checked+' dosya referansı kontrol edildi).','empty'));return;}
    for(const s of result.stale_candidates){
      const card=node('article',null,'candidate stale');
      card.append(node('div',[s.path, s.reason==='SOURCE_MISSING'?'dosya artık yok':'dosya değişti: '+when(s.source_changed_at), 'kayıt: '+when(s.memory_written_at)].join(' · '),'meta'));
      card.append(node('p',s.content));
      const actions=node('div',null,'actions');const keep=node('button','Hâlâ geçerli','secondary');const retire=node('button','Emekliye ayır');
      async function act(action){keep.disabled=retire.disabled=true;
        try{await api('/api/staleness/'+s.memory_id+'/'+action,action==='ack'?{path:s.path}:{note:s.path+' değişti; kayıt eskidi.'});
          el('message').textContent=action==='ack'?'Kayıt geçerli olarak işaretlendi; dosya tekrar değişirse yeniden sorulur.':'Kayıt emekliye ayrıldı; artık bağlama girmez.';await refreshStale();}
        catch(e){el('message').textContent=e.message;keep.disabled=retire.disabled=false;}}
      keep.addEventListener('click',()=>act('ack'));retire.addEventListener('click',()=>act('retire'));actions.append(keep,retire);card.append(actions);el('stale').append(card);
    }
  } catch(e){el('stale').replaceChildren(node('p','Eskime kontrolü yapılamadı: '+e.message,'empty'));}
}
const shapes={terminal_or_code:'Terminal / kod çıktısı',short_ack:'Kısa onay',question:'Soru',prose:'Düz yazı'};
function fillBulk(pending){
  const fill=(id,label,key,names)=>{const sel=el(id);const keep=sel.value;const counts={};
    for(const p of pending){const v=key(p);if(v)counts[v]=(counts[v]||0)+1;}
    sel.replaceChildren(Object.assign(node('option',label+': hepsi'),{value:''}));
    for(const [v,n] of Object.entries(counts).sort((a,b)=>b[1]-a[1])){const o=node('option',(names[v]||v)+' ('+n+')');o.value=v;sel.append(o);}
    sel.value=keep;};
  fill('bulk-reason','Neden',p=>p.reason,reasons);
  fill('bulk-commitment','Kesinlik',p=>p.candidate?.commitment,commitments);
  fill('bulk-shape','Biçim',p=>p.shape,shapes);
  el('bulk-apply').disabled=true;
}
function bulkFilter(){const f={};for(const [k,id] of [['reason','bulk-reason'],['commitment','bulk-commitment'],['shape','bulk-shape']])if(el(id).value)f[k]=el(id).value;return f;}
for(const id of ['bulk-reason','bulk-commitment','bulk-shape'])el(id).addEventListener('change',()=>{el('bulk-apply').disabled=true;el('bulk-result').replaceChildren();});
el('bulk-preview').addEventListener('click',async()=>{
  try{const r=await api('/api/review/bulk-reject',bulkFilter());
    const box=el('bulk-result');box.replaceChildren(node('p',r.matched+' öneri (tekrarlarla '+r.items+' kayıt) reddedilecek. Örnekler:'));
    const ul=node('ul');for(const t of r.samples)ul.append(node('li',t.slice(0,200)));box.append(ul);
    el('bulk-apply').disabled=!r.matched;
  }catch(e){el('message').textContent=e.message;}
});
el('bulk-apply').addEventListener('click',async()=>{
  if(!confirm('Seçili filtreye uyan tüm öneriler reddedilecek. Emin misin?'))return;
  el('bulk-apply').disabled=true;
  try{const r=await api('/api/review/bulk-reject',{...bulkFilter(),confirm:true});el('message').textContent=r.matched+' öneri reddedildi.';el('bulk-result').replaceChildren();await refresh();}
  catch(e){el('message').textContent=e.message;}
});
el('refresh').addEventListener('click',()=>{refresh();refreshStale();});refresh();refreshStale();
