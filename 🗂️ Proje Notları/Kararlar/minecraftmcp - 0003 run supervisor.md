---
type: decision
title: minecraftmcp - Ayrı Run Supervisor Process'i
status: active
created: 2026-08-27
updated: 2026-08-27
tags: [minecraftmcp, architecture, decision]
source: docs/adr/0003-run-supervisor-process.md
---

# Ayrı Run Supervisor Process'i (minecraftmcp ADR-0003)

**Durum:** accepted  
**Tarih:** 2026-07-29

## Karar

Process ownership, build yürütme ve runtime yaşam döngüsü **ayrı Supervisor process'inde** yaşar.

## Modüller

Project Registry, Trust Store, Source Snapshotter, Build Executor, Runtime Registry, Process Ownership, Operation Ledger, Mutation Ledger, Retention Manager, Garbage Collector, Startup Recovery.

## Zorunlu Davranışlar

1. Supervisor MCP çöküşü sırasında ownership bilgisini **korur**
2. Yeniden başlayan Supervisor **startup recovery** çalıştırır (orphan process'leri temizler)
