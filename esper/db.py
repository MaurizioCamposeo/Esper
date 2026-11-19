"""Open a SQLite connection with the project's standard settings."""

import sqlite3
import re
from pathlib import Path
import sqlite_vec
from esper.config import EMBEDDING_DIMENSIONS

CHUNK_SOURCE_COLUMN = "TEXT NOT NULL DEFAULT 'text' CHECK (source IN ('text', 'ocr', 'caption'))"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY,
    sha256        TEXT    NOT NULL UNIQUE,
    original_name TEXT    NOT NULL,
    mime_type     TEXT    NOT NULL,
    size_bytes    INTEGER NOT NULL,
    stored_name   TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued', 'processing', 'indexed', 'error')),
    error         TEXT,
    page_count    INTEGER CHECK (page_count > 0),
    extraction_warning TEXT,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY,
    name TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS document_tags (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES tags(id)      ON DELETE CASCADE,
    PRIMARY KEY (document_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_document_tags_tag ON document_tags(tag_id);

CREATE TABLE IF NOT EXISTS index_settings (
    id                   INTEGER PRIMARY KEY CHECK (id = 1),
    model_name           TEXT NOT NULL,
    dimensions           INTEGER NOT NULL CHECK (dimensions > 0),
    chunk_max_tokens     INTEGER NOT NULL CHECK (chunk_max_tokens > 0),
    chunk_overlap_tokens INTEGER NOT NULL
        CHECK (
            chunk_overlap_tokens >= 0
            AND chunk_overlap_tokens < chunk_max_tokens
        ),
    chunker_version INTEGER NOT NULL DEFAULT 1 CHECK (chunker_version > 0)
);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    page        INTEGER CHECK (page > 0),
    source      {CHUNK_SOURCE_COLUMN},
    UNIQUE (document_id, position)
);

CREATE TABLE IF NOT EXISTS map_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    revision INTEGER NOT NULL DEFAULT 0,
    built_revision INTEGER,
    version INTEGER
);
INSERT OR IGNORE INTO map_state (id) VALUES (1);

CREATE TABLE IF NOT EXISTS map_points (
    document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    x REAL NOT NULL, y REAL NOT NULL, z REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS map_edges (
    first_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    second_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    distance REAL NOT NULL,
    PRIMARY KEY (first_id, second_id)
);

-- write_chunks always publishes new vectors with a final indexed status update.
CREATE TRIGGER IF NOT EXISTS map_status_changed AFTER UPDATE OF status ON documents
WHEN old.status = 'indexed' OR new.status = 'indexed'
BEGIN
    UPDATE map_state SET revision = revision + 1;
END;
CREATE TRIGGER IF NOT EXISTS map_document_deleted AFTER DELETE ON documents
WHEN old.status = 'indexed'
BEGIN
    UPDATE map_state SET revision = revision + 1;
END;

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5 (
    text,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0 (
    embedding float[{EMBEDDING_DIMENSIONS}] distance_metric=cosine
);

CREATE TRIGGER IF NOT EXISTS chunks_after_delete AFTER DELETE ON chunks
BEGIN 
    DELETE FROM chunks_fts WHERE rowid = old.id;
    DELETE FROM chunks_vec WHERE rowid = old.id;
END;
"""

def connect(db_path: Path | str) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row

    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL') # changes are first written to a log file and later copied to the main file
    conn.execute('PRAGMA busy_timeout = 5000')


    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they do not exist."""
    conn.executescript(SCHEMA)
    with conn:
        for table, fields in {
            "chunks": {"page": "INTEGER CHECK (page > 0)", "source": CHUNK_SOURCE_COLUMN},
            "documents": {"page_count": "INTEGER CHECK (page_count > 0)", "extraction_warning": "TEXT"},
        }.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for name, declaration in fields.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(index_settings)")}
    if "chunker_version" not in columns:
        with conn:
            conn.execute(
                "ALTER TABLE index_settings ADD COLUMN chunker_version "
                "INTEGER NOT NULL DEFAULT 1 CHECK (chunker_version > 0)"
            )
    # Older image indexes contain only OCR or a short BLIP caption. Let the
    # normal queue regenerate those images once, including caption-only photos.
    if conn.execute("PRAGMA user_version").fetchone()[0] == 0:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("PRAGMA user_version").fetchone()[0] == 0:
                conn.execute(
                    "UPDATE documents SET status = 'queued' WHERE status = 'indexed' "
                    "AND mime_type IN ('image/jpeg', 'image/png')"
                )
                conn.execute("PRAGMA user_version = 1")


def get_vector_dimensions(conn: sqlite3.Connection) -> int:
    """Read the vector width from the actual table, independent of configuration."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'chunks_vec' AND type = 'table'"
    ).fetchone()
    match = re.search(r"\bfloat\s*\[\s*(\d+)\s*\]", row["sql"], re.IGNORECASE) if row else None
    if match is None:
        raise ValueError("Cannot determine vector index dimensions; run 'esper reindex'")
    return int(match.group(1))


def recreate_vector_index(conn: sqlite3.Connection, dimensions: int) -> None:
    """Replace the vector table inside the caller's reset transaction."""
    if type(dimensions) is not int or dimensions <= 0:
        raise ValueError("dimensions must be a positive integer")
    conn.execute("DROP TABLE chunks_vec")
    conn.execute(
        f"CREATE VIRTUAL TABLE chunks_vec USING vec0 ("
        f"embedding float[{dimensions}] distance_metric=cosine)"
    )
