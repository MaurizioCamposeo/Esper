"""Tests for esper.db: connection settings, schema and constraints."""

import sqlite3

import numpy as np
import pytest

from esper.config import EMBEDDING_DIMENSIONS
from esper.db import connect, init_schema


def insert_document(conn, sha256, status="queued"):
    """Insert a minimal document row and return its id."""
    cur = conn.execute(
        "INSERT INTO documents (sha256, original_name, mime_type, size_bytes, stored_name, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (sha256, "test.txt", "text/plain", 10, f"{sha256}.txt", status),
    )
    return cur.lastrowid


def insert_tag(conn, name):
    """Insert a tag row and return its id."""
    return conn.execute("INSERT INTO tags (name) VALUES (?)", (name,)).lastrowid


# --- Connection settings ---------------------------------------------------


def test_connect_creates_missing_folder(tmp_path):
    db_path = tmp_path / "nested" / "esper.db"
    conn = connect(db_path)
    conn.close()
    assert db_path.is_file()


def test_pragmas(tmp_path):
    # WAL only applies to on-disk databases, so use a real file here
    conn = connect(tmp_path / "esper.db")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    conn.close()


def test_rows_are_accessible_by_name(conn):
    row = conn.execute("SELECT 1 AS answer").fetchone()
    assert row["answer"] == 1


# --- Schema ------------------------------------------------------------------


def test_init_schema_is_idempotent(conn):
    # The fixture already called it once
    init_schema(conn)
    init_schema(conn)


def test_tables_exist(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    # FTS5 and vec0 also create their own shadow tables (chunks_fts_data, chunks_vec_info, ...)
    assert {"documents", "tags", "document_tags", "index_settings", "chunks", "chunks_fts", "chunks_vec"} <= {row["name"] for row in rows}


def test_virtual_tables_use_the_expected_modules(conn):
    rows = conn.execute("SELECT name, sql FROM sqlite_master WHERE name IN ('chunks_fts', 'chunks_vec')").fetchall()
    sql = {row["name"]: row["sql"] for row in rows}
    assert "fts5" in sql["chunks_fts"]
    assert "vec0" in sql["chunks_vec"]
    assert f"float[{EMBEDDING_DIMENSIONS}]" in sql["chunks_vec"]


def test_sqlite_vec_is_loaded(conn):
    assert conn.execute("SELECT vec_version()").fetchone()[0].startswith("v")


def test_extension_loading_is_disabled_again(conn):
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("SELECT load_extension('anything')")


def test_tag_index_exists(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    assert "idx_document_tags_tag" in {row["name"] for row in rows}


def test_document_defaults(conn):
    doc_id = conn.execute(
        "INSERT INTO documents (sha256, original_name, mime_type, size_bytes, stored_name) "
        "VALUES ('abc', 'a.txt', 'text/plain', 1, 'abc.txt')"
    ).lastrowid
    row = conn.execute("SELECT status, error, created_at FROM documents WHERE id = ?", (doc_id,)).fetchone()
    assert row["status"] == "queued"
    assert row["error"] is None
    # ISO 8601 UTC, e.g. 2026-10-11T14:32:05.123Z
    assert row["created_at"].endswith("Z") and "T" in row["created_at"]


# --- Index settings ------------------------------------------------------------


def test_index_settings_start_unknown(conn):
    assert conn.execute("SELECT * FROM index_settings").fetchall() == []


@pytest.mark.parametrize("overlap", [0, 399])
def test_index_settings_accept_valid_overlap_boundaries(conn, overlap):
    conn.execute(
        "INSERT INTO index_settings VALUES (?, ?, ?, ?, ?)",
        (1, "BAAI/bge-m3", 1024, 400, overlap),
    )
    row = conn.execute("SELECT * FROM index_settings WHERE id = 1").fetchone()
    assert tuple(row) == (1, "BAAI/bge-m3", 1024, 400, overlap)


@pytest.mark.parametrize(
    "values",
    [
        (0, "BAAI/bge-m3", 1024, 400, 50),
        (2, "BAAI/bge-m3", 1024, 400, 50),
        (1, "BAAI/bge-m3", 0, 400, 50),
        (1, "BAAI/bge-m3", -1, 400, 50),
        (1, "BAAI/bge-m3", 1024, 0, 0),
        (1, "BAAI/bge-m3", 1024, -1, 0),
        (1, "BAAI/bge-m3", 1024, 400, -1),
        (1, "BAAI/bge-m3", 1024, 400, 400),
        (1, "BAAI/bge-m3", 1024, 400, 401),
    ],
)
def test_index_settings_reject_invalid_values(conn, values):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute("INSERT INTO index_settings VALUES (?, ?, ?, ?, ?)", values)
    assert conn.execute("SELECT COUNT(*) FROM index_settings").fetchone()[0] == 0


@pytest.mark.parametrize("field_index", [1, 2, 3, 4])
def test_index_settings_require_all_settings(conn, field_index):
    values = [1, "BAAI/bge-m3", 1024, 400, 50]
    values[field_index] = None
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
        conn.execute("INSERT INTO index_settings VALUES (?, ?, ?, ?, ?)", values)


def test_index_settings_reject_second_row(conn):
    conn.execute("INSERT INTO index_settings VALUES (1, 'BAAI/bge-m3', 1024, 400, 50)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO index_settings (model_name, dimensions, chunk_max_tokens, chunk_overlap_tokens) "
            "VALUES ('other-model', 1024, 300, 25)"
        )
    rows = conn.execute("SELECT * FROM index_settings").fetchall()
    assert [tuple(row) for row in rows] == [(1, "BAAI/bge-m3", 1024, 400, 50)]


def test_index_settings_survive_reopen_and_schema_initialization(tmp_path):
    db_path = tmp_path / "settings.db"
    conn = connect(db_path)
    try:
        init_schema(conn)
        with conn:
            conn.execute("INSERT INTO index_settings VALUES (1, 'BAAI/bge-m3', 1024, 400, 50)")
    finally:
        conn.close()

    conn = connect(db_path)
    try:
        init_schema(conn)
        row = conn.execute("SELECT * FROM index_settings").fetchone()
        assert tuple(row) == (1, "BAAI/bge-m3", 1024, 400, 50)
    finally:
        conn.close()


def test_adding_settings_table_preserves_unlabelled_existing_index(conn):
    # Simulate a database created before index settings were introduced.
    conn.execute("DROP TABLE index_settings")
    document_id = insert_document(conn, "legacy", status="indexed")
    chunk_id = insert_chunk(conn, document_id, 0, "Existing passage", vector(1.0))
    conn.commit()

    init_schema(conn)

    assert conn.execute("SELECT * FROM index_settings").fetchall() == []
    assert conn.execute("SELECT status FROM documents WHERE id = ?", (document_id,)).fetchone()[0] == "indexed"
    assert conn.execute("SELECT text FROM chunks WHERE id = ?", (chunk_id,)).fetchone()[0] == "Existing passage"
    assert conn.execute("SELECT text FROM chunks_fts WHERE rowid = ?", (chunk_id,)).fetchone()[0] == "Existing passage"
    assert conn.execute("SELECT embedding FROM chunks_vec WHERE rowid = ?", (chunk_id,)).fetchone()[0] == vector(1.0)


# --- Constraints ---------------------------------------------------------------


def test_duplicate_sha256_rejected(conn):
    insert_document(conn, "aaa")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert_document(conn, "aaa")


def test_invalid_status_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        insert_document(conn, "bbb", status="notexistentstatus")


def test_duplicate_tag_name_rejected(conn):
    insert_tag(conn, "lavoro")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert_tag(conn, "lavoro")


def test_tag_link_to_missing_document_rejected(conn):
    tag_id = insert_tag(conn, "lavoro")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute("INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)", (999, tag_id))


def test_deleting_document_cascades_to_tag_links(conn):
    doc_id = insert_document(conn, "ccc")
    tag_id = insert_tag(conn, "lavoro")
    conn.execute("INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)", (doc_id, tag_id))

    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    assert conn.execute("SELECT COUNT(*) FROM document_tags").fetchone()[0] == 0


# --- Chunks, full-text and vector tables -------------------------------------------


def vector(first, second=0.0):
    """Return a float32 vector of the configured size, as the bytes sqlite-vec expects."""
    values = np.zeros(EMBEDDING_DIMENSIONS, dtype=np.float32)
    values[0], values[1] = first, second
    return values.tobytes()


def insert_chunk(conn, document_id, position, text, embedding):
    """Write a chunk in the three tables with the same id, and return the id."""
    chunk_id = conn.execute(
        "INSERT INTO chunks (document_id, position, text) VALUES (?, ?, ?)", (document_id, position, text)
    ).lastrowid
    conn.execute("INSERT INTO chunks_fts (rowid, text) VALUES (?, ?)", (chunk_id, text))
    conn.execute("INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)", (chunk_id, embedding))
    return chunk_id


def chunk_ids(conn, table):
    """Return the sorted ids (or rowids) stored in a chunk table."""
    column = "id" if table == "chunks" else "rowid"
    return sorted(row[0] for row in conn.execute(f"SELECT {column} FROM {table}"))


@pytest.fixture
def two_chunked_docs(conn):
    """Document 1 with two chunks, document 2 with one."""
    doc1, doc2 = insert_document(conn, "d1"), insert_document(conn, "d2")
    ids = (
        insert_chunk(conn, doc1, 0, "La caldaia è stata sostituita a novembre.", vector(1.0)),
        insert_chunk(conn, doc1, 1, "Il costo totale è stato di 2.400 €.", vector(0.9, 0.1)),
        insert_chunk(conn, doc2, 0, "Perché il gatto dorme sul divano?", vector(0.0, 1.0)),
    )
    return doc1, doc2, ids


def test_chunk_position_is_unique_per_document(conn, two_chunked_docs):
    doc1, _, _ = two_chunked_docs
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        conn.execute("INSERT INTO chunks (document_id, position, text) VALUES (?, 0, 'again')", (doc1,))


def test_chunk_of_missing_document_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute("INSERT INTO chunks (document_id, position, text) VALUES (999, 0, 'x')")


def test_deleting_document_removes_chunks_fts_and_vectors(conn, two_chunked_docs):
    doc1, _, (_, _, kept) = two_chunked_docs
    conn.execute("DELETE FROM documents WHERE id = ?", (doc1,))
    for table in ("chunks", "chunks_fts", "chunks_vec"):
        assert chunk_ids(conn, table) == [kept], table


def test_deleting_a_chunk_removes_its_fts_and_vector(conn, two_chunked_docs):
    _, _, (first, second, third) = two_chunked_docs
    conn.execute("DELETE FROM chunks WHERE id = ?", (first,))
    for table in ("chunks", "chunks_fts", "chunks_vec"):
        assert chunk_ids(conn, table) == [second, third], table


@pytest.mark.parametrize("query", ["caldaia", "CALDAIA", "cald*"])
def test_full_text_search(conn, two_chunked_docs, query):
    _, _, (first, _, _) = two_chunked_docs
    rows = conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?", (query,)).fetchall()
    assert [row[0] for row in rows] == [first]


def test_full_text_search_ignores_accents(conn, two_chunked_docs):
    _, _, (_, _, third) = two_chunked_docs
    rows = conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'perche'").fetchall()
    assert [row[0] for row in rows] == [third]


def test_vector_search_returns_nearest_first(conn, two_chunked_docs):
    _, _, (first, second, third) = two_chunked_docs
    rows = conn.execute(
        "SELECT rowid, distance FROM chunks_vec WHERE embedding MATCH ? AND k = 3 ORDER BY distance",
        (vector(1.0),),
    ).fetchall()
    assert [row[0] for row in rows] == [first, second, third]
    assert rows[0][1] == pytest.approx(0.0, abs=1e-6)  # cosine distance of a vector to itself


def test_vector_search_restricted_to_given_chunks(conn, two_chunked_docs):
    # The "filter first" strategy for tags (phase 3): only some rowids are candidates
    _, _, (_, second, third) = two_chunked_docs
    rows = conn.execute(
        "SELECT rowid FROM chunks_vec WHERE embedding MATCH ? AND k = 3 AND rowid IN (?, ?) ORDER BY distance",
        (vector(1.0), second, third),
    ).fetchall()
    assert [row[0] for row in rows] == [second, third]


def test_vector_of_wrong_size_rejected(conn):
    wrong = np.zeros(EMBEDDING_DIMENSIONS - 1, dtype=np.float32).tobytes()
    with pytest.raises(sqlite3.OperationalError, match="Dimension mismatch"):
        conn.execute("INSERT INTO chunks_vec (rowid, embedding) VALUES (1, ?)", (wrong,))
