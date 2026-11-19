"""Build and cache a three-dimensional view of document embeddings in SQLite."""

from dataclasses import dataclass
from itertools import groupby
import sqlite3

import numpy as np


# Bump the version when changing the projection, aggregation or link policy.
LAYOUT_VERSION = 1
MAX_COSINE_DISTANCE = 0.30
NEIGHBORS = 4


@dataclass(frozen=True)
class ArchiveMap:
    revision: int
    positions: dict[int, tuple[float, float, float]]
    edges: tuple[tuple[int, int, float], ...]


def _document_vectors(conn):
    """Stream the existing chunk vectors and normalize each document's mean."""
    ids, vectors = [], []
    rows = conn.execute(
        "SELECT c.document_id, v.embedding FROM documents d "
        "JOIN chunks c ON c.document_id = d.id JOIN chunks_vec v ON v.rowid = c.id "
        "WHERE d.status = 'indexed' ORDER BY c.document_id, c.position"
    )
    for doc_id, passages in groupby(rows, key=lambda row: row[0]):
        total = np.frombuffer(next(passages)[1], dtype=np.float32).astype(np.float64)
        for row in passages:
            total += np.frombuffer(row[1], dtype=np.float32)
        norm = np.linalg.norm(total)
        if norm > 0 and np.isfinite(norm):
            ids.append(doc_id)
            vectors.append(total / norm)
    return ids, np.asarray(vectors, dtype=np.float32)


def _layout(revision, ids, vectors):
    if not ids:
        return ArchiveMap(revision, {}, ())
    centered = vectors - vectors.mean(axis=0)
    # Bound the PCA fit for large archives; project every file on the same axes.
    sample = centered[np.linspace(0, len(ids) - 1, min(len(ids), 512), dtype=int)]
    _, _, axes = np.linalg.svd(sample, full_matrices=False)
    basis = axes[:3].copy()
    for axis in basis:
        if axis[np.argmax(np.abs(axis))] < 0:
            axis *= -1
    coordinates = np.zeros((len(ids), 3))
    coordinates[:, :len(basis)] = centered @ basis.T
    positions = {key: tuple(point.tolist()) for key, point in zip(ids, coordinates, strict=True)}

    # Blocks avoid allocating an archive-sized square matrix. Keep the union
    # of each file's nearest qualifying neighbors so dense clusters stay legible.
    edges = {}
    for start in range(0, len(ids), 128):
        scores = vectors[start:start + 128] @ vectors.T
        for offset, row in enumerate(scores):
            i = start + offset
            row[i] = -np.inf
            candidates = np.flatnonzero(row > 1 - MAX_COSINE_DISTANCE)
            closest = candidates[np.argsort(-row[candidates], kind="stable")[:NEIGHBORS]]
            for j in closest:
                pair = tuple(sorted((ids[i], ids[j])))
                edges[pair] = max(0.0, 1.0 - float(row[j]))
    return ArchiveMap(revision, positions, tuple((*pair, distance) for pair, distance in sorted(edges.items())))


def load_archive_map(conn: sqlite3.Connection) -> ArchiveMap:
    """Read a consistent snapshot and publish new geometry only if still current."""
    while True:
        with conn:
            conn.execute("BEGIN")
            revision, built, version = conn.execute(
                "SELECT revision, built_revision, version FROM map_state"
            ).fetchone()
            if built == revision and version == LAYOUT_VERSION:
                points = {row[0]: tuple(row[1:]) for row in conn.execute("SELECT * FROM map_points")}
                edges = tuple(tuple(row) for row in conn.execute(
                    "SELECT * FROM map_edges ORDER BY first_id, second_id"
                ))
                return ArchiveMap(revision, points, edges)
            ids, vectors = _document_vectors(conn)
        layout = _layout(revision, ids, vectors)
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT revision FROM map_state").fetchone()[0] != revision:
                continue
            conn.execute("DELETE FROM map_edges")
            conn.execute("DELETE FROM map_points")
            conn.executemany("INSERT INTO map_points VALUES (?, ?, ?, ?)",
                             ((key, *point) for key, point in layout.positions.items()))
            conn.executemany("INSERT INTO map_edges VALUES (?, ?, ?)", layout.edges)
            conn.execute("UPDATE map_state SET built_revision = ?, version = ?", (revision, LAYOUT_VERSION))
            return layout
