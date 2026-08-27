---
type: decision
title: UTF-8 Encoding - Common Pitfalls and Solutions
category: Engineering Mindset & Foundations
status: active
created: 2026-08-27
source: mtdvio/every-programmer-should-know (Hamle 4)
tags: [encoding, utf-8, internationalization, strings]
---

# UTF-8 Encoding Pitfalls

**Pattern:** Character vs Byte Confusion

## UTF-8 Basics

```
Character: "é" (one character)
UTF-8 bytes: C3 A9 (two bytes)
String length: 1 character, 2 bytes

❌ Bug:
  str = "café"
  str[3] == 'é'  // False! UTF-8 multi-byte issue

✓ Fix:
  Use grapheme clusters or string libraries
```

## Common Problems

**1. Length Calculation**
```
❌ String len in bytes
  "😀" = 4 bytes (but 1 character)
  len("😀") = 4 (wrong!)

✓ Count Unicode characters
  "😀".length = 1 ✓
```

**2. Substring Extraction**
```
❌ Byte-based slicing
  "café"[0:2] = "ca" + partial 'é' = invalid UTF-8

✓ Character-based slicing
  "café"[0:2] = "ca"
```

**3. Database Storage**
```
❌ Latin1 encoding
  INSERT INTO users (name) VALUES ('Müller')
  // Some characters corrupted

✓ UTF-8 encoding
  CREATE TABLE users (name VARCHAR(100) CHARACTER SET utf8mb4)
```

**4. BOM (Byte Order Mark)**
```
UTF-8 BOM: EF BB BF (unnecessary, causes issues)

❌ Save with BOM
  JSON parser sees: BOM + { ... }
  → Parsing fails!

✓ Save without BOM (UTF-8 no BOM)
```

## File Encoding Declaration

```
Python:
  # -*- coding: utf-8 -*-
  # Or Python 3 (default UTF-8)

HTML:
  <meta charset="UTF-8">

Java:
  Files.write(path, content, StandardCharsets.UTF_8)
```

---

**Bağlantılar:** [[mtdvio/every-programmer-should-know]]
