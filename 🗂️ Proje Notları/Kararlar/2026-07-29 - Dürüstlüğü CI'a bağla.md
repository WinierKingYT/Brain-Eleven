---
tags: [karar, minecraftmcp, güvenlik, yöntem]
tarih: 2026-07-29
durum: accepted
alan: güvenlik / dokümantasyon
kanıt: minecraftmcp ADR-0007
---
# Karar: Güvenlik dürüstlüğünü insana değil CI'a bağla

> `trusted-local` backend **hiçbir yerde** sandbox olarak adlandırılamaz — belge, kod yorumu, hata mesajı, README, commit mesajı, UI dahil. Kural CI'da denetlenir.

## Bağlam
Ürün kullanıcıya *"AI'ın yazdığı kodu güvenle çalıştır"* mesajı veriyor. İki gerçek rahatsız edici:
1. `TrustedLocalBackend`'in path confinement, env allowlist, timeout kontrolleri **sandbox izlenimi veriyor** — vermemesi gerekiyor; aynı kullanıcı yetkisiyle çalışan Java kodu bunları aşabilir.
2. Paper Bridge hedef plugin ile **aynı JVM'de** çalışıyor. Loopback + token auth rastgele process'lere karşı işe yarar; aynı adres alanındaki aktif saldırgana karşı yaramaz.

## Gerekçe
> **Yanlış bir güvenlik iddiası, hiç iddia olmamasından daha tehlikelidir:** kullanıcı, olmayan bir korumaya güvenerek gerçekten kötü niyetli kod çalıştırır.

Ve kritik gözlem: *"Bu iki gerçek, zamanla **iyi niyetli** dokümantasyon düzenlemeleriyle sulanma eğilimindedir."*

Kimse yalan söylemeye niyetlenmiyor. Dürüstlük kötü niyetle değil, **cila ile** aşınıyor. O yüzden insana bırakılmıyor.

## Mekanizma
1. **Yasaklı ifade — CI kapısı.** `trusted-local` / `trusted local` / `TrustedLocal` yakınında `sandbox` geçerse build kırılır (`scripts/check-docs.mjs`).
2. **Muafiyet işareti.** Fuzzy olumsuzlama kelime listesi kaçınılmaz olarak eksik kalır → kuralın kendisini tartışan metinler için greplenebilir, **insan tarafından yazılmış** işaret: `<!-- kpi-11-exempt: neden -->`. Muafiyet sayısı her CI koşusunda raporlanır; **sessizce çoğalamaz.**
3. **Zorunlu limitation cümlesi.** Same-JVM sınırı `docs/security/guarantees.md` içinde açık cümle olarak bulunmak *zorundadır*; varlığı CI'da kontrol edilir.
4. **Garanti sınıflandırması.** Her güvenlik ifadesi ya **Sağlar** (bir test kimliğine bağlı olmak zorunda) ya **Sağlamaz** (açık limitation cümlesi olmak zorunda).

## Neden bu iyi tasarım
Sadece yasak koymuyor; yasağın **kaçınılmaz eksikliğini** kabul edip kaçağı sayılabilir hale getiriyor. Muafiyet sayacı, kuralın sessizce çürümesini imkânsız kılıyor.

Genelleştirilebilir: *rahatsız edici bir gerçeği koruyacaksan, koruma insanın iyi niyetine değil makineye bağlanmalı.*

## Bu kararı ne geri aldırır
`trusted-local` gerçekten izole edilirse (ör. gerçek sandbox backend eklenirse) yasak yeniden değerlendirilir — ama o zaman iddia **Sağlar** kategorisine girer ve bir test kimliğine bağlanması gerekir.

## Kanıt
`docs/adr/0007-security-claims.md` · 2026-07-29 · durum accepted · KPI-11, DOC-GATE-06
