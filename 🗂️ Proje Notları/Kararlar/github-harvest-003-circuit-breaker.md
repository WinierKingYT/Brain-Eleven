---
type: decision
title: Circuit Breaker Pattern - Resilience Through Fault Isolation
category: System Design & Architecture
status: active
created: 2026-08-27
source: donnemartin/system-design-primer
tags: [system-design, resilience, circuit-breaker, fault-tolerance, microservices]
---

# Circuit Breaker Pattern

**Pattern:** Resilience Through Fault Isolation

## Karar

Failing service'e gönderilen istekleri durdurarak cascading failure'ı önle. Circuit Breaker üç durumda çalışır:

1. **CLOSED (normal)** - İstekler geçer
2. **OPEN (fail detected)** - İstekler engellenir, fail fast
3. **HALF-OPEN (recovery test)** - Sınırlı istekler test amaçlı gönderilir

## State Machine

```
CLOSED → [failures exceed threshold] → OPEN
OPEN  → [timeout elapsed] → HALF-OPEN
HALF-OPEN → [success] → CLOSED
HALF-OPEN → [failure] → OPEN
```

## Implementasyon Detayları

**Threshold'lar:**
- Açılacak miktar: 5 başarısız istek
- Timeout: 30 saniye
- Half-open test: 3 istek

**Fallback Stratejileri:**
- Cached response döndür
- Default value kullan
- Alternative service'e yönlendir
- Graceful degradation (partial functionality)

## Kod Örneği (Node.js/Resilience4j tarzı)

```javascript
const circuitBreaker = new CircuitBreaker({
  threshold: 5,        // 5 failure = OPEN
  timeout: 30000,      // 30s timeout
  monitorInterval: 5000 // Check every 5s
});

try {
  const result = await circuitBreaker.fire(() => 
    apiCall(service)
  );
} catch (err) {
  if (err.isCircuitBreakerOpen) {
    // Return cached/default response
  }
}
```

## Avantajları

- ✅ Cascading failure'ı durdurur
- ✅ Failing service'e saygı gösterir (istek göndermez)
- ✅ Fail fast user experience
- ✅ Graceful degradation sağlar

---

**Bağlantılar:** [[github-harvest-004-bulkhead]], [[github-harvest-008-saga-pattern]]
