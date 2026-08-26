---
type: decision
title: petsistemi - Single Database Executor
status: active
created: 2026-08-27
updated: 2026-08-27
tags: [petsistemi, concurrency, decision]
source: docs/adr/0003-single-database-executor.md
---

# Single Database Executor (petsistemi ADR-0003)

Tüm DB yazma işlemleri tek thread'de çalışır (paralel yazma kilitlemesi ve tutarsızlığı önler).

## İmplikasyon

✓ SQLite WAL'ın tam potansiyelini kullan (okuma paralel)  
✓ Yazma tutarlılığı garanti  
✗ Yazma throughput sınırlı (single thread)
