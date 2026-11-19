"""Check persisted index identity, legacy metadata and compatibility barriers."""

from dataclasses import replace
import sqlite3

import pytest

from esper.chunking import CHUNKER_VERSION
from esper.config import EMBEDDING_DIMENSIONS
from esper.db import connect, get_vector_dimensions, init_schema, recreate_vector_index
from esper.index_settings import (
    IndexSettings, ensure_index_settings, get_index_settings, set_index_settings,
)


@pytest.fixture
def settings():
    return IndexSettings("test/model", EMBEDDING_DIMENSIONS, 400, 50)


def test_unknown_settings_are_not_invented_by_reading(conn):
    changes = conn.total_changes
    assert get_index_settings(conn) is None
    assert conn.total_changes == changes


def test_settings_update_persist_and_participate_in_rollback(tmp_path, settings):
    db_path = tmp_path / "settings.db"
    conn = connect(db_path)
    try:
        init_schema(conn)
        with conn:
            set_index_settings(conn, settings)
        with pytest.raises(RuntimeError), conn:
            set_index_settings(conn, replace(settings, chunk_max_tokens=300))
            raise RuntimeError("Abort the containing transaction")
        assert get_index_settings(conn) == settings
        updated = replace(settings, chunk_max_tokens=250)
        with conn:
            set_index_settings(conn, updated)
        assert conn.execute("SELECT COUNT(*) FROM index_settings").fetchone()[0] == 1
    finally:
        conn.close()
    conn = connect(db_path)
    try:
        assert get_index_settings(conn) == updated
    finally:
        conn.close()


@pytest.mark.parametrize("changes", [
    {"model_name": ""}, {"model_name": "  "},
    {"dimensions": 0}, {"dimensions": -1}, {"dimensions": True},
    {"chunk_max_tokens": 0}, {"chunk_overlap_tokens": -1},
    {"chunk_overlap_tokens": 400}, {"chunk_overlap_tokens": 1.5},
    {"chunker_version": 0},
])
def test_invalid_settings_fail_before_any_index_work(settings, changes):
    with pytest.raises(ValueError):
        replace(settings, **changes)


def test_unused_index_records_settings_and_matching_settings_are_read_only(conn, settings):
    ensure_index_settings(conn, settings)
    assert get_index_settings(conn) == settings
    changes = conn.total_changes
    ensure_index_settings(conn, settings)
    assert conn.total_changes == changes
    assert not conn.in_transaction


@pytest.mark.parametrize("changes", [
    {"model_name": "different/model"}, {"dimensions": 768},
    {"chunk_max_tokens": 300}, {"chunk_overlap_tokens": 25},
    {"chunker_version": CHUNKER_VERSION + 1},
])
def test_changed_settings_require_explicit_reindex(conn, settings, changes):
    ensure_index_settings(conn, settings)
    with pytest.raises(ValueError, match="esper reindex"):
        ensure_index_settings(conn, replace(settings, **changes))
    assert get_index_settings(conn) == settings


def test_actual_vector_width_is_checked_even_when_metadata_matches(conn, settings):
    with conn:
        set_index_settings(conn, settings)
        recreate_vector_index(conn, 768)
    assert get_vector_dimensions(conn) == 768
    with pytest.raises(ValueError, match="dimensions.*esper reindex"):
        ensure_index_settings(conn, settings)


@pytest.mark.parametrize("source", ["empty_indexed_document", "chunks", "fts", "vectors"])
def test_unknown_existing_index_is_never_labelled_from_configuration(conn, settings, source):
    if source in {"empty_indexed_document", "chunks"}:
        conn.execute(
            "INSERT INTO documents (sha256, original_name, mime_type, size_bytes, stored_name, status) "
            "VALUES ('abc', 'old.txt', 'text/plain', 0, 'abc.txt', ?)",
            ("indexed" if source == "empty_indexed_document" else "error",),
        )
        if source == "chunks":
            conn.execute("INSERT INTO chunks (document_id, position, text) VALUES (1, 0, 'Old text')")
    elif source == "fts":
        conn.execute("INSERT INTO chunks_fts (rowid, text) VALUES (1, 'Orphan text')")
    else:
        conn.execute(
            "INSERT INTO chunks_vec (rowid, embedding) VALUES (1, ?)",
            (bytes(4 * EMBEDDING_DIMENSIONS),),
        )
    conn.commit()
    with pytest.raises(ValueError, match="unknown.*esper reindex"):
        ensure_index_settings(conn, settings)
    assert get_index_settings(conn) is None


def test_legacy_settings_migration_preserves_values_and_marks_old_chunker(conn, settings):
    conn.execute("DROP TABLE index_settings")
    conn.execute(
        "CREATE TABLE index_settings (id INTEGER PRIMARY KEY, model_name TEXT, "
        "dimensions INTEGER, chunk_max_tokens INTEGER, chunk_overlap_tokens INTEGER)"
    )
    conn.execute("INSERT INTO index_settings VALUES (1, 'test/model', 1024, 400, 50)")
    conn.commit()
    init_schema(conn)
    init_schema(conn)
    recorded = get_index_settings(conn)
    assert recorded == replace(settings, chunker_version=1)
    with pytest.raises(ValueError, match="esper reindex"):
        ensure_index_settings(conn, settings)


def test_migrating_an_empty_legacy_table_keeps_settings_unknown(conn):
    conn.execute("DROP TABLE index_settings")
    conn.execute(
        "CREATE TABLE index_settings (id INTEGER PRIMARY KEY, model_name TEXT, "
        "dimensions INTEGER, chunk_max_tokens INTEGER, chunk_overlap_tokens INTEGER)"
    )
    init_schema(conn)
    assert get_index_settings(conn) is None


def test_failed_vector_replacement_rolls_back_the_original_table(conn):
    with pytest.raises(RuntimeError), conn:
        # Start a transaction before the DDL, as the reset pipeline does.
        conn.execute("DELETE FROM chunks")
        recreate_vector_index(conn, 768)
        assert get_vector_dimensions(conn) == 768
        raise RuntimeError("Abort reset")
    assert get_vector_dimensions(conn) == EMBEDDING_DIMENSIONS


def test_chunker_version_constraint_is_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(
            "INSERT INTO index_settings VALUES (1, 'test/model', 1024, 400, 50, 0)"
        )
