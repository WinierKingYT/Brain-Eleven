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
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import os


class EmbeddingGenerator:
    """Generate vector embeddings for memory content"""

    def __init__(self, vault_path: str, api_key: Optional[str] = None):
        self.vault_path = Path(vault_path)
        self.embedding_cache = self.vault_path / ".claude/embeddings.json"
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
            return

        try:
            with open(self.embedding_cache, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.embeddings = data.get("embeddings", {})
                print(f"📦 Loaded {len(self.embeddings)} cached embeddings")

        except Exception as e:
            print(f"⚠️  Failed to load embedding cache: {e}")

    def _save_cache(self):
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

            with open(self.embedding_cache, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"💾 Saved {len(self.embeddings)} embeddings to cache")

        except Exception as e:
            print(f"❌ Failed to save embedding cache: {e}")

    def save(self):
        """Persist embeddings to disk"""
        self._save_cache()

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
        self.embeddings.clear()
        print("🗑️  Embedding cache cleared")


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
