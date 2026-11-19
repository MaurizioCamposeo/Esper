"""Measure document retrieval on labelled queries without changing the archive."""

from collections.abc import Sequence
from dataclasses import dataclass
import sqlite3
from typing import TYPE_CHECKING

from esper.search import SearchMode, search_documents

if TYPE_CHECKING:
    from esper.embedding import Embedder


@dataclass(frozen=True)
class EvaluationCase:
    """A query and all documents considered relevant to it."""

    query: str
    relevant_document_ids: tuple[int, ...]
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class QueryEvaluation:
    """Ranked document IDs and recall values for one labelled query."""

    query: str
    relevant_document_ids: tuple[int, ...]
    retrieved_document_ids: tuple[int, ...]
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float


@dataclass(frozen=True)
class EvaluationReport:
    """Mean per-query recall; this is not a model benchmark on unseen user data."""

    mode: str
    query_count: int
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    queries: tuple[QueryEvaluation, ...]


def recall_at_k(retrieved: Sequence[int], relevant: Sequence[int], k: int) -> float:
    """Return the fraction of relevant documents found within the first k results."""
    if type(k) is not int or k <= 0:
        raise ValueError("k must be a positive integer")
    expected = set(relevant)
    if not expected:
        raise ValueError("Each evaluation query needs at least one relevant document")
    return len(set(retrieved[:k]) & expected) / len(expected)


def evaluate_search(
    conn: sqlite3.Connection, embedder: "Embedder | None", cases: Sequence[EvaluationCase],
    *, mode: SearchMode = "hybrid",
) -> EvaluationReport:
    """Run each query once and average recall@1, recall@5 and recall@10."""
    if not cases:
        raise ValueError("The evaluation dataset must contain queries")
    results = []
    for case in cases:
        if not case.relevant_document_ids:
            raise ValueError("Each evaluation query needs at least one relevant document")
        retrieved = tuple(hit.document_id for hit in search_documents(
            conn, case.query, embedder, tags=case.tags, limit=10, mode=mode,
        ))
        results.append(QueryEvaluation(
            case.query, case.relevant_document_ids, retrieved,
            recall_at_k(retrieved, case.relevant_document_ids, 1),
            recall_at_k(retrieved, case.relevant_document_ids, 5),
            recall_at_k(retrieved, case.relevant_document_ids, 10),
        ))
    count = len(results)
    return EvaluationReport(
        mode, count,
        sum(result.recall_at_1 for result in results) / count,
        sum(result.recall_at_5 for result in results) / count,
        sum(result.recall_at_10 for result in results) / count,
        tuple(results),
    )
