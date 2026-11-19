"""The map uses existing passage vectors, including indexes created before it."""

import itertools

import numpy as np
import pytest

from esper import archive_map
from esper.db import connect, init_schema, recreate_vector_index
from esper.indexing import set_status, write_chunks
from esper.storage import delete_document, import_file


def add(conn, make_file, files_dir, name, vectors):
    doc_id, _ = import_file(conn, make_file(name, name), files_dir)
    values = np.array(vectors, dtype=np.float32)
    write_chunks(conn, doc_id, [name] * len(values), values)
    return doc_id


def test_projection_and_edges_follow_original_document_means(conn, make_file, files_dir):
    recreate_vector_index(conn, 5)
    rng = np.random.default_rng(16)
    chunks = rng.normal(size=(9, 3, 5)).astype(np.float32)
    chunks /= np.linalg.norm(chunks, axis=2, keepdims=True)
    ids = [add(conn, make_file, files_dir, f"{i}.md", rows) for i, rows in enumerate(chunks)]
    result = archive_map.load_archive_map(conn)
    mean = chunks.mean(axis=1)
    mean /= np.linalg.norm(mean, axis=1, keepdims=True)
    # PCA retains the three largest components of the centered Gram matrix.
    centered = mean - mean.mean(axis=0)
    u, s, _ = np.linalg.svd(centered, full_matrices=False)
    expected = u[:, :3] * s[:3]
    actual = np.array([result.positions[key] for key in ids])
    np.testing.assert_allclose(actual @ actual.T, expected @ expected.T, atol=1e-5)
    similarities = mean @ mean.T
    np.fill_diagonal(similarities, -np.inf)
    pairs = {tuple(sorted((ids[i], ids[j]))) for i, row in enumerate(similarities)
             for j in np.argsort(-row)[:4] if row[j] > 0.7}
    assert pairs and pairs == {(i, j) for i, j, _ in result.edges}
    for i, j, distance in result.edges:
        assert distance == pytest.approx(1 - similarities[ids.index(i), ids.index(j)], abs=1e-6)


def test_cache_reopens_without_vector_scan_and_updates_on_same_count_replacement(tmp_path, make_file, files_dir, monkeypatch):
    db = tmp_path / "map.db"
    conn = connect(db)
    init_schema(conn)
    recreate_vector_index(conn, 2)
    a = add(conn, make_file, files_dir, "one.md", [[1, 0]])
    b = add(conn, make_file, files_dir, "two.md", [[1, 0]])
    # Simulate opening a pre-map archive with populated indexes.
    conn.executescript("DROP TABLE map_edges; DROP TABLE map_points; DROP TABLE map_state;")
    init_schema(conn)
    first = archive_map.load_archive_map(conn)
    assert first.positions[a] == first.positions[b] == (0, 0, 0)
    assert first.edges == ((a, b, 0),)
    conn.close()
    conn = connect(db)
    init_schema(conn)
    with monkeypatch.context() as patch:
        patch.setattr(archive_map, "_document_vectors", lambda *_: pytest.fail("rescanned cached vectors"))
        assert archive_map.load_archive_map(conn) == first
    write_chunks(conn, b, ["updated"], np.array([[0, 1]], dtype=np.float32))
    second = archive_map.load_archive_map(conn)
    assert second.positions[a] != second.positions[b] and not second.edges
    set_status(conn, b, "queued")
    assert set(archive_map.load_archive_map(conn).positions) == {a}
    delete_document(conn, a, files_dir)
    assert not archive_map.load_archive_map(conn).positions
    conn.close()


def test_concurrent_replacement_discards_outdated_geometry(tmp_path, make_file, files_dir, monkeypatch):
    db = tmp_path / "shared.db"
    conn, writer = connect(db), connect(db)
    init_schema(conn)
    recreate_vector_index(conn, 2)
    a = add(conn, make_file, files_dir, "one.md", [[1, 0]])
    b = add(conn, make_file, files_dir, "two.md", [[1, 0]])
    layout = archive_map._layout
    revisions = []

    def replace_during_fit(revision, ids, vectors):
        if not revisions:
            write_chunks(writer, b, ["new"], np.array([[0, 1]], dtype=np.float32))
        revisions.append(revision)
        return layout(revision, ids, vectors)

    monkeypatch.setattr(archive_map, "_layout", replace_during_fit)
    current = archive_map.load_archive_map(conn)
    assert len(revisions) == 2 and revisions[0] < current.revision
    assert current.positions[a] != current.positions[b]
    assert not current.edges
    conn.close()
    writer.close()


def test_dense_cluster_has_bounded_edges_and_unusable_vectors_are_unplaced(conn, make_file, files_dir):
    recreate_vector_index(conn, 2)
    ids = [add(conn, make_file, files_dir, f"{i}.txt", [[1, 0]]) for i in range(10)]
    add(conn, make_file, files_dir, "cancel.txt", [[1, 0], [-1, 0]])
    result = archive_map.load_archive_map(conn)
    assert set(result.positions) == set(ids)
    assert len(result.edges) <= 4 * len(ids)
    assert len(result.edges) < len(list(itertools.combinations(ids, 2)))
    assert all(distance == 0 and i < j for i, j, distance in result.edges)
