---
tags: [ders, güvenlik, supply-chain]
tarih: 2026-08-16
alan: build / tedarik zinciri
kanıt: minecraftmcp ADR-0013
---
# Ders: Doğrulanan şeyden önce çalışan kod doğrulanmamıştır

## Belirti
Maven Wrapper tedarik zinciri doğrulaması (ST-MAVEN-001..006) wrapper JAR'ını **ve** `distributionSha256Sum`'ı doğruluyordu. Kulağa kapalı geliyor. Değildi.

`mvnw` / `mvnw.cmd` script'lerinin **kendisi** checksum'lanmıyordu.

## Kök neden
Script, doğrulanmış Maven dağıtımı indirilmeden **önce** çalışan koddur. Saldırgan projesinin `mvnw` script'ini değiştirirse:

- dağıtım checksum'ı ✅ doğru görünür,
- ama saldırgan kod Maven'dan **önce** çalışmıştır.

Doğrulama zinciri kendi başlatıcısını doğrulamıyordu.

## Çözüm
İki model tartışıldı:
- **A — script checksum pin:** profillere `mvnw` hash'leri eklenir.
- **B — supervisor-only:** proje script'i asla çalıştırılmaz; supervisor kendi doğrulanmış launcher'ını kullanır.

B seçildi (ADR-0013). `mvnw` ASLA çalıştırılmıyor; launcher doğrulanmış wrapper JAR: `java -classpath <jar> MavenWrapperMain`.

## Erken uyarı işareti
> **"Şunu doğruluyoruz" dediğin her yerde sor: doğrulamayı kim başlatıyor, o doğrulanmış mı?**

Bu deseni kuran her şey aynı tuzağı taşır: bootstrap script'leri, install script'leri, `curl | sh`, wrapper'lar, plugin loader'ları, CI'ın kendi checkout adımı, imza doğrulayan kodun kendisi. Zincirin ilk halkası tanımı gereği zincirin dışındadır.

**Pratik test:** doğrulama başarısız olsaydı, o ana kadar hangi kod çalışmış olurdu? O kod senin güven sınırının içinde.

## Kaynak
`docs/adr/0013-wrapper-execution-trust-model.md` · 2026-08-16 · minecraftmcp. Doğrulandı — ADR bağlam bölümünde açık yazılı.
