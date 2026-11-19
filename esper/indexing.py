"""Index archived documents for search."""
import sqlite3
import numpy as np
from pathlib import Path
from typing import TYPE_CHECKING
from collections.abc import Callable

from esper.chunking import chunk_text
from esper.config import CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS, FILES_DIR
from esper.extract import TextSource, extract_document
from esper.db import recreate_vector_index
from esper.index_settings import IndexSettings, ensure_index_settings, get_index_settings, set_index_settings
from esper.storage import get_document

if TYPE_CHECKING:
    from esper.embedding import Embedder


def current_index_settings(embedder: "Embedder") -> IndexSettings:
    """Describe the loaded model and the chunker used by this pipeline."""
    return IndexSettings(
        embedder.model_name, embedder.dimensions,
        CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS,
    )

def set_status(conn: sqlite3.Connection, document_id: int, status: str, error: str | None = None) -> None:
    """Update a document's processing status and optional error message."""
    with conn:
        conn.execute(
            "UPDATE documents SET status = ?, error = ? WHERE id = ?",
            (status, error, document_id)
        )

def write_chunks(
    conn: sqlite3.Connection, document_id: int, chunks: list[str], vectors: np.ndarray,
    *, settings: IndexSettings | None = None,
    pages: list[int | None] | None = None, page_count: int | None = None,
    sources: list[TextSource] | None = None,
    extraction_warning: str | None = None,
) -> None:
    """Replace a document's chunks and search indexes in one transaction."""
    if pages is None:
        pages = [None] * len(chunks)
    if sources is None:
        sources = ["text"] * len(chunks)
    with conn:
        conn.execute(
            "DELETE FROM chunks WHERE document_id = ?",
            (document_id,)
        )
        # The DELETE acquires the write lock. Recheck after inference so a
        # concurrent reset cannot mix vectors from different model settings.
        if settings is not None and get_index_settings(conn) != settings:
            raise ValueError("Index settings changed during processing; run 'esper index' again")

        for position, (text, vector, page, source) in enumerate(zip(chunks, vectors, pages, sources, strict=True)):
            chunk_id = conn.execute(
                "INSERT INTO chunks (document_id, position, text, page, source) VALUES (?, ?, ?, ?, ?)",
                (document_id, position, text, page, source)
            ).lastrowid

            conn.execute(
                "INSERT INTO chunks_fts (rowid, text) VALUES (?, ?)",
                (chunk_id, text),
            )

            conn.execute(
                "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                (chunk_id, vector.tobytes())
            )

        conn.execute(
            "UPDATE documents SET status = 'indexed', error = NULL, page_count = ?, extraction_warning = ? WHERE id = ?",
            (page_count, extraction_warning, document_id)
        )

def index_document(conn: sqlite3.Connection, embedder: "Embedder", document_id: int, files_dir: Path = FILES_DIR) -> bool:
    """Index one archived document; record processing failures and return False."""
    doc = get_document(conn, document_id)
    if doc is None:
        raise ValueError(f"no document #{document_id}")

    settings = current_index_settings(embedder)
    ensure_index_settings(conn, settings)
    set_status(conn, document_id, "processing")

    try:
        path = files_dir / doc["stored_name"]
        extracted = extract_document(path, doc["mime_type"])
        chunks, pages, sources = [], [], []
        for section in extracted.sections:
            section_chunks = chunk_text(section.text, settings.chunk_max_tokens, settings.chunk_overlap_tokens, embedder.count_tokens)
            chunks.extend(section_chunks)
            pages.extend([section.page] * len(section_chunks))
            sources.extend([section.source] * len(section_chunks))
        vectors = embedder.embed(chunks)
        write_chunks(conn, document_id, chunks, vectors, settings=settings, pages=pages,
                     sources=sources, page_count=extracted.page_count, extraction_warning=extracted.warning)
    except Exception as exc:
        set_status(
            conn,
            document_id,
            "error",
            f"{type(exc).__name__}: {exc}"
        )
        return False
    return True

def index_queued(
    conn: sqlite3.Connection, embedder: "Embedder", files_dir: Path = FILES_DIR,
    *, on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[int, int]:
    """Process queued documents and return the indexed and failed counts."""
    if conn.execute(
        "SELECT 1 FROM documents WHERE status IN ('queued', 'processing') LIMIT 1"
    ).fetchone() is None:
        return 0, 0
    ensure_index_settings(conn, current_index_settings(embedder))
    with conn:
        conn.execute(
            "UPDATE documents SET status = 'queued', error = NULL "
            "WHERE status = 'processing'"
        )

    document_ids = [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM documents WHERE status = 'queued' ORDER BY id"
        )
    ]

    indexed = 0
    failed = 0

    for document_id in document_ids:
        if should_stop is not None and should_stop():
            break
        if index_document(conn, embedder, document_id, files_dir):
            indexed += 1
        else:
            failed += 1
        if on_progress is not None:
            on_progress(indexed, failed)

    return indexed, failed


def reindex_all(
    conn: sqlite3.Connection, embedder: "Embedder", files_dir: Path = FILES_DIR,
    *, on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[int, int]:
    """Reset derived data atomically, then rebuild using the resumable queue."""
    settings = current_index_settings(embedder)
    with conn:
        # Keep originals, document metadata and tags; discard only derived data.
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM chunks_fts")
        recreate_vector_index(conn, settings.dimensions)
        set_index_settings(conn, settings)
        conn.execute("UPDATE documents SET status = 'queued', error = NULL")
    return index_queued(conn, embedder, files_dir, on_progress=on_progress, should_stop=should_stop)
