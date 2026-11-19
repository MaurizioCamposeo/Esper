"""Verify OCR routing, caption provenance and the normal retrieval path."""

import json
import subprocess

import numpy as np
from PIL import Image
import pytest

from esper.cli import cmd_search
from esper.extract import extract_document
from esper.image_text import ImageExtractionError, ocr_text, transcribe_image
from esper.indexing import index_document
from esper.storage import import_file


TSV_HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tconf\ttext\n"


def tsv_line(*words):
    return TSV_HEADER + "".join(
        f"5\t1\t1\t1\t1\t{confidence}\t{word}\n" for confidence, word in words
    )


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        ([], ""),
        ([(97, "AB-7429")], "AB-7429"),
        ([(90, "48")], "48"),
        ([(82, "Totale"), (49, "18,40"), (20, "4©")], "Totale 18,40"),
        ([(70.59, "ty"), (53, "nl"), (91, "|")], ""),
        ([(88, "Sì"), (90, "No")], "Sì No"),
    ],
)
def test_ocr_preserves_legible_text_and_discards_noise(tokens, expected):
    assert ocr_text(tsv_line(*tokens)) == expected


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (FileNotFoundError(), "installa Tesseract"),
        (subprocess.TimeoutExpired("tesseract", 45), "Tempo massimo"),
        (subprocess.CompletedProcess([], 1, b"", b""), "non riuscito"),
        (subprocess.CompletedProcess([], 0, TSV_HEADER.encode(), b"Failed loading language 'ita'"), "ita e eng"),
        (subprocess.CompletedProcess([], 0, b"invalid", b""), "risultato OCR non valido"),
    ],
)
def test_ocr_reports_engine_failures(error, message, monkeypatch):
    def run(*args, **kwargs):
        if isinstance(error, Exception):
            raise error
        return error

    monkeypatch.setattr("esper.image_text.subprocess.run", run)
    with pytest.raises(ImageExtractionError, match=message):
        transcribe_image(Image.new("RGB", (8, 8)))


def test_ocr_uses_the_provisioned_binary_and_languages_without_path(tmp_path, monkeypatch):
    runtime = tmp_path / "tesseract"
    executable = runtime / "bin" / "tesseract"
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr("esper.image_text.RUNTIME_DIR", tmp_path)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("TESSDATA_PREFIX", "/stale/path")

    def run(command, **kwargs):
        assert command == [
            str(executable), "stdin", "stdout", "-l", "ita+eng", "--psm", "11",
            "--tessdata-dir", str(runtime / "tessdata"), "tsv",
        ]
        return subprocess.CompletedProcess(command, 0, tsv_line((93, "AB-7429")).encode(), b"")

    monkeypatch.setattr("esper.image_text.subprocess.run", run)
    assert transcribe_image(Image.new("RGB", (8, 8))) == "AB-7429"


def test_corrupt_image_is_reported_without_running_ocr(tmp_path, monkeypatch):
    path = tmp_path / "corrupt.jpg"
    path.write_bytes(b"not an image")
    monkeypatch.setattr("esper.image_text.transcribe_image", lambda _: pytest.fail("OCR was called"))
    with pytest.raises(ImageExtractionError, match="Impossibile leggere"):
        extract_document(path, "image/jpeg")


class ImageTestEmbedder:
    model_name = "test/image-text"
    dimensions = 1024

    def count_tokens(self, text):
        return len(text.split())

    def embed(self, passages):
        vectors = np.zeros((len(passages), self.dimensions), dtype=np.float32)
        vectors[:, 0] = 1
        return vectors


@pytest.mark.parametrize(
    ("extension", "tokens", "query", "source"),
    [
        ("png", [(93, "AB-7429")], "7429", "ocr"),
        ("jpg", [(71, "ty")], "tomatoes", "caption"),
    ],
)
def test_archived_image_indexes_caption_and_any_readable_text(
    conn, files_dir, tmp_path, monkeypatch, capsys, extension, tokens, query, source,
):
    path = tmp_path / f"image.{extension}"
    Image.new("RGB", (8, 8), "white").save(path)
    calls = []

    def run(command, *, input, capture_output, check, timeout):
        assert command == ["tesseract", "stdin", "stdout", "-l", "ita+eng", "--psm", "11", "tsv"]
        assert input.startswith(b"\x89PNG")
        return subprocess.CompletedProcess(command, 0, tsv_line(*tokens).encode(), b"")

    def describe(image):
        calls.append(image.size)
        return "Fresh tomatoes on a wooden table."

    monkeypatch.setattr("esper.image_text.subprocess.run", run)
    monkeypatch.setattr("esper.image_text.RUNTIME_DIR", tmp_path / "no-runtime")
    monkeypatch.setattr("esper.image_text.describe_image", describe)
    doc_id, _ = import_file(conn, path, files_dir)
    assert index_document(conn, ImageTestEmbedder(), doc_id, files_dir)
    assert calls == [(8, 8)]
    assert cmd_search(conn, "tomatoes", [], 5, "keyword", json_output=True) == 0
    assert json.loads(capsys.readouterr().out)[0]["matches"][0]["source"] == "caption"

    assert cmd_search(conn, query, [], 5, "keyword", json_output=True) == 0
    hit, = json.loads(capsys.readouterr().out)
    match, = hit["matches"]
    assert hit["document_id"] == doc_id
    assert match["source"] == source
    assert match["page"] is None


@pytest.mark.parametrize("failed_source", ["ocr", "caption", "both"])
def test_partial_or_total_image_failure(conn, files_dir, tmp_path, monkeypatch, failed_source):
    path = tmp_path / "image.png"
    Image.new("RGB", (8, 8)).save(path)
    doc_id, _ = import_file(conn, path, files_dir)

    def fail(_):
        raise ImageExtractionError("engine unavailable")

    monkeypatch.setattr("esper.image_text.transcribe_image", fail if failed_source in ("ocr", "both") else lambda _: "AB-7429")
    monkeypatch.setattr("esper.image_text.describe_image", fail if failed_source in ("caption", "both") else lambda _: "Tomatoes on a table.")
    success = index_document(conn, ImageTestEmbedder(), doc_id, files_dir)
    status, error, warning = conn.execute("SELECT status, error, extraction_warning FROM documents").fetchone()
    if failed_source == "both":
        assert not success and status == "error"
        assert "OCR:" in error and "Descrizione:" in error
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
    else:
        assert success and status == "indexed" and "engine unavailable" in warning
        expected = "caption" if failed_source == "ocr" else "ocr"
        assert conn.execute("SELECT source FROM chunks").fetchone()[0] == expected


def test_existing_images_are_queued_once(conn, files_dir, tmp_path):
    from esper.db import init_schema

    for name in ("old.png", "old.txt"):
        path = tmp_path / name
        path.write_text(name)
        import_file(conn, path, files_dir)
    with conn:
        conn.execute("UPDATE documents SET status='indexed'")
        conn.execute("PRAGMA user_version = 0")
    init_schema(conn)
    assert [row[0] for row in conn.execute("SELECT status FROM documents ORDER BY id")] == ["queued", "indexed"]
    with conn:
        conn.execute("UPDATE documents SET status='indexed'")
    init_schema(conn)
    assert conn.execute("SELECT COUNT(*) FROM documents WHERE status='queued'").fetchone()[0] == 0
