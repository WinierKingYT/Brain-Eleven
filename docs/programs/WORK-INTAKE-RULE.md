# Work intake rule — does this move the recall test?

**Status: CURRENT — owner rule, 2026-09-23.** Governs whether new IG
packages, weakness contracts, or evidence-gathering work may be opened. It
does not itself change any threshold, corpus, mode or Phase 20/V2 state.

## The problem this responds to

As of 2026-09-22 the project has a large, genuinely rigorous engineering and
evidence-review apparatus (dozens of IG packages, weakness contracts,
independent reviews) relative to what it has actually delivered to daily
use: a fresh session's real recall-test score was **0/5** (`TEST-LOG.md`).
The rigor is real and should not be diluted — no threshold lowering, no
skip, no holdout tampering, ever. The imbalance is in *what gets opened*,
not in how carefully it's executed once opened.

## The rule

Before opening any new IG package, weakness contract, or bounded evidence
package, answer one question in the proposal itself:

> **Does this measurably move the recall test, or unblock something that
> directly does?**

- **Yes, directly** (e.g., turning on `shadow_accept` and reviewing real
  candidates, fixing a bug that silently drops real capture — like
  `CAPTURE_SILENT_GAP` — anything in the hook → queue → canonical → delivery
  path a real session depends on): open it.
- **Yes, indirectly, with a stated causal chain** (e.g., "V2 recall must
  clear the promotion gate before CANARY can open, and CANARY is what lets
  `shadow_accept`'s human-reviewed content actually reach delivery" — a real
  chain, even if the payoff is a few steps away): open it, but write the
  chain down in the proposal, not just the technical goal.
- **No, or only "this is good practice"/"this closes a known gap in the
  evidence" with no stated path back to the recall test**: do not open it as
  new work. This does not mean the gap is unimportant — it means it waits,
  or it is folded into something that already qualifies, or it is logged as
  a known limitation instead of a package.

This is the same red line the owner already set for this session
("hiçbir şey ekleme, sadece kullan" / "yapay zekâ sana yeni bir faz, paket
veya değerlendirme kümesi önerirse cevap hayır") — recorded here so it
applies by default to every future proposal, not only the ones the owner
happens to catch in review.

## What this does not relax

- No threshold, corpus, holdout, Phase 20, or V2-mode change is authorized
  by this rule or by anything it lets through.
- Safety, privacy and correctness fixes are never blocked by this rule even
  when their recall-test connection is indirect — a real defect (data loss,
  leakage, silent failure) is fixed regardless. The rule governs *new
  packages*, not "should we fix a bug we already found."
- This does not retroactively judge already-shipped work. It governs what
  gets opened from 2026-09-23 forward.

## Applying it

Whoever proposes the next package — Claude, Codex, or the owner — states
the answer to the question above in the first paragraph of the proposal.
`CONTRIBUTING.md`'s Roles section already has Claude deciding the next
bounded package and writing its contract; this rule is the one-line
gate Claude applies before doing so, and the same gate Codex should expect
before starting anything not already in an approved contract.
