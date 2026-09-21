# R0 results — real semantic + embedding provider sockets

Status: complete. No hard gate tripped, no canonical-store import was added,
and the full regression stayed green.

## Built

- Added `brain_eleven/extraction/providers/` with:
  - `openai_api.py`: production OpenAI Responses/Chat adapter, gated by
    `OPENAI_API_KEY` and the provider switch.
  - `codex_cli.py`: measurement-only, one-CLI-invocation-per-case adapter using
    ephemeral `codex exec`; it is explicitly not a production per-capture path.
  - `__init__.py`: `openai_api|codex_cli|unavailable` factory with default
    `unavailable` and fail-closed construction.
- Added `brain_eleven/retrieval/embedding_provider.py` with real OpenAI
  embeddings, an optional explicitly selected SentenceTransformers adapter,
  an explicit `EMBEDDING_UNAVAILABLE` result, and a cross-encoder reranker
  socket that remains unavailable until a real reranker is installed.
- Wired the configured semantic provider into IG-03’s optional benchmark input
  and the configured embedding socket into IG01-D without running R1.
- Added provider tests for factory selection, strict output validation,
  timeout/non-zero/invalid-output handling, import guards, content-free logs,
  and no-fake-vector behavior.

All provider output still passes through the existing frozen IG01-A proposition
builder and validator. No provider module imports `MemoryStore`, `StateStore`,
lifecycle writers, or other canonical-effect modules.

## Auth and reachability on this machine

Evidence collected on 2026-09-09:

- `OPENAI_API_KEY` environment variable: absent.
- `%USERPROFILE%/.codex/auth.json`: present; `auth_mode` is `chatgpt`; its
  `OPENAI_API_KEY` field is null. The credential itself was never read into or
  printed by this result.
- `.claude/ig-provider-config.json`: absent.
- `IG_SEMANTIC_PROVIDER` and `IG_EMBEDDING_PROVIDER`: unset.
- `sentence_transformers`: not installed.

The ChatGPT-authenticated Codex CLI is reachable. A direct ephemeral control
round-trip with model `gpt-5.6-luna` exited 0 and returned the requested JSON.
The actual adapter was then invoked once on a throwaway string and returned:

```text
provider_id=codex-cli
model=gpt-5.6-luna
status=MEASURED
error_code=None
proposition_count=0
elapsed_ms=9757.182
```

This proves the `codex_cli` auth/subprocess path is reachable now. The zero
proposition count is not a benchmark result; it is only round-trip reachability
evidence.

The OpenAI API semantic path was not reachable because no API key was supplied.
The embedding path was also not reachable: no API key, no local embedding
package, and no embedding override were present. The default factory therefore
returned explicit unavailable providers and produced no vectors.

## What the user must supply for production and R1-a

For the production semantic path, provide `OPENAI_API_KEY` through the runtime
environment or a secret manager, ensure network access to the OpenAI API, and
select it explicitly with either:

```text
IG_SEMANTIC_PROVIDER=openai_api
```

or a non-secret config file containing:

```json
{"semantic_provider": "openai_api"}
```

For R1-a embeddings, provide the same API key and explicitly select:

```text
IG_EMBEDDING_PROVIDER=openai_api
```

or add `"embedding_provider": "openai_api"` to the non-secret config. The
configured embedding model must be enabled for that API account. Alternatively,
install `sentence-transformers`, supply `IG_LOCAL_EMBEDDING_MODEL`, and select
`IG_EMBEDDING_PROVIDER=local`. A real cross-encoder/reranker is additionally
required for an R1-a embedding-plus-reranker measurement; its socket remains
unavailable until such a model is supplied.

No key or token belongs in a tracked file. With no explicit selection or with a
missing credential/model, behavior remains fail-closed and deterministic.

## Verification

```text
baseline: 819 passed, 0 failed
after R0: 827 passed, 0 failed
warnings: 2 existing dependency deprecation warnings
Bandit (new provider/embedding modules): exit 0
detect-secrets scan --baseline .secrets.baseline: exit 0
```

No R1 feasibility probe or benchmark was run manually. The full pytest suite
only exercised the existing contract-level IG01-D test; it did not perform a
real embedding measurement.
