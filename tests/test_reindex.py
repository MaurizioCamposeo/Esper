"""Verify explicit index replacement, identity checks and restart recovery."""

from dataclasses import replace

import numpy as np
import pytest

from esper import indexing
from esper.config import EMBEDDING_DIMENSIONS
from esper.db import get_vector_dimensions
from esper.index_settings import get_index_settings, set_index_settings
from esper.storage import import_file
from esper.tags import add_tag


class ToyEmbedder:
    """Represent different models with deterministic normalized vectors."""

    def __init__(self, name="test/model", dimensions=EMBEDDING_DIMENSIONS):
        self.model_name = name
        self.dimensions = dimensions
        self.calls = []

    def count_tokens(self, text):
        return len(text.split())

    def embed(self, texts):
        self.calls.append(list(texts))
        vectors = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        vectors[:, 0] = 1
        return vectors


def database_snapshot(conn):
    """Capture user data, derived data and index metadata for rollback checks."""
    tables = ("documents", "tags", "document_tags", "chunks", "chunks_fts", "chunks_vec", "index_settings")
    return {
        table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        for table in tables
    }


def test_reindex_rebuilds_every_document_and_preserves_originals_and_tags(conn, make_file, files_dir):
    first_id = import_file(conn, make_file("first.md", "# Notes\nOriginal passage."), files_dir)[0]
    empty_id = import_file(conn, make_file("empty.txt", ""), files_dir)[0]
    bad_id = import_file(conn, make_file("bad.pdf", "Not supported yet."), files_dir)[0]
    embedder = ToyEmbedder()
    assert indexing.index_queued(conn, embedder, files_dir) == (2, 1)
    add_tag(conn, first_id, "keep")
    before = database_snapshot(conn)
    originals = {path.name: path.read_bytes() for path in files_dir.iterdir()}
    # Simulate an old index without trustworthy settings and stale text.
    with conn:
        conn.execute("DELETE FROM index_settings")
        conn.execute("UPDATE chunks SET text = 'Obsolete text'")
    embedder.calls.clear()

    assert indexing.reindex_all(conn, embedder, files_dir) == (2, 1)

    after = database_snapshot(conn)
    assert after["tags"] == before["tags"]
    assert after["document_tags"] == before["document_tags"]
    assert [row[:6] + row[8:] for row in after["documents"]] == [
        row[:6] + row[8:] for row in before["documents"]
    ]
    assert {path.name: path.read_bytes() for path in files_dir.iterdir()} == originals
    assert embedder.calls == [["# Notes\nOriginal passage."], []]
    assert conn.execute("SELECT text FROM chunks").fetchone()[0] == "# Notes\nOriginal passage."
    states = {row["id"]: row["status"] for row in conn.execute("SELECT id, status FROM documents")}
    assert states == {first_id: "indexed", empty_id: "indexed", bad_id: "error"}
    assert get_index_settings(conn) == indexing.current_index_settings(embedder)


@pytest.mark.parametrize("operation", [indexing.index_document, indexing.index_queued])
@pytest.mark.parametrize("change", ["model", "dimensions", "chunk_size", "chunker_version", "unknown"])
def test_incompatible_index_fails_before_document_states_change(
    conn, make_file, files_dir, monkeypatch, operation, change
):
    first_id = import_file(conn, make_file("first.txt", "Original passage."), files_dir)[0]
    embedder = ToyEmbedder()
    assert indexing.index_document(conn, embedder, first_id, files_dir)
    second_id = import_file(conn, make_file("second.txt", "New passage."), files_dir)[0]
    indexing.set_status(conn, second_id, "processing", "Interrupted")
    if change == "model":
        embedder.model_name = "other/model"
    elif change == "dimensions":
        embedder.dimensions = 768
    elif change == "chunk_size":
        monkeypatch.setattr(indexing, "CHUNK_MAX_TOKENS", 300)
    else:
        with conn:
            if change == "unknown":
                conn.execute("DELETE FROM index_settings")
            else:
                set_index_settings(conn, replace(get_index_settings(conn), chunker_version=1))
    before = database_snapshot(conn)
    embedder.calls.clear()
    args = (conn, embedder, second_id, files_dir) if operation == indexing.index_document else (conn, embedder, files_dir)

    with pytest.raises(ValueError, match="esper reindex"):
        operation(*args)

    assert database_snapshot(conn) == before
    assert embedder.calls == []


def test_reindex_changes_vector_dimensions_and_deletion_trigger_still_works(conn, make_file, files_dir):
    document_id = import_file(conn, make_file("notes.txt", "Original passage."), files_dir)[0]
    assert indexing.index_queued(conn, ToyEmbedder(), files_dir) == (1, 0)
    new_model = ToyEmbedder("other/model", 768)

    assert indexing.reindex_all(conn, new_model, files_dir) == (1, 0)

    assert get_vector_dimensions(conn) == 768
    assert get_index_settings(conn) == indexing.current_index_settings(new_model)
    stored = conn.execute("SELECT embedding FROM chunks_vec").fetchone()[0]
    assert len(stored) == 768 * 4
    assert np.linalg.norm(np.frombuffer(stored, dtype=np.float32)) == pytest.approx(1)
    with conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    for table in ("chunks", "chunks_fts", "chunks_vec"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


@pytest.mark.parametrize("failure", ["reset", "invalid_settings"])
def test_failed_reset_preserves_the_entire_previous_index(conn, make_file, files_dir, monkeypatch, failure):
    import_file(conn, make_file("notes.txt", "Original passage."), files_dir)
    embedder = ToyEmbedder()
    assert indexing.index_queued(conn, embedder, files_dir) == (1, 0)
    before = database_snapshot(conn)
    new_model = ToyEmbedder("other/model", 768)
    if failure == "reset":
        def fail_after_recreating_vector_table(*args):
            raise RuntimeError("Reset failed")
        monkeypatch.setattr(indexing, "set_index_settings", fail_after_recreating_vector_table)
        expected = RuntimeError
    else:
        new_model.dimensions = 0
        expected = ValueError

    with pytest.raises(expected):
        indexing.reindex_all(conn, new_model, files_dir)

    assert get_vector_dimensions(conn) == EMBEDDING_DIMENSIONS
    assert database_snapshot(conn) == before


def test_interrupted_rebuild_resumes_without_repeating_finished_documents(conn, make_file, files_dir, monkeypatch):
    first_id = import_file(conn, make_file("first.txt", "First passage."), files_dir)[0]
    second_id = import_file(conn, make_file("second.txt", "Second passage."), files_dir)[0]
    third_id = import_file(conn, make_file("third.txt", "Third passage."), files_dir)[0]
    assert indexing.index_queued(conn, ToyEmbedder(), files_dir) == (3, 0)
    embedder = ToyEmbedder("new/model", 768)
    original_embed = embedder.embed

    def interrupt_second(texts):
        if texts == ["Second passage."]:
            raise KeyboardInterrupt
        return original_embed(texts)

    monkeypatch.setattr(embedder, "embed", interrupt_second)
    with pytest.raises(KeyboardInterrupt):
        indexing.reindex_all(conn, embedder, files_dir)
    states = [tuple(row) for row in conn.execute("SELECT id, status FROM documents ORDER BY id")]
    assert states == [(first_id, "indexed"), (second_id, "processing"), (third_id, "queued")]
    assert conn.execute("SELECT COUNT(*) FROM chunks_vec").fetchone()[0] == 1
    monkeypatch.setattr(embedder, "embed", original_embed)

    assert indexing.index_queued(conn, embedder, files_dir) == (2, 0)

    assert embedder.calls == [["First passage."], ["Second passage."], ["Third passage."]]
    assert conn.execute("SELECT COUNT(*) FROM chunks_vec").fetchone()[0] == 3


def test_failed_document_after_model_change_has_no_vectors_from_old_model(conn, make_file, files_dir):
    document_id = import_file(conn, make_file("notes.txt", "Original passage."), files_dir)[0]
    assert indexing.index_queued(conn, ToyEmbedder(), files_dir) == (1, 0)

    class BrokenEmbedder(ToyEmbedder):
        def embed(self, texts):
            raise RuntimeError("Inference failed")

    assert indexing.reindex_all(conn, BrokenEmbedder("other/model", 768), files_dir) == (0, 1)
    for table in ("chunks", "chunks_fts", "chunks_vec"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM documents WHERE id = ?", (document_id,)).fetchone()[0] == "error"


def test_settings_are_rechecked_before_storing_vectors_after_inference(conn, make_file, files_dir, monkeypatch):
    document_id = import_file(conn, make_file("notes.txt", "Original passage."), files_dir)[0]
    embedder = ToyEmbedder()
    assert indexing.index_queued(conn, embedder, files_dir) == (1, 0)
    before = database_snapshot(conn)
    original_embed = embedder.embed

    def change_settings_during_inference(texts):
        with conn:
            set_index_settings(conn, replace(get_index_settings(conn), model_name="other/model"))
        return original_embed(texts)

    monkeypatch.setattr(embedder, "embed", change_settings_during_inference)
    assert indexing.index_document(conn, embedder, document_id, files_dir) is False
    after = database_snapshot(conn)
    for table in ("chunks", "chunks_fts", "chunks_vec"):
        assert after[table] == before[table]
    assert "settings changed during processing" in conn.execute("SELECT error FROM documents").fetchone()[0]
