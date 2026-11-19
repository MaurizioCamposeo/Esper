"""Digital PDF extraction, page provenance, migration and failure recovery."""

from pathlib import Path
import sqlite3

import numpy as np
import pymupdf
import pytest

from esper.db import connect, init_schema
from esper.extract import PDFExtractionError, extract_document, extract_text
from esper.indexing import index_document, write_chunks
from esper.search import search_documents
from esper.storage import import_file


def make_pdf(path, texts, *, headers=False, password=None):
    with pymupdf.open() as pdf:
        for text in texts:
            page = pdf.new_page()
            if headers:
                page.insert_text((45, 25), "Esper fictional archive", fontsize=9)
                page.insert_text((45, 820), "Repeated footer", fontsize=9)
            if text:
                assert page.insert_textbox(pymupdf.Rect(60, 100, 530, 760), text, fontsize=12) >= 0
        options = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "owner_pw": "owner", "user_pw": password} if password else {}
        pdf.save(path, **options)
    return path


class Model:
    model_name = "pdf-test"
    dimensions = 1024

    def count_tokens(self, text):
        return len(text.split())

    def embed(self, texts):
        values = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        for i, text in enumerate(texts):
            values[i, int("caldaia" in text)] = 1
        return values

    def embed_query(self, text):
        return self.embed([text])[0]


def test_pdf_preserves_pages_and_removes_repeated_margins(tmp_path):
    path = make_pdf(tmp_path / "notes.pdf", ["Primo capitolo.", "Costo della caldaia 2400 euro.", "Ultimo capitolo."], headers=True)
    result = extract_document(path, "application/pdf")
    assert result.page_count == 3 and result.warning is None
    assert [section.page for section in result.sections] == [1, 2, 3]
    assert "caldaia" in result.sections[1].text
    assert "Repeated footer" not in extract_text(path, "application/pdf")
    assert "fictional archive" not in extract_text(path, "application/pdf")


def test_pdf_body_repetitions_are_preserved_and_inline_hyphens_survive(tmp_path):
    path = make_pdf(tmp_path / "notes.pdf", ["Codice AB-123. Testo identico nel corpo."] * 3)
    result = extract_document(path, "application/pdf")
    assert all("AB-123" in section.text for section in result.sections)
    assert len(result.sections) == 3


def test_pdf_rejoins_line_end_hyphenation(tmp_path):
    path = make_pdf(tmp_path / "hyphen.pdf", ["Costo dell inter-\nvento: 95 euro. Codice AB-123.\nSerie AB-\nCD."])
    text = extract_text(path, "application/pdf")
    assert "intervento" in text and "AB-123" in text
    assert "AB-\nCD" in text


def test_long_pdf_pages_chunk_independently(conn, tmp_path):
    path = tmp_path / "long.pdf"
    with pymupdf.open() as pdf:
        for text in ("Prima pagina contratto. " * 150, "Seconda pagina caldaia. " * 150):
            page = pdf.new_page()
            assert page.insert_textbox(pymupdf.Rect(60, 80, 540, 780), text, fontsize=9) >= 0
        pdf.save(path)
    files = tmp_path / "archive"
    document_id = import_file(conn, path, files)[0]
    assert index_document(conn, Model(), document_id, files)
    chunks = list(conn.execute("SELECT text, page FROM chunks ORDER BY position"))
    assert len(chunks) >= 4
    assert {chunk["page"] for chunk in chunks} == {1, 2}
    for chunk in chunks:
        assert len(chunk["text"].split()) <= 400
        assert ("Prima" in chunk["text"]) == (chunk["page"] == 1)
        assert ("Seconda" in chunk["text"]) == (chunk["page"] == 2)


def test_mixed_pdf_warns_without_renumbering_pages(tmp_path):
    path = make_pdf(tmp_path / "mixed.pdf", ["Testo iniziale", "", "Caldaia e ricevuta"])
    result = extract_document(path, "application/pdf")
    assert [section.page for section in result.sections] == [1, 3]
    assert result.page_count == 3
    assert "2" in result.warning and "OCR" in result.warning


@pytest.mark.parametrize("kind, message", [("blank", "OCR"), ("encrypted", "password"), ("corrupt", "Impossibile leggere")])
def test_unreadable_pdf_has_actionable_error(tmp_path, kind, message):
    path = tmp_path / "bad.pdf"
    if kind == "corrupt":
        path.write_bytes(b"%PDF-1.7 broken")
    else:
        make_pdf(path, ["" if kind == "blank" else "Secret text"], password="secret" if kind == "encrypted" else None)
    with pytest.raises(PDFExtractionError, match=message):
        extract_document(path, "application/pdf")


def test_index_search_and_failed_replacement_preserve_page_provenance(conn, tmp_path):
    path = make_pdf(tmp_path / "invoice.pdf", ["Contratto di acquisto", "", "Ricevuta caldaia 2400 euro"])
    files = tmp_path / "archive"
    doc_id = import_file(conn, path, files)[0]
    model = Model()
    assert index_document(conn, model, doc_id, files)
    hit = search_documents(conn, "caldaia", model, mode="hybrid")[0]
    assert hit.document_id == doc_id and hit.matches[0].page == 3
    rows = [tuple(row) for row in conn.execute("SELECT position, page, text FROM chunks ORDER BY position")]
    assert [row[1] for row in rows] == [1, 3]
    assert all(not ("Contratto" in row[2] and "caldaia" in row[2]) for row in rows)
    metadata = tuple(conn.execute("SELECT page_count, extraction_warning FROM documents").fetchone())
    assert metadata[0] == 3 and "2" in metadata[1]
    with pytest.raises(ValueError):
        write_chunks(conn, doc_id, ["New"], model.embed(["New"]), pages=[], page_count=1)
    assert rows == [tuple(row) for row in conn.execute("SELECT position, page, text FROM chunks ORDER BY position")]
    assert metadata == tuple(conn.execute("SELECT page_count, extraction_warning FROM documents").fetchone())


def test_old_database_migrates_without_rebuilding_text_or_touching_primary_data(tmp_path):
    path = tmp_path / "old.db"
    conn = connect(path)
    conn.executescript("""
        CREATE TABLE documents (
          id INTEGER PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL, original_name TEXT NOT NULL,
          mime_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, stored_name TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued', error TEXT,
          created_at TEXT NOT NULL DEFAULT '2026-01-01');
        CREATE TABLE chunks (
          id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id),
          position INTEGER NOT NULL, text TEXT NOT NULL, UNIQUE(document_id, position));
        INSERT INTO documents VALUES (1, 'hash', 'old.txt', 'text/plain', 3, 'hash.txt', 'indexed', NULL, '2026-01-01');
        INSERT INTO chunks VALUES (1, 1, 0, 'Preserved text');
    """)
    init_schema(conn)
    init_schema(conn)
    assert tuple(conn.execute("SELECT text, page, source FROM chunks").fetchone()) == ("Preserved text", None, "text")
    assert tuple(conn.execute("SELECT original_name, status, page_count, extraction_warning FROM documents").fetchone()) == ("old.txt", "indexed", None, None)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE chunks SET page=0")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE chunks SET source='unknown'")
    conn.close()
