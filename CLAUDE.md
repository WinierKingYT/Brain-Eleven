# Brain-Eleven — ajan kuralları

Eleven'in yerel ikinci beyni. Ne olduğu için [README.md](README.md), nasıl
çalıştığı için [ARCHITECTURE.md](ARCHITECTURE.md), nerede olduğumuz için
[NEXT.md](NEXT.md).

## Çalışma biçimi

- Her iş kendi dalında, PR ile. Master'a doğrudan push ve force push yok.
- Bir PR, kullanıcıya görünen tek bir iyileştirme. Kontrat, rapor, kanıt ya
  da inceleme dosyası açılmaz; iş bitince NEXT.md'ye 2–3 satır yazılır.
- Hata düzeltirken: yeniden üret → kök neden → düzelt → aynı kontrolle doğrula.
- Kapanış ölçütü: `python -m pytest tests -q` yeşil. Hatırlamayı etkileyen
  değişiklikte `python -m brain_eleven recall-probe` önce/sonra sonucu PR'a yazılır.
- Yeni bağımlılık ve yeni soyutlama varsayılan olarak yok; gerekiyorsa PR'da
  bir cümleyle gerekçelendir.

## Değişmeyenler

- Hafızaya yazım yalnız `MemoryStore` (`brain_eleven/memory`) üzerinden.
  İkinci bir hafıza/durum sistemi kurulmaz.
- Sır, token, parola, tam döküm ve tam dosya yolu hafızaya, PR'a ya da commit'e
  yazılmaz.
- Sahibin onayı (`approval ON`) ve deneme süresi güvenlik sınırıdır; bunları
  atlayan otomatik yazım yolu eklenmez.

## Vault notları

- `🔮 Companion/`: günlük (Daily.md), açık konular (Threads), son oturum
  (Last Session.md), profil.
- `🗂️ Proje Notları/`: proje kararları ve dersleri.
- Hiçbir not silinmez.
