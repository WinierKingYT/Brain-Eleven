---
type: decision
title: OWASP Top 10 - Security Checklist
category: Security & DevOps
status: active
created: 2026-08-27
source: OWASP/CheatSheetSeries (Hamle 4)
tags: [security, owasp, checklist, vulnerabilities]
---

# OWASP Top 10 Checklist

**Pattern:** Security-First Development

## Critical Issues (Block Deployment)

| Issue | Prevention | Test |
|-------|-----------|------|
| SQL Injection | Parameterized queries | Try `' OR '1'='1` |
| XSS | Sanitize output, CSP | Try `<script>alert(1)</script>` |
| CSRF | CSRF tokens, SameSite cookies | Cross-origin POST attack |
| Broken Auth | Strong password hash, 2FA | Can bypass login? |
| Sensitive Data | Encryption, PII masking | Logs contain passwords? |

## JWT Validation Checklist

```
□ Verify signature (don't trust unverified tokens)
□ Check expiration (exp claim)
□ Validate issuer (iss claim)
□ Validate audience (aud claim)
□ Check algorithm (reject 'none')
□ Use HTTPS only (not HTTP)
□ Short expiration (15min, not 1yr)
□ Secure refresh tokens (sameSite, httpOnly)
```

## Password Security

```
✓ Use bcrypt/scrypt (slow hash)
✗ Use MD5, SHA1 (too fast, craceable)
✓ Salt included (bcrypt handles)
✓ Unique per user
✗ Plaintext never
```

## Data Classification

```
Sensitive (encrypt + mask):
- Passwords
- Credit cards
- SSN
- Medical records

Public (standard log):
- User ID
- Order status
- Product names

Never log:
- Full credit cards (last 4 OK)
- JWT tokens
- API keys
```

---

**Bağlantılar:** 
- [[hamle4-009-jwt-validation]] (JWT specifics)
- [[hamle4-010-rate-limiting]] (rate limiting)
- [[hamle6-security-001-argon2-password-hashing]] (password hashing foundation)
- [[hamle6-security-004-rate-limiting-distributed]] (DDoS protection patterns)
