"""Real embedding socket with an explicit unavailable state.

No deterministic or hash-seeded vector is produced here. The OpenAI path is
selected only by explicit configuration and an environment-provided API key;
a local SentenceTransformers path is optional and likewise explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
import os
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Protocol, Sequence

from brain_eleven.extraction.providers.common import ProviderConfigurationError


class EmbeddingStatus(str, Enum):
    EMBEDDING_AVAILABLE = "EMBEDDING_AVAILABLE"
    EMBEDDING_UNAVAILABLE = "EMBEDDING_UNAVAILABLE"


@dataclass(frozen=True)
class EmbeddingResult:
    status: str
    provider_id: str
    model: str
    vectors: tuple[tuple[float, ...], ...] = ()
    error_code: str | None = None
    elapsed_ms: float | None = None

    def __post_init__(self) -> None:
        if self.status not in {item.value for item in EmbeddingStatus}:
            raise ValueError("unknown embedding status")
        if not self.provider_id or not self.model:
            raise ValueError("embedding provider identity is required")
        if self.error_code is not None and (not self.error_code or len(self.error_code) > 64):
            raise ValueError("embedding error code is invalid")
        if self.elapsed_ms is not None and (self.elapsed_ms < 0 or not math.isfinite(float(self.elapsed_ms))):
            raise ValueError("embedding elapsed_ms is invalid")
        for vector in self.vectors:
            if not vector or any(not math.isfinite(float(value)) for value in vector):
                raise ValueError("embedding vectors must contain finite values")


class EmbeddingProvider(Protocol):
    provider_id: str
    model: str

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        ...


class Reranker(Protocol):
    provider_id: str

    def rerank(self, query: str, candidates: Sequence[str]) -> "RerankerResult":
        ...


@dataclass(frozen=True)
class RerankerResult:
    status: str
    provider_id: str
    scores: tuple[float, ...] = ()
    error_code: str | None = None


class UnavailableEmbeddingProvider:
    """Explicit no-vector result; never fabricates semantic evidence."""

    def __init__(self, provider_id: str = "unavailable", model: str = "unavailable", reason: str = "not_configured") -> None:
        self.provider_id = provider_id
        self.model = model
        self.reason = reason

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        del texts
        return EmbeddingResult(
            status=EmbeddingStatus.EMBEDDING_UNAVAILABLE.value,
            provider_id=self.provider_id,
            model=self.model,
            error_code=self.reason,
        )

    def embed_text(self, text: str) -> EmbeddingResult:
        return self.embed((text,))


class OpenAIEmbeddingProvider:
    """OpenAI embeddings adapter; credentials are never stored by this class."""

    provider_id = "openai-embeddings"

    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        timeout_s: float = 30.0,
    ) -> None:
        if not model.strip():
            raise ProviderConfigurationError("invalid_model")
        if timeout_s <= 0:
            raise ProviderConfigurationError("invalid_timeout")
        if client is None:
            if not api_key:
                raise ProviderConfigurationError("missing_api_key")
            try:
                from openai import OpenAI
            except ImportError as error:
                raise ProviderConfigurationError("openai_sdk_not_installed") from error
            try:
                client = OpenAI(api_key=api_key, timeout=timeout_s, max_retries=0)
            except Exception as error:
                raise ProviderConfigurationError("openai_client_init_failed") from error
        self.client = client
        self.model = model
        self.timeout_s = timeout_s

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        client: Any | None = None,
    ) -> "OpenAIEmbeddingProvider":
        values = os.environ if environ is None else environ
        return cls(
            client=client,
            api_key=values.get("OPENAI_API_KEY"),
            model=values.get("IG_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            timeout_s=float(values.get("IG_OPENAI_EMBEDDING_TIMEOUT_S", "30")),
        )

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        started = perf_counter()
        if isinstance(texts, (str, bytes)) or any(not isinstance(text, str) for text in texts):
            return EmbeddingResult(
                status=EmbeddingStatus.EMBEDDING_UNAVAILABLE.value,
                provider_id=self.provider_id,
                model=self.model,
                error_code="invalid_input",
                elapsed_ms=round((perf_counter() - started) * 1000, 3),
            )
        values = list(texts)
        if not values:
            return EmbeddingResult(
                status=EmbeddingStatus.EMBEDDING_AVAILABLE.value,
                provider_id=self.provider_id,
                model=self.model,
                vectors=(),
                elapsed_ms=round((perf_counter() - started) * 1000, 3),
            )
        try:
            response = self.client.embeddings.create(model=self.model, input=values)
            rows = getattr(response, "data", None)
            if rows is None and isinstance(response, Mapping):
                rows = response.get("data")
            if not isinstance(rows, Sequence) or len(rows) != len(values):
                raise ValueError("embedding response length mismatch")
            def index_for(item: Any) -> int:
                value = getattr(item, "index", None)
                if value is None and isinstance(item, Mapping):
                    value = item.get("index", 0)
                return int(value or 0)
            ordered = sorted(rows, key=index_for)
            vectors: list[tuple[float, ...]] = []
            for item in ordered:
                vector = getattr(item, "embedding", None)
                if vector is None and isinstance(item, Mapping):
                    vector = item.get("embedding")
                if isinstance(vector, (str, bytes)) or not isinstance(vector, Sequence):
                    raise ValueError("embedding vector is invalid")
                vectors.append(tuple(float(value) for value in vector))
            return EmbeddingResult(
                status=EmbeddingStatus.EMBEDDING_AVAILABLE.value,
                provider_id=self.provider_id,
                model=self.model,
                vectors=tuple(vectors),
                elapsed_ms=round((perf_counter() - started) * 1000, 3),
            )
        except Exception:
            return EmbeddingResult(
                status=EmbeddingStatus.EMBEDDING_UNAVAILABLE.value,
                provider_id=self.provider_id,
                model=self.model,
                error_code="provider_call_failed",
                elapsed_ms=round((perf_counter() - started) * 1000, 3),
            )

    def embed_text(self, text: str) -> EmbeddingResult:
        return self.embed((text,))


class LocalSentenceTransformerProvider:
    """Optional local real-model adapter, loaded only when explicitly selected."""

    provider_id = "sentence-transformers"

    def __init__(self, model_name: str) -> None:
        if not model_name.strip():
            raise ProviderConfigurationError("local_model_not_configured")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise ProviderConfigurationError("local_embedding_not_installed") from error
        try:
            self.model = model_name
            self._model = SentenceTransformer(model_name)
        except Exception as error:
            raise ProviderConfigurationError("local_embedding_init_failed") from error

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        started = perf_counter()
        try:
            values = list(texts)
            vectors = self._model.encode(values, convert_to_numpy=True)
            return EmbeddingResult(
                status=EmbeddingStatus.EMBEDDING_AVAILABLE.value,
                provider_id=self.provider_id,
                model=self.model,
                vectors=tuple(tuple(float(value) for value in vector) for vector in vectors),
                elapsed_ms=round((perf_counter() - started) * 1000, 3),
            )
        except Exception:
            return EmbeddingResult(
                status=EmbeddingStatus.EMBEDDING_UNAVAILABLE.value,
                provider_id=self.provider_id,
                model=self.model,
                error_code="provider_call_failed",
                elapsed_ms=round((perf_counter() - started) * 1000, 3),
            )

    def embed_text(self, text: str) -> EmbeddingResult:
        return self.embed((text,))


class UnavailableReranker:
    """Cross-encoder socket reserved until a real local model is installed."""

    provider_id = "unavailable-reranker"

    def rerank(self, query: str, candidates: Sequence[str]) -> RerankerResult:
        del query, candidates
        return RerankerResult(
            status=EmbeddingStatus.EMBEDDING_UNAVAILABLE.value,
            provider_id=self.provider_id,
            error_code="cross_encoder_not_configured",
        )


def _selected_embedding_provider(
    *,
    config_path: Path | str | None,
    environ: Mapping[str, str],
) -> str:
    explicit = environ.get("IG_EMBEDDING_PROVIDER")
    if explicit is not None:
        return explicit.strip().lower()
    path = Path(config_path) if config_path is not None else Path(environ.get("IG_PROVIDER_CONFIG", ".claude/ig-provider-config.json"))
    if not path.is_file():
        return "unavailable"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("embedding config is unreadable") from error
    if not isinstance(payload, Mapping):
        raise ValueError("embedding config must be an object")
    selected = payload.get("embedding_provider", payload.get("provider", "unavailable"))
    if not isinstance(selected, str):
        raise ValueError("embedding selection must be a string")
    return selected.strip().lower()


def create_embedding_provider(
    *,
    config_path: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
    openai_client: Any | None = None,
) -> EmbeddingProvider:
    """Create the configured real provider, failing closed to no vectors."""

    values = os.environ if environ is None else environ
    try:
        selected = _selected_embedding_provider(config_path=config_path, environ=values)
        if selected == "openai_api":
            return OpenAIEmbeddingProvider.from_environment(environ=values, client=openai_client)
        if selected == "local":
            return LocalSentenceTransformerProvider(values.get("IG_LOCAL_EMBEDDING_MODEL", ""))
        if selected == "unavailable":
            return UnavailableEmbeddingProvider()
        return UnavailableEmbeddingProvider(reason="unknown_provider")
    except Exception as error:
        reason = getattr(error, "reason_code", "provider_construction_failed")
        if not isinstance(reason, str) or not reason:
            reason = "provider_construction_failed"
        return UnavailableEmbeddingProvider(reason=reason[:64])


__all__ = [
    "EmbeddingProvider",
    "EmbeddingResult",
    "EmbeddingStatus",
    "LocalSentenceTransformerProvider",
    "OpenAIEmbeddingProvider",
    "Reranker",
    "RerankerResult",
    "UnavailableEmbeddingProvider",
    "UnavailableReranker",
    "create_embedding_provider",
]
