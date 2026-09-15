#!/usr/bin/env python3
"""
Brain-Eleven Embedding Generator
Generate and cache vector embeddings for semantic search

OpenAI embeddings (text-embedding-3-small):
- 1536 dimensions
- Fast & cost-effective
- 99.9% performance of large model
"""

import json
import hashlib
import copy
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import os

from brain_eleven.runtime.storage import runtime_file_lock as file_lock, write_json


class CachePersistenceError(RuntimeError):
    """Raised when a cache publication cannot preserve the prior snapshot."""


class EmbeddingGenerator:
    """Generate vector embeddings for memory content"""

    def __init__(self, vault_path: str, api_key: Optional[str] = None):
        self.vault_path = Path(vault_path)
        self.embedding_cache = self.vault_path / ".claude/embeddings.json"
        # ``file_lock`` derives the sidecar path from the cache path.  Keep
        # the resolved name visible for compatibility, but always pass the
        # cache path to the lock helper so the sidecar is exactly
        # ``embeddings.json.lock`` (never ``.lock.lock``).
        self.embedding_lock = self.embedding_cache.with_name(self.embedding_cache.name + ".lock")
        self.model = "text-embedding-3-small"
        self.dimension = 1536
        self.provider = "openai"
        self.embedding_schema_version = 2

        # Try to use OpenAI if API key available. An empty string counts as
        # "not set" - e.g. a .env with `OPENAI_API_KEY=` (no value) loaded
        # via python-dotenv sets the env var to "", and os.getenv() returns
        # that "" rather than None, so `is not None` alone would wrongly
        # treat an empty key as present and initialize a client that fails
        # on the first real call instead of reporting semantic unavailability.
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.use_openai = bool(self.api_key)

        if self.use_openai:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
                print("✅ OpenAI API initialized")
            except ImportError:
                print("⚠️  OpenAI library not installed; semantic search is unavailable")
                self.use_openai = False
        else:
            print("⚠️  No OpenAI API key; semantic search is unavailable")

        self.embeddings = {}
        self._cache_base_entries = {}
        self._cache_fingerprint = None
        self._load_cache()

    # ========================================================================
    # EMBEDDING GENERATION
    # ========================================================================

    @property
    def semantic_available(self) -> bool:
        """Whether this generator can produce trustworthy semantic vectors."""

        return bool(self.use_openai and hasattr(self, "client"))

    def embed_text(self, text: str) -> Optional[np.ndarray]:
        """Generate a provider-backed embedding, or ``None`` when unavailable.

        A hash-seeded random vector is intentionally not used as a production
        fallback: it has no semantic meaning and can corrupt hybrid ranking.
        """

        if not self.semantic_available:
            return None
        return self._embed_openai(text)

    def _embed_openai(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding using OpenAI API"""

        try:
            response = self.client.embeddings.create(
                input=text,
                model=self.model
            )
            embedding = response.data[0].embedding
            vector = np.array(embedding, dtype=np.float32)
            if vector.shape != (self.dimension,) or not np.isfinite(vector).all():
                raise ValueError("provider returned an invalid embedding vector")
            return vector

        except Exception as e:
            print(f"❌ OpenAI API error: {e}")
            self.use_openai = False
            return None

    def _embed_fallback(self, text: str) -> np.ndarray:
        """Legacy deterministic vector helper retained for old tooling only.

        It is never called by ``embed_text`` or any production search path.
        """

        # Create a deterministic vector for legacy tests/tools only. Production
        # search never consumes this helper.

        # Normalize text
        normalized = ' '.join(text.lower().split())

        # Generate base hash (deterministic seed)
        hash_seed = int(hashlib.sha256(normalized.encode()).hexdigest(), 16)

        # Create deterministic embedding using seeded random
        np.random.seed(hash_seed % (2**31))
        embedding = np.random.randn(self.dimension).astype(np.float32)

        # Normalize to unit vector
        embedding = embedding / np.linalg.norm(embedding)

        return embedding

    # ========================================================================
    # BATCH OPERATIONS
    # ========================================================================

    def batch_embed(self, memories: List[Dict]) -> Dict[str, np.ndarray]:
        """Generate embeddings for multiple memories"""

        print(f"\n📊 Batch embedding {len(memories)} memories...")

        embeddings = {}
        skipped = 0

        for i, memory in enumerate(memories):
            try:
                mem_id = memory["memory_id"]
                content = memory["content"]

                if not self.semantic_available:
                    skipped += 1
                    continue

                # Reuse only a cache entry generated for this exact content,
                # provider, model and dimension.
                source_revision = memory.get("source_revision", memory.get("revision"))
                cached = self.get_embedding(mem_id, content, source_revision=source_revision)
                if cached is not None:
                    embeddings[mem_id] = cached
                    continue

                # Generate embedding
                embedding = self.embed_text(content)
                if embedding is None:
                    skipped += 1
                    continue
                embeddings[mem_id] = embedding

                # Store in cache
                self.embeddings[mem_id] = self._cache_entry(content, embedding, source_revision=source_revision)

                if (i + 1) % 10 == 0:
                    print(f"   → {i + 1}/{len(memories)} embedded")

            except Exception as e:
                print(f"   ⚠️  Failed to embed {mem_id}: {e}")
                skipped += 1
                continue

        print(f"✅ Batch complete: {len(embeddings)} embedded, {skipped} skipped")
        return embeddings

    # ========================================================================
    # CACHE MANAGEMENT
    # ========================================================================

    def _load_cache(self):
        """Load embeddings from cache file"""

        if not self.embedding_cache.exists():
            self.embeddings = {}
            self._cache_base_entries = {}
            self._cache_fingerprint = None
            return

        try:
            with open(self.embedding_cache, 'r', encoding='utf-8') as f:
                data = json.load(f)
                loaded = data.get("embeddings", {}) if isinstance(data, dict) else {}
                self.embeddings = loaded if isinstance(loaded, dict) else {}
                self._cache_base_entries = copy.deepcopy(self.embeddings)
                self._cache_fingerprint = self._cache_signature()
                print(f"📦 Loaded {len(self.embeddings)} cached embeddings")

        except Exception:
            self.embeddings = {}
            self._cache_base_entries = {}
            self._cache_fingerprint = self._cache_signature()
            print("⚠️  Failed to load embedding cache; semantic cache unavailable")

    def _cache_signature(self):
        try:
            return hashlib.sha256(self.embedding_cache.read_bytes()).hexdigest()
        except OSError:
            return None

    @staticmethod
    def _entries_equal(left, right):
        """Compare JSON-like entries without allowing array truth ambiguity."""
        try:
            result = left == right
            if isinstance(result, np.ndarray):
                return bool(np.array_equal(left, right))
            return bool(result)
        except (TypeError, ValueError):
            return False

    def _dirty_cache_entries(self):
        """Return local additions/changes since the last loaded snapshot.

        Entries read from an older snapshot are deliberately excluded when a
        concurrent writer has published a newer cache.  This prevents a stale
        generator from resurrecting entries cleared by another process while
        still allowing independently-created entries to merge.
        """
        return {
            memory_id: entry
            for memory_id, entry in self.embeddings.items()
            if memory_id not in self._cache_base_entries
            or not self._entries_equal(self._cache_base_entries[memory_id], entry)
        }

    @staticmethod
    def _entry_metadata(entry):
        if not isinstance(entry, dict):
            return None
        return tuple(entry.get(key) for key in (
            "content_hash", "provider", "model", "dimension",
            "embedding_schema_version", "source_revision",
        ))

    def _merge_cache_entries(self, disk, incoming, *, force_replace=False):
        if force_replace:
            return {}
        merged = dict(disk)
        for memory_id, entry in incoming.items():
            existing = merged.get(memory_id)
            if existing is None:
                merged[memory_id] = entry
                continue
            if self._entries_equal(existing, entry):
                continue
            if self._entry_metadata(existing) != self._entry_metadata(entry):
                raise CachePersistenceError("incompatible embedding cache entry")
            # A provider may return a numerically different vector for the
            # same content. The caller's update wins when provenance matches.
            merged[memory_id] = entry
        return merged

    def _read_disk_entries(self):
        if not self.embedding_cache.exists():
            return {}
        try:
            with open(self.embedding_cache, "r", encoding="utf-8") as stream:
                data = json.load(stream)
        except FileNotFoundError:
            return {}
        except (OSError, TypeError, ValueError) as exc:
            raise CachePersistenceError("embedding cache is not valid JSON") from exc
        if not isinstance(data, dict) or not isinstance(data.get("embeddings"), dict):
            raise CachePersistenceError("embedding cache has an invalid envelope")
        entries = data.get("embeddings", {}) if isinstance(data, dict) else {}
        return entries

    def _save_cache(self, *, force_replace=False):
        """Save embeddings to cache file"""

        try:
            data = {
                "embeddings": self.embeddings,
                "metadata": {
                    "schema_version": 2,
                    "provider": self.provider if self.semantic_available else "unavailable",
                    "model": self.model,
                    "dimension": self.dimension,
                    "last_updated": datetime.now().isoformat(),
                    "total_embeddings": len(self.embeddings)
                }
            }

            self.embedding_cache.parent.mkdir(parents=True, exist_ok=True)
            with file_lock(self.embedding_cache, timeout=5):
                disk_entries = self._read_disk_entries()
                incoming = self._dirty_cache_entries()
                merged = self._merge_cache_entries(
                    disk_entries, incoming, force_replace=force_replace
                )
                data["embeddings"] = merged
                data["metadata"]["total_embeddings"] = len(merged)
                write_json(self.embedding_cache, data)
                self.embeddings = merged
                self._cache_base_entries = copy.deepcopy(merged)
                self._cache_fingerprint = self._cache_signature()

            print(f"💾 Saved {len(merged)} embeddings to cache")
            return True

        except Exception:
            print("❌ Failed to save embedding cache; prior snapshot preserved")
            return False

    def save(self):
        """Persist embeddings to disk"""
        return self._save_cache()

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(" ".join(str(content).split()).encode("utf-8")).hexdigest()

    def _cache_entry(self, content: str, embedding: np.ndarray, *, source_revision: Optional[object] = None) -> Dict:
        return {
            "vector": embedding.tolist(),
            "content_hash": self._content_hash(content),
            "provider": self.provider,
            "model": self.model,
            "dimension": self.dimension,
            "embedding_schema_version": self.embedding_schema_version,
            "source_revision": source_revision,
            "generated_at": datetime.now().isoformat(),
        }

    def get_embedding(
        self,
        memory_id: str,
        content: Optional[str] = None,
        *,
        source_revision: Optional[object] = None,
    ) -> Optional[np.ndarray]:
        """Retrieve a valid provider-backed cached embedding.

        Legacy list-only entries are rejected because their provenance cannot
        prove that they match the current content or provider.
        """
        if memory_id in self.embeddings:
            entry = self.embeddings[memory_id]
            if not isinstance(entry, dict):
                return None
            if not self.semantic_available:
                return None
            if entry.get("provider") != self.provider:
                return None
            if entry.get("model") != self.model or entry.get("dimension") != self.dimension:
                return None
            if entry.get("embedding_schema_version") != self.embedding_schema_version:
                return None
            if content is not None and entry.get("content_hash") != self._content_hash(content):
                return None
            if source_revision is not None and entry.get("source_revision") != source_revision:
                return None
            vector = entry.get("vector")
            if not isinstance(vector, list) or len(vector) != self.dimension:
                return None
            return np.array(vector, dtype=np.float32)
        return None

    def embedding_exists(self, memory_id: str) -> bool:
        """Check if embedding is cached"""
        return self.get_embedding(memory_id) is not None

    def clear_cache(self):
        """Clear all embeddings"""
        previous_embeddings = copy.deepcopy(self.embeddings)
        self.embeddings.clear()
        result = self._save_cache(force_replace=True)
        if not result:
            self.embeddings = previous_embeddings
        if result:
            print("🗑️  Embedding cache cleared")
        return result

    def refresh_cache(self):
        """Reload the atomically published cache when another process changed it."""
        signature = self._cache_signature()
        if signature != self._cache_fingerprint:
            self._load_cache()
            return True
        return False


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys

    vault_path = Path.home() / "Documents/Brain-Eleven"

    # Load memories to embed
    validated_file = vault_path / ".claude/validated-memory.json"
    if not validated_file.exists():
        print("❌ No validated memories found")
        sys.exit(1)

    with open(validated_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        memories = data.get("validated_memory", [])

    print(f"🔍 Found {len(memories)} memories to embed")

    # Generate embeddings
    generator = EmbeddingGenerator(str(vault_path))
    embeddings = generator.batch_embed(memories)

    # Save cache
    generator.save()

    print(f"\n✅ Embedding generation complete")
    print(f"   Total embeddings: {len(embeddings)}")
    print(f"   Cached: {generator.embedding_cache}")

    # Show sample
    if embeddings:
        sample_id = list(embeddings.keys())[0]
        sample_embedding = embeddings[sample_id]
        print(f"\n📊 Sample embedding:")
        print(f"   ID: {sample_id}")
        print(f"   Shape: {sample_embedding.shape}")
        print(f"   Norm: {np.linalg.norm(sample_embedding):.4f}")
        print(f"   First 5 values: {sample_embedding[:5]}")
