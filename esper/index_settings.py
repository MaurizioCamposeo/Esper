"""Describe the settings used to build a search index."""
from dataclasses import dataclass
import sqlite3

@dataclass(frozen=True)
class IndexSettings:
    """Identify the embedding and chunking settings of an index."""
    model_name: str
    dimensions: int
    chunk_max_tokens: int
    chunk_overlap_tokens: int

    
def get_index_settings(conn: sqlite3.Connection) -> IndexSettings | None:
    """Return recorded index settings, or None if they are unknown."""
    row = conn.execute(
        "SELECT model_name, dimensions, chunk_max_tokens, chunk_overlap_tokens FROM index_settings WHERE id = 1"
    ).fetchone()

    if row is None:
        return None

    return IndexSettings(
        model_name=row["model_name"],
        dimensions=row["dimensions"],
        chunk_max_tokens=row["chunk_max_tokens"],
        chunk_overlap_tokens=row["chunk_overlap_tokens"]
    )
