# W-07B Native Maintenance Delivery — Independent Contract Review

**Reviewed revision:** `acebec18cd6c7da4e17ebb1d79bf71f2078f2490`  
**Contract:** `WEAKNESS-W07B-MAINTENANCE-DELIVERY-CONTRACT.md`  
**Reviewer:** independent read-only reviewer (`/root/w07b_contract_review2`)

## Verified contract properties

- Scope is bounded to native runtime coordination, a small durable
  intent/receipt surface, report projection and focused tests. Maintenance
  algorithms, ranking/retrieval, V2, Phase 20, canonical persistence and
  Markdown continuity writes are explicitly excluded.
- SessionEnd versus Stop semantics are explicit; maintenance is asynchronous
  after a terminal capture and cannot block the hook.
- Reports are required to be project/revision-bound, atomic, privacy-safe and
  content-free on errors. Stale, corrupt and cross-project reports are
  status-only and cannot be injected into context.
- Required tests cover trigger timing, crash/restart idempotence, freshness,
  wrong-project rejection, privacy/size limits, failure visibility, queue
  receipt preservation, manual parity and full regression gates.

## Residual risk

Implementation complexity remains around durable exactly-once intent handling
and freshness validation across memory/state/graph revisions; the contract
names both risks and requires evidence for them.

## Verdict

**SHIP**

This accepts the contract only. Runtime implementation remains unshipped until
the package evidence and independent implementation review pass.

