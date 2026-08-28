---
type: decision
title: Secret Rotation Strategy - Version Tracking & Graceful Rollover
category: Security & Cryptography
status: active
created: 2026-08-28
source: HashiCorp Vault (Hamle 6)
tags: [security, secrets, rotation, key-management, versioning]
---

# Secret Rotation with Graceful Migration

**Pattern:** Versioned Secrets + Dual-Validate + Deprecation Windows

## The Problem

```
Static secrets (never rotated):
  ✗ 1-year-old compromised key still works
  ✗ No audit trail when key was used
  ✗ Insider threat = permanent access

Hard cutoff rotation:
  ✗ All consumers must update simultaneously
  ✗ Deployment lag → requests fail
  ✗ Stale caches → decryption failures
```

## Solution: Dual-Validation

```
Phase 1: Active old key + new key in parallel
  Encryption: Use new key (for new data)
  Decryption: Try new key first, fallback to old key (read old data)
  Duration: 1-7 days (cache expiry window)

Phase 2: New key only
  Encryption: Use new key
  Decryption: New key only
  Old key: marked deprecated (tracked but not used)

Phase 3: Archive old key
  Old key: moved to archive (for audit trail)
  Inaccessible for new operations
  Kept for 7-year compliance if required
```

## Implementation

```javascript
class SecretRotationManager {
  constructor(vault) {
    this.vault = vault
    this.cache = new Map()
  }
  
  // Generate new key version
  rotateSecret(secretName) {
    const newKey = crypto.randomBytes(32)
    const versionId = Date.now()
    
    const current = this.vault.get(secretName)
    
    // Mark old key as deprecated
    if (current) {
      current.deprecated = new Date()
      current.deprecationNotice = 'Replaced by new key'
      this.vault.archiveVersion(secretName, current.versionId)
    }
    
    // Store new key as active
    this.vault.set(secretName, {
      versionId,
      value: newKey,
      created: new Date(),
      status: 'active'
    })
    
    // Log rotation event
    this.vault.logEvent('secret_rotated', {
      secretName,
      oldVersionId: current?.versionId,
      newVersionId: versionId
    })
    
    return newKey
  }
  
  // Encrypt with new key
  encrypt(secretName, plaintext) {
    const activeKey = this.vault.getActive(secretName)
    const iv = crypto.randomBytes(16)
    const cipher = crypto.createCipheriv('aes-256-gcm', activeKey.value, iv)
    
    const encrypted = Buffer.concat([
      cipher.update(plaintext),
      cipher.final()
    ])
    
    return {
      versionId: activeKey.versionId,
      iv: iv.toString('hex'),
      ciphertext: encrypted.toString('hex'),
      authTag: cipher.getAuthTag().toString('hex')
    }
  }
  
  // Decrypt with fallback to old keys
  decrypt(secretName, encrypted) {
    const keys = this.vault.getAllVersions(secretName)  // [current, deprecated, ...]
    
    for (const key of keys) {
      try {
        const iv = Buffer.from(encrypted.iv, 'hex')
        const ciphertext = Buffer.from(encrypted.ciphertext, 'hex')
        const authTag = Buffer.from(encrypted.authTag, 'hex')
        
        const decipher = crypto.createDecipheriv('aes-256-gcm', key.value, iv)
        decipher.setAuthTag(authTag)
        
        const plaintext = Buffer.concat([
          decipher.update(ciphertext),
          decipher.final()
        ])
        
        // Log if using deprecated key
        if (key.status === 'deprecated') {
          this.vault.logEvent('deprecated_key_used', {
            secretName,
            versionId: key.versionId,
            usedAt: new Date()
          })
        }
        
        return plaintext
      } catch (err) {
        // Try next key
        continue
      }
    }
    
    throw new Error(`Decryption failed for ${secretName}`)
  }
}

// Usage
const manager = new SecretRotationManager(vault)

// Week 1: Rotate key
manager.rotateSecret('db_encryption_key')

// Week 1-7: Encryption uses new, decryption tries both
const encrypted = manager.encrypt('db_encryption_key', userData)
const decrypted = manager.decrypt('db_encryption_key', encrypted)  // Tries new first, then old

// Week 8: Remove old key support
vault.removeOldVersions('db_encryption_key')
```

## Rotation Schedule

```
Time-based rotation:
  Encryption keys: Every 90 days
  Database passwords: Every 30 days
  API keys: Every 12 months (critical for stability)
  Master keys: Annual (high ceremony)

Event-based rotation:
  Immediately after employee departure
  After accidental commit to git
  After suspected compromise
  Before moving to new environment

Monitoring:
  Track old key usage
  Alert if deprecated key still used after cutoff
  Monitor for rotation delays
  Audit trail for all rotations
```

---

**Bağlantılar:** [[hamle6-security-004-rate-limiting]]
