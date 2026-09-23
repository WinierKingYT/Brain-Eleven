# TEST-LOG — yeni oturumda hatırlama testi

Tek hedef: yeni bir oturum, geçmişte verdiğimiz kararı hatırlıyor mu?
Yeni faz, paket veya değerlendirme kümesi bu dosyanın konusu değildir.

## Protokol

1. Her soruyu **ayrı, yeni bir oturumda** sor. Bir oturumda tek soru.
2. Oturuma şunu de: "Dosyalara, git geçmişine ve TEST-LOG.md'ye bakma. Yalnızca oturum başında sana
   verilen bağlamdan yanıtla. Bilmiyorsan bilmiyorum de." Aksi halde test hafızayı değil, repodaki
   belgeleri ölçer (bu kararlar NEXT.md ve SRT00-PLAN.md'de de yazılı).
3. Cevabı puanla: **doğru / kısmen / yanlış / hiç**. "Yanlış", uydurulmuş ya da çelişen cevaptır;
   "hiç", bilmiyorum ya da boş cevaptır. İkisi farklı sorun demektir (adım 4).
4. Anahtar cevabı çıkarmadan önce kendin doğrula. Yanlış saydığın bir anahtar varsa o soruyu değiştir.

## Sorular ve anahtar cevaplar

| # | Soru | Anahtar cevap |
|---|---|---|
| 1 | Holdout (corpus-v2) kapısı kırmızıyken ne karar verdik? | Kırmızı bilerek bırakıldı; dondurulmuş corpus-v2 kapısı korunur, PRE-13 promosyonu ertelendi. Eşik düşürülmez, test atlanmaz. |
| 2 | Gerçek Claude oturumları neden hiç kanonik hafızaya girmiyordu? | 205/205 iş `EVIDENCE_INVALID` ile dead-letter olmuştu: okuyucu bilinmeyen kayıt tipinde tüm oturumu reddediyordu. Boyut hipotezi çürütüldü. Düzeltme: bilinmeyen tipler atlanıp sayılıyor. |
| 3 | `master` neden origin'e push edilmedi? | Push, `ghcr.io/...:latest` imajını yayınlar; PRE-13 kalitesi kırmızıyken bu istenmedi. Varsayılan: push yok. |
| 4 | Phase 20 ve aktif program hangi durumda? | Phase 20 FROZEN. Aktif program Intelligence Graduation (IG). Knowledge Engine başlatılmaz. |
| 5 | Retrieval-kalite sözleşmesi hakkında ne dedik? | Kullanıcı bunu ayırdı (kapsam dışı bıraktı); holdout kararını o sözleşme değiştirebilir ama şimdilik yürürlükte değil. |

## Sonuçlar

Tarih: 2026-09-20

Yöntem: `claude -p "<soru>" --tools '' --strict-mcp-config` ile 5 ayrı, taze headless
oturum. Araç ve MCP erişimi tamamen kapalı, yani oturum dosyalara/git'e zaten
fiziksel olarak bakamadı — bu, "bakma" talimatına güvenmekten daha sıkı bir izolasyon.
Yalnızca `SessionStart` hook'unun enjekte ettiği bağlam (varsa) cevap kaynağıydı.

| # | Puan | Not |
|---|---|---|
| 1 | hiç | "Bilmiyorum" dedi. Bağlamda holdout/corpus-v2 kararına dair hiçbir iz yoktu; izlenmeyen `.local-pre13-holdout-*.json` dosyalarını fark etti ama içeriklerini bilmiyordu. |
| 2 | kısmen | Doğru mekanizmayı (bilinmeyen kayıt tipinde tüm oturumun reddi) yalnızca son üç commit **başlığından** çıkardı, "kesin değil" diye işaretledi. 205/205 sayısını, boyut hipotezinin çürütülmesini bilmiyordu. Bu, gerçek hafıza değil — oturum başına otomatik eklenen git log'dan (`gitStatus` bağlamı) çıkarım. |
| 3 | hiç | "Bilmiyorum" dedi; git ahead/behind bilgisi bile elinde yoktu, sadece iki commit mesajından zayıf bir ipucu gördü. Gerekçeyi (latest imaj yayınlanır, PRE-13 kırmızıyken istenmedi) bilmiyordu. |
| 4 | doğru* | Phase 20 FROZEN / IG aktif / IG-00→IG-01 sırası hepsi doğru. *Ama bu CLAUDE.md'nin kendi metninden — her oturuma otomatik yüklenen dosya içeriği. Gerçek hafıza testi değil, dosya okuma testi. |
| 5 | hiç | "Bilmiyorum" dedi; "retrieval-kalite sözleşmesi" ifadesi bağlamda hiç geçmiyordu, CLAUDE.md'deki genel retrieval-kapsam kuralıyla karıştırmadı. |

Özet: **0 doğru (hafızadan), 1 kısmen, 0 yanlış, 4 hiç.** Tek "doğru" (#4) dosyadan
geliyor, hafızadan değil — gerçek hafıza skoru fiilen **0/5**.

**Sonuç → Kırmızı çizgiye göre karar:** "Hiçbir şey gelmiyorsa: sorun hook'lar.
Sadece SessionStart'ı düzelt." Bu, retrieval precision sorunundan (0.18) önce gelen
daha temel bir bulgu: precision'ın düşük olması bir şey geldiği anlamına gelir; burada
5 sorudan 4'ünde **hiçbir şey gelmedi**. Yani sıradaki iş retrieval'ı iyileştirmek değil,
`SessionStart` hook'unun bağlamı gerçekten enjekte edip etmediğini doğrulamak.

## SessionStart teşhisi (2026-09-20)

**Hook kırık değil.** Her test oturumunda gerçekten çalıştı ve `additionalContext`
teslim etti — servise doğrudan sorup doğrulandı (`provider: V1`, `delivered: true`,
`delivery_approved: true`).

**Teslim edilen içerik işe yaramaz.** `.claude/validated-memory.json`'dan geliyor:
`validated_at: 2026-09-04`, dosya en son 6 Eylül'de değişmiş, tek seferlik doğrulanmış
46 eski kayıt. Beş soruya da giren sabit 5 madde (Phase 4 kalite pivotu, Memory
Compiler, mem0 entegrasyonu, retrieval engine "not started") **16 gün öncesinden** —
SRT-00'un, holdout kararının, transcript-fix'inin hiçbirinden değil.

**Kök neden.** Güncel yakalama pipeline'ı gerçekten çalışıyor: review queue'da 249
kayıt, 248'i PENDING, en yenisi bugün. Ama `mode: SHADOW` olduğu için hiçbiri canonical
hafızaya terfi etmiyor (review-accept CANARY/ACTIVE gerektirir) — yani doğru yakalanan
hiçbir şey asla sunulabilir hale gelmiyor. Servis bunun yerine donmuş V1 dosyasına
düşüyor.

**Bu neden hemen düzeltilmedi.** Gerçek düzeltme mode'u SHADOW'dan çıkarmak
(CANARY/ACTIVE) — bu, daha önce ayrı bırakılmış **pilot gate / CANARY promosyonu**
kararının ta kendisi, ve CANARY'ye geçiş dondurulmuş holdout kalite kapısını tetikler
(o kapı şu an kırmızı, bilerek). Kullanıcı onayı olmadan mod değiştirilmedi.

### CANARY denemesi (2026-09-20, kullanıcı onayıyla)

`RuntimeConfig.set_mode('CANARY')` çağrıldı. Kod kendi içinde bağımsız holdout
kalite testini (`evals.runtime_eval.run('holdout')`) çalıştırıp sonucu değerlendirdi;
`status != PASS` olduğu için **mod değiştirmeden** `ValueError` fırlattı — eşik
düşürme, atlama ya da bypass yok, `mode` hâlâ `SHADOW`.

Rapor (`.brain-eleven/runtime/canary-quality.json`):

| Eşik | Gerekli | Ölçülen (runtime/V1) | Sonuç |
|---|---|---|---|
| `precision_70` | ≥0.70 | 0.169 / 0.173 | FAIL |
| `required_recall_80` | ≥0.80 | 0.676 / 0.706 | FAIL |
| `nonregression_precision` / `nonregression_recall` | V2 ≥ V1 | değil | FAIL |
| `no_forbidden` / `no_lifecycle_leaks` / `no_project_leaks` | — | temiz | PASS |

Sızıntı yok, proje karışması yok — sorun tamamen alaka düzeyi düşük seçim (precision).
Bu, daha önce ayrı bırakılan **retrieval-kalite sözleşmesi** meselesiyle aynı kapı.
CANARY yolu şu sayılarla kapalı kalıyor; bu README/kod tarafından zorlanıyor, tek
taraflı bir karar değil.

### Retrieval düzeltmesi #1: kritik-ihtiyaç bypass'ı (2026-09-20, kullanıcı onayıyla)

`retrieval_decision_v2/engine.py`'de gerçek bir hata bulundu ve TDD ile düzeltildi:
"critical" öncelikli bir ihtiyaç (`need_state`, `need_constraints`) yalnızca geniş bir
`content_type` kategorisiyle eşleştiğinde (örn. herhangi bir `blocker`/`risk` kaydı),
o kategorideki **her** aday, konuyla hiç ilgisi olmasa da, alaka-filtresini tamamen
atlıyordu. Yalnızca kesin kayıt-id eşleşmesi (`need_record_<id>`) bu atlamayı hak
etmeli. Düzeltme: geniş kategori eşleşmesi artık atlama hakkı vermiyor; bunun yerine
o ihtiyaç hâlâ hiç karşılanmamışsa tek bir "backfill" adayı ekleniyor (kapsama
garantisi kalıyor, toptan dahil etme kalkıyor).

- 2 yeni birim testi (RED→GREEN), 93 ilgili test yeşil, tam paket (1450 test)
  yalnızca önceden var olan iki ilgisiz nedenle kırmızı (kirli çalışma ağacı kilidi,
  yükte zamanlamaya duyarlı test — ikisi de bu değişiklikten önce de böyleydi).
- Holdout'u tekrar çalıştırdım: **precision ve recall hiç değişmedi** (0.169 / 0.676,
  bit bit aynı). Sebebini tek tek izleyerek buldum.

### Asıl kök neden: alaka skorlama'nın kendisi zayıf

En kötü vakayı (`p15_v2_authority_traps_041`) canlı çalıştırıp incelendi. Bu görevde
hiçbir "critical" ihtiyaç hiç oluşmuyor — yalnızca herkesle eşleşen `need_general`
yedek kategorisi devreye giriyor, yani düzeltmemin dokunduğu yol hiç çalışmıyor.
Asıl neden, terim-örtüşmesine dayalı basit puanlama formülü:

- Soru: *"Select only active promtgen context for the authority traps evaluation case."*
- İlgili kayıtlar "promtgen" kelimesini paylaşıyor (skor ≈0.060).
- Sentetik gürültü kayıtları hepsi `"Synthetic irrelevant evaluation noise N-M."`
  metnine sahip; sorudaki **"evaluation"** kelimesiyle örtüşüyor, ve bu 9 adaylık
  küçük havuzda yalnızca 4 belgede geçtiği için IDF ağırlığı "promtgen"den (5 belgede
  geçiyor) **daha yüksek** çıkıyor — skor ≈0.067. Gürültü, gerçek içerikten daha
  alakalı görünüyor.
- Eşik en yüksek skorun %35'i (≈0.023) — hem gerçek hem gürültü bunu kolayca geçiyor,
  hiçbir şey elenmiyor.

Bu, eval'in adının da işaret ettiği gibi ("authority_traps", "lexical_traps") kasıtlı
bir tuzak vakası: küçük, kısa metinlerde IDF yalnızca o anki aday havuzuna göre
hesaplanınca, paylaşılan sıradan bir kelime gerçek konudan daha "nadir" görünüp
öne çıkabiliyor. Kritik-bypass hatası gerçekti ve düzeltildi, ama holdout'un genel
başarısızlığını asıl bu ikinci, daha temel zayıflık sürüklüyor.

**Bunu eşiğe dokunmadan, gerçekten düzeltmek** — havuz-içi IDF yerine daha kararlı bir
alaka sinyali (ör. `brain_eleven/retrieval/embedding_provider.py` — halihazırda var
ama burada hiç kullanılmıyor — ya da tüm canonical hafızaya göre sabit bir IDF tablosu)
gerektiriyor. Bu, ilk düzeltmeden belirgin biçimde daha büyük bir değişiklik: temel
puanlama mekanizmasını değiştirmek. Kullanıcıya sorulup yön onaylanmadan başlanmadı.

### Sinyal deneyi (2026-09-21, yalnızca `public` suite, üretim koduna dokunulmadı)

Kullanıcı "1" (embedding) dedi. Üretime dokunmadan önce ucuz bir deney yapıldı
(130 vaka; betik: oturum scratchpad'i `signal_experiment.py`). Holdout'a bakılmadı;
not: önceki adımda tek bir holdout vakası (`authority_traps_041`) ayrıntılı
incelenmişti, bu holdout bağımsızlığını biraz zayıflatır.

| Ölçüm | Sonuç |
|---|---|
| Kelime-örtüşmesi (mevcut) — gerçek kayıtlar arasında ilk doğru kaydın MRR'ı | 0.499 |
| Tüm-vault IDF (seçenek 2) | 0.503 |
| Rastgele sıralamanın beklenen değeri | 0.487 |
| Kusursuz gürültü elemesi, proje-içi ayrım yok → precision tavanı | **0.211** |
| Aynı seçicinin recall tavanı | **0.779** |
| Gerekli kaydın aday havuzuna hiç girmediği vaka | **33 / 130** |

Bulgular:

1. **Seçenek 2 ölçülüp elendi.** Havuz-içi ya da tüm-vault IDF fark etmiyor; en iyi
   precision 0.203. Kelime örtüşmesi bu derlemde gerçek kayıtlar arasında **şans
   düzeyinde** — sorun IDF'in nasıl hesaplandığı değil, sinyalin kendisi. Önceki
   "IDF düzeltilirse geçer" varsayımım yanlıştı.
2. **Recall kapısı karar aşamasında aşılamaz.** Gerekli kayıt 33/130 vakada aday
   havuzuna hiç girmiyor (ör. istem "global engineering rules" diyor, gerekli kayıt
   `mem_markdown_source_of_truth`, kelime örtüşmesi yok). Aday üretimi
   (`context_router`) kelime/alt-dize eşlemesiyle çalıştığı için, karar aşamasındaki
   kusursuz bir seçici bile en fazla 0.779 recall alır; kapı 0.80 istiyor.
3. **Embedding ölçüldü ve elendi (kullanıcı izniyle indirilen
   `intfloat/multilingual-e5-base`, rev `d128750`, 1134 MB, çevrimdışı çalıştırıldı).**

   | Sinyal | Gerçek kayıtlar arasında MRR | Gerçek kaydı gürültüden kesin ayırma |
   |---|---|---|
   | kelime örtüşmesi (mevcut) | 0.499 | %0.8 |
   | tüm-vault IDF | 0.503 | %1.6 |
   | e5-base cosine | **0.472** | **%22.0** |
   | rastgele (beklenen) | 0.487 | — |

   Embedding gürültüyü kelime sinyalinden çok daha iyi eliyor (%22 vs ~%1), ama
   *gerçek kayıtlar arasında doğruyu seçemiyor* (şans düzeyinin bile altında).
   Hangi marj eşiği seçilirse seçilsin precision 0.187–0.211 aralığında kalıyor;
   yani tavan olan 0.211'i aşmıyor. IG-01d'deki üç model (MPNet, E5-large, BGE-M3)
   da aynı sonuca işaret ediyordu; şimdi dördüncü bağımsız ölçüm bunu doğruluyor.
4. **Sonuç: precision ≥ 0.70 kapısı, istemden başka girdi kullanmayan hiçbir seçiciyle
   ulaşılabilir görünmüyor.** İstem, ~4.5 gerçek kayıttan hangisinin gerekli olduğunu
   ayırt ettirecek bilgi taşımıyor (şablonlu: "...eleven_capture relevance
   scenario 1."). Bu, `D0-RECHECK-FINDINGS.md` §1'deki bulgunun (eşik, tavanın
   üstünde) bu kapıdaki karşılığı. Sınırlar: tek embedding modeli, sentetik şablonlu
   derlem, public suite (123 vaka); holdout'ta tavan ölçülmedi (gate raporundaki
   vaka yapısı benzer: 4 seçilen, 1 ilgili).
5. **Ne gerekir?** Bu, geri çekilebilecek bir "kalite" değil, kapının ölçtüğü şeyin
   ulaşılabilirliği sorusu. Eşik gevşetme, atlama ya da derlemi değiştirme benim
   yapacağım işler değil; kapı tasarımı proje sahibi + bağımsız inceleme
   kararıdır. Ayrıca kapı, teslim edilmeyen V2 hattını ölçüyor ("Native delivery
   never calls this function") ve `review_action` accept iznini ona bağlıyor.

## Şimdi hatırlama testini gerçekten çalıştırmak (2026-09-21 kararı)

Kilit kaldırıldı ama **açılmadı**: `shadow_accept` varsayılan kapalı, bayrağı sen açarsın.

1. `python -m brain_eleven shadow-accept ON` — SHADOW'da insan onaylı kabulü açar.
2. `python -m brain_eleven review` — inceleme sayfasını açar. 248 bekleyen kayıt var; hepsini
   onaylamana gerek yok, önemli birkaç kararı (holdout kararı, push kararı, Phase 20 durumu,
   transcript düzeltmesi) seçip "Kabul et"le yeterli. Sırları ve gürültüyü kabul etme.
3. Yeni bir oturumda yukarıdaki 5 soruyu yeniden sor, tabloyu doldur.

Beklenti: onayladığın kayıtlar SessionStart bağlamına V1 yolundan girer (testle doğrulandı).
Bayrağı geri almak için `shadow-accept OFF`; onaylanmış kayıtlar canonical'da kalır.

## İlk gerçek sonuç (2026-09-23) — pilot fiilen çalıştı

09-20'deki teşhis (`SessionStart teşhisi` yukarıda) "gerçek hafıza skoru fiilen 0/5" idi
ve kök nedeni `.claude/validated-memory.json`'ın 09-04'te donmuş kalması + SHADOW'da
review-accept'in CANARY/ACTIVE gerektirmesiydi. Bugün: `shadow-accept ON` açıldı, review
kuyruğundan (682 bekleyen) 13 gerçek, tekrarsız karar/bulgu elle seçilip kabul edildi
(Claude tarafından, Ahmet'in açık isteğiyle — "review sayfasından ben değil sen değerli
bilgileri seç ve onayla"). `.claude/validated-memory.json` doğrulandı: artık **canlı**
(revision 18, `updated_at: 2026-09-23`, 61 kayıt) — 09-20'deki "donmuş dosya" bulgusu
artık geçerli değil.

**Protokole göre yeni, taze bir oturumda** (bu konuşmadan ayrı, Ahmet tarafından açılan)
Soru #1 soruldu, dosya/git erişimi olmadan:

| # | Puan | Not |
|---|---|---|
| 1 | **doğru** | Anahtar cevabı ("kırmızı bilerek bırakıldı, corpus-v2 kapısı korunur, PRE-13 ertelendi, eşik düşürülmez") birebir üretti; ayrıca bugün kabul edilen "holdout gate red by decision" ve "remote CI green except holdout quality (by decision)" kayıtlarını kelimesi kelimesine doğru aktardı. Kendi başına bir tutarsızlık da yakaladı (aşağıya bakın) ve bunu dürüstçe "bilmiyorum" diye işaretledi — uydurmadı. |

**Yan bulgu — gerçek bir hafıza çelişkisi yakalandı ve düzeltildi:** Oturum, bağlamda hem
eski "SRT-00 remains NOT SHIP" kaydını hem `CLAUDE.md`'nin güncel "SRT-00 kapandı"
durumunu gördü ve hangisinin güncel olduğunu bilemediğini açıkça belirtti. Kontrol edildi:
kabul edilen kayıt 09-20 tarihliydi, `CLAUDE.md`'nin durumu 09-23'te değişmiş. Eski kayıt
`SUPERSEDE_EXISTING` ile düzeltildi (`mem_83f4ae0a...` → `superseded`, yeni doğru kayıt
`mem_0a830a55...` → `active`). Bu, hem canonical hafızanın canlı/düzeltilebilir olduğunu
hem de test protokolünün gerçek hataları yakaladığını gösteriyor — beklenen ve istenen bir
sonuç.

Aynı gün, ayrı taze bir oturumda Soru 4 de soruldu:

| # | Puan | Not |
|---|---|---|
| 4 | doğru* | Phase 20 FROZEN / IG aktif — doğru ve güncel, artı doğru ek detay (IG-05 kapandı, IG-06/07 açılmıyor, SRT-00 kapandı). *Kaynağı kendi ifadesiyle "CLAUDE.md ve açılış hafıza özeti" — yani 09-20'deki aynı yıldızlı kayıtla tutarlı: bu soru CLAUDE.md'nin kendi metninden de cevaplanabilir, hafıza pipeline'ını Soru 1 kadar güçlü sınamıyor. Yine de burada da bir çelişkiyi (CLAUDE.md'nin alt kısmındaki eski IG-00→IG-01 ifadesinin üstteki güncel durumdan eski olduğu) kendi başına, doğru şekilde fark etti — uydurmadı. |

**Özet (bugüne kadar): 1 doğru (hafızadan, Soru 1), 1 doğru\* (kısmen dosyadan, Soru 4).**
09-20'deki 0/5'ten ilk kez gerçek "evet, hatırladı" örnekleri. Küçük örneklem (n=2) —
program çapında bir sayı değil, ama mekanizmanın artık uçtan uca çalıştığının somut
kanıtı. Soru 2/3/5 şu an test edilmeye uygun değil: Soru 3'ün anahtar cevabı artık bayat
(master o zamandan beri gerçekten push edildi), Soru 2/5'in gerçeği henüz kabul edilmiş
bir hafıza kaydı olarak yok (review kuyruğunda net bir aday bulunamadı).

## Günlük (iki hafta)

Her gün bir satır: "Bugün hatırladı mı? Evet/hayır, neyi."

| Tarih | Hatırladı mı? | Neyi |
|---|---|---|
| 2026-09-23 | Evet | Soru #1 (holdout/corpus-v2 kararı) — doğru; Soru #4 (Phase 20/IG durumu) — doğru* (kısmen dosyadan). Bkz. "İlk gerçek sonuç" yukarıda. |
