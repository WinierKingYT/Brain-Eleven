# Günlük kullanım kılavuzu

**Durum:** CURRENT operatör kılavuzu. Komutların nasıl kullanılacağını anlatır;
hiçbir eşiği, corpus'u, holdout'u, Phase 20 ya da V2 modunu değiştirmez ve yeni
paket açmaz. Runtime'ın kendisi için bkz. `../RUNTIME-DATAFLOW.md`.

Tüm komutlar Brain-Eleven klasöründe, projenin sanal ortamıyla çalışır
(Windows'ta `.venv\Scripts\python.exe`, aşağıda kısaca `python`).

## Her gün: tek bakış

```
python -m brain_eleven doctor
```

Önce `status` (`READY` / `ATTENTION`), sonra `suggestions` satırına bak. Öneriler
bir sonraki adımı söyler:

| Öneri | Ne yapılır |
|---|---|
| `... dead-lettered capture(s) are retryable` | `python -m brain_eleven worker --retry-dead-letter` |
| `last codex/claude capture was CWD_NOT_REGISTERED` | O oturum kayıtlı bir proje klasöründe açılmamış; proje kaydını ya da klasörü kontrol et |
| `... hook file ... is BOM` / `INVALID_JSON` | İstemci hiçbir hook'u çalıştırmıyor: `python -m brain_eleven install` dosyayı temiz yeniden yazar |
| `codex loads hooks from both hooks.json and config.toml` | Codex tek bir kaynak ister; `config.toml`'daki hook'u taşımayı değerlendir |
| `... review candidates pending` | İnceleme ekranında **Toplu temizlik** |
| `... committed review candidate(s) expire within 48h` | İnceleme ekranında karar ver ya da **7 gün daha sakla** |
| `recall score dropped ...` / `capture misses grew ...` | Son 7 günde gerileme var: `recall-probe` hangi sorunun düştüğünü gösterir |
| `no measurement yet` | `python -m brain_eleven measure` |

Diğer alanlar: `capture_queue` (bekleyen / işlenen / dead-letter, hata koduna
göre), `last_capture` (istemci başına son Stop sonucu), `clients.<ad>.file`
(hook dosyası istemcinin okuyabileceği durumda mı), `stale_memories`,
`last_measurement`, `measurement_trend` (son 7 günün ölçümleri: skor, capture sonucu, kayıp).

## Otomatik süzgeç

Alıntılar, kısa onaylar ("tamam", "evet"), zayıf kanıtlı düz metin ve terminal
çıktısı kuyruğa hiç girmez; yalnız sayıları `doctor` → `auto_triage`'da görünür
(metin tutulmaz). Kesin kararlar (`COMMITTED` + karar) hiçbir kurala takılmaz.
Kuyrukta bekleyenlere aynı kuralları uygulamak için:

```
python -m brain_eleven triage           # yalnız sayar
python -m brain_eleven triage --apply   # "Otomatik süzgeç: <kural>" notuyla reddeder
```

Kapatmak için runtime yapılandırmasında `"auto_triage": false`.

## Model ön değerlendirmesi

Bir model (ör. Codex / GPT Luna) bekleyen kararları okuyup
`.brain-eleven/runtime/review-suggestions.json` yazar (metin içermez; yalnız
`ACCEPT` / `REJECT` / `REVIEW` / `DUPLICATE_OF:<id>` ve neden kodu). Sonra:

```
python -m brain_eleven apply-suggestions           # yalnız sayar
python -m brain_eleven apply-suggestions --apply   # ACCEPT'leri hafızaya yazar
```

`ACCEPT` kararları "Model onayı (<model>): <neden>" notuyla yazılır; yanlışsa
"Eskimiş olabilir" / emekliye ayır ile geri alınır. `REJECT` ve `DUPLICATE`
yazılmaz: ekranda gizlenir, 7 gün içinde kendiliğinden düşer (yanılgı geri
alınabilir kalsın diye). `REVIEW` sana bırakılır.

## İnceleme ekranı

Öneriler değer sırasıyla gelir: kesin kararlar, hafızada benzeri olmayanlar ve
cümle uzunluğundakiler önce; hatırlama testi cevabı taşıyanlar en üstte. Ekran
varsayılan olarak günün en değerli 10 önerisini gösterir; **Tümünü göster**
hepsini açar. Kalanlar silinmez, 7 gün sonra kendiliğinden düşer.
**Görünen N öneriyi kabul et** listeyi tek tıkla (onay sorusuyla) kaydeder; her
öneri tek tek kabulle aynı yoldan geçer. Tarayıcısız hızlı bakış:
`python -m brain_eleven digest`.

```
python -m brain_eleven review
```

- **Toplu temizlik:** Neden / kesinlik / biçim seç, **Önizle** ile kaç öneri
  etkileneceğini ve örnekleri gör, emin olunca **Hepsini reddet**. Hiçbir şey
  silinmez; her rete `Toplu ret: <filtre>` notu yazılır.
- **Hızlı inceleme:** Tek öneriye odaklanır. `A` kabul (hedef seçiliyse yerine
  geçirir), `R` reddet, `D` tekrar olarak reddet, `J`/`→` sonraki, `K`/`←` önceki,
  `Esc` çıkış. Metin kutusunda yazarken kısayollar çalışmaz.
- **Kart:** Proje, istemci, söylendiği zaman, son gün, tür ve kesinlik, en benzer
  üç kayıt. `%60` üzeri benzerlikte **Tekrar olarak reddet** çıkar.
- **Konu anahtarı:** Benzer bir kaydın anahtarı önerilir; bir anahtar aktif bir
  kayıtta varsa kabul etmeden önce uyarı çıkar, o kayıt hedef seçilir ve düğme
  **Yerine geçir** olur.
- **Saklama:** Öneri metni 7 gün tutulur; son 48 saatte son gün kırmızı görünür.
  Son 3 günde ya da hatırlama cevabı taşıyan kartta **7 gün daha sakla** çıkar;
  toplam en fazla 30 gün. Otomatik uzatma yoktur.
- **Karar gerekçesi:** İsteğe bağlı, en fazla 280 karakter; sonuç kaydında kalır.
- **Eskimiş olabilir:** Söz ettiği dosya kayıttan sonra değişen ya da silinen
  kayıtlar. **Hâlâ geçerli** (dosya tekrar değişene kadar susar) ya da
  **Emekliye ayır** (kayıt `resolved` olur, bağlama girmez).

## Haftalık: ölçüm

```
python -m brain_eleven measure
```

Son kurulumdan bu yana (ya da `--since <ISO zaman>`):

- `capture.verdict`: `PASS` için 2+ proje, 20+ oturum, istemci başına 5+ oturum,
  kayıp (`missing`) ve kalıcı düşen (`dead_letter`) sıfır.
- `review_noise.created_since`: Nedene göre yeni öneriler; gürültü azaltma işe
  yarıyorsa `LOW_EVIDENCE_COMMITMENT` düşük kalır.
- `staleness`: Kontrol edilen dosya referansı ve eskimiş kayıt sayısı.
- `bootstrap`: Proje başına oturum başı bağlamında eski ve yeni seçimdeki tekrar
  ve eskimiş kayıt sayısı.

Sonuç `.brain-eleven/runtime/measurements/<zaman>.json` dosyasına da yazılır
(yalnız sayı ve kimlik, hafıza metni yok), ölçümler zamanla karşılaştırılabilir.

### Otomatik haftalık hatırlama kontrolü

PowerShell 7 ile depo kökünden çalıştır:

```
pwsh -NoProfile -File .\scripts\weekly_recall_check.ps1
```

Betik önce `measure` ve `recall-probe` komutlarını çalıştırır; ardından beş
soruyu beş ayrı, araçsız Claude oturumunda sorar. Her oturumun zaman aşımı
120 saniyedir. `.brain-eleven/runtime/measurements/weekly-<tarih>.json`
sadece sayısal probe bilgisi ve her soru için numara, cevap uzunluğu,
zaman aşımı ve `SessionStart` makbuz durumunu tutar; cevap metni yazılmaz.
Son satırdaki özet zamanlanmış görev günlüklerinde de kullanılabilir.

Windows Görev Zamanlayıcı'ya pazartesi 09.00 için görev eklemek üzere depo
kökünde tek komut örneği (kurulumu kendin çalıştır):

```
Register-ScheduledTask -TaskName 'Brain-Eleven Weekly Recall Check' -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At '9:00 AM') -Action (New-ScheduledTaskAction -Execute 'pwsh.exe' -Argument ('-WindowStyle Hidden -NoProfile -File "' + (Resolve-Path '.\scripts\weekly_recall_check.ps1').Path + '"'))
```

## Hatırlama: neden hatırlamadı?

```
python -m brain_eleven recall-probe
python -m brain_eleven bootstrap-explain
```

`recall-probe`, `TEST-LOG.md`'deki beş sorunun anahtar cevabının yeni bir oturumun
başında modele verilecek bağlamda olup olmadığını bakar (model çalıştırmaz):

- `IN_CONTEXT`: cevap bağlamda.
- `IN_MEMORY_NOT_DELIVERED`: kayıt hafızada ama seçilmedi; `why_not_delivered`
  nedeni söyler (ör. `SLOT_LIMIT`, `NEAR_DUPLICATE_OF:<id>`, `BELOW_POOL`).
- `IN_REVIEW_QUEUE`: kayıt hafızada yok ama bekleyen bir öneride var;
  `review_ids` o öneriyi gösterir. İnceleme ekranında bu öneriler
  **Hatırlama testi #N** etiketiyle en üstte çıkar; kabul etmek yeterli.
  `split: true` ise cevabın parçaları birden çok öneride; listedeki hepsini
  kabul et (skor yalnız bağlamdakini sayar, kabulden sonra yeniden bak).
- `NOT_IN_MEMORY`: ne hafızada ne bekleyen önerilerde var; oturum yakalanmamış
  ya da önerinin süresi dolmuş/reddedilmiş (metni silinir). Bilgiyi bir kez
  `/remember` ile kaydet.

`bootstrap-explain`, projedeki her aktif kaydın bağlama neden girip girmediğini
listeler. Bu bir yaklaşık ölçümdür; asıl test yine taze oturumda sorulan sorudur.
`measure` çıktısı da `recall_probe` skorunu içerir.

## Eski konuşmaları yeniden tara

```
python -m brain_eleven backfill                 # yalnız sayar
python -m brain_eleven backfill --apply         # inceleme kuyruğuna ekler
python -m brain_eleven backfill --apply --reoffer-expired
```

Çıkarıcı iyileştikçe (Türkçe karar kalıpları, onayladığın asistan önerileri)
son 14 günün (`--days`) transcript'leri yeni kurallarla yeniden okunur. Hiçbir
şey doğrudan hafızaya yazılmaz; öneriler **BACKFILL** nedeniyle inceleme
ekranına gelir. Kabul ettiğin ya da reddettiğin bir öneri geri gelmez. Karar
vermeden 7 günü dolan öneriler yalnız `--reoffer-expired` ile yeniden sunulur.
Sonra `recall-probe` ile `NOT_IN_MEMORY` cevapların `IN_REVIEW_QUEUE` olup
olmadığına bak.

## Güncellemeden sonra

```
git pull
python -m brain_eleven install
python -c "from brain_eleven.runtime.launcher import request_service; print(request_service('.', '/api/runtime/stop', {}))"
```

`install` hook komutlarını yeniden yazar (Codex yeni komuta tekrar güven
isteyebilir); son satır eski kodla çalışan worker servisini durdurur, ilk hook
yeni kodla yeniden başlatır.

## Windows notları

- PowerShell 5.1'de hook dosyalarını `Set-Content -Encoding utf8` ile yazma: dosya
  başına BOM ekler ve Codex bütün hook'ları sessizce bırakır. Dosyayı elle
  düzeltmek yerine `install` kullan.
- Codex hook komutu kabuktan bağımsız yazılır (yolda boşluk yoksa); bir hook'un
  gerçekten çalıştığını `doctor` içindeki `last_capture` gösterir.
