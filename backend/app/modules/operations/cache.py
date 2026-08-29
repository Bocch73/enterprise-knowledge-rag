"""Bounded time-to-live vector cache and embedding-provider decorator."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from time import monotonic

import anyio

from app.modules.indexing.providers import EmbeddingProvider
from app.modules.operations.metrics import OperationsMetrics


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    value: tuple[float, ...]
    expires_at: float


class TTLVectorCache:
    """Process-local least-recently-used cache with expiration and copy isolation."""

    def __init__(
        self,
        *,
        max_entries: int,
        ttl_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_entries <= 0 or ttl_seconds <= 0:
            raise ValueError("cache bounds must be positive")
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = anyio.Lock()

    async def get(self, key: str) -> list[float] | None:
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._clock():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return list(entry.value)

    async def put(self, key: str, value: Sequence[float]) -> None:
        async with self._lock:
            self._entries[key] = _CacheEntry(
                value=tuple(value),
                expires_at=self._clock() + self._ttl_seconds,
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)


class CachingEmbeddingProvider:
    """Cache identical text embeddings and serialize cache fills to avoid stampedes."""

    def __init__(
        self,
        delegate: EmbeddingProvider,
        cache: TTLVectorCache,
        metrics: OperationsMetrics,
    ) -> None:
        self._delegate = delegate
        self._cache = cache
        self._metrics = metrics
        self._fill_lock = anyio.Lock()
        self.name = delegate.name
        self.dimensions = delegate.dimensions

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        keys = [self._key(text) for text in texts]
        results: list[list[float] | None] = []
        for key in keys:
            cached = await self._cache.get(key)
            self._metrics.observe_cache("hit" if cached is not None else "miss")
            results.append(cached)
        if all(result is not None for result in results):
            return [list(result) for result in results if result is not None]

        async with self._fill_lock:
            missing_by_key: dict[str, str] = {}
            for index, key in enumerate(keys):
                if results[index] is not None:
                    continue
                cached = await self._cache.get(key)
                if cached is not None:
                    results[index] = cached
                else:
                    missing_by_key.setdefault(key, texts[index])
            if missing_by_key:
                missing_keys = list(missing_by_key)
                vectors = await self._delegate.embed_documents(
                    [missing_by_key[key] for key in missing_keys]
                )
                if len(vectors) != len(missing_keys):
                    raise RuntimeError("embedding provider returned an invalid cache-fill batch")
                for key, vector in zip(missing_keys, vectors, strict=True):
                    await self._cache.put(key, vector)
            for index, key in enumerate(keys):
                if results[index] is None:
                    results[index] = await self._cache.get(key)

        if any(result is None for result in results):
            raise RuntimeError("embedding cache fill did not produce every requested vector")
        return [list(result) for result in results if result is not None]

    def _key(self, text: str) -> str:
        return sha256(f"{self.name}\0{text}".encode()).hexdigest()
