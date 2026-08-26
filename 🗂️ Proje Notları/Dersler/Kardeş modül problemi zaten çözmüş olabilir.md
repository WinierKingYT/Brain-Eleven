---
tags: [ders, mimari]
tarih: 2026-08-16
alan: bakım
kanıt: minecraftmcp ADR-0013
---
# Ders: Kardeş modül problemi zaten çözmüş olabilir

## Belirti
Maven wrapper güven modeli için sıfırdan iki alternatif tasarlandı ve tartışıldı (script checksum pin vs supervisor-only).

## Kök neden
**Gradle tarafı bu problemi zaten çözmüştü.** `trusted-local-backend.ts` içindeki `GRADLE_WRAPPER_MAIN`, `gradlew`/`gradlew.bat` script'lerini hiç çalıştırmıyor; checksum'ı doğrulanmış `gradle-wrapper.jar`'ı `java -cp` ile launcher olarak kullanıyor.

Yani "proje script'ini çalıştırma" kuralı üründe **mevcut bir önceliktir**. Maven tarafı sadece henüz bu modele dokunmamıştı.

Cevap kod tabanının içindeydi, iki dosya ötede.

## Erken uyarı işareti
> **Zor bir tasarım sorusuna oturmadan önce sor: bu sistemde aynı sınıftan başka bir şey var mı, o nasıl çözmüş?**

İki kardeş (Gradle/Maven, iOS/Android, web/desktop, v1/v2) varsa ve biri olgunsa, olgun olanın çözümü tasarım değil **envanter** işidir. Aramak dakikalar, sıfırdan tasarlamak saatler sürer — ve iki kardeş farklı çözerse tutarsızlık kalıcı borç olur.

Ek fayda: mevcut çözümü kopyalamak "neden böyle" sorusunu da beraberinde getirir; sıfırdan tasarım o gerekçeyi kaybeder.

## Kaynak
`docs/adr/0013-wrapper-execution-trust-model.md` · minecraftmcp. Doğrulandı — ADR bağlamında birebir yazılı.
