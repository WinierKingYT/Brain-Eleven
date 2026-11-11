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
| `brain_eleven/projects/` | Proje kimliği ve kayıt defteri; hook, oturumun cwd'sini en yakın kayıtlı ata köke çözer (`resolve_containing`), alt klasör ve proje içi worktree oturumları o projeye aittir |
| `brain_eleven/extraction/`, `retrieval/`, `search/` | Çıkarım sağlayıcıları, embedding |
| `scripts/` | Canlı kod pakette; burada yalnız repo dışından çağrılabilen girişler kalır (aşağıdaki liste) |
| `evals/recall_probe/` | `recall-probe` komutunun 5 sorusu |
| `🔮 Companion/`, `🗂️ Proje Notları/`, `📝 Template/` | Obsidian vault içeriği |

## `scripts/` içindekiler

- `context-compiler.py`: kurulu SessionStart hook şablonunun çağırdığı giriş noktası; `brain_eleven.runtime.context_compiler.main`'i çalıştırır.
- `remember.py`: `/remember` komutunun çağırdığı yol; `brain_eleven.memory.capture`'a yönlenir.
- `remember_opt_in.py`: SessionEnd hook şablonunun sorduğu, projede proaktif yakalama izni olup olmadığını denetleyen kapı.
- `install-cross-project-memory.py`: eski `~/.claude` kurulumu (hook ve komut dosyalarını yazar/kaldırır); yeni kurulum `brain_eleven/runtime/install.py`.
- `memory_backup.py`: kanonik hafızanın doğrulanmış yedeğini alır ve geri yükler.
- `post_session_maintenance.py`: `brain_eleven.runtime.maintenance`'a yönlenen eski bakım girişi (graf yenileme, anomali, özet).
- `weekly_recall_check.ps1`, `weekly_recall_check_core.ps1`: haftalık hatırlama kontrolü (Windows zamanlanmış görevi için).
- `__init__.py`: testlerin `scripts.` altından içe aktardığı paket işareti.

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

## İş sonuçları

`runtime/receipts.py`: ajanın yazdığı değişmez sonuç kayıtları, runtime
kökünde dosya başına bir JSON. Proje notu, SessionStart kart bölümü ve `recap`
bunları gösterir; kanonik hafızaya girmez.

## Yakala

`runtime/yakala.py`: `📥 Gelen/` gelen kutusu (Markdown öğe, `durum: bekliyor`),
pano okuma ve Windows Başlat Menüsü kısayolu. URL açmaz, model çağırmaz;
işleme `beyin-yakala` skill'iyle ajanın kendi araçlarıyla yapılır, sonuç
`🧠 Bilgi/` notlarıdır (kanonik hafıza değil).

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
