# Brain-Eleven v3 — Current Project Status

**Last updated:** 2026-08-31
**Scope decision:** Personal, local-first memory system
**Overall status:** 🟡 Phase 14 scope-aware cross-project memory implemented; registry and type-aware identity hardening in progress

This file describes the repository as it exists now. It is intentionally evidence-based: implemented code is separated from claims that still need to be verified in a real runtime.

## What the project is

Brain-Eleven is a personal memory system built around an Obsidian vault and local Python services. Its canonical memory store is `.claude/validated-memory.json`; Markdown notes are compiled into structured memories, validated, searched, analyzed, and surfaced back into future sessions.

The current product boundary is deliberately narrow:

- Single user
- Local-first operation
- File-backed canonical memory
- Optional OpenAI embeddings
- No multi-user or cloud platform roadmap at this time

## Current implementation

| Area | Status | Evidence |
|---|---|---|
| Vault structure and session hooks | ✅ Implemented | `CLAUDE.md`, `.claude/settings.json`, `.claude/hooks/` |
| Memory compilation | ✅ Implemented | `scripts/memory-compiler.py` |
| Validation, deduplication and conflict detection | ✅ Implemented | `scripts/memory-validator.py` |
| ULID identity, provenance and lifecycle | ✅ Implemented | `scripts/memory-lifecycle.py` and validator persistence |
| Lexical retrieval | ✅ Implemented | `scripts/memory-retriever.py` |
| Semantic and hybrid search | ✅ Implemented | `scripts/semantic-search.py`, `scripts/hybrid-search.py` |
| ML-style candidate ranking | ✅ Implemented | `scripts/ml-ranker.py` |
| Multi-level cache | ✅ Implemented | `scripts/cache_manager.py` |
| Auto-summary and anomaly detection | ✅ Implemented | `scripts/summarizer.py`, `scripts/anomaly_detector.py` |
| Knowledge graph | 🟡 Implemented with revisioned projection/recovery checks; runtime verification pending | In-process NetworkX graph in `scripts/knowledge_graph.py` |
| Rule-based chat interface | ✅ Implemented | `scripts/chat_interface.py` |
| REST API | ✅ Implemented | 21 routes in `scripts/search-api.py` |
| Docker and CI scaffolding | ✅ Present; runtime verification pending | `Dockerfile`, `docker-compose.yml`, `.github/workflows/` |
| Post-session maintenance | ✅ Implemented | `scripts/post_session_maintenance.py` and SessionEnd hook |
| Cross-project memory capture | ✅ Implemented; explicit opt-in remains fail-closed | `scripts/remember.py`, `scripts/remember_opt_in.py` |
| Memory scope and project identity | 🟡 Registry-backed identity implemented; migration/runtime verification pending | `scripts/memory_scope.py`, `scripts/project_registry.py`, `scripts/migrate-memory-scope.py` |
| Scope-aware dedup and conflict detection | 🟡 Type-aware fingerprint implemented; legacy migration/runtime verification pending | `scripts/memory-validator.py`, `scripts/memory_scope.py`, `scripts/memory_store_lock.py` |
| Canonical store transactions and CAS | 🟡 Revisioned `MemoryStore` integrated into canonical writers; runtime verification pending | `scripts/memory_store.py`, `scripts/memory-validator.py`, `scripts/memory-lifecycle.py`, `scripts/search-api.py` |
| Scope-aware retrieval and context bootstrap | ✅ Implemented | `scripts/context-compiler.py`, `scripts/hybrid-search.py`, `scripts/search-api.py` |
| Project provenance in knowledge graph | 🟡 Revisioned projection, stale/corrupt detection and rebuild oracle implemented; runtime verification pending | `scripts/entity_extractor.py`, `scripts/knowledge_graph.py` |
| Reproducible global Claude integration | ✅ Installer and templates present | `scripts/install-cross-project-memory.py`, `templates/claude/` |

## Phase history

The original Phase 7–12 planning documents are now historical. The implementation has moved through Phase 13.

| Phase | Focus | Current state |
|---|---|---|
| 1 | Foundation and vault integration | ✅ Complete |
| 2 | Memory compiler | ✅ Complete |
| 3 | Memory validator | ✅ Complete |
| 4 | Memory retrieval | ✅ Complete |
| 5 | Integrity, ULIDs and provenance | ✅ Complete |
| 6 | Regression testing and optimization | ✅ Complete |
| 7 | Semantic search, hybrid search and ranking | ✅ Complete |
| 8A | Docker containerization | ✅ Implemented |
| 8B | GitHub Actions CI/CD | ✅ Implemented; GitHub run still needs confirmation |
| 8C | FastAPI service | ✅ Implemented |
| 9A | L1/L2/L3 caching | ✅ Implemented |
| 9B | Performance tests | ✅ Implemented |
| 10A | Memory digest and summarization | ✅ Implemented |
| 10B | Anomaly detection | ✅ Implemented |
| 11A/B | Entity extraction and knowledge graph | 🟡 NetworkX projection has canonical revision metadata and recovery checks; no Neo4j dependency |
| 11C | Rule-based chat | ✅ Implemented |
| 12 | Post-session maintenance integration | ✅ Implemented |
| 13 | Cross-project memory capture with explicit opt-in | ✅ Implemented; runtime verification pending |
| 14 | Scope-aware identity, retrieval, graph provenance and safe global integration | 🟡 Registry/fingerprint, retrieval and revisioned graph projection slices implemented; runtime verification pending |

Recent commits support Phases 8A–13. Phase 14 is the current working-tree implementation and is not committed yet.

## Repository snapshot

These are static counts from the current working tree, not performance or pass-rate claims:

```text
Python production code:  6,115 lines under scripts/
Python test code:        3,091 lines under tests/
Test files:                 12
Discovered test functions: 244
Scripts:                    30 files
API routes:                 21
```

Current memory-store snapshot:

```text
Total records: 46
Active:       21
Resolved:      2
Superseded:   23
```

## Architecture at a glance

```text
Obsidian Markdown notes
        │
        ▼
Memory Compiler
        │
        ▼
Memory Validator ──► MemoryStore ──► validated-memory.json
        │                 │
        │                 └─ scope: global | project + opaque project_id
        │
        └─ file lock + reload + revision/CAS + atomic write for concurrent writers
        │                       │
        ├─► Retriever            ├─► Digest / anomaly detection
        ├─► Semantic search      ├─► Knowledge graph
        ├─► Hybrid search        └─► Rule-based chat
        └─► ML ranking
                │
                ▼
          Scope policy
          current project + global by default
          other projects only via explicit all scope
                │
                ▼
          FastAPI REST API
                │
       L1 memory / L2 Redis / L3 disk cache
```

The canonical data path is file-backed. Redis is used as a cache. PostgreSQL is declared in Docker Compose, but the current application does not contain a PostgreSQL driver or persistence adapter; it should not be described as an active database layer yet.

## Verification status

### Verified by repository inspection

- Docker Compose configuration parses successfully.
- The API has health, status, search, ranking, embedding, memory CRUD, cache, digest, anomaly, graph, chat and metrics routes.
- The memory store contains 46 records with the status distribution above.
- Scope policy is centralized in `scripts/memory_scope.py`: records without
  legacy project metadata are global; project-root identity is a short hash of
  the normalized root and the display label is stored separately.
- The migration is idempotent and preserves `memory_id`, lifecycle fields and
  legacy project labels; it creates a pre-scope backup before writing.
- Global Claude integration is reproducible through
  `scripts/install-cross-project-memory.py`; installation preserves unrelated
  settings and uninstall skips user-modified managed files.

### Not verified in this environment

- The full pytest suite could not be executed because no Python interpreter is installed on this host.
- Docker services could not be started because the Docker daemon was unavailable.
- A current GitHub Actions run was not independently confirmed.
- Production latency and backup-restore behavior have not been measured in this session.

Therefore, “implemented” below means present in source and tests; it does not mean that the current runtime is proven green.

## Open risks and known gaps

### High priority

1. **Local session hook drift:** the repository’s `.claude/settings.json` references `.claude/hooks/prompt-counter.sh`, but that file is not present. The UserPromptSubmit hook is therefore not currently trustworthy.
2. **Runtime migration and installer verification:** Python is not installed in this environment, so the Phase 14 tests, migration, and installer have not been executed here.
3. **Container healthcheck mismatch:** `Dockerfile` checks health by importing `requests`, but `requests` is not a direct dependency in `requirements.txt`.
4. **Unauthenticated Compose default:** `BRAIN_ELEVEN_API_KEY` defaults to empty in Compose while the API binds to `0.0.0.0` inside the container. This is acceptable only when the deployment boundary is genuinely trusted and the service is not exposed beyond it.

### Medium priority

5. **Integration-test signal is weak:** the test tree currently has no `@pytest.mark.integration` tests, while CI invokes a separate integration-test selection and allows that job to fail. The job should either contain real marked tests or be removed.
6. **Documentation drift:** older planning and orchestration documents still describe Phase 7–11 as future or in-progress work. They should be marked historical or updated so future sessions do not treat them as active instructions.
7. **Deployment surface is larger than the personal-use scope:** Docker, PostgreSQL, CI publishing, SARIF and multi-service operations add maintenance cost without currently adding personal-use value.

## Recommended next steps

### Immediate hardening

1. Run the complete Phase 14 suite in Python 3.13 and confirm GitHub Actions is green.
2. Run the scope migration against a backup/copy of the canonical store and verify current-project bootstrap from a non-vault project.
3. Run the installer in dry-run mode, then install/uninstall in a test home; only then use it for the real global Claude configuration.
4. Restore or remove the missing `prompt-counter.sh` hook and test all configured hooks.
5. Change the Docker healthcheck to use an installed dependency or a standard-library check.
6. Make authenticated deployment the safe default, or bind Compose ports to localhost explicitly.

### Evidence loop

1. Run `pytest tests/ -q` in Python 3.13.
2. Run the coverage command used by CI and record the actual result.
3. Start the Compose stack and verify `/health`, cache fallback, API-key protection and backup/restore.
4. Use the system daily for one week before adding another feature.

### Simplification

After the evidence loop, decide whether Docker, PostgreSQL declarations, CI publishing and old phase documents still earn their maintenance cost for a single-user local system. Do not add multi-user, cloud or “market-ready” work unless the product boundary changes explicitly.

## Definition of “solid enough” for this project

Brain-Eleven is ready for dependable personal use when:

- The complete test suite passes in a reproducible Python environment.
- Memory writes are atomic across compiler, validator and API paths.
- Project-specific memory cannot deduplicate with another project or create a
  cross-project contradiction during normal validation.
- Default retrieval includes only global and current-project memory; all-project
  retrieval is explicit.
- Graph memory nodes retain project provenance through `BELONGS_TO` edges.
- Session hooks either run successfully or fail visibly.
- A backup can be restored into a fresh directory and queried.
- Local API exposure is intentional and protected when it is not loopback-only.
- The status file and active instructions describe the same system as the code.

## Primary references

- [CLAUDE.md](CLAUDE.md) — vault routing and memory protocol
- [🧠 Brain-Eleven.md](🧠%20Brain-Eleven.md) — vault hub
- [DEPLOYMENT-STACK.md](DEPLOYMENT-STACK.md) — deployment notes
- [TESTING-FRAMEWORK.md](TESTING-FRAMEWORK.md) — testing design and targets
- [INTEGRATION-CHECKLIST.md](INTEGRATION-CHECKLIST.md) — integration checklist
