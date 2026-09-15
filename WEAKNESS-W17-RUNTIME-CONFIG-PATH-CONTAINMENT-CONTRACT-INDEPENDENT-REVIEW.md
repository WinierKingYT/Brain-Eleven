# W-17 Runtime Path Containment — Contract Independent Review

**Contract revision:** `5054dda8d58452d58e40950eaf683f70408f6444`  
**Verdict:** **SHIP**

The contract is bounded to vault-owned `.brain-eleven/runtime/**` paths and
keeps host Claude/Codex configuration as a separate filesystem policy.  It
requires component-level `lstat()` checks, Windows reparse detection,
containment and escape rejection, pre-lock/pre-temp validation, final-file
symlink behavior, and explicit fail-closed handling when a path swap cannot be
made race-safe.

The required caller audit covers RuntimeConfig, installer, worker, launcher,
review, maintenance, service, graduation and telemetry writes.  Existing
W-15 lock/CAS/fingerprint behavior, JSON schema, atomic write path and
canonical authorities remain protected boundaries.  The symlink, junction,
escape, external-effect, path-swap and regular-path parity tests are sufficient
for an implementation review, and the 120–260 production LOC estimate is
realistic for a shared primitive.

**SHIP** — implementation may proceed within the contract; this review does
not accept any implementation.
