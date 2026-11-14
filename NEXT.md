# Durum ve sıradaki işler

Tek durum dosyası. Her oturum sonunda en üste 2–3 satır eklenir; eskiyen
satırlar silinir. Kontrat, rapor ya da inceleme dosyası açılmaz.

## Şu an (2026-11-14)

- **v1.4 kapandı (PR #106–#108): ölçebilir hale getir.** Hatırlama sınaması yeni
  beş soruyla ve `map` profilini anlayarak çalışıyor (oturum başı 0/5 puan + 5/5
  konu notunda, `--mode prompt` 5/5). 80 bekleyen aday ayıklandı: 17 sohbetten
  onaylandı (deneme süresinde), 4 ders temiz metinle yeniden kaydedildi, gerisi
  reddedildi; kuyruk 0, etkin kayıt 87 → 108, hepsi konulu. Eski kurulum betiği
  silindi. Ölçüm: testler 1347 geçti, 0 kırmızı; `doctor` READY. Ölçülmeyen: ajanın `map` profilinde doğru notu gerçekten açtığı;
  `normal` profilde oturum başı; `/remember` ve `/study` eğik çizgi komutu olarak.
- **v1.3 kapandı (PR #102–#104): Obsidian'dan oku.** Kayıtlar konu taşıyor, her
  konunun kısa bir notu var, `profile map` oturum başında kayıt metni yerine konu
  listesi veriyor (Brain-Eleven'da 2.301 → 581 karakter). Gerçek kurulum `map`
  profilinde. Sahibin onayıyla 13 eski dönem kaydı iptal edildi (etkin 100 → 87).
  Ölçüm: testler 1361 geçti, 0 kırmızı; `doctor` READY. `recall-probe` artık bir şey
  ölçmüyor: oturum başı 4/5 → 0/5, `--mode prompt` 5/5 → 1/5. Neden: beş sorunun
  üçünün yanıtı iptal edilen kayıtlardı (`NOT_IN_MEMORY`) ve `map` profili oturum
  başında kayıt metni vermiyor. Sorular sahibin yazdığı sorular; yenilenmeden
  sınama hatırlamanın bozulup bozulmadığını söyleyemez.
- **v1.2 kapandı (PR #97–#100): adaylar boşa gitmesin.** `decide` ile adaylar
  sohbetten onaylanıyor (kayıt deneme süresinde kalır); oturum başı hafıza yeri
  8 → 12; `install` `/remember` ve `/study`'yi de kuruyor; Codex yakalamasında
  hata yok, `doctor` önerileri nedenini söylüyor. Ölçüm: testler 1356 geçti, 0
  kırmızı; `recall-probe` oturum başı 2/5 → 4/5; `--mode prompt` güncelleme
  öncesi servisle 5/5 (yeni kodla güncellemeden sonra ölçülecek). Onay yükünün
  sonrası ölçümü bir hafta kullanım ister (başlangıç: bakılmadan düşen 164).
- **v1.1 kapandı (PR #90–#94): yakalama güvenilir.** Alt klasör/worktree
  oturumları yakalanıyor, süzgece takılan aday oturumu düşürmüyor, Ctrl+Alt+B
  hatası görünür, iki ölü betik gitti, `close-milestone` eski durum satırını
  kapattı. Ölçüm: testler 1354 geçti, 0 kırmızı; `doctor` READY; `recall-probe`
  önce/sonra aynı (oturum başı 2/5 `SLOT_LIMIT`, `--mode prompt` 5/5). Ölü
  mektup 50 → 32 (kalanların dökümü yok, kurtarılamaz).
- **Güvenlik süzgecine takılan aday artık oturumu düşürmüyor.** 18
  `REVIEW_PERSIST_FAILED` ölü mektubunun hepsi tek nedendi: 80 satırı aşan bir
  kullanıcı mesajı (`too_many_lines`). Ret kalıcı olduğu için iş 3 kez düşüp
  oturumun tüm adaylarını kaybediyordu. Şimdi ret `UNSAFE_*` koduyla
  `auto-triage` sayacına (doctor) yazılır, metin yazılmaz; gerçek yazım hatası
  yine yeniden denenir. Kurtarma: `worker --retry-dead-letter` artık bu kodu
  da kapsıyor (18 dökümün hepsi duruyor; sahip çalıştıracak).
- **Alt klasör ve worktree oturumları yakalanıyor.** Kayıtlı bir kökün altındaki
  cwd (ör. `tests/`, `.claude/worktrees/…`) en yakın kayıtlı köke çözülür; yakalama,
  bağlam ve döküm sahipliği o projeyi görür. Sınır: kökün dışındaki worktree'ler.
- **v1.0: sadeleştirme (PR #79–#89).** Gölgedeki V2 bağlam derleyicisi (beş
  paket, ~6.500 satır) canlı yolda çalışmıyordu, silindi; kullandığı tek
  bayatlık kontrolü `context.py` içinde `_inputs_current` oldu. Canlı kod
  `scripts/`'ten `brain_eleven/` altına taşındı, `_legacy.py` köprüsü, 15 ince
  adaptör ve 5 ölü betik gitti; `scripts/`'te kalan her dosya ARCHITECTURE.md'de
  yazılı. Docker/Postgres/Redis ve `search-api.py` kullanılmıyordu, kaldırıldı
  (`redis`, `python-dotenv`, `defusedxml` bağımlılıkları da).
- **v1.0: ölçümler.** Testler 1637 → 1327 geçti, 0 kırmızı (gidenler silinen
  kodun testleri). `recall-probe` önce/sonra aynı: oturum başı 2/5 (üç yanıt
  hafızada ama 8 yere sığmıyor: `SLOT_LIMIT`), `--mode prompt` 5/5. Servis istem
  başına bağlam süresi ortanca 460 ms → 430 ms, en çok 491 → 505 ms (20 istek,
  sıcak servis, tekrar eden 5 soru).
- **v1.0: sürüm ve kurulum.** `kur.ps1` kurulumu, `-Guncelle` ile güncellemeyi
  tek komuta indirir ve eski servisi durdurur (`install` servisi yeniden
  başlatmıyor; servis eski kodu boşta 4 saate kadar tutuyordu). `v*` etiketi
  itilince `release.yml` testleri çalıştırır, kaynak arşivini ve `SHA256SUMS`'ı
  sürüme ekler. Gerçek Windows kurulumunda `doctor` READY. İlk Ctrl+Alt+B
  denemesinde `yakala pano` 64 bit pano tutamacında sessizce çöküyordu; düzeltildi.
- **v1.0: vault.** `Jane - Core.md` arşiv olarak işaretlendi (silinmedi);
  sahibin profili `Core.md`.
- **`why` (PR #78).** `why <mem_id>`: hafızanın içeriği, durumu, sahip onayı ve
  her kanıtı için rol ve asıl mesaj. Kanıt yalnız hash tuttuğu için döküm,
  güvenilen köklerde yol hash'iyle bulunur ve bayt aralığı normal okuyucuyla
  yeniden okunur; alıntı yalnız evidence id birebir tutarsa gösterilir
  (değişmiş dosya `SOURCE_CHANGED`, silinmiş `SOURCE_DELETED`). `doctor`
  artık Claude'un döküm saklama süresini (`cleanupPeriodDays`, varsayılan 30)
  gösterir ve 90 günden azsa önerir; ayarı değiştirmez. TencentDB
  araştırmasının tek "alınmalı" maddesi buydu; diğerleri ertelendi ya da
  gereksiz bulundu (proxy gerektiren offload, ekip odaklı asset/ACL).
- **Yakala (PR #77, Windows kısayolu denenmedi).** `yakala ekle <URL|dosya|metin>`
  `📥 Gelen/` altına bekleyen öğe yazar (sır reddedilir, dosyalar `Ekler/`e
  kopyalanır). `yakala kur` Windows'ta Başlat Menüsü'ne `Ctrl+Alt+B` kısayolu
  ekler (panodakini atar; dinleyici yok). `beyin-yakala` skill'i öğeleri okuyup
  `🧠 Bilgi/` notlarına çevirir, içeriği güvenilmeyen veri sayar, `yakala bitti`
  ile işaretler. Obsidian Web Clipper şablonu: `templates/obsidian/beyne-at.json`.
  Açık: kısayolun gerçek Windows'ta denenmesi; YouTube transkripti ajanın kendi
  araçlarına bağlı.
- **İş sonucu kayıtları (PR #76).** `receipt "<ne bitti>" --next … --source …`:
  ajan anlamlı bir iş bitince kısa, kaynaklı bir sonuç bırakır (beyin skill'i
  söyler). Kayıtlar değişmez, aynısı tekrar gönderilirse kopya oluşmaz; tam
  dosya yolu ve sır reddedilir. Proje notunda "Son iş sonuçları", SessionStart'ta
  son 3 sonuç, `recap`'te projenin ilk bölümü olarak görünür. Kanonik hafıza
  değildir, ajanın iddiasıdır.
- **Seni tanıma (PR #75).** `🔮 Companion/Core.md` (sahip kim, nasıl
  çalışılır) ve `Kurallar.md` (sahibin düzeltmeleri: kural + neden) proje
  bağımsız; her SessionStart bağlamı bunlarla açılır, sonra oturum kartları,
  sonra hafıza. "Nerede kalmıştık / beni tanıyor musun" türü istemlerde de
  eklenir (avenoxbeyin'in kalıbı). `install` iki başlangıç notunu bir kez
  oluşturur, var olanı ezmez; boşken ajana doldurma talimatı gider. Claude'a
  giden bağlam 9500 karakterde satır sınırında kesilir (baş kısım korunur).
- **Skill üçlüsü (PR #74).** `install` `~/.claude/skills/` altına `beyin`,
  `beyin-doktor`, `beyin-guncelle` yazar (Python ve vault yolu doldurulmuş).
  Sahibin değiştirdiği ya da başka kaynaktan gelen aynı adlı dosya ezilmez;
  `uninstall` yalnız kendi yazdığı, değişmemiş dosyaları siler. Güncelleme
  skill'i git tabanlı: yalnız `pull --ff-only`, yerel değişiklik varsa durur.
- **Hafıza notları (PR #73).** `🔮 Companion/Hafıza/<proje>.md` ve `Genel.md`:
  aktif hafızalar türlerine göre (Kararlar, Dersler, …), id ve tarihle. Servis
  hafıza revizyonu değişince en çok 30 sn'de bir yeniler; `notes` hemen yazar.
  Notlar türetilmiş görünüm: elle düzenleme hafızaya geri yazılmaz. "Markdown
  kaynak" yönü (notu düzenleyip hafızayı değiştirmek) hâlâ açık.
- **Tüketim modları (PR #72).** `profile normal|economical|manual`. Normal:
  oturum başı + her istem (eskisi gibi). Ekonomik: yalnız oturum başı, en çok
  2000 karakter; alt ajana 1000 karakter; istemlerde hiçbir şey derlenmez.
  Manuel: hiçbir bağlam eklenmez. Yakalama her modda sürer. Oturum kartları
  artık bağlamın başında, kısaltmada ilk onlar kalır.
- **`recap` (PR #71).** `recap --days 7` (ya da `--since/--until`, `--project`)
  oturum kartlarından ve o aralıkta yazılmış aktif hafızalardan Markdown liste
  basar. Model çağırmaz, döküm okumaz. Arşive taşınmış kartlar listelenmez.
- **Oturum kartları ve açık konular (PR #70).** Her yakalanan oturum, proje
  notunda (`🔮 Companion/Oturumlar/<proje>.md`) kısa bir kart tutuyor: ilk ve
  son istek, son yanıt, özetten sıradaki adım. Notun üstünde StateStore'daki
  açık konular var. Kart bölümü 3000 karakteri aşınca en eski kartlar
  kelimesi kelimesine `🔮 Companion/Arşiv/` altına taşınıyor. SessionStart son
  iki kartı bağlama ekliyor. Model çağrısı yok. Repodaki eski proje hook'ları
  (bayat "Last Session" basan `session-start.sh` vb.) kaldırıldı.
- **Alt ajan desteği (PR #69).** `SubagentStart` hook'u her alt ajana proje
  hafızasını (en çok 2500 karakter) ve raporunun sonuna
  `### Brain-Eleven bulguları` başlığıyla kalıcı bulgularını yazma talimatını
  veriyor. Ana dökümdeki rapor (ön plan araç sonucu ya da arka plan dönüşü)
  `subagent` rolüyle okunuyor; yalnız o başlığın maddeleri aday oluyor ve
  her zaman incelemeye düşüyor. Codex'te alt ajan hook'u yok. Sınır: alt
  ajanın raporuna yazmadığı ara bilgi hâlâ yakalanmıyor (alt ajan dökümleri
  okunmuyor). Kurulumda yeni hook için `install` yeniden çalıştırılmalı.
- **Büyük temizlik yapıldı.** 300'den fazla süreç belgesi, kontrat ve rapor;
  IG/PRE-13 eval korpusları; holdout ve graduation kalite kapıları; her
  istemde çalışan baseline karşılaştırması; ölü betikler ve bunların testleri
  kaldırıldı. Eski hali `pre-cleanup` etiketinde duruyor.
- Testler: 1563 geçti, 0 kırmızı (eskiden 15 kalıcı kırmızı vardı).
- `rollout ACTIVE` artık kapısız. Gerçek kurulum `SHADOW` + `shadow_recall`
  ile çalışıyordu; `rollout ACTIVE` ile normal moda geçilebilir.
  `approval ON` açık kaldıkça her hafıza yine onaydan geçer.
- Çalışan kısım: ana oturum yakalama, istem anında hatırlama (resmî 5/5,
  401 kayıtta 9/10), projeler arası referans, deneme süresi, `/study`.

## Sıradaki işler: v1.5 (onaylandı 2026-11-14) — proje, ajanın bağlam penceresi olsun

Hedef: yapılan iş ve öğrenilen bilgi sıkıştırmadan (compaction) sonra da
kalsın; yeni ajana aynı şey yeniden öğretilmesin. Başarı ölçüsü: gerçek bir
sıkıştırmadan sonra "neredeyiz, sırada ne var" sorusu yalnız kayıtlardan
yanıtlanabilsin.

1. **Sıkıştırma özeti oturum kartına.** Özetin "yapılan / yarım kalan / karar"
   kısımları karta girer (bugün yalnız "sıradaki adım", 200 karakter). Onay
   istemez, sır süzgecinden geçer.
2. **Sıkıştırmadan sonra oturum kendi kartını geri alsın.** Önce yeniden üret:
   "kendi kartı dışarıda bırakılıyor" bulgusu yalnız kod okumasından.
3. **Her alt ajan raporu projenin altına iş kaydı olarak.** Hafıza değil,
   "ajanın kaydı" etiketiyle. Çerçeve metni sızıntısının düzeltmesi burada.
4. **Oturum başı = durum.** Neredeyiz → açık işler → konu haritası; önce ölç.
5. **Model karnesi.** Bir modelin tekrarlayan hataları sayılarıyla genel konu
   notunda; onaydan geçer.
6. **Skill'ler "neden" notuna bağlansın.**
7. **`/orchestrate` sonuçlarını Brain-Eleven'a yazsın, karneyi okusun.** Skill
   depo dışında: doğrudan dosya düzenlemesi, başlamadan gösterilir. Gerçek uçtan
   uca deneme en sonda.

## v1.4 maddeleri (kapandı 2026-11-14) — ölçebilir hale getir

1. ~~Hatırlama sınamasının sorularını yenile.~~ **Yapıldı (sahip onayı 2026-11-14).**
   Beş sorudan biri eskisinden kaldı; dördü güncel kayıtlardan. Gerçek kurulumda
   (`map` profili): oturum başı 0/5 puan + 5/5 konu notunda, `--mode prompt` 5/5.
   `normal` profilde oturum başı ölçülmedi.
2. ~~Sınama harita profilini anlasın.~~ **Yapıldı.** `map` profilinde yanıtı tutan
   kaydın konusu oturum başındaki listede ise durum `IN_TOPIC_NOTE` (bir okuma
   uzakta); ayrı sayılır, puana girmez. Eski beş soruda oturum başı 0/5, biri konu notunda
   (üçünün yanıtı hafızada değil); taslak beş soruda oturum başı 0/5 puan + 5/5 konu notunda,
   `--mode prompt` 5/5. Sınır: taslak sorular var olan kayıtlardan seçildi, yani
   kolay; ajanın notu gerçekten açtığını ölçmez.
3. ~~Bekleyen adayları ayıkla.~~ **Yapıldı (2026-11-14).** 80 adayı Sonnet
   ayıkladı, orkestratör denetledi: 17'si `decide` ile sohbetten onaylandı (ilk
   gerçek deneme; 14 günlük deneme süresinde), 63'ü reddedildi. Bulunan hata:
   alt ajan teslim çerçevesinin metni 9 adayın içine sızmıştı; değerli dördü
   kirli haliyle kabul edilmedi, `remember.py` ile temiz yazıldı (bu yol kaydı
   doğrudan onaylı yazar, deneme süresi yok). Sızıntının düzeltmesi v1.5 madde 3.
4. ~~Eski kurulum betiğini sil.~~ **Yapıldı.** `install-cross-project-memory.py`,
   yalnız onun kurduğu hook ve `legacy` şablonları ve testleri silindi.
   `context-compiler.py` ve `remember_opt_in.py` kaldı: eski kurulumlarda duran
   hook dosyaları hâlâ onları çağırabilir.

## v1.3 maddeleri (kapandı 2026-11-13) — Obsidian'dan oku

Ölçüm (2026-11-11): 100 etkin kayıt, hiçbiri konu taşımıyordu. Bölmeden harita
kazandırmıyor: kayıt başına 60 karakterlik başlıkla harita 1.716 karakter
(bugünkü oturum başı 2.301), tek ayrıntı için notun tamamı (+6.319) okunuyor.

1. ~~Konu alanı.~~ **Yapıldı.** Kayıtta `topic` alanı; `topic` komutu listeler ve
   atar, `decide --topic` onaylananı konuya bağlar. Yalnız gruplar; içerik,
   durum ve onay değişmez. Sınır: yerine yenisi yazılan (supersede) kayıt konuyu
   devralmıyor.
2. ~~Mevcut 100 kaydı konulandır.~~ **Yapıldı (2026-11-12).** Sahibin sohbetteki
   onayıyla 100 kaydın tamamı 20 konuya ayrıldı (5 grup).
3. ~~Konu notları.~~ **Yapıldı.** Konusu olan kayıt `Hafıza/<proje>/<konu>.md`
   notunda; proje notu **Konular** başlığıyla harita. Gerçek boylar: harita
   299–654, konu notu 1.133–3.618 karakter. Konular arası bağlantı yok.
4. ~~Konu haritası.~~ **Yapıldı, seçilebilir.** `profile map`: oturum başında kayıt
   metni yerine konu listesi (Brain-Eleven'da 2.301 → 581 karakter, 797 → 198
   token tahmini); istem anı hatırlama aynen. Varsayılan `normal` değişmedi,
   `recall-probe`'a dokunulmadı. Sınır: bu profilde sahip bildirimi satırı yok.
5. **Ölçüm.** Ertelendi (sahip kararı 2026-11-13). Oturum başı kısmı madde 4'te
   ölçüldü; ajanın not açınca toplam ne harcadığı gerçek kullanım ister.

## v1.2 maddeleri (kapandı 2026-11-11) — adaylar boşa gitmesin

1. ~~Onay yükünü azalt.~~ **Yapıldı.** Ölçüm: süresi dolan 1.172 adayın 828'i
   zaten gürültü/tekrar işaretliydi; gerçek kayıp "sahibi baksın" denip
   bakılmayan 164 (180'i hiç değerlendirilmemiş). `digest` vardı, eksik olan
   onay yoluydu: `decide --accept/--reject` sahibin sohbetteki sözünü uygular
   (`beyin` skill'i adayları sohbette gösterir). Bu yolla yazılan kayıt
   "Sohbetten onay" notunu taşır ve deneme süresinde kalır. Başarı ölçüsü: bir
   hafta sonra süresi dolan "sahibi baksın" adayı sayısı.
2. ~~Oturum başı hatırlamayı düzelt.~~ **Yapıldı.** Oturum başı yer sayısı 8 → 12
   (sahip kararı). `recall-probe` oturum başı 2/5 → 4/5, `--mode prompt` 5/5
   (değişmedi). Kalan tek yanıt (SRT-00) `stale_candidate` işaretli olduğu için
   bilerek arkada. Not: beş test sorusu eski döneme ait; yenilemek sahibin kararı.
3. **`/remember` ve `/study` kurulumu.** `install` artık iki komutu da
   `~/.claude/commands/` altına yazıyor; eski kurulumun kopyasını (manifestindeki
   özetle tanıyıp) devralıyor, sahibin değiştirdiği dosyaya dokunmuyor. Kalan:
   `install-cross-project-memory.py`, yalnız onun kullandığı hook şablonları ve
   testlerinin silinmesi (sahip onayı).
4. ~~Codex yakalaması.~~ **İncelendi, hata yok.** Son 40 Codex oturumunun hepsi
   kayıtlı olmayan klasörlerde açılmış; `CWD_NOT_REGISTERED` doğru sonuç
   (yakalanması istenen klasör için `project add`). Çift hook uyarısındaki
   `config.toml` girdisi Brain-Eleven'ın değil, başka bir aracın. `doctor`
   önerileri artık ikisini de böyle açıklıyor.

## v1.1 maddeleri (kapandı 2026-11-11) — yakalamayı güvenilir yap

1. ~~Sessiz hataları görünür yap.~~ **Yapıldı.** Ctrl+Alt+B (`yakala pano`)
   başarısız olunca içeriksiz bir kod kaydediliyor (`EMPTY`, `SECRET`,
   `TOO_LONG`, `FILE_TOO_LARGE` ya da hata sınıfının adı); `yakala liste`
   `son_deneme`, `doctor` `last_yakala` ve bir öneri satırı gösteriyor.
2. **Ölü mektup kuyruğu.** 18 `REVIEW_PERSIST_FAILED` işi gerçek kurulumda
   yeniden kuyruğa alındı (2026-11-11) ve yeni kodla işlendi. Kalan 25 `TRANSCRIPT_NOT_FOUND` ve
   7 `TRANSCRIPT_OWNERSHIP_UNVERIFIED` işinin dökümü artık diskte yok:
   kurtarılamaz, yalnız neden silindikleri (saklama süresi mi) anlaşılmalı.
3. ~~Alt ajan ölçümü.~~ **Yapıldı (2026-11-11).** Son 30 günde 403 alt ajan
   raporunun 37'si (%9) bulgular başlığıyla bitmiş; yalnız talimatın açıkça
   verildiği projelerde yazılıyor. Bu raporlardan çıkan 262 adayın hiçbiri
   onaylanmadı ya da reddedilmedi: 228'i bakılmadan süresi doldu, 34'ü bekliyor.
   Karar: `subagents/*.jsonl` dökümleri okunmayacak; darboğaz yakalama değil,
   adayların bakılmadan düşmesi (sonraki sürüm konusu).
4. **Durum satırı ve küçük temizlik.** Hiçbir yerden çağrılmayan
   `weekly_recall_check*.ps1` ve `post_session_maintenance.py` silindi (bakım
   testleri artık doğrudan `brain_eleven.runtime.maintenance`'ı sınıyor).
   `memory_backup.py` kaldı. `install-cross-project-memory.py` de kaldı:
   `/remember` ve `/study` komut dosyalarını kuran tek yol o. StateStore'daki
   "V2 SHADOW" satırı kod değil, kurulumdaki veriydi: `close-milestone` komutu
   açık kilometre taşını tamamlandı sayıyor, kapanan taş durum satırında
   görünmüyor. Gerçek kurulumda güncellemeden sonra bir kez çalıştırılmalı.
5. **Markdown'dan geri yazım.** Yapılmadı; bu sürümde ihtiyaç görülmedi.

## Açık konular

- `doctor`'daki `review_pending` gürültü işaretli adayları da sayıyor (2026-11-11:
  65'in 13'ü gerçekten sahibe kalan; 2026-11-13: 80, ayrımı ölçülmedi).
- `recall-probe` soruları var olan kayıtlardan seçildi (kolay); zor soru eklemek
  sahibin kararı.
- `map` profilinde ajanın doğru konu notunu kendiliğinden açıp açmadığı ölçülmedi.
- Canlı doğrulanmayanlar: alt klasörde gerçek oturum, fiziksel Ctrl+Alt+B.
- Luna (Hermes) kotası açılınca etiketli sette ölçülecek.
- Codex çift hook uyarısı sürüyor: `config.toml`'daki girdi başka bir aracın; taşımak sahibin kararı.
- `kur.ps1` yalnız Windows; başka sistemde üç adım elle.
