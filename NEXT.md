# Durum ve sıradaki işler

Tek durum dosyası. Her oturum sonunda en üste 2–3 satır eklenir; eskiyen
satırlar silinir. Kontrat, rapor ya da inceleme dosyası açılmaz.

## Şu an (2026-10-14)

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

## Sıradaki işler (sırayla)

0. **Yakala'yı Windows'ta dene.** `install` + `yakala kur`, sonra bir
   bağlantıyı kopyalayıp Ctrl+Alt+B; `yakala liste` ile gör.
1. **Alt ajan ölçümü.** Gerçek orchestrator oturumlarında bulgular başlığı ne
   sıklıkla yazılıyor, adaylar ne kadar işe yarıyor; gerekirse
   `<oturum>/subagents/*.jsonl` dökümlerini de okumak.
2. **Markdown'dan geri yazım.** Nottaki düzenlemeyi onaydan geçirerek hafızaya
   işlemek (Markdown kaynak, veritabanı türev yönü); ihtiyaç görülürse.
3. **Sürüm paketi.** Checksum'lı kararlı sürüm, tek mesajla kurulum ve
   güncelleme.
4. **V2 sadeleştirme.** Gölgedeki V2 paketlerini ölçüp kaldırmak ya da V1'e
   katmak.

## Açık konular

- texforge, robloxdevOs, obsidian-S&box `project add` ile kaydedilmedi.
- Luna (Hermes) kotası açılınca etiketli sette ölçülecek.
- `auto_accept_verified` gerçek kurulumda açık bulundu; sahip teyidi bekliyor.
