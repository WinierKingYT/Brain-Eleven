PACKAGE: W-06B
REVISION: 06644facb12c2d05cdd523d6f929adf3c0c8aa74 (implementation/evidence head)
OBJECTIVE: bounded task-aware V1 ranking for native UserPromptSubmit /api/context
FILES CHANGED: brain_eleven/runtime/storage.py; brain_eleven/runtime/context.py; brain_eleven/runtime/task_aware.py; evals/baseline.py; evals/w09a/evaluation.py; tests/test_w06b_task_aware.py; tests/test_w09a_retrieval_evaluation.py; evals/reports/w06b-*.json
ROOT CAUSES ADDRESSED: task-unaware ranking, unstable task ordering, missing runtime fallback, malformed retrieval gate handling
TESTS ADDED: W-06B gate/fallback/approval/stale/determinism tests; W-09A W-06B provider and DEV/TEST split tests
TESTS EXECUTED: focused runtime suite 77 passed, 2 warnings; W-09A evaluation suite 11 passed; full suite at review baseline 1081 passed, 2 warnings; critical flake8/compileall/diff-check passed; W-09A W06B/V1 DEV+TEST reports generated; operational benchmark 30 repetitions per task passed latency/item-count gates
QUALITY METRICS BEFORE: V1 DEV precision 0.165714, recall 0.714286, mandatory recall 0.714286, MRR 0.454524, noise 0.834286, token waste 0.828697; V1 TEST precision 0.180000, recall 0.825000, mandatory recall 0.825000, MRR 0.491944, noise 0.820000, token waste 0.814245
QUALITY METRICS AFTER: W06B DEV precision 0.182857, recall 0.800000, mandatory recall 0.800000, MRR 0.448095, noise 0.802857, token waste 0.800778; W06B TEST precision 0.176667, recall 0.841667, mandatory recall 0.841667, MRR 0.424722, noise 0.740000, token waste 0.736258
SAFETY METRICS: DEV/TEST wrong-project=0, forbidden=0, superseded=0, resolved=0; runtime scope/approval/secret/stale guards covered; operational max selected=5, p95 warm/cold <=1.27ms on frozen harness
ROLLBACK EVIDENCE: retrieval_mode defaults/invalid values fail closed to V1_LEGACY; explicit rollback and non-UserPrompt parity pass; SessionStart remains V1
KNOWN LIMITATIONS: Contract quality target precision >=0.60 is not met on either public split; W06B TEST MRR regresses versus V1; mandatory-overflow fault-injection evidence remains incomplete; holdout was not used for tuning
OPEN FAILURES: Lexical task-aware ranking fails the frozen precision and TEST MRR gates; no score increase is justified.
INDEPENDENT REVIEW: RETHINK (WEAKNESS-W06B-INDEPENDENT-REVIEW.md, a26912c)
SCORE BEFORE: retrieval quality 4.5/10; context compilation 6.8/10
SCORE AFTER: unchanged; evidence shows recall/noise improvement but the quality gate remains failed
VERDICT: RETHINK
