---
tags: [ders, veri-kaybı, sessiz-hata]
tarih: 2026-08-07
alan: kalıcılık / operasyon
kanıt: petsistemi c195a7a
---
# Ders: Sessizce çalışmayan yedek, yedek değildir

## Belirti
`AutoBackupTask` **hiçbir zaman yedek almıyordu ve bunu sessizce yapıyordu.**

Yöneticiye her şey sağlıklı görünüyordu. 6 saatte bir loga düşen tek iz:

```
Otomatik veritabanı yedeği sırasında hata: null
```

## Kök neden — dört hatanın üst üste binmesi
1. **Sabit kopyası.** Görev kendi dosya/klasör sabitlerini taşıyordu: `"petsistemi.db"` — gerçek veritabanı `"database.db"`. `"backups"` — diğer her şey `"database-backups"`.
2. **Sessiz null.** `MigrationBackupManager.createBackup` kaynak dosya yoksa **istisna atmıyor, null dönüyordu.**
3. **Kontrolsüz çağrı.** `AutoBackupTask` dönen değeri kontrol etmeden `backupFile.getName()` çağırıyordu → NPE.
4. **Mesajsız hata.** NPE `exceptionally`'ye düşüyor, mesajsız olduğu için log `null` yazıyordu.

Tek başına hiçbiri felaket değil. Zincir halinde: **yedek hiç çalışmıyor, yanlış klasöre bakıyor ve sağlıklı görünüyor.**

## Çözüm
- Dosya/klasör adları tek kaynağa bağlandı: `DatabaseManager.DATABASE_FILE_NAME` / `BACKUP_DIR_NAME`, `databaseFile(plugin)` / `backupDirectory(plugin)` yardımcıları. `PetAdminCommand` ve `PetPluginBootstrap` de bunları kullanıyor.
- Kaynak veritabanı yoksa veya klasör açılamıyorsa **yüksek sesle** uyarılıyor.

## Erken uyarı işareti
> **Hiç geri yüklemediğin yedek, yedek değil — hipotez.**

Ve daha keskini: **"hata: null" gibi mesajsız bir log satırı, tesadüfen çirkin bir çıktı değil — bir şeyin tamamen çalışmadığının kanıtıdır.** Bu satır aylarca loglarda durabilir ve kimse okumaz.

Kontrol listesi — bir yedekleme mekanizması yazdıysan:
- [ ] Yedekten **gerçekten geri yükleme** yaptın mı, bir kere?
- [ ] Yedek **alınamadığında** yüksek sesle bağırıyor mu, yoksa null mı dönüyor?
- [ ] Yol/dosya adları tek kaynaktan mı geliyor, yoksa her modül kendi sabitini mi taşıyor?
- [ ] Log satırında mesaj var mı?

## Bugüne bağlantı
2026-08-20: bu vault'un `Sıfırdan/` klasörü ve 21 notu Obsidian'dan tek tıkla silindi. Geri Dönüşüm Kutusu'ndan kurtarıldı — **yedek olduğu için değil, şans eseri.** Bu vault'un hâlâ sürüm kontrolü yok.
→ [[Açık Döngüler]]

## Kaynak
`c195a7a` · 2026-08-07 · petsistemi · 6 dosya, +141 / −17. Doğrulandı — commit gövdesinde tam teşhis yazılı.
