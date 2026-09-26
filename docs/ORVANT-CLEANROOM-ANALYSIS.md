# Orvant temiz oda analizi — davranış envanteri ve Brain-Eleven fark tablosu

**Durum: CURRENT — karar girdisi, 2026-09-23.** Bu belge yeni bir IG paketi,
faz veya sözleşme açmaz; hiçbir eşik, korpus, holdout, Phase 20 veya V2 modu
değiştirmez. Amacı, bir sonraki adımda (parça seçimi + sözleşme) hangi fikrin
`docs/programs/WORK-INTAKE-RULE.md` sorusunu geçebileceğine karar vermek için
girdi üretmektir.

## Kaynak ve lisans sınırı

- İncelenen: `github.com/fornhere/orvant`, commit `c059a99` (2026-09-17),
  branch `codex/public-pilot`. Tek yazar, 7 commit, v0.3 pilot.
- **Repoda lisans dosyası yok.** Varsayılan olarak tüm haklar saklıdır. Bu
  yüzden Orvant'tan **hiçbir kod, test, metin veya JSON örneği** bu repoya
  kopyalanmaz ya da uyarlanmaz. Klon yalnız oturum scratchpad'inde tutuldu.
- Aşağıdaki envanter, Orvant'ın yayımlanmış belgelerinden
  (`README.md`, `TEKNIK-TASARIM.md`, `skills/orvant/references/model.md`) ve
  kodun yapısal okumasından çıkarılmış **davranış tarifleridir**; kod aktarımı
  değildir. Uygulanacak her parça Brain-Eleven'in kendi tasarımıyla, önce test
  yazılarak sıfırdan kurulur.
- Orvant kodu çalıştırılmadı; testlerinin geçtiği bağımsız doğrulanmadı.

## 1. Orvant davranış envanteri

| # | Davranış | Kısa tarif |
|---|---|---|
| O-01 | Tek yetkili durum dosyası | Bütün proje durumu tek JSON'da; insan okuyabilir görünümler ondan türetilir, otorite değildir. |
| O-02 | Revizyon + atomik yazım + kilit | Her başarılı eylem revizyonu bir artırır; geçici dosya + `os.replace`; OS düzeyi advisory kilit. |
| O-03 | Katı girdi okuma | Tekrarlanan JSON anahtarı, NaN/Infinity, symlink ve beklenmeyen dosya türü reddedilir. |
| O-04 | Önizleme → özetle uygulama | `preview` aynı motoru kopyada çalıştırır, etkileri ve bir `preview_digest` döndürür. `apply` aynı revizyon ve digest'i ister; araya giren durum/dosya değişimini reddeder. |
| O-05 | Görev başlangıç anlık görüntüsü | `start_task` girdilerin manifestini kaydeder. Girdiler çalışma sırasında değiştiyse kanıt sunumu reddedilir. |
| O-06 | Dosya parmak izli kanıt | Kanıt, kabul ölçütüne bağlanır ve incelenen dosyaların SHA-256 değerini taşır. |
| O-07 | Dayanak değişince kabulün eskimesi | Kayıtlı durum (`status`) ile hesaplanan güncellik (`freshness: current/stale/unverified`) ve yapılabilirlik (`readiness`) ayrı tutulur. Bir girdi/dosya değişirse `done` görev güncel başarı sayılmaz. |
| O-08 | Yönlü etki yayılımı | İlişki türü etki yönü taşır (`forward/reverse/both/none`). Değişiklik yalnız ilan edilmiş yönde bağlı işleri eskitir; ilgisiz etiket değişikliği hiçbir şeyi eskitmez. |
| O-09 | Üretici kuşakları | Bir çıktının tek üreticisi var. Üretici yeniden tamamlanırsa, aynı byte'lar üretilse bile eski tüketici kanıtı otomatik geçerli olmaz. |
| O-10 | Alternatif destek grupları | `all` (hepsi gerekli) ile `any` (incelenmiş biri yeterli) ayrılır. Yeni eklenen alternatif kendiliğinden "incelenmiş" sayılmaz; kaybolan dal geri gelince eski kabul dirilmez. |
| O-11 | Karar yaşam döngüsü | `proposed → accepted/rejected`, konu başına tek etkin kabul, açık `supersedes`. Ajan insan kabulü veremez. Eski karara dayanan iş etkin başarı sayılmaz. |
| O-12 | Değişmez tarihsel kayıt | `immutable: true` türler düzenlenmez; yeni koşul yeni kimlik alır. Silinen kimlik yeniden kullanılamaz. |
| O-13 | Sınırlı, kodsuz kabul kuralları | `equal_sets / disjoint / count / all / any` + ilişki yolu seçicileri. `eval` yok, derinlik sınırlı. |
| O-14 | Açık sınır beyanı | "Hash eşleşmesi içerik doğruluğu değildir", "ilişki adı ispat değildir", "geçmiş imzalı defter değildir". |

## 2. Brain-Eleven'deki karşılıkları

"Doğrulandı" sütunu, bu analiz sırasında kodda gerçekten görülen yeri gösterir.

| # | Brain-Eleven durumu | Doğrulandı |
|---|---|---|
| O-01 | **Var.** Canonical otorite MemoryStore, StateStore, ProjectRegistry; provenance ve graph ayrı projeksiyonlar. | `brain_eleven/memory/provenance.py:1-6`, `CLAUDE.md` |
| O-02 | **Var.** Revizyon, kilit, atomik yazım, `expected_revision` ile CAS. | `brain_eleven/memory/store.py`, `CLAUDE.md` |
| O-03 | **Kısmen var.** Kayıt alan doğrulaması var; TSC-03 ile görev durumu okuma katılaştı. | `brain_eleven/memory/store.py:75-115`, `authority/serialization.py` |
| O-04 | **Kısmen var.** CAS eski revizyonu reddeder; memory truth'ta preflight izleri var. Genel "etki önizlemesi + digest" yok. | `brain_eleven/memory/truth.py:81` (`_REPLAYABLE_PREFLIGHT_REASONS`) |
| O-05 | **Yok.** Work item'larda girdi manifesti yok. | `brain_eleven/state/store.py` içinde `evidence/depends_on/acceptance` eşleşmesi 0 |
| O-06 | **Zayıf.** `evidence_refs` var ama yalnız dizgi kimlikleri (oturum veya içerik hash kimliği); kaynağın **şimdiki** hâliyle karşılaştırılmıyor. | `brain_eleven/memory/provenance.py:60`, `brain_eleven/extraction/semantic.py:633,755` |
| O-07 | **Yok (hafıza için).** Retrieval'daki `freshness` yalnız zaman bozunması (yeni = yüksek skor). Kaynağın hâlâ geçerli olup olmadığına bakılmıyor. State resolver'daki `freshness` yalnız durum yaşı. `last_confirmed_at` alanı var ama legacy projeksiyonda hep `None`. | `scripts/memory-retriever.py:86-88`, `brain_eleven/state/resolver.py`, `brain_eleven/memory/provenance.py:100` |
| O-08 | **Yok.** Graph projeksiyonu var ama etki yönü ve yayılım kuralı yok. | `brain_eleven/graph/projection.py` |
| O-09 | **Uygulanamaz.** Brain-Eleven'de üretici/tüketici görev zinciri yok. | — |
| O-10 | **Yok.** | — |
| O-11 | **Kısmen var.** Hafıza durumları `active/resolved/superseded`; retriever aktif olmayanı atlar. StateStore blocker `memory_ref` durumunu denetler. Konu başına tek etkin karar ve insan/ajan kabul ayrımı hafıza için açık bir sözleşme değil (shadow-accept insan onaylı). | `scripts/memory-lifecycle.py`, `brain_eleven/state/store.py:145,1068` |
| O-12 | **Kısmen var.** `memory_id` değişmez; güncelleme yerine `superseded`. | `brain_eleven/memory/provenance.py:1-6` |
| O-13 | **Gereksiz.** Brain-Eleven görev kabul motoru değil. | — |
| O-14 | **Var ve güçlü.** Ör. "configured ≠ delivered", SHADOW sınırları. | `RUNTIME-DATAFLOW.md` |

## 3. Değerlendirme

Orvant'ın en güçlü ve Brain-Eleven'de gerçekten eksik olan fikri **O-06 + O-07**:
"bu kayıt neye dayanıyordu, o dayanak hâlâ aynı mı?" sorusunun makinece
cevaplanması. Brain-Eleven'de bu soru hafıza için hiç sorulmuyor. Bir hafıza,
dayandığı dosya veya karar değişmiş olsa bile retrieval'da yalnız yaşına göre
puanlanıyor ve yeni oturuma sunulabiliyor.

Görev ve ontoloji makinesinin geri kalanı (O-05, O-08–O-10, O-13) Brain-Eleven'in
amacı olan hatırlama için ağır ve dolaylı. Kopyalanması gereken bir şey değil.

## 4. Intake kuralına göre aday

**Aday A — Dayanağı değişen hafızanın eskimesi (O-06 + O-07 uyarlaması).**

- **Hatırlama testini ilerletiyor mu?** Dolaylı, ama nedensellik zinciri yazılabilir:
  hafızaya kaynak parmak izi eklenir → oturum başı teslimde kaynak değişmiş
  hafıza `stale` işaretlenir veya geri plana alınır → yeni oturuma eski/yanlış
  bilgi sunulmaz → hatırlama testinde **yanlış hatırlanan** madde sayısı düşer.
- **Açık risk:** Mevcut 0/5 skorun nedeni büyük ihtimalle yanlış bilgi değil,
  **hiç bilgi gelmemesi** (teslim/kabul yolu). Bu durumda Aday A skoru
  yükseltmez; yalnız gelecekteki yanlış hatırlamayı önler. Sözleşme bunu açıkça
  ölçmeli: TEST-LOG'daki başarısızlıklar "eksik" mi, "yanlış" mı?
- **Kapsam önerisi (sözleşmede daraltılacak):** yalnız dosya kaynaklı hafızalar;
  kaynak yolu + SHA-256 kaydı; retrieval/teslim anında karşılaştırma; `current /
  stale / unverified` ayrımı. Kaynak değişti diye hafıza **silinmez** veya
  otomatik `superseded` yapılmaz (O-14 ilkesi: dayanak kaybı, bilginin yanlış
  olduğunu kanıtlamaz). Canonical otorite MemoryStore'da kalır.

**Aday B — Önizleme + digest (O-04).** Güvenlik/doğruluk açısından değerli ama
hatırlama testine bağlantısı zayıf. Şimdilik bilinen sınır olarak kalır.

**Kopyalanmayacaklar:** Ontoloji tür sistemi, görev kabul motoru, destek grupları, kabul kuralı DSL'i.

## 5. Adım 2 bulgusu: TEST-LOG sınıflandırması (2026-09-23)

| Ölçüm | doğru | kısmen | yanlış / çelişki | hiç |
|---|---|---|---|---|
| 09-20 (5 soru, donmuş V1 dosyası) | 0 (+1 dosyadan) | 1 | 0 | 4 |
| 09-23 (2 soru, shadow-accept sonrası) | 1 (+1 kısmen dosyadan) | 0 | **1 çelişki** (Soru 1 oturumunda) | 0 |

- **"Hiç" hataları** SHADOW'daki teslim yolundan kaynaklanıyordu ve
  `shadow-accept` ile giderildi. Bu, Orvant'tan alınacak hiçbir fikirle ilgili değil.
- **Gözlenen tek çelişki:** eski "SRT-00 remains NOT SHIP" kaydı ile güncel durum
  birlikte teslim edildi, oturum hangisinin güncel olduğunu bilemedi, kayıt elle
  supersede edildi.
- **Aday A bu hatayı yakalamazdı.** Kaydın `evidence_refs` alanı ve dosya kaynağı
  yok; dayanağı değişmeyen bir transcript. Dosya parmak izi yaklaşımı burada boşa
  çalışır. Aday A ertelenir.
- **Yakalayabilecek olan Orvant O-11'in karşılığı:** konu başına tek etkin kayıt.
  Brain-Eleven'de bunun mekanizması (`claim_key`, `scripts/memory_truth.py:500`)
  **zaten var ama ölü**: 61 canonical kaydın hiçbirinde dolu değil. Ayrıca
  `occurred_at` yoksa kabul anı olay zamanı olarak yazılıyor
  (`scripts/memory_truth.py:510`), bu yüzden eski bilgi yeni görünüyor.
- **Yeni aday:** `docs/contracts/MEMCLAIM-01-CLAIM-KEY-SUPERSESSION-CONTRACT-DRAFT.md`.
  Intake sorusuna doğrudan "evet" diyor, çünkü gözlenen bir hatayı hedefliyor.

## 6. Sonraki adım

2. adım tamamlandı (§5). MEMCLAIM-01 taslağı bağımsız incelemeden geçerse 3. adımda
önce testleri yazılarak uygulanır. Aday A ve B bilinen sınır olarak kalır.
