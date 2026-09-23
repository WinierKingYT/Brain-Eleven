# MEMCLAIM-01 — Aynı konudaki eski hafızanın sessizce aktif kalmaması

**Durum: R1 IMPLEMENTED — bağımsız inceleme (REVISE) bulguları işlendi; sahip onayıyla
uygulamaya açıldı, 2026-09-23.** Kaynak: `docs/ORVANT-CLEANROOM-ANALYSIS.md` §5
(Orvant O-11 "konu başına tek etkin karar" fikrinin temiz oda uyarlaması;
Orvant'tan kod alınmaz).

## Intake kuralı cevabı

**Evet, doğrudan — aynı hata sınıfı için.** Hatırlama testinde
(`docs/history/evidence/TEST-LOG.md`, 2026-09-23) gözlenen tek "çelişki" hatası:
taze oturum hem `mem_83f4ae0a…` ("SRT-00 remains NOT SHIP") hem güncel durumu gördü,
hangisinin güncel olduğunu bilemedi; kayıt elle `superseded` yapıldı. Bu paket o
olayı geriye dönük düzeltmez. Aynı sınıftaki bir sonraki çelişkinin kabul anında
görünür olmasını ve olay tarihinin doğru kaydedilmesini hedefler.

Hiçbir eşik, korpus, holdout, Phase 20 veya V2 modu değişmez. SHADOW kalır.

## Kanıt: bugünkü davranış

1. `scripts/memory_truth.py:500` aynı `claim_key`'e sahip aktif hafıza varsa
   `CONFLICT / ACTIVE_CLAIM_KEY_CONFLICT` döndürür. Bu canlı yoldur:
   `brain_eleven/memory/truth.py` aynı modülü yükleyen uyumluluk katmanıdır,
   runtime worker onu çağırır. **Mekanizma ölü:** 61 canonical kaydın hiçbirinde
   `claim_key` dolu değil.
2. **Asıl engel:** `brain_eleven/runtime/worker.py:72-74`
   (`_memory_candidate_values`) truth motoruna yalnız 8 alanlık bir izin listesi
   geçirir. `claim_key` ve `occurred_at` bu listede yok. Çıkarım adımı
   `occurred_at`'ı zaten üretiyor (`worker.py:828-829`), ama bu liste onu siliyor.
   `scripts/memory_truth.py:510` (`timestamp = occurred_at or now`) bu yüzden
   hep kabul anını yazıyor. SRT-00 kaydının 09-20/21 yerine 09-23 tarihini
   taşımasının nedeni budur.
3. İki SRT-00 kaydı da `source: worker`, yani inceleme kuyruğundan insan
   onayıyla geldi. Bu yolda `claim_key`'i atayabilecek bir yer yok.
4. Çakışmada `review_action` `DEGRADED` döndürür ve kabul niyetini temizler
   (`brain_eleven/runtime/service.py:73-75`). Yeniden deneme mümkündür ama
   arayüz yalnız "İşlem tamamlanmadı: DEGRADED" gösterir; hangi kayıtla
   çakıştığını söylemez. Mevcut "değiştirilecek kayıt" seçimi
   (`ui/review.js`, `targets`) supersede için zaten vardır.
5. `_new_record` `evidence_refs`'i canonical kayda yazmaz.
6. `MemoryStore._validate_record` kapalı anahtar kümesi dayatmaz.
   `tests/` içinde canonical kayıt anahtar kümesini birebir sabitleyen test yok.

## Değişiklik

- **C0 — İzin listesi hatası.** `_memory_candidate_values` `claim_key` ve
  `occurred_at`'ı da geçirir. Bu tek başına tarih hatasını düzeltir.
- **C1 — `claim_key` insan onayında belirlenir (sahip kararı).** Kabul isteği
  isteğe bağlı `claim_key` alır. İnceleme sayfası bir metin alanı ve projedeki
  mevcut aktif anahtarları öneri listesi olarak gösterir. Böylece aynı konu için
  aynı anahtarın yeniden kullanılması kolaylaşır; anahtarı model uydurmaz.
  - Biçim: küçük harf; `konu.özellik` veya `konu:özellik` (ör.
    `srt-00.ship-status`); en fazla 80 karakter.
  - İnsan geçersiz anahtar girerse kabul reddedilir ve açık hata verilir.
  - Başka bir kaynaktan (ör. model) gelen geçersiz anahtar truth sınırında
    boşaltılır. Aday reddedilmez; kayda `issues: ["CLAIM_KEY_INVALID"]` yazılır.
- **C2 — Çatışma otomatik çözülmez.** Aynı anahtarla aktif kayıt varsa sonuç
  `CONFLICT` olur ve hiçbir şey yazılmaz. Kabul yanıtına çakışan kaydın kimliği,
  metni ve tarihi eklenir. Metin, `targets` ile aynı güvenlik süzgecinden geçer.
  Arayüz bunu gösterir ve çakışan kaydı "değiştirilecek kayıt" olarak önceden
  seçer. İnsan tekrar kabul ederse mevcut `SUPERSEDE_EXISTING` yolu çalışır.
  Açık supersede sırasında hedef dışında aynı anahtara sahip başka bir aktif kayıt
  varsa sonuç yine `CONFLICT` olur. Ajan veya model kendi başına supersede etmez.
- **C3 — Olay zamanı.** `occurred_at` geçerli bir ISO-8601 değeriyse (saat
  dilimli zaman veya `YYYY-MM-DD`) canonical kayda ayrı alan olarak yazılır ve
  mevcut `timestamp = occurred_at or now` kuralı değişmeden çalışır. Geçersiz
  değer boşaltılır ve `issues: ["OCCURRED_AT_INVALID"]` yazılır. Retrieval
  puanlama formülü değişmez.
- **C4 — Dayanak izi.** `evidence_refs` canonical kayda liste olarak yazılır.
  Yalnız opak kimlikler kabul edilir: `^[A-Za-z0-9_:.-]{1,128}$`, yani yol
  ayırıcı, boşluk veya metin içermez. Uymayan kimlik kayda yazılmaz ve
  `issues: ["EVIDENCE_REF_DROPPED"]` eklenir. Doğruluk iddiası değildir.

## Kapsam dışı (RETHINK sebebi)

- Dosya parmak iziyle otomatik eskime (analizdeki Aday A).
- Mevcut 61 kayda geriye dönük `claim_key` atanması (ayrı, insan onaylı iş).
- Model/çıkarım şemasının `claim_key` üretmesi (anahtarı insan belirler).
- Retrieval puanlaması, holdout, V2 teslim yolu, mod değişikliği, anlamsal çelişki tespiti.

## Kabul ölçütleri (önce test)

1. C0: Worker yolundan geçen `occurred_at` canonical `timestamp` ve
   `occurred_at` alanlarına yazılır; `claim_key` motora ulaşır.
2. C1: Kabulde verilen geçerli `claim_key` kayda yazılır. Geçersiz biçim
   `ValueError` ile reddedilir ve hiçbir şey yazılmaz. Truth sınırında gelen
   geçersiz anahtar boşaltılır ve `issues`'a yazılır.
3. C2 yeniden oynatma (09-23 SRT-00 yapısında iki aday): ikinci aday aynı
   anahtarla kabul edilince `DEGRADED` + `conflict` döner, iki kayıt aynı anda
   aktif olmaz, niyet temizlenir. Çakışan kayıt hedef seçilerek tekrar kabul
   edilince eski kayıt `superseded`, yeni kayıt aynı anahtarla `active` olur.
4. C2: Açık supersede, hedef dışındaki aynı anahtarlı aktif kaydı gözden kaçırmaz.
5. C3: Geçersiz `occurred_at` boşaltılır ve `issues`'a yazılır; `YYYY-MM-DD` ve
   saat dilimli zaman kabul edilir.
6. C4: Opak kimlikler kayda yazılır; yol veya boşluk içeren kimlik düşürülür.
7. Aday listesi projedeki aktif `claim_key`'leri döndürür.
8. Mevcut `tests/test_memory_truth.py`, `tests/test_w24_memory_truth_safety.py`,
   `tests/test_shadow_accept.py` ve tam paket yeşil kalır.

## Ölçüm

Uygulamadan sonra TEST-LOG protokolüyle yeni bir soru sorulur. Başarı: cevap tek
ve güncel, oturum çelişki bildirmiyor. n küçük olduğu için bu, program çapında
bir sayı değildir.

## Uygulama kanıtı (2026-09-24, commit edilmedi)

- Değişen dosyalar:
  - `scripts/memory_truth.py`: normalizasyon, açık supersede çakışma kontrolü, yeni kayıt alanları.
  - `brain_eleven/memory/truth.py`: `normalize_claim_key` dışa açıldı.
  - `brain_eleven/runtime/worker.py`: C0.
  - `brain_eleven/runtime/service.py`: kabulde `claim_key`, `conflict` yanıtı, `claim_keys` listesi.
  - `brain_eleven/runtime/ui/review.js`, `review.css`: anahtar alanı ve çakışma mesajı.
- Test: `tests/test_memclaim01_claim_key.py`, 19 test. Önce 19'u da kırmızıydı,
  uygulamadan sonra 19'u da yeşil.
- Tasarım düzeltmesi: normalizasyon sorunları önce `TruthCandidate` üzerinde bir
  alan olarak tutuldu. Bu, W-24'ün aday yapısını ve istek özetini sabitleyen
  korumasını kırdı. Sorunlar bu yüzden tarihsel yapının dışındaki özel
  `_CandidateEnvelope.issues` alanına taşındı.
- Etkilenen paketler (truth, W-24, shadow-accept, provenance, IG-04 B1/B2,
  PRE-13 runtime, IG-03): 168 geçti.
- Tam paket: 1591 geçti, 4 atlandı, 5 başarısız. Beşi de
  `tests/test_w06c0r1_contract.py` kapsam korumasıdır ve HEAD'e göre commit
  edilmemiş diff'i reddeder (`evals/w06c0r1/evaluation.py:504-505`). Temiz HEAD
  worktree'sinde aynı dosyadaki 23 testin hepsi geçti. TSC-03 raporundaki
  durumla aynıdır. Commit sonrası tekrar çalıştırılıp teyit edilmelidir.
- Bilinen sınır: Worker artık `occurred_at`'ı geçirdiği için istek özeti
  değişti. Bu değişiklikten önce yarıda kalmış bir kabul niyeti (çökme
  kurtarması) veya CANARY/ACTIVE otomatik yolunda aynı adayın tekrarı
  `OPERATION_REPLAY_MISMATCH` alabilir. SHADOW'da ve bekleyen niyet yoksa etkisi
  yoktur.
- Mevcut 61 canonical kayıt değiştirilmedi.

## Bağımsız inceleme R0 → R1 izi

R0 kararı REVISE. İşlenen bulgular:
- BLOCKER izin listesi → C0.
- HIGH worker yolu ve anahtar tutarlılığı → C1, insan belirler ve öneri listesi
  gösterilir.
- HIGH karşılaştırma ekranı yok → C2 yeni iş olarak tanımlandı; mevcut hedef
  seçimi yeniden kullanılır.
- MEDIUM kapalı şema testi yok → Kanıt 6.
- MEDIUM opak kimlik kısıtı → C4.
- LOW intake cevabı → "aynı hata sınıfı" olarak daraltıldı.
