"""Check native archive operations without Qt widgets or real model downloads."""

import numpy as np
import pytest

from esper.desktop.service import Archive
from esper.indexing import write_chunks
from esper.tags import get_document_tags, set_document_tags


class TestEmbedder:
    __test__ = False
    model_name = "test/model"
    dimensions = 1024

    def count_tokens(self, text):
        return len(text.split())

    def embed(self, texts):
        values = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        for i, text in enumerate(texts):
            values[i, int("gatto" in text.lower())] = 1
        return values

    def embed_query(self, query):
        return self.embed([query])[0]


@pytest.fixture
def archive(tmp_path):
    created = []
    def factory():
        model = TestEmbedder()
        created.append(model)
        return model
    service = Archive(tmp_path / "data", factory)
    service.created_models = created
    return service


def test_empty_archive_does_not_load_model(archive):
    assert archive.list_documents() == []
    assert archive.list_tags() == []
    assert archive.index() == (0, 0)
    assert archive.search("caldaia") == []
    assert archive.created_models == []


def test_import_index_search_and_rebuild_reuse_one_model(archive, make_file):
    path = make_file("heating.md", "# Caldaia\nCosto della sostituzione 2400 euro.")
    report = archive.import_paths([path, path, path.parent / "missing.txt"])
    assert (report.imported, report.duplicates, len(report.errors)) == (1, 1, 1)
    assert archive.list_documents()[0].status == "queued"
    messages, progress = [], []
    assert archive.index(notify=messages.append, progress=lambda good, bad: progress.append((good, bad))) == (1, 0)
    doc = archive.list_documents()[0]
    assert doc.chunk_count == 1 and doc.status == "indexed"
    assert archive.search("caldaia")[0].document_id == doc.id
    assert archive.index(rebuild=True) == (1, 0)
    assert len(archive.created_models) == 1
    assert progress == [(1, 0)]
    assert messages[0].startswith("Caricamento")
    assert path.read_text() == "# Caldaia\nCosto della sostituzione 2400 euro."


def test_detail_preview_uses_original_instead_of_overlapping_chunks(archive, make_file):
    original = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    archive.import_paths([make_file("notes.txt", original)])
    doc = archive.list_documents()[0]
    with archive.connection() as conn:
        write_chunks(conn, doc.id, ["First paragraph. Second paragraph.", "Second paragraph. Third paragraph."], TestEmbedder().embed(["one", "two"]))
    detail = archive.detail(doc.id)
    assert detail.preview == original
    assert len(detail.chunks) == 2
    assert not detail.truncated


def test_large_utf8_preview_does_not_corrupt_multibyte_characters(archive, make_file):
    content = "€" * 800000
    archive.import_paths([make_file("unicode.txt", content)])
    detail = archive.detail(archive.list_documents()[0].id)
    assert detail.truncated
    assert detail.preview and set(detail.preview) == {"€"}
    assert len(detail.preview) < len(content)


def test_tags_filter_and_deletion_preserve_source(archive, make_file):
    source = make_file("notes.txt", "caldaia")
    archive.import_paths([source])
    assert archive.index() == (1, 0)
    doc = archive.list_documents()[0]
    archive.update_tags(doc.id, ["Casa", "spese casa", "casa"])
    assert archive.list_tags() == [("casa", 1), ("spese-casa", 1)]
    assert archive.list_documents(["CASA", "Spese casa"])[0].id == doc.id
    assert archive.search("caldaia", ["spese casa"])[0].document_id == doc.id
    assert archive.search("caldaia", ["missing"]) == []
    assert archive.delete(doc.id)
    assert archive.list_documents() == []
    assert archive.list_tags() == []
    assert not doc.path.exists()
    assert source.read_text() == "caldaia"


def test_invalid_replacement_tags_leave_existing_tags_intact(archive, make_file):
    archive.import_paths([make_file("notes.txt", "caldaia")])
    document_id = archive.list_documents()[0].id
    archive.update_tags(document_id, ["old"])
    with pytest.raises(ValueError):
        archive.update_tags(document_id, ["new", "  "])
    assert archive.list_tags() == [("old", 1)]
    with pytest.raises(ValueError):
        archive.update_tags(999, ["new"])
    assert archive.list_tags() == [("old", 1)]


def test_unknown_existing_metadata_requires_explicit_rebuild(archive, make_file):
    archive.import_paths([make_file("notes.txt", "caldaia")])
    assert archive.index() == (1, 0)
    with archive.connection() as conn, conn:
        conn.execute("DELETE FROM index_settings")
    with pytest.raises(ValueError, match="esper reindex"):
        archive.search("caldaia")
    assert archive.search("caldaia", mode="keyword")
    assert archive.index(rebuild=True) == (1, 0)
    assert archive.search("caldaia")


def test_cooperative_stop_preserves_unfinished_queue_for_resume(archive, make_file):
    archive.import_paths([make_file("one.txt", "one"), make_file("two.txt", "two")])
    progress = []
    assert archive.index(progress=lambda good, bad: progress.append(good), should_stop=lambda: bool(progress)) == (1, 0)
    assert [doc.status for doc in archive.list_documents()] == ["indexed", "queued"]
    assert archive.index() == (1, 0)
    assert all(doc.status == "indexed" for doc in archive.list_documents())


def test_stop_before_model_loading_does_not_load_or_reset(archive, make_file):
    archive.import_paths([make_file("one.txt", "one")])
    assert archive.index(rebuild=True, should_stop=lambda: True) == (0, 0)
    assert archive.created_models == []
    assert archive.list_documents()[0].status == "queued"


def test_unsupported_documents_keep_originals_and_record_an_error(archive, make_file):
    archive.import_paths([make_file("document.pdf", "Not a supported text document.")])
    assert archive.index() == (0, 1)
    doc = archive.list_documents()[0]
    assert doc.kind == "pdf" and doc.status == "error" and doc.path.exists()
    assert archive.detail(doc.id).preview == ""


def test_unknown_document_detail_fails_cleanly(archive):
    with pytest.raises(ValueError, match="no document"):
        archive.detail(999)
