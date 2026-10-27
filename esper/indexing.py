"""Index archived documents for search."""
import sqlite3
import numpy as np
from pathlib import Path
from typing import TYPE_CHECKING

from esper.chunking import chunk_text
from esper.config import CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS, FILES_DIR
from esper.extract import extract_text
from esper.storage import get_document

if TYPE_CHECKING:
    from esper.embedding import Embedder

def set_status(conn: sqlite3.Connection, document_id: int, status: str, error: str | None = None) -> None:
    """Update a document's processing status and optional error message."""
    with conn:
        conn.execute("" \
            "UPDATE documents SET status = ?, error = ? WHERE id = ?",
            (status, error, document_id)
        )

def write_chunks(conn: sqlite3.Connection, document_id: int, chunks: list[str], vectors: np.ndarray) -> None:
    """Replace a document's chunks and search indexes in one transaction."""
    with conn:
        conn.execute(
            "DELETE FROM chunks WHERE document_id = ?",
            (document_id,)
        )

        for position, (text, vector) in enumerate(zip(chunks, vectors, strict=True)):
            chunk_id = conn.execute(
                "INSERT INTO chunks (document_id, position, text) VALUES (?, ?, ?)",
                (document_id, position, text)
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
            "UPDATE documents SET status = 'indexed', error = NULL WHERE id = ?",
            (document_id,)
        )

def index_document(conn: sqlite3.Connection, embedder: "Embedder", document_id: int, files_dir: Path = FILES_DIR) -> bool:
    """Index one archived document; record processing failures and return False."""
    doc = get_document(conn, document_id)
    if doc is None:
        raise ValueError(f"no document #{document_id}")

    set_status(conn, document_id, "processing")

    try:
        path = files_dir / doc["stored_name"]
        text = extract_text(path, doc["mime_type"])

        chunks = chunk_text(text, CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS, embedder.count_tokens)
        vectors = embedder.embed(chunks)
        write_chunks(conn, document_id, chunks, vectors)
    except Exception as exc:
        set_status(
            conn,
            document_id,
            "error",
            f"{type(exc).__name__}: {exc}"
        )
        return False
    return True

def index_queued(conn: sqlite3.Connection, embedder: "Embedder", files_dir: Path = FILES_DIR) -> tuple[int, int]:
    """Process queued documents and return the indexed and failed counts."""
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
        if index_document(conn, embedder, document_id, files_dir):
            indexed += 1
        else:
            failed += 1

    return indexed, failed