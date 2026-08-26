---
type: decision
title: petsistemi - SQLite Depolama Motoru
status: active
created: 2026-08-27
updated: 2026-08-27
tags: [petsistemi, database, decision]
source: docs/adr/0001-sqlite-storage.md
---

# SQLite Depolama Motoru ve WAL Modu (petsistemi ADR-0001)

**Durum:** Kabul Edildi

## Karar

**SQLite JDBC** veritabanı motoru + WAL modu. PRAGMA ayarları:
- `journal_mode = WAL`
- `foreign_keys = ON`
- `busy_timeout = 5000`

## İmplikasyon

✓ Harici DB sunucusu gerekli değil  
✓ WAL: okuma yazma engellemez  
✓ Single-thread executor: paralel yazma kilitlenmeleri önler  
✗ Kilitlenmeler ve veri bozulması riski ortadan kalkar
