"""Object-storage abstraction and a safe local-filesystem implementation."""

from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol
from uuid import uuid4


class ObjectStorage(Protocol):
    """Minimal immutable-object operations required by document ingestion."""

    def put_file(self, key: str, source: Path) -> None:
        """Create an object from a local staging file without overwriting."""

    def open_binary(self, key: str) -> BinaryIO:
        """Open one object for binary reading."""

    def delete(self, key: str) -> None:
        """Delete an object when compensating for a failed database write."""


class LocalObjectStorage:
    """Store immutable objects below one configured directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_key(self, key: str) -> Path:
        path = PurePosixPath(key)
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("storage key must be a safe relative path")
        candidate = self.root.joinpath(*path.parts).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("storage key escapes the configured root")
        return candidate

    def put_file(self, key: str, source: Path) -> None:
        destination = self._resolve_key(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            with source.open("rb") as reader, temporary.open("xb") as writer:
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
                writer.flush()
                os.fsync(writer.fileno())
            if destination.exists():
                raise FileExistsError(f"immutable object already exists: {key}")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

    def open_binary(self, key: str) -> BinaryIO:
        return self._resolve_key(key).open("rb")

    def delete(self, key: str) -> None:
        self._resolve_key(key).unlink(missing_ok=True)
