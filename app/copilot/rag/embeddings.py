"""
Embedding Generation via RequestyAI
Uses OpenAI-compatible embedding models for vector generation
"""
from typing import Optional

from app.core.config import settings


async def generate_embeddings(
    text: str,
    model: str = "openai/text-embedding-3-small",
) -> tuple[list[float], int]:
    """
    Generate embeddings for a text chunk using RequestyAI.

    Args:
        text: Text to generate embedding for
        model: Embedding model to use (default: OpenAI text-embedding-3-small)

    Returns:
        Tuple of (embedding vector, token count)
    """
    import httpx

    # Truncate text if too long (max ~8000 tokens for most embedding models)
    max_chars = 30000  # Approximate limit
    if len(text) > max_chars:
        text = text[:max_chars]

    url = f"{settings.REQUESTY_AI_BASE_URL}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.REQUESTY_AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": text,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    embedding = data["data"][0]["embedding"]
    tokens = data.get("usage", {}).get("total_tokens", 0)

    return embedding, tokens


async def generate_batch_embeddings(
    texts: list[str],
    model: str = "openai/text-embedding-3-small",
    batch_size: int = 100,
) -> list[tuple[list[float], int]]:
    """
    Generate embeddings for multiple texts in batches.

    Args:
        texts: List of texts to generate embeddings for
        model: Embedding model to use
        batch_size: Number of texts per API call

    Returns:
        List of (embedding vector, token count) tuples
    """
    import httpx

    results = []

    url = f"{settings.REQUESTY_AI_BASE_URL}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.REQUESTY_AI_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            # Truncate texts
            max_chars = 30000
            batch = [t[:max_chars] if len(t) > max_chars else t for t in batch]

            payload = {
                "model": model,
                "input": batch,
            }

            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Process results
            embeddings_data = sorted(data["data"], key=lambda x: x["index"])
            total_tokens = data.get("usage", {}).get("total_tokens", 0)
            tokens_per_text = total_tokens // len(batch) if batch else 0

            for emb_data in embeddings_data:
                results.append((emb_data["embedding"], tokens_per_text))

    return results


async def compute_similarity(
    embedding1: list[float],
    embedding2: list[float],
) -> float:
    """
    Compute cosine similarity between two embeddings.

    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector

    Returns:
        Similarity score between 0 and 1
    """
    import math

    # Compute dot product
    dot_product = sum(a * b for a, b in zip(embedding1, embedding2))

    # Compute magnitudes
    mag1 = math.sqrt(sum(a * a for a in embedding1))
    mag2 = math.sqrt(sum(b * b for b in embedding2))

    if mag1 == 0 or mag2 == 0:
        return 0.0

    return dot_product / (mag1 * mag2)


class EmbeddingCache:
    """
    Simple in-memory cache for embeddings to avoid duplicate API calls.
    """

    def __init__(self, max_size: int = 1000):
        self.cache: dict[str, tuple[list[float], int]] = {}
        self.max_size = max_size

    def _hash_text(self, text: str) -> str:
        """Generate a hash key for text."""
        import hashlib
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def get(self, text: str) -> Optional[tuple[list[float], int]]:
        """Get cached embedding if available."""
        key = self._hash_text(text)
        return self.cache.get(key)

    def set(self, text: str, embedding: list[float], tokens: int) -> None:
        """Cache an embedding."""
        if len(self.cache) >= self.max_size:
            # Simple eviction: remove oldest entry
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]

        key = self._hash_text(text)
        self.cache[key] = (embedding, tokens)

    def clear(self) -> None:
        """Clear the cache."""
        self.cache.clear()


# Global cache instance
embedding_cache = EmbeddingCache()


async def generate_embeddings_cached(
    text: str,
    model: str = "openai/text-embedding-3-small",
    use_cache: bool = True,
) -> tuple[list[float], int]:
    """
    Generate embeddings with caching support.

    Args:
        text: Text to generate embedding for
        model: Embedding model to use
        use_cache: Whether to use caching

    Returns:
        Tuple of (embedding vector, token count)
    """
    if use_cache:
        cached = embedding_cache.get(text)
        if cached:
            return cached

    embedding, tokens = await generate_embeddings(text, model)

    if use_cache:
        embedding_cache.set(text, embedding, tokens)

    return embedding, tokens
