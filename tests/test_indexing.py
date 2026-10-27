"""Check chunk storage, replacement, and rollback without loading a model."""

import sqlite3

import numpy as np
import pytest

from esper.config import EMBEDDING_DIMENSIONS
from esper.indexing import index_document, index_queued, set_status, write_chunks
from esper.storage import import_file


def vectors_for(count, dimensions=EMBEDDING_DIMENSIONS):
    """Build distinct unit vectors for storage checks."""
    vectors = np.zeros((count, dimensions), dtype=np.float32)
    for index in range(count):
        vectors[index, index % dimensions] = 1.0
    return vectors


@pytest.fixture
def document_id(conn, make_file, files_dir):
    path = make_file("notes.txt", "Archived notes.")
    return import_file(conn, path, files_dir)[0]


def snapshot(conn):
    """Capture document states and all three chunk representations."""
    queries = {
        "documents": "SELECT id, status, error FROM documents ORDER BY id",
        "chunks": "SELECT id, document_id, position, text FROM chunks ORDER BY id",
        "fts": "SELECT rowid, text FROM chunks_fts ORDER BY rowid",
        "vectors": "SELECT rowid, embedding FROM chunks_vec ORDER BY rowid",
    }
    return {
        name: [tuple(row) for row in conn.execute(query)]
        for name, query in queries.items()
    }


@pytest.mark.parametrize("count", [0, 1, 2])
def test_write_chunks_aligns_text_and_vectors_and_finishes_document(conn, document_id, count):
    chunks = [f"Passage {index}." for index in range(count)]
    vectors = vectors_for(count)
    set_status(conn, document_id, "error", "Earlier failure")

    write_chunks(conn, document_id, chunks, vectors)

    state = snapshot(conn)
    assert state["documents"] == [(document_id, "indexed", None)]
    assert [(row[1], row[2], row[3]) for row in state["chunks"]] == [
        (document_id, index, text) for index, text in enumerate(chunks)
    ]
    ids = [row[0] for row in state["chunks"]]
    assert state["fts"] == list(zip(ids, chunks, strict=True))
    assert state["vectors"] == [
        (chunk_id, vector.tobytes())
        for chunk_id, vector in zip(ids, vectors, strict=True)
    ]
    if count:
        hits = conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'Passage' ORDER BY rowid"
        ).fetchall()
        assert [row[0] for row in hits] == ids


@pytest.mark.parametrize("replacement", [[], ["Replacement passage."]])
def test_replacing_chunks_cleans_indexes_and_preserves_other_documents(
    conn, document_id, make_file, files_dir, replacement
):
    other_id = import_file(conn, make_file("other.txt", "Different notes."), files_dir)[0]
    write_chunks(conn, other_id, ["Unrelated passage."], vectors_for(1))
    other_state = snapshot(conn)
    write_chunks(conn, document_id, ["Obsolete passage.", "Old details."], vectors_for(2))

    write_chunks(conn, document_id, replacement, vectors_for(len(replacement)))

    state = snapshot(conn)
    assert [row[3] for row in state["chunks"] if row[1] == document_id] == replacement
    assert len(state["chunks"]) == len(state["fts"]) == len(state["vectors"]) == 1 + len(replacement)
    for table in ("chunks", "fts", "vectors"):
        assert other_state[table][0] in state[table]
    assert conn.execute(
        "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH 'Obsolete OR Old'"
    ).fetchone()[0] == 0
    assert tuple(conn.execute(
        "SELECT status, error FROM documents WHERE id = ?", (document_id,)
    ).fetchone()) == ("indexed", None)


@pytest.mark.parametrize("failure", ["missing_vector", "extra_vector", "wrong_dimensions"])
def test_failed_replacement_restores_old_chunks_indexes_and_status(conn, document_id, failure):
    write_chunks(conn, document_id, ["Original passage."], vectors_for(1))
    set_status(conn, document_id, "processing")
    before = snapshot(conn)

    if failure == "missing_vector":
        chunks, vectors = ["New passage.", "Another passage."], vectors_for(1)
        expected_error = ValueError
    elif failure == "extra_vector":
        chunks, vectors = ["New passage."], vectors_for(2)
        expected_error = ValueError
    else:
        chunks, vectors = ["New passage."], vectors_for(1, EMBEDDING_DIMENSIONS - 1)
        expected_error = sqlite3.OperationalError

    with pytest.raises(expected_error):
        write_chunks(conn, document_id, chunks, vectors)

    assert snapshot(conn) == before


class FakeEmbedder:
    """Record received text and return unit vectors without loading a model."""

    def __init__(self):
        self.calls = []

    def count_tokens(self, text):
        return len(text.split())

    def embed(self, texts):
        self.calls.append(list(texts))
        return vectors_for(len(texts))


@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest.mark.parametrize(
    ("name", "text", "expected_chunks"),
    [
        ("plain.txt", "Archived notes.", ["Archived notes."]),
        (
            "notes.md",
            "# Heating\nBoiler replaced.\n\n# Bills\nElectricity paid.",
            ["# Heating\nBoiler replaced.", "# Bills\nElectricity paid."],
        ),
    ],
)
def test_index_document_connects_extraction_chunking_embedding_and_storage(
    conn, make_file, files_dir, embedder, monkeypatch, name, text, expected_chunks
):
    document_id = import_file(conn, make_file(name, text), files_dir)[0]
    original_embed = embedder.embed

    def inspect_then_embed(texts):
        assert not conn.in_transaction
        assert conn.execute(
            "SELECT status FROM documents WHERE id = ?", (document_id,)
        ).fetchone()[0] == "processing"
        return original_embed(texts)

    monkeypatch.setattr(embedder, "embed", inspect_then_embed)

    assert index_document(conn, embedder, document_id, files_dir) is True

    state = snapshot(conn)
    assert embedder.calls == [expected_chunks]
    assert state["documents"] == [(document_id, "indexed", None)]
    assert [row[3] for row in state["chunks"]] == expected_chunks
    assert len(state["fts"]) == len(state["vectors"]) == len(expected_chunks)


def test_index_document_replaces_old_content_and_clears_previous_error(
    conn, document_id, files_dir, embedder
):
    assert index_document(conn, embedder, document_id, files_dir) is True
    stored_name = conn.execute(
        "SELECT stored_name FROM documents WHERE id = ?", (document_id,)
    ).fetchone()[0]
    (files_dir / stored_name).write_text("Updated passage.", encoding="utf-8")
    set_status(conn, document_id, "error", "Earlier failure")

    assert index_document(conn, embedder, document_id, files_dir) is True

    state = snapshot(conn)
    assert state["documents"] == [(document_id, "indexed", None)]
    assert [row[3] for row in state["chunks"]] == ["Updated passage."]
    assert len(state["chunks"]) == len(state["fts"]) == len(state["vectors"]) == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH 'Archived'"
    ).fetchone()[0] == 0


def test_index_document_handles_an_empty_file(conn, make_file, files_dir, embedder):
    document_id = import_file(conn, make_file("empty.txt", ""), files_dir)[0]

    assert index_document(conn, embedder, document_id, files_dir) is True

    state = snapshot(conn)
    assert state["documents"] == [(document_id, "indexed", None)]
    assert embedder.calls == [[]]
    assert state["chunks"] == state["fts"] == state["vectors"] == []


@pytest.mark.parametrize("failure", ["missing_file", "unsupported_format"])
def test_index_document_records_extraction_errors(
    conn, make_file, files_dir, embedder, failure
):
    name = "missing.txt" if failure == "missing_file" else "unsupported.pdf"
    document_id = import_file(conn, make_file(name, "Sample content."), files_dir)[0]
    if failure == "missing_file":
        stored_name = conn.execute(
            "SELECT stored_name FROM documents WHERE id = ?", (document_id,)
        ).fetchone()[0]
        (files_dir / stored_name).unlink()

    assert index_document(conn, embedder, document_id, files_dir) is False

    state = snapshot(conn)
    _, status, error = state["documents"][0]
    assert status == "error"
    prefix = "FileNotFoundError:" if failure == "missing_file" else "UnsupportedFormatError:"
    assert error.startswith(prefix)
    assert embedder.calls == []
    assert state["chunks"] == state["fts"] == state["vectors"] == []


def test_index_document_rejects_unknown_id_without_changing_the_archive(
    conn, document_id, files_dir, embedder
):
    before = snapshot(conn)
    with pytest.raises(ValueError, match="no document #999"):
        index_document(conn, embedder, 999, files_dir)
    assert snapshot(conn) == before
    assert embedder.calls == []


@pytest.mark.parametrize("failure", ["embedding", "storage"])
def test_index_document_keeps_previous_index_when_processing_fails(
    conn, document_id, files_dir, embedder, monkeypatch, failure
):
    assert index_document(conn, embedder, document_id, files_dir) is True
    before = snapshot(conn)

    def fail_or_return_invalid_vectors(texts):
        if failure == "embedding":
            raise RuntimeError("Embedding failed")
        return vectors_for(len(texts), EMBEDDING_DIMENSIONS - 1)

    monkeypatch.setattr(embedder, "embed", fail_or_return_invalid_vectors)

    assert index_document(conn, embedder, document_id, files_dir) is False

    state = snapshot(conn)
    for table in ("chunks", "fts", "vectors"):
        assert state[table] == before[table]
    _, status, error = state["documents"][0]
    assert status == "error"
    prefix = "RuntimeError:" if failure == "embedding" else "OperationalError:"
    assert error.startswith(prefix)


def test_index_document_allows_keyboard_interrupt_and_leaves_processing_status(
    conn, document_id, files_dir, embedder, monkeypatch
):
    def interrupt(texts):
        raise KeyboardInterrupt

    monkeypatch.setattr(embedder, "embed", interrupt)
    with pytest.raises(KeyboardInterrupt):
        index_document(conn, embedder, document_id, files_dir)
    assert snapshot(conn)["documents"] == [(document_id, "processing", None)]


def test_index_queued_recovers_interrupted_work_and_continues_after_failure(
    conn, document_id, make_file, files_dir, embedder
):
    bad_id = import_file(conn, make_file("unsupported.pdf", "Unsupported document."), files_dir)[0]
    next_id = import_file(conn, make_file("next.txt", "Next document."), files_dir)[0]
    interrupted_id = import_file(conn, make_file("interrupted.txt", "Interrupted document."), files_dir)[0]
    indexed_id = import_file(conn, make_file("indexed.txt", "Already indexed."), files_dir)[0]
    error_id = import_file(conn, make_file("error.txt", "Previous error."), files_dir)[0]
    set_status(conn, interrupted_id, "processing", "Stale message")
    assert index_document(conn, embedder, indexed_id, files_dir) is True
    set_status(conn, error_id, "error", "Do not retry automatically")
    indexed_chunks = [row for row in snapshot(conn)["chunks"] if row[1] == indexed_id]
    embedder.calls.clear()

    assert index_queued(conn, embedder, files_dir) == (3, 1)

    state = snapshot(conn)
    documents = {row[0]: row[1:] for row in state["documents"]}
    for succeeded_id in (document_id, next_id, interrupted_id, indexed_id):
        assert documents[succeeded_id] == ("indexed", None)
    assert documents[bad_id][0] == "error"
    assert documents[bad_id][1].startswith("UnsupportedFormatError:")
    assert documents[error_id] == ("error", "Do not retry automatically")
    assert embedder.calls == [
        ["Archived notes."], ["Next document."], ["Interrupted document."]
    ]
    assert [row for row in state["chunks"] if row[1] == indexed_id] == indexed_chunks


@pytest.mark.parametrize("existing_status", [None, "indexed", "error"])
def test_index_queued_leaves_an_archive_without_pending_work_unchanged(
    conn, make_file, files_dir, embedder, existing_status
):
    if existing_status is not None:
        document_id = import_file(conn, make_file("old.txt", "Existing document."), files_dir)[0]
        if existing_status == "indexed":
            assert index_document(conn, embedder, document_id, files_dir) is True
        else:
            set_status(conn, document_id, "error", "Previous failure")
    before = snapshot(conn)
    embedder.calls.clear()

    assert index_queued(conn, embedder, files_dir) == (0, 0)

    assert snapshot(conn) == before
    assert embedder.calls == []


def test_index_queued_resumes_after_keyboard_interrupt_without_repeating_completed_work(
    conn, document_id, make_file, files_dir, embedder, monkeypatch
):
    second_id = import_file(conn, make_file("second.txt", "Second document."), files_dir)[0]
    third_id = import_file(conn, make_file("third.txt", "Third document."), files_dir)[0]
    original_embed = embedder.embed

    def interrupt_second_document(texts):
        if texts == ["Second document."]:
            raise KeyboardInterrupt
        return original_embed(texts)

    monkeypatch.setattr(embedder, "embed", interrupt_second_document)
    with pytest.raises(KeyboardInterrupt):
        index_queued(conn, embedder, files_dir)
    assert snapshot(conn)["documents"] == [
        (document_id, "indexed", None),
        (second_id, "processing", None),
        (third_id, "queued", None),
    ]
    monkeypatch.setattr(embedder, "embed", original_embed)

    assert index_queued(conn, embedder, files_dir) == (2, 0)

    assert embedder.calls == [
        ["Archived notes."], ["Second document."], ["Third document."]
    ]
    assert all(row[1:] == ("indexed", None) for row in snapshot(conn)["documents"])
