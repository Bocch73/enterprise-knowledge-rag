"""Small embedding-provider contract and deterministic local implementation."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from hashlib import sha256
from typing import Protocol

import anyio

EMBEDDING_DIMENSIONS = 384
DETERMINISTIC_EMBEDDING_MODEL = "deterministic-hash-v1"
WORD_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)


class EmbeddingProvider(Protocol):
    """Convert a batch of text into fixed-size floating-point vectors."""

    name: str
    dimensions: int

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector for each input text in the original order."""


class EmbeddingProviderError(Exception):
    """Safe provider failure metadata used by the retryable job state machine."""

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class DeterministicHashEmbeddingProvider:
    """Offline lexical hashing for repeatable development and automated tests.

    This provider proves the vector pipeline without a model download or secret key.
    It is deliberately not presented as a production semantic embedding model.
    """

    name = DETERMINISTIC_EMBEDDING_MODEL
    dimensions = EMBEDDING_DIMENSIONS

    @staticmethod
    def _features(text: str) -> list[str]:
        normalized = " ".join(text.casefold().split())
        words = WORD_PATTERN.findall(normalized)
        compact = "".join(character for character in normalized if not character.isspace())
        character_pairs = [compact[index : index + 2] for index in range(len(compact) - 1)]
        return words + character_pairs

    @classmethod
    def _embed_one(cls, text: str) -> list[float]:
        features = cls._features(text)
        if not features:
            raise EmbeddingProviderError(
                "embedding_input_empty",
                "A document chunk did not contain embeddable text",
                retryable=False,
            )

        vector = [0.0] * cls.dimensions
        for feature in features:
            digest = sha256(feature.encode("utf-8")).digest()
            position = int.from_bytes(digest[:4], byteorder="big") % cls.dimensions
            direction = 1.0 if digest[4] & 1 else -1.0
            vector[position] += direction

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            raise EmbeddingProviderError(
                "embedding_normalization_failed",
                "The local embedding vector could not be normalized",
                retryable=False,
            )
        return [value / magnitude for value in vector]

    @classmethod
    def _embed_many(cls, texts: Sequence[str]) -> list[list[float]]:
        return [cls._embed_one(text) for text in texts]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        copied_texts = tuple(texts)
        return await anyio.to_thread.run_sync(self._embed_many, copied_texts)
