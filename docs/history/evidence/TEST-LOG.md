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
| 3 | SRT-00 nasıl kapandı, master push edildi mi? | 2026-09-23'te CI yeşil kapandı ve master'a push edildi; bu bir stabilizasyon kapanışı, bağımsız SHIP değil; PRE-13 holdout kapısı bilerek kırmızı. (2026-09-30, sahip onayı: eski soru "master neden push edilmedi?" push sonrası yanlış kaldığı için değişti.) |
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

### 2026-09-27 Sonuçlar

#### İlk koşu (geçersiz ölçüm)

**Geçersiz ölçüm: model cevaplamadı, araç denedi.** Q1 zaman aşımına uğradı; Q2, Q3 ve Q5 araç taslağı verdi; Q4 kısmen yanıtladı. İlk koşunun toplam puanı geçerli ölçüm sayılmaz; soru satırları ve hafıza kaynakları tarihçe olarak korunmuştur.
Araç/komut taslakları (yalnız adlar): Q2 `Grep`, `grep`; Q3 `git fetch`, `git log`, `git status`; Q5 `Bash`. Çağrı çalıştırılmadı.
Devir kontrolü ilişkisi: Q3 taslağındaki `git fetch` kuraldaki komutlardan biriyle örtüşüyor; `git ls-remote`, `gh pr list` ve `gh issue list` taslaklarda yok. Q2/Q5 adları kuralın komutlarıyla doğrudan eşleşmiyor.


**Tarih:** 2026-09-27. `recall-probe` 2026-09-26'da çalıştırıldı; taze Claude oturumları gece yarısını geçti.

**Probe skoru:** **5/5** — `delivered_memories=8`; beş sorunun durumu `IN_CONTEXT`.

**İlk koşu durumu: GEÇERSİZ ÖLÇÜM — model cevaplamadı, araç denedi.** Aşağıdaki ilk koşu kaydı tarihçe için korunuyor; ölçüm sonucu olarak kullanılmamalı.

**İlk koşuda kaydedilen puan (geçersiz ölçüm):** **0 doğru, 1 kısmen, 0 yanlış, 4 hiç** (tam doğru: **0/5**).

İlk koşu yöntemi: her soru için ayrı `claude -p "<soru>" --tools '' --strict-mcp-config` süreci. Q1 beş dakikadan uzun süre cevap vermedi ve sonlandırıldı. Q2, Q3 ve Q5 cevap yerine yalnızca araç çağrısı taslağı üretti; araçlar kapalı olduğu için hiçbir çağrı çalıştırılmadı. Q4, Phase 20'nin FROZEN ve Intelligence Graduation'ın aktif olduğunu söyledi, ancak anahtardaki Knowledge Engine'in başlatılmadığı bilgisini vermedi.

| # | Puan | Hafıza kaynağı / not |
|---|---|---|
| 1 | hiç | Cevap yok. İlgili canonical kayıtlar `/remember` ve kabul edilmiş aday kaynaklarını içeriyor; ayrıca StateStore `source=user` bağlamı var. |
| 2 | hiç | Yalnızca araç çağrısı taslağı. İlgili canonical hafıza kayıtları elle `/remember` kaynaklı. |
| 3 | hiç | Yalnızca araç çağrısı taslağı. StateStore `source=user` bağlamı ve `source=worker` bir kayıt var; eldeki ReviewStore kayıtlarında bu worker kaydına bağlı bir kabul kararı doğrulanamadı. Bu nedenle kabul edilmiş aday olarak sayılmadı. |
| 4 | kısmen | Phase 20 / IG bilgisi doğru, Knowledge Engine durumu eksik. İlgili canonical kayıtlar hem `/remember` hem kabul edilmiş aday kaynaklı. |
| 5 | hiç | Yalnızca araç çağrısı taslağı. İlgili canonical hafıza kayıtları elle `/remember` kaynaklı. |

Provenance özeti: Q1 ve Q4 için hem elle `/remember` hem de kabul edilmiş aday kaynaklı kayıtlar bulundu; Q2 ve Q5 için `/remember` kayıtları bulundu. Q3'te kabul kararı eldeki kayıtlarla doğrulanamadı. StateStore kullanıcı kaynaklı girdileri canonical hafıza kökeninden ayrı tutuldu. Adaylarda kabul/ret işlemi yapılmadı.

#### İkinci koşu (ek talimatlı tekrar) — 2026-09-27

Yöntem farkı: aynı beş soru, her biri ayrı ve taze `claude -p "<soru> — Araç kullanma, komut çalıştırma; yalnızca oturum başında sana verilen bağlamla kısaca cevap ver. Bilmiyorsan 'bilmiyorum' de." --tools '' --strict-mcp-config` sürecinde soruldu. Her süreç için 120 saniye zaman aşımı uygulandı; beşi de zaman aşımına uğramadan tamamlandı.
Probe skoru: **5/5** (`IN_CONTEXT`). Gerçek skor: **1/5 tam doğru**; 3 kısmen, 0 yanlış, 1 hiç. Kısmi puanlar tam doğru toplamına eklenmedi.
Teslim makbuzu: Q1–Q5 oturumlarının her birinde Claude `SessionStart=DELIVERED`, `context_delivered=true`.

| # | Puan | Zaman aşımı | SessionStart makbuzu | Not |
|---|---|---|---|---|
| 1 | kısmen | hayır | `DELIVERED` (`context_delivered=true`) | Holdout kapısının korunmasını yakaladı; PRE-13 ertelemesi ve eşik/test kısıtı eksikti. |
| 2 | kısmen | hayır | `DELIVERED` (`context_delivered=true`) | `EVIDENCE_INVALID` ve 205/205 dead-letter nedenini yakaladı; boyut hipotezi ile bilinmeyen tipleri atlayıp sayma düzeltmesi eksikti. |
| 3 | hiç | hayır | `DELIVERED` (`context_delivered=true`) | Anahtar cevaptaki gerekçeler verilmedi. |
| 4 | kısmen | hayır | `DELIVERED` (`context_delivered=true`) | Phase 20 ve IG durumu doğru; Knowledge Engine’in başlatılmadığı bilgisi eksikti. |
| 5 | doğru | hayır | `DELIVERED` (`context_delivered=true`) | Anahtar cevabın üç noktası da vardı. |

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

## 2026-09-28 ölçüm yorumu (türetilmiş)

2026-09-27 ek talimatlı koşuda Q1, Q2 ve Q4 kısmen; Q3 hiç; Q5 doğru
puanlandı. Aynı koşu için beş cevap da `IN_CONTEXT` olarak ölçüldü ve beş SessionStart makbuzu da DELIVERED /
context_delivered=true kaydedildi. İçeriksiz kanıta göre dört eksik cevap,
yakalama/bağlam teslimi kaybı değil, teslim edilmiş bağlamdan beklenen cevabı
çıkarma başarısızlığı sınıfındadır. Ham cevap metni incelenmedi; bu yüzden
daha ince bir kök neden iddia edilmiyor.

Eski haftalık ölçüm çıktısı Claude CLI çıkış kodunu saklamadığından, bu koşunun
her oturumunu yeni ölçülebilirlik şartlarına göre geriye dönük doğrulamak mümkün
değil. Gelecek koşularda sıfır dışı CLI çıkışı, boş yanıt, timeout veya
DELIVERED olmayan makbuz oturumu puan dışı bırakır; yalnızca sayısal durum
saklanır. Eşik, holdout ve corpus değişmedi.

## 2026-09-30 — istem-zamanı hafıza ölçümü

Yöntem: `recall-probe` (resmî 5 soru ve yerel W39 soruları), gerçek `launcher.py` hook'u ile uçtan uca süre ölçümü.
Model cevabı puanlanmadı; bu, bağlamda cevap var mı ölçümüdür (IN_CONTEXT).

| Yol | Önce (2026-09-29) | Sonra |
|---|---|---|
| W39, SessionStart | 0/5 | 0/5 (değişmedi: 8 sabit kayıt) |
| W39, istem-zamanı | 0/5 (yerel modeller kapalı, V1 sırası) | 4/5 |
| Resmî 5, istem-zamanı | — | 4/5 |
| Resmî 5, SessionStart | 5/5 | 4/5 |

Kaçan W39 sorusu (1): cevap kaydı dikte dolgusuyla bozuk yakalanmış ("Dökümanları e, uzun bir süre…");
yeni yakalamalarda dolgular temizlenir, eski kayıt değişmedi. Hook süresi (yerel modeller açık): sürekli
çalışmada 60/60 teslim, p50 1.11 sn, maks 1.19 sn; servis yeniden başlarken ilk ~20 sn V1 sırası, üç
yeniden başlatmada 63 istemden 1 kayıp. Not: `recall-probe --mode prompt` PR #39'a kadar yeni süreçte
modelleri ısıtmadan ölçüyordu (V1 sırası); bu tarihten önceki istem-modu CLI sonuçları buna göre okunmalı.

## Gerçek kullanım puanları (2026-09-30'dan itibaren)

Yöntem: Brain-Eleven klasöründe yeni oturum, ilk mesaj doğrudan soru + "Dosyalara ve git'e bakma,
yalnız sana verilen bağlamdan cevapla; bilmiyorsan bilmiyorum de." Her soru ayrı oturum. Puanı
sahip verir (doğru / kısmen / yanlış / hiç). Bu, probe'dan farklı olarak cevabın kendisini ölçer.

| Tarih | Soru | Puan | Not |
|---|---|---|---|
| 2026-09-30 | Bandit subprocess bulgusu nasıl giderildi? (W39 Q4) | doğru | `nosec` kuralı, kapı değişmedi; bağlamda olmayan ayrıntıları (dosya, kural kodu) "bilmiyorum" diye ayırdı. İstem-zamanı bağlamı cevabın üç parçasını getirdi. |

