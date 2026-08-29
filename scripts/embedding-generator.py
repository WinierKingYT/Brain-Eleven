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

        # Try to use OpenAI if API key available. An empty string counts as
        # "not set" - e.g. a .env with `OPENAI_API_KEY=` (no value) loaded
        # via python-dotenv sets the env var to "", and os.getenv() returns
        # that "" rather than None, so `is not None` alone would wrongly
        # treat an empty key as present and initialize a client that fails
        # on the first real call instead of using the fallback embeddings.
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.use_openai = bool(self.api_key)

        if self.use_openai:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
                print("✅ OpenAI API initialized")
            except ImportError:
                print("⚠️  OpenAI library not installed, using fallback embeddings")
                self.use_openai = False
        else:
            print("⚠️  No OpenAI API key, using deterministic fallback embeddings")

        self.embeddings = {}
        self._load_cache()

    # ========================================================================
    # EMBEDDING GENERATION
    # ========================================================================

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text using OpenAI or fallback"""

        if self.use_openai:
            return self._embed_openai(text)
        else:
            return self._embed_fallback(text)

    def _embed_openai(self, text: str) -> np.ndarray:
        """Generate embedding using OpenAI API"""

        try:
            response = self.client.embeddings.create(
                input=text,
                model=self.model
            )
            embedding = response.data[0].embedding
            return np.array(embedding, dtype=np.float32)

        except Exception as e:
            print(f"❌ OpenAI API error: {e}")
            print("   Falling back to deterministic embedding")
            return self._embed_fallback(text)

    def _embed_fallback(self, text: str) -> np.ndarray:
        """Deterministic fallback embedding (for development/testing)"""

        # Create deterministic embedding based on text hash
        # For production, this would be replaced with actual OpenAI embeddings

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

                # Skip if already cached
                if mem_id in self.embeddings:
                    embeddings[mem_id] = np.array(self.embeddings[mem_id])
                    continue

                # Generate embedding
                embedding = self.embed_text(content)
                embeddings[mem_id] = embedding

                # Store in cache
                self.embeddings[mem_id] = embedding.tolist()

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

    def get_embedding(self, memory_id: str) -> Optional[np.ndarray]:
        """Retrieve cached embedding"""

        if memory_id in self.embeddings:
            return np.array(self.embeddings[memory_id], dtype=np.float32)
        return None

    def embedding_exists(self, memory_id: str) -> bool:
        """Check if embedding is cached"""
        return memory_id in self.embeddings

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
