# IG01-B Targeted Prior-Art Review

**Status:** GENERATED EVIDENCE / read-only research input  
**Decision scope:** corpus and measurement design only

The review asks which failure classes, provenance fields and split safeguards
are missing from the existing Brain-Eleven evaluation assets. It does not copy
benchmark data, scores, or production algorithms.

| Source | Adopt for IG01-B | Reject / guardrail |
| --- | --- | --- |
| [LongMemEval paper](https://arxiv.org/abs/2410.10813) and [format](https://github.com/xiaowu0162/LongMemEval) | evidence locations, timestamps, extraction/update/abstention families, separate retrieval metrics | public release is not a DEV/VALIDATION/HOLDOUT protocol; split by lineage here |
| [LoCoMo paper](https://arxiv.org/abs/2402.17753) and [schema](https://github.com/snap-research/locomo) | turn/session IDs, evidence labels, temporal and adversarial strata | random conversation splits and external asset metadata can leak; public fixtures stay self-contained |
| [MemoryBench paper](https://arxiv.org/abs/2510.17281) | heterogeneous language/task strata and efficiency reporting | a random case split or normalized aggregate cannot replace immutable family metrics |
| [Mem0 paper](https://arxiv.org/abs/2504.19413) | explicit ADD/UPDATE/NOOP conflict labels, token and latency measurements | destructive delete and silently dropped unanswerable cases violate canonical history/abstention rules |
| [Graphiti/Zep paper](https://arxiv.org/abs/2501.13956) and [docs](https://help.getzep.com/graphiti/getting-started/overview) | episode provenance, entity/edge labels and two time axes | automatic LLM contradiction supersession is not a Brain-Eleven truth rule |
| [Letta archival memory](https://docs.letta.com/v1-sdk/memory/archival-memory) and [MemGPT paper](https://arxiv.org/abs/2310.08560) | current/archive tiers and on-demand retrieval labels | tiers/tags cannot replace evidence, scope and lifecycle labels |
| [Supermemory API/repository](https://github.com/supermemoryai/supermemory) | separate memory-vs-RAG retrieval concerns, source/provenance metadata and context-size reporting | vendor-reported benchmark scores are not imported; external connectors and opaque hosted ranking stay out of this corpus |
| [ConvoMem paper](https://arxiv.org/abs/2511.10523) and [benchmark repository](https://github.com/SalesforceAIResearch/ConvoMem) | multi-message evidence distance, user/assistant facts, changing facts and explicit abstention strata | full-context-vs-RAG comparisons are workload-dependent; no claim is generalized without same-case measurement |
| [RAG evaluation survey](https://arxiv.org/abs/2405.07437) | independent retrieval precision/recall, ranking and answerability metrics plus efficiency/noise reporting | one end-to-end answer score cannot replace candidate-level safety gates or mandatory-context recall |

Cross-source conclusions adopted by the contract:

- Keep answerability and safe abstention explicit; do not remove missing-ground-
  truth cases from denominators without recording the exclusion.
- Preserve evidence-level provenance, generator identity, SUT identity,
  contamination class, immutable content/label fingerprints and both event and
  ingestion timestamps.
- Split by project/conversation lineage where possible, and keep V1/V2 on the
  same fixtures and split in the later evaluator package.
- Report retrieval, extraction, temporal update, abstention, token and latency
  families independently. No aggregate can mask wrong-project, forbidden,
  superseded, resolved or assistant-as-user violations.
- Keep private/CI evaluation telemetry content-free and default it off.

These are design inputs only. Production intelligence remains unchanged until
IG01-C and later packages have their own evidence and independent review.
