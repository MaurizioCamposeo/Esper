"""Retrieve indexed documents by meaning, keywords, or both, without UI dependencies."""

from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import re
import sqlite3
from typing import TYPE_CHECKING, Literal

import numpy as np

from esper.db import get_vector_dimensions
from esper.extract import TextSource
from esper.index_settings import check_index_settings
from esper.indexing import current_index_settings
from esper.tags import get_document_tags, normalize_tag

if TYPE_CHECKING:
    from esper.embedding import Embedder

SearchMode = Literal["hybrid", "semantic", "keyword"]
SEARCH_MODES = ("hybrid", "semantic", "keyword")
RRF_CONSTANT = 60


@dataclass(frozen=True)
class RankedChunk:
    """One branch's candidate; value is cosine distance or BM25 (lower is better)."""

    chunk_id: int
    document_id: int
    value: float


@dataclass(frozen=True)
class PassageMatch:
    """A source passage and its retrieval signals; position is zero-based."""

    chunk_id: int
    position: int
    text: str
    score: float
    via: Literal["semantic", "keyword", "both"]
    distance: float | None
    bm25: float | None
    page: int | None = None
    source: TextSource = "text"


@dataclass(frozen=True)
class SearchHit:
    """A document ranked by its strongest passage, with up to three passages."""

    document_id: int
    name: str
    mime_type: str
    size_bytes: int
    created_at: str
    tags: tuple[str, ...]
    score: float
    matches: tuple[PassageMatch, ...]


def validate_search(query: str, limit: int, mode: str) -> None:
    """Reject invalid requests before loading models or accessing the archive."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query must not be empty")
    if type(limit) is not int or limit <= 0:
        raise ValueError("Search limit must be a positive integer")
    if mode not in SEARCH_MODES:
        raise ValueError(f"Search mode must be one of: {', '.join(SEARCH_MODES)}")


def _eligible_chunks(tags: Sequence[str]) -> tuple[str, tuple]:
    """Build the common filter applied before either branch's ranking limit."""
    names = sorted({normalize_tag(tag) for tag in tags})
    sql = (
        "SELECT c.id FROM chunks AS c JOIN documents AS d ON d.id = c.document_id "
        "WHERE d.status = 'indexed'"
    )
    if not names:
        return sql, ()
    placeholders = ", ".join("?" for _ in names)
    sql += (
        " AND d.id IN (SELECT dt.document_id FROM document_tags AS dt "
        "JOIN tags AS t ON t.id = dt.tag_id "
        f"WHERE t.name IN ({placeholders}) GROUP BY dt.document_id HAVING COUNT(*) = ?)"
    )
    return sql, (*names, len(names))


def searchable_chunk_count(conn: sqlite3.Connection, tags: Sequence[str] = ()) -> int:
    """Count eligible source chunks without loading an embedding model."""
    sql, parameters = _eligible_chunks(tags)
    return conn.execute(f"SELECT COUNT(*) FROM ({sql})", parameters).fetchone()[0]


def keyword_expression(query: str) -> str:
    """Treat natural language as literal Unicode words, never as FTS operators."""
    terms = dict.fromkeys(re.findall(r"[^\W_]+", query, flags=re.UNICODE))
    return " OR ".join(f'"{term}"' for term in terms)


def vector_search(
    conn: sqlite3.Connection, vector: np.ndarray, *, tags: Sequence[str] = (), limit: int = 50,
) -> list[RankedChunk]:
    """Return exact cosine neighbors among eligible chunks with stable tie ordering."""
    validate_search("vector", limit, "semantic")
    values = np.asarray(vector, dtype=np.float32)
    if values.shape != (get_vector_dimensions(conn),) or not np.isfinite(values).all():
        raise ValueError("Query vector must be finite and match the index dimensions")
    norm = float(np.linalg.norm(values.astype(np.float64)))
    if norm == 0:
        raise ValueError("Query vector must not be zero")
    values = np.asarray(values / norm, dtype=np.float32)
    sql, parameters = _eligible_chunks(tags)
    # An exact scalar query avoids vec0's 4096-neighbor cap and permits stable
    # rowid ties as well as expanding a candidate pool dominated by one document.
    rows = conn.execute(
        "SELECT v.rowid AS chunk_id, c.document_id, "
        "vec_distance_cosine(v.embedding, ?) AS distance "
        "FROM chunks_vec AS v JOIN chunks AS c ON c.id = v.rowid "
        f"WHERE v.rowid IN ({sql}) ORDER BY distance, v.rowid LIMIT ?",
        (values.tobytes(), *parameters, limit),
    ).fetchall()
    return [RankedChunk(row["chunk_id"], row["document_id"], row["distance"]) for row in rows]


def keyword_search(
    conn: sqlite3.Connection, query: str, *, tags: Sequence[str] = (), limit: int = 50,
) -> list[RankedChunk]:
    """Rank literal word matches with FTS5 BM25 after filtering eligible chunks."""
    validate_search(query, limit, "keyword")
    expression = keyword_expression(query)
    if not expression:
        return []
    sql, parameters = _eligible_chunks(tags)
    rows = conn.execute(
        "SELECT chunks_fts.rowid AS chunk_id, c.document_id, bm25(chunks_fts) AS score "
        "FROM chunks_fts JOIN chunks AS c ON c.id = chunks_fts.rowid "
        f"WHERE chunks_fts MATCH ? AND chunks_fts.rowid IN ({sql}) "
        "ORDER BY score, chunks_fts.rowid LIMIT ?",
        (expression, *parameters, limit),
    ).fetchall()
    return [RankedChunk(row["chunk_id"], row["document_id"], row["score"]) for row in rows]


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[int]], constant: int = RRF_CONSTANT,
) -> list[tuple[int, float]]:
    """Sum 1/(constant + rank) for each unique chunk's position in each branch."""
    if type(constant) is not int or constant <= 0:
        raise ValueError("RRF constant must be a positive integer")
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(dict.fromkeys(ranking), start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (constant + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


@contextmanager
def _read_snapshot(conn: sqlite3.Connection):
    """Use one consistent read snapshot, preserving any transaction owned by a caller."""
    owns_transaction = not conn.in_transaction
    if owns_transaction:
        conn.execute("BEGIN")
    try:
        yield
    finally:
        if owns_transaction:
            conn.rollback()


def search_documents(
    conn: sqlite3.Connection, query: str, embedder: "Embedder | None" = None,
    *, tags: Sequence[str] = (), limit: int = 5, mode: SearchMode = "hybrid",
    candidate_limit: int = 50, max_passages: int = 3,
) -> list[SearchHit]:
    """Fuse chunk rankings and return distinct documents without modifying the index."""
    validate_search(query, limit, mode)
    if type(candidate_limit) is not int or candidate_limit <= 0:
        raise ValueError("candidate_limit must be a positive integer")
    if type(max_passages) is not int or max_passages <= 0:
        raise ValueError("max_passages must be a positive integer")
    if searchable_chunk_count(conn, tags) == 0:
        return []
    vector = None
    settings = None
    if mode != "keyword":
        if embedder is None:
            raise ValueError("An embedding model is required for semantic search")
        settings = current_index_settings(embedder)
        check_index_settings(conn, settings)
        # Keep slow inference outside our read snapshot; validate again inside it.
        vector = embedder.embed_query(query.strip())

    with _read_snapshot(conn):
        if settings is not None:
            check_index_settings(conn, settings)
        count = searchable_chunk_count(conn, tags)
        if count == 0:
            return []
        window = min(count, max(candidate_limit, limit))
        while True:
            semantic = vector_search(conn, vector, tags=tags, limit=window) if mode != "keyword" else []
            keyword = keyword_search(conn, query, tags=tags, limit=window) if mode != "semantic" else []
            candidates = {chunk.chunk_id: chunk for chunk in (*semantic, *keyword)}
            fused = reciprocal_rank_fusion([
                [chunk.chunk_id for chunk in semantic], [chunk.chunk_id for chunk in keyword],
            ])
            document_order = list(dict.fromkeys(candidates[chunk_id].document_id for chunk_id, _ in fused))
            exhausted = len(semantic) < window and len(keyword) < window
            if len(document_order) >= limit or window >= count or exhausted:
                break
            window = min(count, window * 2)

        chosen_documents = set(document_order[:limit])
        selected: dict[int, list[tuple[int, float]]] = {doc_id: [] for doc_id in document_order[:limit]}
        for chunk_id, score in fused:
            document_id = candidates[chunk_id].document_id
            if document_id in chosen_documents and len(selected[document_id]) < max_passages:
                selected[document_id].append((chunk_id, score))

        semantic_values = {chunk.chunk_id: chunk.value for chunk in semantic}
        keyword_values = {chunk.chunk_id: chunk.value for chunk in keyword}
        hits = []
        for document_id, chunk_scores in selected.items():
            doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
            matches = []
            for chunk_id, score in chunk_scores:
                row = conn.execute("SELECT position, text, page, source FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
                via = "both" if chunk_id in semantic_values and chunk_id in keyword_values else (
                    "semantic" if chunk_id in semantic_values else "keyword"
                )
                matches.append(PassageMatch(
                    chunk_id, row["position"], row["text"], score, via,
                    semantic_values.get(chunk_id), keyword_values.get(chunk_id), row["page"], row["source"],
                ))
            hits.append(SearchHit(
                document_id, doc["original_name"], doc["mime_type"], doc["size_bytes"],
                doc["created_at"], tuple(get_document_tags(conn, document_id)),
                chunk_scores[0][1], tuple(matches),
            ))
        return hits
