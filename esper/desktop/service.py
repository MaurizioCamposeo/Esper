"""Desktop archive operations independent of Qt, with one connection per operation."""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import codecs
import sqlite3
from typing import Any

from esper.archive_map import load_archive_map
from esper.db import connect, init_schema
from esper.extract import TextSource, decode_text
from esper.indexing import index_queued, reindex_all
from esper.search import SearchHit, search_documents, searchable_chunk_count
from esper.storage import delete_document, get_document, import_file
from esper.tags import get_document_by_tag, get_document_tags, set_document_tags


@dataclass(frozen=True)
class Document:
    id: int
    name: str
    mime: str
    size: int
    status: str
    error: str | None
    created_at: str
    tags: tuple[str, ...]
    chunk_count: int
    excerpt: str
    path: Path
    page_count: int | None = None
    extraction_warning: str | None = None
    excerpt_source: TextSource = "text"

    @property
    def kind(self) -> str:
        if self.mime == "application/pdf":
            return "pdf"
        if self.mime.startswith("image/"):
            return "image"
        if self.path.suffix.lower() in (".md", ".markdown"):
            return "markdown"
        return "text" if self.mime == "text/plain" else "file"


@dataclass(frozen=True)
class DocumentDetail:
    document: Document
    chunks: tuple[dict, ...]
    preview: str
    truncated: bool


@dataclass(frozen=True)
class ImportReport:
    imported: int
    duplicates: int
    errors: tuple[str, ...]


@dataclass(frozen=True)
class PDFPage:
    document_id: int
    page: int
    page_count: int
    png: bytes


class Archive:
    """Reuse one lazily loaded model on the desktop worker's thread."""

    def __init__(self, data_dir: Path, embedder_factory: Callable[[], Any] | None = None):
        self.data_dir = Path(data_dir).resolve()
        self.db_path = self.data_dir / "esper.db"
        self.files_dir = self.data_dir / "files"
        self._embedder_factory = embedder_factory
        self._embedder = None
        with self.connection() as conn:
            init_schema(conn)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _document(self, conn: sqlite3.Connection, row: sqlite3.Row) -> Document:
        chunks = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (row["id"],),
        ).fetchone()[0]
        first = conn.execute(
            "SELECT text, source FROM chunks WHERE document_id = ? ORDER BY position LIMIT 1", (row["id"],),
        ).fetchone()
        return Document(
            row["id"], row["original_name"], row["mime_type"], row["size_bytes"],
            row["status"], row["error"], row["created_at"],
            tuple(get_document_tags(conn, row["id"])), chunks, first["text"][:400] if first else "",
            self.files_dir / row["stored_name"],
            row["page_count"], row["extraction_warning"], first["source"] if first else "text",
        )

    def list_documents(self, tags: Sequence[str] = ()) -> list[Document]:
        with self.connection() as conn:
            conn.execute("BEGIN")
            ids = get_document_by_tag(conn, list(tags))
            return [self._document(conn, get_document(conn, document_id)) for document_id in ids]

    def map_revision(self) -> int:
        with self.connection() as conn:
            return conn.execute("SELECT revision FROM map_state").fetchone()[0]

    def spatial_map(self):
        with self.connection() as conn:
            return load_archive_map(conn)

    def list_tags(self) -> list[tuple[str, int]]:
        with self.connection() as conn:
            return [tuple(row) for row in conn.execute(
                "SELECT t.name, COUNT(*) FROM tags AS t "
                "JOIN document_tags AS dt ON dt.tag_id = t.id GROUP BY t.id ORDER BY t.name"
            )]

    def detail(self, document_id: int) -> DocumentDetail:
        with self.connection() as conn:
            row = get_document(conn, document_id)
            if row is None:
                raise ValueError(f"no document #{document_id}")
            doc = self._document(conn, row)
            chunks = tuple(dict(chunk) for chunk in conn.execute(
                "SELECT id, position, text, page, source FROM chunks WHERE document_id = ? ORDER BY position",
                (document_id,),
            ))
        preview, truncated = "", False
        if doc.mime in ("text/plain", "text/markdown"):
            with doc.path.open("rb") as source:
                data = source.read(2 * 1024 * 1024 + 1)
            truncated = len(data) > 2 * 1024 * 1024
            data = data[:2 * 1024 * 1024]
            if truncated:
                try:
                    preview = codecs.getincrementaldecoder("utf-8-sig")().decode(data, final=False)
                except UnicodeDecodeError:
                    preview = decode_text(data)
            else:
                preview = decode_text(data)
        return DocumentDetail(doc, chunks, preview, truncated)

    def render_pdf_page(self, document_id: int, page: int) -> PDFPage:
        """Render one bounded-size page on the archive worker, not the GUI thread."""
        import pymupdf

        with self.connection() as conn:
            row = get_document(conn, document_id)
            if row is None or row["mime_type"] != "application/pdf":
                raise ValueError("Documento PDF non disponibile")
            path = self.files_dir / row["stored_name"]
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass:
                raise ValueError("PDF protetto da password: importa una copia sbloccata.")
            if type(page) is not int or not 1 <= page <= len(pdf):
                raise ValueError("Numero di pagina non valido")
            source = pdf[page - 1]
            scale = min(1.5, 1400 / max(source.rect.width, source.rect.height))
            pixmap = source.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False, colorspace=pymupdf.csRGB)
            return PDFPage(document_id, page, len(pdf), pixmap.tobytes("png"))

    def import_paths(self, paths: Sequence[Path]) -> ImportReport:
        imported, duplicates, errors = 0, 0, []
        with self.connection() as conn:
            for path in paths:
                try:
                    _, created = import_file(conn, Path(path), self.files_dir)
                    imported += int(created)
                    duplicates += int(not created)
                except (OSError, ValueError, sqlite3.DatabaseError) as exc:
                    errors.append(f"{Path(path).name}: {exc}")
        return ImportReport(imported, duplicates, tuple(errors))

    def update_tags(self, document_id: int, tags: list[str]) -> None:
        with self.connection() as conn:
            set_document_tags(conn, document_id, tags)

    def delete(self, document_id: int) -> bool:
        with self.connection() as conn:
            return delete_document(conn, document_id, self.files_dir)

    def _model(self, notify: Callable[[str], None]):
        if self._embedder is None:
            notify("Caricamento del modello di ricerca…")
            if self._embedder_factory is None:
                from esper.embedding import Embedder
                self._embedder = Embedder()
            else:
                self._embedder = self._embedder_factory()
        return self._embedder

    def index(
        self, *, rebuild: bool = False, notify: Callable[[str], None] = lambda _: None,
        progress: Callable[[int, int], None] | None = None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> tuple[int, int]:
        with self.connection() as conn:
            condition = "" if rebuild else "WHERE status IN ('queued', 'processing')"
            count = conn.execute(f"SELECT COUNT(*) FROM documents {condition}").fetchone()[0]
            if not count or should_stop():
                return 0, 0
            model = self._model(notify)
            if should_stop():
                return 0, 0
            notify("Ricostruzione dell’indice…" if rebuild else "Indicizzazione dei documenti…")
            operation = reindex_all if rebuild else index_queued
            return operation(conn, model, self.files_dir, on_progress=progress, should_stop=should_stop)

    def search(
        self, query: str, tags: Sequence[str] = (), mode: str = "hybrid",
        notify: Callable[[str], None] = lambda _: None,
    ) -> list[SearchHit]:
        with self.connection() as conn:
            if not searchable_chunk_count(conn, tags):
                return []
            model = self._model(notify) if mode != "keyword" else None
            notify("Ricerca in corso…")
            return search_documents(conn, query, model, tags=tags, mode=mode, limit=20)
