---
type: decision
title: JWT with Refresh Token Rotation - Secure Token Strategy
category: Security & Cryptography
status: active
created: 2026-08-28
source: JWT Best Practices (Hamle 6)
tags: [security, jwt, authentication, refresh-tokens, tokens]
---

# JWT Refresh Token Rotation Pattern

**Pattern:** Short-lived Access Tokens + Single-Use Refresh Tokens

## The Problem

```
Long-lived JWTs (24+ hours):
  ✗ Large exposure window if compromised
  ✗ Can't revoke early (no server lookup)
  ✗ Token theft = account compromise until expiry

localStorage storage:
  ✗ Vulnerable to XSS attacks
  ✗ No httpOnly flag = JavaScript can read

Refresh token reuse:
  ✗ Stolen refresh token usable forever
  ✗ No way to detect unauthorized use
  ✗ Attacker can keep session alive indefinitely
```

## Solution Architecture

```
Tokens:
  Access Token (JWT):
    - Lifetime: 5-15 minutes
    - Stored in: Memory or closure (NOT localStorage)
    - Sent in: Authorization header
    - Claims: userId, scopes, permissions
    - Stateless (server doesn't look up)

  Refresh Token (JWT):
    - Lifetime: 7-30 days
    - Stored in: HttpOnly Secure SameSite cookie
    - Sent by: Browser automatically (cookie)
    - Claims: userId, type: "refresh", jti: "unique ID"
    - Single-use (must rotate on each use)

Flow:
  1. Login → POST /auth/login
     ↓
     Response: access token (in body) + refresh token (in httpOnly cookie)
  
  2. Request API → GET /api/data
     Authorization: Bearer <access_token>
     ↓
     Response: 200 OK
  
  3. Access token expires → GET /api/data
     Authorization: Bearer <expired_token>
     ↓
     Response: 401 Unauthorized
  
  4. Client → POST /auth/refresh
     Cookie: refresh_token=<jti>
     ↓
     Verify refresh token (check DB)
     Delete old refresh token (mark as used)
     Generate new access token + new refresh token
     ↓
     Response: new access token + new refresh token (httpOnly)
```

## Implementation

```javascript
const issueTokens = (userId) => {
  const accessToken = jwt.sign(
    { 
      userId, 
      type: 'access',
      scope: ['read', 'write']
    },
    process.env.ACCESS_SECRET,
    { expiresIn: '15m', algorithm: 'HS256' }
  )
  
  const refreshTokenId = randomUUID()
  const refreshToken = jwt.sign(
    { 
      userId, 
      type: 'refresh',
      jti: refreshTokenId  // Unique ID for revocation
    },
    process.env.REFRESH_SECRET,
    { expiresIn: '7d', algorithm: 'HS256' }
  )
  
  // Store jti in DB to track used tokens
  db.refreshTokens.insert({
    jti: refreshTokenId,
    userId,
    issuedAt: new Date(),
    expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
    isRevoked: false
  })
  
  return { accessToken, refreshToken }
}

app.post('/auth/login', async (req, res) => {
  const user = await validateCredentials(req.body.email, req.body.password)
  const { accessToken, refreshToken } = issueTokens(user.id)
  
  res.cookie('refresh_token', refreshToken, {
    httpOnly: true,
    secure: true,          // HTTPS only
    sameSite: 'strict',    // Prevent CSRF
    maxAge: 7 * 24 * 60 * 60 * 1000  // 7 days
  })
  
  res.json({ accessToken })  // Send access token in body
})

app.post('/auth/refresh', async (req, res) => {
  const refreshToken = req.cookies.refresh_token
  if (!refreshToken) return res.status(401).json({ error: 'No refresh token' })
  
  try {
    const payload = jwt.verify(refreshToken, process.env.REFRESH_SECRET)
    
    // Check if jti is revoked
    const tokenRecord = await db.refreshTokens.findOne({ jti: payload.jti })
    if (!tokenRecord || tokenRecord.isRevoked) {
      return res.status(401).json({ error: 'Token revoked or used' })
    }
    
    // Mark old token as used (single-use)
    await db.refreshTokens.update({ jti: payload.jti }, { isRevoked: true })
    
    // Issue new tokens
    const { accessToken, refreshToken: newRefreshToken } = issueTokens(payload.userId)
    
    res.cookie('refresh_token', newRefreshToken, {
      httpOnly: true,
      secure: true,
      sameSite: 'strict',
      maxAge: 7 * 24 * 60 * 60 * 1000
    })
    
    res.json({ accessToken })
  } catch (err) {
    res.status(401).json({ error: 'Invalid token' })
  }
})

app.post('/auth/logout', async (req, res) => {
  const refreshToken = req.cookies.refresh_token
  if (refreshToken) {
    const payload = jwt.decode(refreshToken)
    // Revoke refresh token
    await db.refreshTokens.update({ jti: payload.jti }, { isRevoked: true })
  }
  
  res.clearCookie('refresh_token')
  res.json({ success: true })
})
```

## Security Considerations

```
✓ Access tokens in memory (no XSS exposure to localStorage)
✓ Refresh tokens in httpOnly cookies (no XSS access)
✓ Single-use refresh tokens (caught immediately if stolen)
✓ Short-lived access tokens (limited exposure window)
✓ Database tracking (can revoke sessions, detect anomalies)

⚠️ Trade-offs:
  - DB overhead (verify each refresh token)
  - Client-side state loss (refresh token in HttpOnly = can't access from JS)
  - Requires secure HTTPS (HttpOnly + Secure flags)
```

## Detecting Token Compromise

```
Monitor for:
  1. Multiple refresh token uses from different IPs
     → Likely theft; revoke all tokens for user
  
  2. Refresh token use after marked-as-used
     → Attacker using stolen token; revoke immediately
  
  3. Rapid token refresh (< 1 second apart)
     → Abnormal pattern; potential replay
  
  4. Geographic anomalies
     → Token issued in New York, used in Moscow within 1 hour
     → Very unlikely travel; revoke

Alert examples:
  if (tokenRecord.isRevoked && attempt) {
    logger.warn(`Token replay detected: ${payload.jti}`)
    await revokeAllTokensForUser(payload.userId)
    await sendSecurityAlert(user.email)
  }
```

---

**Bağlantılar:** [[hamle6-security-003-secret-rotation]]
