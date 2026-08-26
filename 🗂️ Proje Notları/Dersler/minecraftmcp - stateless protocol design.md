---
type: lesson
title: Stateless Protocol Design Patterns
status: active
created: 2026-08-27
tags: [minecraftmcp, architecture, lesson]
source: ADR-0008, git history
---

# Stateless Protocol Design (minecraftmcp)

**Öğretim:** Protokol katmanını state'ten ayırmak.

## Bulgu

- MCP SDK 2.0.0 → stable, stateless design
- State: separate Run Supervisor process
- Protocol: stateless request/response pairs
- Recovery: startup recovery mechanism

## Çıkarım

Uzun yaşanan component (MCP Server) state'i başka process'te tutarsa,
protocol layer ölüp yeniden başlayabilir. **State-protocol separation** 
reliability kritiği.
