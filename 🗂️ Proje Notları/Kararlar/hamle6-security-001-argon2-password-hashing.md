---
type: decision
title: Argon2 Password Hashing - Memory-Hard Key Derivation
category: Security & Cryptography
status: active
created: 2026-08-28
source: OWASP Guidelines (Hamle 6)
tags: [security, password-hashing, argon2, cryptography, authentication]
---

# Argon2 Password Hashing Strategy

**Pattern:** OWASP-Recommended Memory-Hard Key Derivation

## The Problem

```
Weak hashing allows GPU/ASIC cracking:

MD5: 8 billion hashes/second (worthless)
SHA-1: 2 billion hashes/second (worthless)
bcrypt: 100 thousand hashes/second (better, but still crackleable with modern GPUs)
Argon2: 5-50 hashes/second (GPU-resistant, resistant to parallel attacks)

Attack scenario:
  Attacker steals password database (MD5 hashed)
  Uses GPU cluster to crack:
    - Rainbow tables: instant (pre-computed)
    - Brute force: 8B hashes/sec = all 8-char passwords in hours
```

## Why Argon2 Wins

```
Memory-hard: requires large RAM amounts per hash (makes GPU/ASIC attacks expensive)
Time-cost: configurable iterations (as hardware improves, increase iterations)
Parallelism: utilizes multiple cores (hard to parallelize attacks)

Variants:
  - Argon2i: resistant to side-channel attacks (slower, for passwords)
  - Argon2d: resistant to GPU cracking (faster, for crypto)
  - Argon2id: hybrid (default, best for passwords)
```

## Implementation

```javascript
import argon2 from 'argon2'

// Hash password
const hash = await argon2.hash('user_password', {
  type: argon2.argon2id,
  memoryCost: 65536,      // 64MB (recommended for password)
  timeCost: 3,            // iterations
  parallelism: 4          // threads
})
// Result: $argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>

// Verify
try {
  const match = await argon2.verify(hash, inputPassword)
  if (match) {
    // Password correct
  } else {
    // Password wrong
  }
} catch (err) {
  // Hash format invalid
}
```

## Configuration Tuning

```
OWASP 2023 Recommendations:

memoryCost: 64-128 MiB (minimum 64MB for passwords)
  └─ Higher = more resistant to GPU attacks
  └─ Too high = slow hash (>2 seconds)

timeCost: 2-4 iterations
  └─ Higher = slower (trade throughput for security)
  └─ Only if you need < 2-3 password hashes/second

parallelism: 1-4 threads
  └─ Match CPU cores (usually 2-4)
  └─ Higher = more CPU needed for attacker

Typical profile:
  memoryCost: 65536 (64MB)
  timeCost: 3
  parallelism: 4
  = ~500ms per hash on modern CPU
```

## Production Gotchas

```
❌ Too aggressive (1000ms+ hash time)
  → Login/signup becomes painful
  → Users abandon site
  
  ✓ Tune to 300-500ms range
  ✓ Use queue for password resets

❌ Hash time varies by hardware
  → Different environments hash different speeds
  
  ✓ Include memory/time costs in hash output (Argon2 does)
  ✓ Verify hash includes metadata

❌ Never reduce costs in production
  → Breaks password verification for existing users
  
  ✓ Only increase when upgrading hardware
  ✓ Plan ahead for cost increases

❌ Hashing in request handler (blocking)
  → Each login blocks the thread
  
  ✓ Use async/await (never .hashSync)
  ✓ Queue password operations separately
```

## Migration Strategy

```
Old system (bcrypt, MD5, plaintext):

Step 1: Hash migration
  IF password_hash IS NULL THEN
    new_hash = argon2.hash(plaintext_password)
    UPDATE users SET password_hash = new_hash

Step 2: Lazy migration (better)
  ON LOGIN:
    IF hash_algorithm = 'md5' THEN
      Verify against MD5
      IF correct:
        new_hash = argon2.hash(plaintext_password)
        UPDATE users SET password_hash = new_hash
      
Step 3: Cutoff date
  After 6 months, force password reset for unmigrated users

Result:
  New passwords: Argon2 from day 1
  Existing: Gradually migrated on next login
```

## Monitoring

```
Track password operations:

- Hash duration (p50, p95, p99)
  └─ Alert if > 1000ms (misconfiguration)
  └─ Alert if < 100ms (too weak)

- Failed verifications
  └─ Count login failures
  └─ Alert on >10 failures from single IP

- Cost parameters drift
  └─ Monitor that all hashes use correct parameters
  └─ Detect if app is accidentally using weak settings

Example Prometheus metric:
  argon2_hash_duration_ms{type="id",cost="64MB"} 520ms
  argon2_verify_failures_total{ip="192.168.1.1"} 15
```

---

**Bağlantılar:** [[hamle6-security-002-jwt-refresh-tokens]]
