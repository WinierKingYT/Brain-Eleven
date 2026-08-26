---
tags: [karar, yöntem, minecraftmcp]
tarih: 2026-08-20
durum: gözlemlenen desen
alan: karar yönetimi
kanıt: minecraftmcp ADR-0013 → 0015 → 0020
---
# Yöntem: Kapıyı kapatırken yeniden açma koşulunu yaz

## Gözlem
minecraftmcp'de 20 ADR var ve supersede zinciri **madde düzeyinde** işliyor — tüm ADR değil, tek karar maddesi geçersizleniyor:

| ADR | Tarih | Ne yaptı |
|---|---|---|
| 0013 | 08-16 | Supervisor-only: `mvnw` **asla** çalıştırılmaz, launcher doğrulanmış JAR |
| 0015 | — | only-script (JAR'sız) Maven projelerini reddet: `MVN_WRAPPER_JAR_REQUIRED`. **Ve kapının provisioning altyapısı gelince ayrı bir ADR ile yeniden açılacağını ilan etti.** |
| 0020 | 08-20 | Kapıyı üç koşula bağlı olarak yeniden açtı: kullanıcı onayı + profil `jar_sha256` beyanı + host allowlist uyumu. Biri eksikse davranış değişmiyor. |

**Yürütme modeli zincir boyunca hiç değişmedi.** `mvnw` hâlâ asla çalıştırılmıyor. Değişen sadece kapının genişliği.

## Neden bu iyi
Bu "dört kez yanılıp düzeltmek" değil. **Kasıtlı daraltma, sonra ilan edilmiş koşulla genişletme.**

ADR-0015 kapıyı kapatırken *"bu ayrı bir ADR ile yeniden açılacak"* diye yazdığı için, ADR-0020 bir geri adım değil **planlanmış teslimat** oldu. Kapıyı kapatan kişi, açacak kişiye not bırakmış.

## Kendime not — proje arası çelişki
minecraftmcp ADR'leri "bu kararı ne geri aldırır"ı **yazıyor.**
PromtGen kararları **yazmıyor** — hasatta 5 karardan 3'ünün gerekçesi çıkmadı ([[2026-08-02 - Tur başına tek AI çağrısı]], [[Ürün sınırı - kod üretimi ana ürün değil]]), local-first'te ise gerekçe vardı ama süresi dolmuştu ([[Ürün sınırı - local-first, bulut yok]]).

Aynı kişi, iki proje, bir tanesinde disiplin var. Fark yetenek değil **format**: minecraftmcp'de ADR şablonu soruyu sormaya zorluyor, PromtGen'de kararlar commit'e ve doküman metnine dağılmış.

→ Uygulanabilir sonuç: PromtGen'e ADR klasörü aç, ya da en azından karar verirken [[ŞABLON - Karar]]'daki *"bu kararı ne geri aldırır"* alanını doldur.

## Kanıt
`docs/adr/0013`, `0015`, `0020` · minecraftmcp · ADR README'de supersede tablosu tutuluyor
