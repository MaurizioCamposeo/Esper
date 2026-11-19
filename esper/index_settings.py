"""Describe the settings used to build a search index."""
from dataclasses import dataclass
import sqlite3

from esper.chunking import CHUNKER_VERSION
from esper.db import get_vector_dimensions


@dataclass(frozen=True)
class IndexSettings:
    """Identify the embedding and chunking settings of an index."""
    model_name: str
    dimensions: int
    chunk_max_tokens: int
    chunk_overlap_tokens: int
    chunker_version: int = CHUNKER_VERSION

    def __post_init__(self) -> None:
        """Reject invalid settings before model work or index replacement."""
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name must not be empty")
        for name in ("dimensions", "chunk_max_tokens", "chunker_version"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.chunk_overlap_tokens) is not int or not 0 <= self.chunk_overlap_tokens < self.chunk_max_tokens:
            raise ValueError("chunk_overlap_tokens must be nonnegative and smaller than chunk_max_tokens")


def get_index_settings(conn: sqlite3.Connection) -> IndexSettings | None:
    """Return recorded index settings, or None if they are unknown."""
    row = conn.execute(
        "SELECT model_name, dimensions, chunk_max_tokens, chunk_overlap_tokens, "
        "chunker_version FROM index_settings WHERE id = 1"
    ).fetchone()

    if row is None:
        return None

    return IndexSettings(
        model_name=row["model_name"],
        dimensions=row["dimensions"],
        chunk_max_tokens=row["chunk_max_tokens"],
        chunk_overlap_tokens=row["chunk_overlap_tokens"],
        chunker_version=row["chunker_version"],
    )


def set_index_settings(conn: sqlite3.Connection, settings: IndexSettings) -> None:
    """Save settings without committing the caller's transaction."""
    conn.execute(
        "INSERT INTO index_settings "
        "(id, model_name, dimensions, chunk_max_tokens, chunk_overlap_tokens, chunker_version) "
        "VALUES (1, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
        "model_name = excluded.model_name, dimensions = excluded.dimensions, "
        "chunk_max_tokens = excluded.chunk_max_tokens, "
        "chunk_overlap_tokens = excluded.chunk_overlap_tokens, "
        "chunker_version = excluded.chunker_version",
        (settings.model_name, settings.dimensions, settings.chunk_max_tokens,
         settings.chunk_overlap_tokens, settings.chunker_version),
    )


def check_index_settings(conn: sqlite3.Connection, settings: IndexSettings) -> None:
    """Validate a populated index without writing metadata or committing."""
    recorded = get_index_settings(conn)
    if recorded is None:
        raise ValueError("Existing index settings are unknown; run 'esper reindex'")
    if recorded != settings:
        raise ValueError("Index settings have changed; run 'esper reindex'")
    if get_vector_dimensions(conn) != settings.dimensions:
        raise ValueError("Vector index dimensions do not match the model; run 'esper reindex'")


def ensure_index_settings(conn: sqlite3.Connection, settings: IndexSettings) -> None:
    """Require compatible metadata, recording settings only for an unused index."""
    with conn:
        recorded = get_index_settings(conn)
        if recorded is not None and recorded != settings:
            raise ValueError("Index settings have changed; run 'esper reindex'")
        if get_vector_dimensions(conn) != settings.dimensions:
            raise ValueError("Vector index dimensions do not match the model; run 'esper reindex'")
        if recorded is None:
            has_index = any(
                conn.execute(query).fetchone() is not None
                for query in (
                    "SELECT 1 FROM documents WHERE status = 'indexed' LIMIT 1",
                    "SELECT 1 FROM chunks LIMIT 1",
                    "SELECT 1 FROM chunks_fts LIMIT 1",
                    "SELECT 1 FROM chunks_vec LIMIT 1",
                )
            )
            if has_index:
                raise ValueError("Existing index settings are unknown; run 'esper reindex'")
            set_index_settings(conn, settings)
