# Durum ve sıradaki işler

Tek durum dosyası. Her oturum sonunda en üste 2–3 satır eklenir; eskiyen
satırlar silinir. Kontrat, rapor ya da inceleme dosyası açılmaz.

## Şu an (2026-10-13)

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

1. **Alt ajan desteği.** `SubagentStart` hook'u ile alt ajana proje hafızası
   vermek; `<session>/subagents/*.jsonl` dökümlerini yakalamak; alt ajan
   raporlarını ayrı bir kaynak olarak değerlendirmek.
2. **Last-Session ve Threads kartları.** Oturum başına kısa devir kartı ve
   açık konuların güncel durumu; boyut sınırı, taşan kısım kelimesi kelimesine
   arşive (avenoxbeyin'deki yapı).
3. **`recap`.** Model çağırmadan son N günün kaynaklı iş listesi.
4. **Tüketim modları.** Normal, ekonomik ve manuel modlar; bağlam karakter
   bütçesi.
5. **Markdown görünümü.** Hafızanın Obsidian'da okunur hali (Markdown kaynak,
   veritabanı türev).
6. **Skill üçlüsü.** `beyin` / `beyin-doktor` / `beyin-guncelle`.
7. **Sürüm paketi.** Checksum'lı kararlı sürüm, tek mesajla kurulum ve
   güncelleme.
8. **V2 sadeleştirme.** Gölgedeki V2 paketlerini ölçüp kaldırmak ya da V1'e
   katmak.

## Açık konular

- texforge, robloxdevOs, obsidian-S&box `project add` ile kaydedilmedi.
- Luna (Hermes) kotası açılınca etiketli sette ölçülecek.
- `auto_accept_verified` gerçek kurulumda açık bulundu; sahip teyidi bekliyor.
