---
tags: [karar, promtsitesi, güvenlik]
tarih: 2026-07-22
durum: geçerli
alan: rate limiting
kanıt: fd78d1a
---
# Karar: Upstash yoksa rate limit fail-open — in-memory fallback açık kalsın

`src/proxy.ts` içinde production-only bayrağı `false`'a çekildi; Redis/Upstash yokken rate limiter kapanmak yerine in-memory fallback'e düşüyor.

## Gerekçe
Kodda yazılı: *"This is a broad first line of defense, not the only limit on sensitive endpoints. Keep the in-memory fallback active when optional Upstash is unavailable so a free/single-instance deployment does not reject every mutation. Critical routes still enforce their own tighter policies."*

Üç dayanak:
1. Bu **geniş bir ilk savunma hattı**, tek kontrol değil.
2. **Kritik rotaların kendi daha sıkı politikaları var.**
3. Upstash'siz free/tek-instance deploy aksi halde **her mutation'ı reddederdi.**

## Neyden vazgeçtim
Dağıtık rate limit garantisi. Çok instance'lı çalışmada in-memory sayaç instance başına ayrı olur → efektif limit instance sayısı kadar gevşer.

## Neden bu iyi yazılmış
Güvenlik kontrolünde **fail-open** normalde alarm verir. Bir okuyucu `false` görüp "bug" der ve düzeltmeye kalkar. Yorum tam da bunu engelliyor: kararın bilinçli olduğunu, hangi telafi edici kontrollerin devrede olduğunu ve hangi senaryo için verildiğini söylüyor.

→ Genel kural: **fail-open bir güvenlik kararı, gerekçesi yanında yazılmadan bırakılmaz.** Yoksa ya sessizce "düzeltilir" ya da körü körüne güvenilir.

## Bu kararı ne geri aldırır
Çok instance'a geçiş — o noktada in-memory fallback'in gevşemesi ölçülebilir hale gelir ve Upstash zorunlu olur. *(Doğrula: kritik rotaların "daha sıkı politikaları" gerçekte neler? Yorum iddia ediyor, kanıt görülmedi.)*

## Kanıt
`fd78d1a` · 2026-07-22 · `src/proxy.ts` +5 / −1
