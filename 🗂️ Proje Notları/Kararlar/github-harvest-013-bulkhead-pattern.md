---
type: decision
title: Bulkhead Pattern - Resource Isolation
category: Design Patterns & Microservices
status: active
created: 2026-08-27
source: mehdihadeli/awesome-software-architecture
tags: [design-patterns, bulkhead, resilience, isolation, microservices]
---

# Bulkhead Pattern

**Pattern:** Isolating Resources to Prevent Cascading Failures

## Karar

Sistem resources'ı compartment'lere böl. Bir compartment'in failure diğer compartment'leri etkilemesin.

## Gemi Analoji

Gemi design: Her compartment watertight
- Bir compartment'da delik → sadece o sink'i
- Tüm gemi batmaz

## Implementasyon

**1. Thread Pool Isolation**
```
OrderService → OrderThreadPool (10 threads)
                ↓ protected
                
PaymentService → PaymentThreadPool (5 threads)
                ↓ protected

// PaymentService slow → OrderService unaffected
```

**2. Connection Pool Separation**
```
Primary DB    → Connection Pool (50 connections)
Reporting DB  → Connection Pool (10 connections)

// Reporting queries (slow) → Primary unaffected
```

**3. Memory Partition**
```
Cache (100MB) ├─ Hot cache (80MB)
              └─ Cold cache (20MB)

// Cold cache eviction → Hot cache protected
```

**4. Service Isolation (Kubernetes)**
```
OrderService Pod     → Resource Limit: 512MB, 1 CPU
PaymentService Pod   → Resource Limit: 256MB, 500m CPU

// PaymentService crash → OrderService untouched
```

## Circuit Breaker ile Combine

```
┌─────────────────────────────┐
│ OrderService                │
├─────────────────────────────┤
│ Thread Pool: 10             │
│ Circuit Breaker             │
└──────────┬────────────────┘
           │
           ├─→ Payment (fail) → Circuit OPEN → Fail fast
           └─→ Inventory (OK) → proceeds
```

## Avantajları

- ✅ Prevents cascading failures
- ✅ Enables graceful degradation
- ✅ Clear resource accountability
- ✅ Easier troubleshooting

## Trade-offs

- ✗ Resource overhead (separate pools)
- ✗ Complex configuration
- ✗ Needs monitoring (alert on limits)

---

**Bağlantılar:** [[github-harvest-003-circuit-breaker]], [[github-harvest-012-saga-pattern]]
