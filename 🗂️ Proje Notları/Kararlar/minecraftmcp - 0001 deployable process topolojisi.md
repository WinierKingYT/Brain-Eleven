---
type: decision
title: minecraftmcp - Deployable Process Topolojisi
status: active
created: 2026-08-27
updated: 2026-08-27
tags: [minecraftmcp, architecture, decision]
source: docs/adr/0001-process-topology.md
---

# Deployable Process Topolojisi (minecraftmcp ADR-0001)

**Durum:** accepted  
**Tarih:** 2026-07-29

## Karar

Dört **ayrı process** tanımlandı:
1. **MCP Server** — Protokol yüzeyi, client iletişimi
2. **Run Supervisor** — Build orkestrasyonu, process ownership, yaşam döngüsü
3. **Paper Server** — Gerçek Minecraft sunucusu, plugin runtime
4. **Protocol Test Actor** — Test senaryoları (koşullu)

**Neden?** Tek process'te MCP çöküşü orphan Paper JVM'ler bırakıyor (KPI-06 ihlali).

## İmplikasyon

- MCP Server stateless → ölür ve yeniden başlar, Paper devam eder
- Supervisor startup recovery ile sahipsiz process'leri temizler
- Ownership bilgisi MCP Server'dan bağımsız yaşar
