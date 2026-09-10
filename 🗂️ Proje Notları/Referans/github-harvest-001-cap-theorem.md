---
type: decision
title: CAP Theorem - Trade-offs as First Principle
category: System Design & Architecture
status: active
created: 2026-08-27
source: donnemartin/system-design-primer (GitHub Harvest)
tags: [system-design, distributed-systems, consistency, availability, partition-tolerance]
---

# CAP Theorem: Trade-offs as First Principle

**Pattern:** Distributed System Trade-off Analysis

## Karar

Hiç bir distributed system, Consistency (tutarlılık), Availability (erişilebilirlik), ve Partition Tolerance (bölüm toleransı) üçünü aynı anda garantileyemez. Bir sistem tasarlarken, bu üç özellikten hangisini tercih edeceğine karar vermelisin.

## Consistency vs Availability: Bölüm Sırasında

**Network bölümü meydana gelirse:**
- Consistency seç → errorlar döndür (veri tutarlı kalır, ama sistem kısmen işlemez)
- Availability seç → eski veriyi döndür (sistem çalışır, ama veriler tutarsız olabilir)

Partition tolerance kaçınılmazdır (ağlar başarısız olur), bu yüzden aslında CA vs CP seçimidir.

## Hangi Sistemleri Seç?

| Seçim | Sistemler | Örnek Kullanım |
|-------|-----------|----------------|
| **CP** (Consistency + Partition) | PostgreSQL, MySQL, ZooKeeper | Finansal işlemler, sıkı ACID gerekliliği |
| **AP** (Availability + Partition) | DynamoDB, Cassandra, MongoDB | Sosyal medya, timeline'lar, cache katmanı |
| **CA** (Consistency + Availability) | Monolitik veritabanlar | Tek veri merkezi (üretim ortamında nadir) |

## Ortak Mimariler

**Strong Consistency (CP):**
- Synchronous replication
- PostgreSQL master + replicas
- ZooKeeper consensus

**Eventual Consistency (AP):**
- Asynchronous replication  
- Amazon DynamoDB
- Redis (single master, async followers)

---

**Kaynaklar:** System Design Primer (donnemartin/system-design-primer)  
**Bağlantılar:** [[github-harvest-002-sharding]], [[github-harvest-003-replication]]
