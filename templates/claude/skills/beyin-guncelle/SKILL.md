---
name: beyin-guncelle
description: Brain-Eleven'ı güncellemek, güncel olup olmadığını kontrol etmek ya da son güncellemeyi geri almak istendiğinde kullan ("beynimi güncelle", "yeni sürüm var mı", "güncellemeyi geri al").
---

# Beyin güncelle

Brain-Eleven bir git deposu olarak kurulu: `{{VAULT_PATH}}`. Güncelleme,
yalnız `master` dalına hızlı ileri (fast-forward) çekmektir; yerel değişiklik
asla ezilmez. Hafıza ve ayarlar (`.brain-eleven/`) git'te değildir, korunur.

## Kontrol

```text
git -C "{{VAULT_PATH}}" fetch origin master
git -C "{{VAULT_PATH}}" log --oneline HEAD..origin/master
```

Çıktı boşsa güncel; değilse gelecek değişiklikleri kullanıcıya özetle.

## Güncelle

1. `git -C "{{VAULT_PATH}}" status --porcelain` boş olmalı. Değilse dur,
   değişen dosyaları kullanıcıya göster; commit/stash kararını o versin.
2. Şu anki commit'i not et: `git -C "{{VAULT_PATH}}" rev-parse HEAD` (geri alma için).
3. `git -C "{{VAULT_PATH}}" checkout master` ve `git -C "{{VAULT_PATH}}" pull --ff-only origin master`.
   Hızlı ileri olmuyorsa dur ve kullanıcıya söyle.
4. `{{PYTHON}} -m pip install -r "{{VAULT_PATH}}/requirements.txt"`
5. `{{PYTHON}} -m brain_eleven --vault "{{VAULT_PATH}}" install` (yeni hook ve skill'ler için).
6. `{{PYTHON}} -m brain_eleven --vault "{{VAULT_PATH}}" doctor` → `READY` olmalı.
7. Kullanıcıya: eski ve yeni commit, `NEXT.md`'nin en üst maddeleri, gerekiyorsa
   istemcide hook güven onayı ve yeni oturum başlatması.

## Geri al

Kullanıcı isterse, 2. adımda not edilen commit'e dön:

```text
git -C "{{VAULT_PATH}}" checkout <eski-commit>
{{PYTHON}} -m brain_eleven --vault "{{VAULT_PATH}}" install
{{PYTHON}} -m brain_eleven --vault "{{VAULT_PATH}}" doctor
```

Sonra `master`'a dönmek için güncelle adımlarını tekrar çalıştır.

## Kurallar

- `reset --hard`, `clean`, force push ya da `.brain-eleven/` silme yok.
- Güncelleme sırasında hata olursa dur, ne olduğunu ve geri alma komutunu söyle.
