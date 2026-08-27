---
type: decision
title: Horizontal Partitioning via Sharding
category: System Design & Architecture
status: active
created: 2026-08-27
source: donnemartin/system-design-primer
tags: [system-design, database, scaling, sharding, partitioning]
---

# Horizontal Partitioning via Sharding

**Pattern:** Database Scaling Strategy

## Karar

Tek bir veritabanı ölçeklemeyi aştığında, veriyi birden fazla veritabanına bölerek (shard) yatayda ölçeklenebilir. Her shard, toplam veri setinin bir alt kümesini tutar ve independent transaction handling sağlar.

## Sharding Stratejileri

**1. Range-Based Sharding**
```
User ID 1-1000000    → Shard A
User ID 1000001-2000000 → Shard B
User ID 2000001+     → Shard C
```
- ✓ Basit implementasyon
- ✗ Hotspot riski (bölümlerde eşit olmayan yükleme)

**2. Consistent Hashing**
```
hash(user_id) mod ring_size → Shard location
```
- ✓ Node eklendiğinde sadece %N veri taşınır
- ✗ Daha karmaşık implementation

**3. Directory-Based Sharding**
```
Lookup table: user_id → shard_location
```
- ✓ Esneklik (herhangi bir algoritma)
- ✗ Lookup overhead, single point of failure

## Sharding Zorlukları

1. **Cross-shard queries** - JOIN'ler karmaşık hale gelir
2. **Rebalancing** - Yeni shard eklendiğinde veri taşıma
3. **Hotspot** - Bazı shardlar diğerlerinden yoğun olabilir
4. **Transaction consistency** - Distributed transactions zordur

## Çözüm Yolu

- Read-heavy workloads: Denormalization + caching
- Cross-shard queries: Application-level JOIN
- Large shards: Secondary sharding (shard içinde shard)

---

**Bağlantılar:** [[github-harvest-001-cap-theorem]], [[github-harvest-003-replication]]
