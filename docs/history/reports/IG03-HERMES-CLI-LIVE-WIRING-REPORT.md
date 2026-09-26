# IG-03 follow-up: wiring a live semantic provider (Hermes CLI) into capture

**Status:** BUILT, TESTED, AND BENCHMARKED (2026-09-23 IG-03 run, see
limitation 4 below). Currently **enabled** via
`.claude/ig-provider-config.json` (`{"semantic_provider": "hermes_cli"}`).
Every candidate it produces still requires human review before reaching
canonical memory — see "How to enable" below. Written 2026-09-23.

## Why

`IG03-PACKAGE-REPORT.md` froze a proposal-only semantic extraction boundary
(`brain_eleven/extraction/semantic.py`) but explicitly did not wire it into
the live capture path: "No canonical writer, lifecycle mutation, retrieval
path or V2 runtime path was changed." As a result, every review candidate
the running worker ever produced was either a verbatim/lightly-classified
segment of what the user typed (`DeterministicExtractor`) or required an
already-configured local HTTP model endpoint (`brain_eleven/runtime/model.py`'s
`propose()`, gated by a `local_model` config value nobody had set). Asked
directly, Ahmet confirmed this was not what he wanted: "benim yazdıklarımı
değil konuşmalardaki değerli şeyleri istiyorum" (not what I typed — the
valuable things in the conversation).

## What was built

1. **`brain_eleven/extraction/providers/hermes_cli.py`** — a new
   `SemanticProvider` implementation, same shape as the existing
   `codex_cli.py` adapter: one ephemeral `hermes -z <prompt> --ignore-rules`
   invocation per case, parsed as JSON, validated by the existing frozen
   IG01-A proposition schema (`brain_eleven/extraction/semantic.py`'s
   `CallableSemanticProvider` — unchanged). Uses the Hermes Agent CLI
   already installed and authenticated on this machine (`ChatGPT or Codex
   Subscription`, per `hermes status`) — no separate API key, no new
   credential. `--ignore-rules` prevents the CWD's own AGENTS.md/memory/
   rules from leaking into the classification call.
2. **`brain_eleven/extraction/providers/__init__.py`** — registered
   `hermes_cli` as a third `SUPPORTED_PROVIDERS` value alongside
   `codex_cli`/`openai_api`, selectable the same way (env var or config
   file), defaulting to `UnavailableProvider` (a no-op) when not selected.
3. **`brain_eleven/runtime/worker.py`** — the actual live wiring:
   - `Worker.__init__` now constructs `self.semantic_provider =
     create_semantic_provider()` once.
   - A new `_semantic_review_candidates(provider, message, project_id)`
     generator runs per captured message, alongside (not instead of) the
     existing `DeterministicExtractor` and `local_model` paths.
   - **Deliberately narrow for a first version:** only propositions with
     `commitment == "committed"` and a `claim_type` that already maps onto
     an existing `MemoryType` (`decision, lesson, preference, observation,
     open_loop`) are converted into a review candidate. `requirement`,
     `blocker`, `no_commitment`, and any non-committed commitment
     (`proposed/hypothetical/question/negated/quoted/observed/uncertain`)
     are skipped, not forced into the wrong shape — matching this
     project's existing "quarantine on uncertainty" posture.
   - **Deliberately always review-gated.** Unlike the deterministic path
     (which can auto-apply outside SHADOW/`b1_human_approval`), semantic
     candidates are unconditionally pushed to `_add_review` with a new
     reason code `SEMANTIC_REVIEW_REQUIRED` (added to `_REVIEW_REASONS`).
     This is new, non-deterministic, LLM-based output; it does not get the
     auto-apply trust the audited deterministic extractor has, regardless
     of runtime mode.
   - Never raises into the worker's real processing loop:
     `provider.extract()` already converts transport/timeout/parse
     failures into a `SEMANTIC_UNAVAILABLE` result (existing
     `CallableSemanticProvider` behavior, unchanged), and the new generator
     additionally treats any unexpected proposition shape as skippable.

## Tested

- `HermesCLIProvider._call()` against the real installed CLI: clean JSON
  output, ~7-9s latency per call, works with realistic message-length
  content (~2100 chars tested explicitly).
- End-to-end through the full validation pipeline
  (`create_semantic_provider` → `HermesCLIProvider.extract` →
  `CallableSemanticProvider`): a real "Our decision is to use SQLite with
  WAL mode..." message produced a correctly-typed, correctly-scoped
  `SemanticProposition` (`claim_type=decision, commitment=committed`,
  `confidence=0.99`), with `project_id`/`evidence_refs` correctly
  authority-injected from the evidence, not the model.
- `_semantic_review_candidates` against a real `EvidenceMessage`: produces
  the expected `NEW_MEMORY` candidate dict, compatible with both
  `_add_review` and `apply_candidate`'s exact field expectations.
- A question/uncertain-phrased message ("Should we maybe use SQLite
  instead? Not sure yet.") correctly produces **zero** candidates — the
  filter does not fabricate a decision from an open question.
- Full relevant test surface (`test_capture_provenance`, `test_ig00_bootstrap`,
  `test_ig02_capture_closure`, `test_ig04_b1_human_approval`,
  `test_ig04_b1_p2_coverage`, `test_pre13_runtime`, `test_shadow_accept`,
  `test_w02_terminal_state`, `test_w03b_transcript_ownership`,
  `test_w05_prompt_event`, `test_w06b_task_aware`,
  `test_w07b_maintenance_delivery`, `test_w10_v2_delivery_gate`,
  `test_w24_memory_truth_safety`, `test_ig03_semantic_extraction`,
  `test_ig_provider`): **275 passed**, no regressions from these changes.

## Known limitations (v1, honestly not yet resolved)

1. **Argument-length cap.** Hermes's one-shot mode (`-z PROMPT`) takes the
   prompt as a process argument, not stdin (unlike the Codex CLI adapter,
   which pipes via stdin to avoid exactly this). `hermes_cli.py` guards
   this explicitly (`MAX_PROMPT_CHARS = 6000`, raises before invoking
   rather than risking a silent OS-level truncation/failure), but a long
   message is simply skipped (becomes `SEMANTIC_UNAVAILABLE`), not
   chunked or summarized first. Not fixed here.
2. **`hermes proxy` (the natural OpenAI-compatible-endpoint alternative
   that would have reused the already-wired `local_model` config path in
   `model.py` with zero new worker.py code) could not be evaluated in this
   session** — starting a local proxy server was blocked by this sandbox's
   own safety classifier ("Traffic Redirection"). It also forwards to a
   different upstream (`Nous Portal`/`xAI`) than the `ChatGPT or Codex
   Subscription` backend this report's quality testing used via `-z`, so
   its output quality is unverified either way. Worth revisiting outside
   a sandboxed session if the per-call CLI-spawn latency (~7-9s) becomes a
   real bottleneck.
3. **Latency.** ~7-9s per Hermes call, once per captured message (not per
   message segment). Acceptable for background/async capture processing
   (not blocking interactive use), but real for busy sessions — not
   load-tested at volume.
4. **Extraction quality now benchmarked (2026-09-23).** Ran
   `evals/ig03/run_hermes_benchmark.py` — the same `benchmark_providers()`
   IG-03 already used for `codex_cli`/`openai_api`, applied to
   `HermesCLIProvider` on the frozen `dev` (49 cases) and `validation`
   (25 cases) splits, `regex` (`DeterministicRegexProvider`) as control.
   Raw output: `docs/history/evidence/ig03-hermes-benchmark-result.json`.
   Pooled dev+validation (74 cases):

   | metric | hermes_cli | regex (control) |
   |---|---|---|
   | decision_recall | 1.00 (6/6) | 0.67 (4/6) |
   | decision_precision | 0.18 (6/33) | 0.50 (4/8) |
   | wrong_type_rate | 0.46 (29/63) | 0.94 (63/67) |
   | false_commitment_rate | 0.00 (0/6) | 0.00 (0/6) |
   | ece (10-bin, lower=better) | 0.88 | 0.94 |
   | unusable (FILTERED+INVALID_OUTPUT) | 11/74 (15%) | 7/74 (9%, all FILTERED) |

   Reading: Hermes classifies the correct `claim_type`/`scope` far more
   often than the regex baseline (46% wrong-type vs 94% wrong-type — the
   regex baseline is barely better than chance at typing, which is
   consistent with it being a proposal control, not a real classifier) and
   never misses a real decision (recall 1.00). But it over-labels things as
   `decision` — precision 0.18 means roughly 5 of every 6 things it calls a
   decision aren't one — and both providers are badly overconfident
   (ECE 0.88-0.94 on a 0-1 scale where 0 is perfect calibration; `confidence`
   values do not track actual correctness for either provider). Hermes also
   produced unusable output (non-JSON or the `MAX_PROMPT_CHARS` guard) on
   15% of cases, worse than the regex control's 9% (which is only
   IG01-C's category-based `FILTERED`, never an invalid-output failure —
   regex generation can't emit malformed JSON).

   **Conclusion:** confirms the manual 2-case spot-check's direction (real
   semantic typing, better than the deterministic baseline) but the
   benchmark surfaces two problems invisible to those 2 cases: chronic
   `decision` over-labeling and a real (not hypothetical)
   unusable-output rate. Neither blocks the existing design — every
   candidate is still human-review-gated (`SEMANTIC_REVIEW_REQUIRED`,
   never auto-applied) — but the low decision-precision means a reviewer
   should expect to reject most `decision`-typed suggestions specifically,
   and the confidence field should not be trusted or surfaced as a
   reliability signal until calibration improves. Not a benchmark blocker
   for continuing to run Hermes in SHADOW-reviewed capture; worth
   revisiting if `decision` review-queue rejection rate in practice matches
   this prediction.

## How to enable

Not on by default. To activate in the actually-running worker service,
create `.claude/ig-provider-config.json`:

```json
{"semantic_provider": "hermes_cli"}
```

or set `IG_SEMANTIC_PROVIDER=hermes_cli` in the worker service's own
environment (not just an interactive shell — the config file is the
reliable path for a background service). To disable, remove the file or
set the value back to `"unavailable"`.

Regardless of this setting, every resulting candidate still requires
human review (`python -m brain_eleven review`) before it reaches canonical
memory — this follow-up does not change `shadow_accept`, Phase 20, or V2.
