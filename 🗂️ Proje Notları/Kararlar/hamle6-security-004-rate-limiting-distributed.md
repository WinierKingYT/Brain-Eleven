---
type: decision
title: Distributed Rate Limiting - Sliding Window Algorithm
category: Security & Cryptography
status: active
created: 2026-08-28
source: Redis Rate Limiting Patterns (Hamle 6)
tags: [security, rate-limiting, distributed, redis, dos-protection]
---

# Distributed Rate Limiting with Sliding Window

**Pattern:** Sliding Window Counter using Redis for DDoS Protection

## Algorithm Comparison

```
Fixed Window (bad):
  Window: [00:00-01:00]
  Limit: 100 requests
  Problem: 50 at 00:59, 50 at 01:01 = 100 req in 2 minutes (burst)

Sliding Window (good):
  Track all requests in past N seconds
  Reject if count > limit
  No bursts allowed

Token Bucket (balanced):
  Tokens refill at rate, requests consume tokens
  Allows controlled bursts
  Smooth under load
```

## Sliding Window Implementation

```javascript
const redis = require('redis').createClient()

// Sliding window rate limiter
async function rateLimit(userId, limit, windowSeconds) {
  const key = `rate_limit:${userId}`
  const now = Date.now()
  const windowStart = now - (windowSeconds * 1000)
  
  // Remove old entries outside window
  await redis.zremrangebyscore(key, '-inf', windowStart)
  
  // Count requests in window
  const count = await redis.zcount(key, windowStart, now)
  
  if (count >= limit) {
    return { allowed: false, remaining: 0, resetAt: now + windowSeconds * 1000 }
  }
  
  // Add current request
  await redis.zadd(key, now, `${now}:${Math.random()}`)
  
  // Set expiry on key
  await redis.expire(key, windowSeconds + 1)
  
  return { 
    allowed: true, 
    remaining: limit - count - 1,
    resetAt: now + windowSeconds * 1000
  }
}

// Usage
app.post('/login', async (req, res) => {
  const limit = await rateLimit(req.body.email, 5, 900)  // 5 attempts per 15 min
  
  if (!limit.allowed) {
    return res.status(429).json({
      error: 'Too many login attempts',
      retryAfter: Math.ceil((limit.resetAt - Date.now()) / 1000)
    })
  }
  
  // Proceed with login
})
```

## Per-User vs Per-IP

```
Per-user rate limiting:
  ✓ Fair (each user gets their quota)
  ✗ Requires authentication first (login endpoint vulnerable)
  ✓ Prevents abuse after login

Per-IP rate limiting:
  ✓ Works before authentication
  ✓ Simple to implement
  ✗ Proxy/CDN users all share IP
  ✗ Unfair (legitimate users lumped with abusers)

Hybrid (recommended):
  Combine both limits
  Login: 5 per 15 min per IP, 50 per hour per user
  API calls: 100 per minute per user, 1000 per hour per IP
```

## Distributed Setup

```
Single Redis:
  ✓ Simple, consistent
  ✗ Single point of failure
  ✗ Not replicated

Redis Cluster:
  ✓ Fault tolerant
  ✗ Cross-node consistency tricky (key might hash to different node)
  ✗ Split-brain scenarios

Solution: Use Redis Streams + Lua script for atomic ops

// Lua script (atomic in Redis)
const luaScript = `
  local key = KEYS[1]
  local limit = tonumber(ARGV[1])
  local windowSeconds = tonumber(ARGV[2])
  local now = tonumber(ARGV[3])
  local windowStart = now - (windowSeconds * 1000)
  
  redis.call('ZREMRANGEBYSCORE', key, '-inf', windowStart)
  local count = redis.call('ZCOUNT', key, windowStart, now)
  
  if count >= limit then
    return {0, limit - count, math.ceil(windowStart + windowSeconds * 1000)}
  end
  
  redis.call('ZADD', key, now, now .. ':' .. math.random())
  redis.call('EXPIRE', key, windowSeconds + 1)
  return {1, limit - count - 1, now + windowSeconds * 1000}
`

// Use in cluster (atomic per key)
const allowed = await redis.eval(luaScript, 1, key, limit, windowSeconds, Date.now())
```

## Handling Distributed Timeouts

```
Clock skew (servers 100ms apart):
  Server A: now = 12:00:00.000
  Server B: now = 12:00:00.100
  
  Window overlap = 100ms difference in counting
  Solution: Use centralized clock (NTP sync), 5-sec clock skew tolerance

Network partition (Redis unavailable):
  Option 1: Fail open (allow all) → DDoS risk
  Option 2: Fail closed (reject all) → Bad UX
  Option 3: Client-side fallback (cache last state) → Best

// Client-side fallback
const cachedLimits = new Map()

async function rateLimitWithFallback(userId, limit, windowSeconds) {
  try {
    return await rateLimit(userId, limit, windowSeconds)
  } catch (redisDown) {
    // Use stale cached value
    const cached = cachedLimits.get(userId)
    if (cached && cached.expiry > Date.now()) {
      return cached
    }
    // Redis down + no cache = reject to prevent DDoS
    return { allowed: false }
  }
}
```

---

**Bağlantılar:** [[hamle6-devops-001-structured-logging]]
