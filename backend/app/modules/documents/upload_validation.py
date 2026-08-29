"""Streaming upload limits and lightweight file-structure validation."""

from __future__ import annotations

import hashlib
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import anyio
from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import AppError

CHUNK_SIZE = 1024 * 1024
ALLOWED_MEDIA_TYPES: dict[str, tuple[str, set[str]]] = {
    ".pdf": ("application/pdf", {"application/pdf"}),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ),
    ".md": ("text/markdown", {"text/markdown", "text/plain"}),
    ".markdown": ("text/markdown", {"text/markdown", "text/plain"}),
}


@dataclass(frozen=True)
class StagedUpload:
    """A validated temporary file that is safe to move into object storage."""

    path: Path
    filename: str
    extension: str
    media_type: str
    size_bytes: int
    sha256: str

    def cleanup(self) -> None:
        self.path.unlink(missing_ok=True)


def _validate_filename(filename: str | None) -> tuple[str, str]:
    if filename is None or not filename.strip():
        raise AppError(code="filename_required", message="A filename is required", status_code=422)
    cleaned = filename.strip()
    if len(cleaned) > 255 or "\x00" in cleaned or "/" in cleaned or "\\" in cleaned:
        raise AppError(code="unsafe_filename", message="The filename is not safe", status_code=422)
    extension = Path(cleaned).suffix.lower()
    if extension not in ALLOWED_MEDIA_TYPES:
        raise AppError(
            code="unsupported_file_type",
            message="Only PDF, DOCX, and Markdown files are supported",
            status_code=415,
        )
    return cleaned, extension


def _validate_media_type(extension: str, supplied_media_type: str | None) -> str:
    canonical, allowed = ALLOWED_MEDIA_TYPES[extension]
    normalized = (supplied_media_type or "").split(";", maxsplit=1)[0].strip().lower()
    if normalized not in allowed:
        raise AppError(
            code="content_type_mismatch",
            message="The file content type does not match its extension",
            status_code=415,
        )
    return canonical


def _validate_pdf(path: Path) -> None:
    with path.open("rb") as source:
        header = source.read(5)
        source.seek(max(0, path.stat().st_size - 4096))
        trailer = source.read()
    if header != b"%PDF-" or b"%%EOF" not in trailer:
        raise AppError(
            code="invalid_pdf_structure",
            message="The PDF file structure is invalid",
            status_code=422,
        )


def _validate_docx(path: Path, settings: Settings) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(names):
                raise AppError(
                    code="invalid_docx_structure",
                    message="The DOCX file structure is invalid",
                    status_code=422,
                )
            total_size = 0
            for entry in archive.infolist():
                if entry.flag_bits & 0x1:
                    raise AppError(
                        code="encrypted_docx_not_supported",
                        message="Encrypted DOCX files are not supported",
                        status_code=422,
                    )
                total_size += entry.file_size
                if total_size > settings.document_docx_max_uncompressed_bytes:
                    raise AppError(
                        code="docx_expansion_limit_exceeded",
                        message="The expanded DOCX file is too large",
                        status_code=413,
                    )
                if entry.file_size > CHUNK_SIZE and entry.file_size > entry.compress_size * 200:
                    raise AppError(
                        code="docx_compression_ratio_exceeded",
                        message="The DOCX compression ratio is unsafe",
                        status_code=422,
                    )
    except zipfile.BadZipFile as exception:
        raise AppError(
            code="invalid_docx_structure",
            message="The DOCX file structure is invalid",
            status_code=422,
        ) from exception


def _validate_markdown(path: Path) -> None:
    try:
        path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exception:
        raise AppError(
            code="invalid_markdown_encoding",
            message="Markdown files must use UTF-8 encoding",
            status_code=422,
        ) from exception


def _validate_structure(path: Path, extension: str, settings: Settings) -> None:
    if extension == ".pdf":
        _validate_pdf(path)
    elif extension == ".docx":
        _validate_docx(path, settings)
    else:
        _validate_markdown(path)


async def stage_and_validate_upload(upload: UploadFile, settings: Settings) -> StagedUpload:
    """Stream one upload to a random staging path while hashing and limiting it."""
    filename, extension = _validate_filename(upload.filename)
    media_type = _validate_media_type(extension, upload.content_type)
    staging_directory = settings.object_storage_path.parent / ".rag-staging"
    staging_directory.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(dir=staging_directory, delete=False)
    temporary_path = Path(temporary.name)
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with temporary:
            while chunk := await upload.read(CHUNK_SIZE):
                size_bytes += len(chunk)
                if size_bytes > settings.document_upload_max_bytes:
                    raise AppError(
                        code="file_too_large",
                        message="The uploaded file exceeds the configured size limit",
                        status_code=413,
                    )
                digest.update(chunk)
                temporary.write(chunk)
        if size_bytes == 0:
            raise AppError(code="empty_file", message="The uploaded file is empty", status_code=422)
        await anyio.to_thread.run_sync(_validate_structure, temporary_path, extension, settings)
        return StagedUpload(
            path=temporary_path,
            filename=filename,
            extension=extension,
            media_type=media_type,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
        )
    except Exception:
        await anyio.to_thread.run_sync(lambda: temporary_path.unlink(missing_ok=True))
        raise
