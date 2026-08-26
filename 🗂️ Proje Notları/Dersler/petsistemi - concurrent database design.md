---
type: lesson
title: Concurrent Database Pattern (Single Executor + WAL)
status: active
created: 2026-08-27
tags: [petsistemi, database, lesson]
source: ADR-0001, ADR-0003
---

# Single-Threaded Database + WAL Mode (petsistemi)

**Öğretim:** Concurrency control stratejileri.

## Bulgu

SQLite single executor (tüm yazma 1 thread'de) + WAL mode:
- Write: single thread → no locks
- Read: parallel (WAL says okumalar yazma engellemez)
- Result: high read throughput, safe writes

## Çıkarım

Yazma throughput sınırlıysa ve okuma yüksekse, single executor + 
WAL mode optimal. Deadlock ve corruption riski sıfır.
