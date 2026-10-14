# Mimari

Tek bir yol var: hook → kuyruk → çıkarım → onay → hafıza → bağlam.

```
Claude/Codex hook'u ──► runtime/launcher.py ──► yerel servis (runtime/service.py)
                                                   │
        ┌──────────────── yakalama ────────────────┤──────────── hatırlama ───────────┐
        ▼                                          │                                 ▼
 capture_queue → worker.py → extraction.py         │                       context.py
  (döküm okuma: evidence.py,                        │        kapsam filtresi → embedding kısa
   güvenlik: capture_safety.py)                     │        liste → cross-encoder sıralama
        ▼                                          │        (+ cross-project referanslar)
 inceleme kuyruğu ── triage / queue_triage ─► review / digest / apply-suggestions
        ▼ (onaylanan)
 MemoryStore (brain_eleven/memory)   StateStore (brain_eleven/state)   ProjectRegistry (brain_eleven/projects)
        ▲
 probation / memory_audit / staleness (bakım, servis içinde)
```

## Paketler

| Yer | Görev |
|---|---|
| `brain_eleven/runtime/` | Hook giriş noktası, servis, worker, bağlam derleme, bakım, CLI işleri |
| `brain_eleven/memory/` | Kanonik hafıza deposu (revizyon + kilit + atomik yazım) |
| `brain_eleven/state/` | Proje/görev durumu |
| `brain_eleven/projects/` | Proje kimliği ve kayıt defteri |
| `brain_eleven/extraction/`, `retrieval/`, `search/` | Çıkarım sağlayıcıları, embedding |
| `scripts/` | Eski betikler; bir kısmı hâlâ canlı yolda (`capture_queue.py`, `context-compiler.py`, `memory_store.py`), `search-api.py` Docker HTTP API'si |
| `context_compiler_v2/`, `authority/`, `context_router/`, `retrieval_decision_v2/`, `context_density_v2/` | V2 bağlam derleyicisi. Yalnız gölge modda çalışır, model bağlamına girmez. Sadeleştirme adayı. |
| `evals/recall_probe/` | `recall-probe` komutunun 5 sorusu |
| `🔮 Companion/`, `🗂️ Proje Notları/`, `📝 Template/` | Obsidian vault içeriği |

## Seni tanıma notları

`runtime/companion.py`: `🔮 Companion/Core.md` ve `Kurallar.md` sahibin
notlarıdır, kanonik hafıza değildir; ajan düzeltmeleri `Kurallar.md`'ye ekler
(beyin skill'i). SessionStart bağlam sırası: sahip notları → oturum kartları →
hafıza. Devam/kimlik sorusu soran istemlerde notlar ve kartlar da eklenir.
Launcher bağlamı istemci sınırına (9500 karakter) satır sınırında sığdırır.

## Oturum kartları

`runtime/session_cards.py`: worker her yakalamadan sonra oturumun kartını
günceller ve proje notunu (`🔮 Companion/Oturumlar/<proje>.md`) yeniden yazar.
Kart durumu JSON olarak runtime kökünde durur, not ondan türetilir. Kart bölümü
3000 karakteri aşınca en eski kartlar `🔮 Companion/Arşiv/<proje> - YYYY-AA.md`
dosyasına eklenir. SessionStart bağlamına son iki kart eklenir.

## Alt ajanlar

`SubagentStart` (yalnız Claude) alt ajana proje hafızasını ve bir talimat
verir: rapor `### Brain-Eleven bulguları` başlığıyla biter. Okuyucu
(`runtime/evidence.py`) ana dökümde bu başlığı taşıyan araç sonucunu ya da meta
kaydı `subagent` rolüyle alır. Çıkarıcı yalnız o başlığın maddelerini aday
yapar, worker bunları her zaman incelemeye koyar.

## Modlar

`OFF` (kapalı), `SHADOW` (yakalar ama yazmaz; `shadow-recall ON` ile bağlam
verir), `ACTIVE` (normal çalışma). `CANARY` eski uyumluluk için duruyor,
`ACTIVE` ile aynı davranır. Mod değişikliğinde kalite kapısı yoktur; güvenlik
sahibin onayından (`approval ON`) ve deneme süresinden gelir.

## Hafıza notları

`runtime/memory_notes.py`: MemoryStore'dan proje başına okunur not üretir
(`🔮 Companion/Hafıza/`). Servis döngüsü revizyon değiştiğinde yeniler; notlar
yalnız görünümdür, yazım yolu MemoryStore'dur.

## Tüketim profili

`context_profile` (`profile` komutu): `normal` her olayda bağlam verir;
`economical` yalnız SessionStart'ta, 2000 karakterle (alt ajan 1000) verir ve
istemlerde servisi çağırmaz; `manual` hiç bağlam vermez. Yakalama profilden
etkilenmez.

## Güvenlik kuralları

- Hafızaya yazım yalnız `MemoryStore` üzerinden.
- Sır, token, parola ve tam döküm hafızaya yazılmaz (`capture_safety.py`).
- Bir proje, başka projenin hafızasını yalnız etiketli referans olarak görür.
