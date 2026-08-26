---
type: decision
title: minecraftmcp - MCP Stdio Taşıması
status: active
created: 2026-08-27
updated: 2026-08-27
tags: [minecraftmcp, protocol, decision]
source: docs/adr/0002-mcp-stdio-transport.md
---

# MCP Stdio Taşıması (minecraftmcp ADR-0002)

**Durum:** Kısmen superseded by ADR-0008  
**Tarih:** 2026-07-29

## Karar

- **Taşıma:** V1 yalnızca yerel `stdio` destekler (stdout purity invariant'ı)
- **SDK:** `@modelcontextprotocol/server@2.0.0` stable (alpha SDK bağımlılığı kaldırıldı)

## İmplikasyon

- Yerel development aracı (uzak taşıma yok)
- Protocol revision 2026-07-28 (stable, `initialize` el sıkışması kaldırıldı)
- ADR-0008 tarafından revize edildi
