"""Exercise the native desktop event loop using Qt's offscreen platform."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from threading import Event
import numpy as np
import pytest
from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtGui import QDesktopServices, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea

from esper.desktop.app import MainWindow
from esper.desktop.service import Archive


class FakeEmbedder:
    model_name = "test/model"
    dimensions = 1024

    def count_tokens(self, text):
        return len(text.split())

    def embed(self, texts):
        values = np.zeros((len(texts), 1024), dtype=np.float32)
        for i, text in enumerate(texts):
            values[i, int("gatto" in text.lower())] = 1
        return values

    def embed_query(self, query):
        return self.embed([query])[0]


def wait_for(predicate, timeout=5000):
    if predicate():
        return
    loop = QEventLoop()
    check = QTimer()
    check.setInterval(10)
    check.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    check.start()
    deadline.start(timeout)
    loop.exec()
    check.stop()
    deadline.stop()
    assert predicate(), "Native UI operation did not finish"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def window(qapp, tmp_path):
    archive = Archive(tmp_path / "archive", FakeEmbedder)
    settings = QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat)
    instance = MainWindow(archive, settings, auto_index=False)
    instance.show()
    QApplication.processEvents()
    yield instance
    instance.close()
    wait_for(lambda: not instance.thread.isRunning())
    QApplication.processEvents()
    instance.deleteLater()
    QApplication.processEvents()


def button(window, text):
    return next(widget for widget in window.findChildren(QPushButton) if widget.text() == text)


def import_note(window, make_file):
    path = make_file("heating.md", "# Caldaia\nCosto della sostituzione 2400 euro.")
    window.import_files([path])
    wait_for(lambda: len(window.documents) == 1 and window.documents[0].status == "indexed")
    wait_for(lambda: not window._busy)
    return path


def test_native_import_and_semantic_search_show_real_source_passages(window, make_file):
    source = import_note(window, make_file)
    window.search_input.setText("riscaldamento")
    window.run_search()
    wait_for(lambda: bool(window.hits) and not window._searching)
    assert window.hits[0].name == "heating.md"
    assert "2400 euro" in window.hits[0].matches[0].text
    assert window.section_title.text() == "1 risultato"
    assert source.exists()


def test_native_image_retry_and_caption_provenance(window, monkeypatch, tmp_path):
    from esper.image_text import ImageExtractionError

    path = tmp_path / "photo.png"
    image = QImage(12, 12, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.green)
    assert image.save(str(path))

    def ocr_unavailable(_):
        raise ImageExtractionError("Per indicizzare le immagini, installa Tesseract.")

    monkeypatch.setattr("esper.image_text.transcribe_image", ocr_unavailable)
    monkeypatch.setattr("esper.image_text.describe_image", ocr_unavailable)
    window.import_files([path])
    wait_for(lambda: len(window.documents) == 1 and window.documents[0].status == "error")
    doc_id = window.documents[0].id
    window.open_document(doc_id)
    wait_for(lambda: window.reader is not None and window.reader.isVisible())
    retry = button(window.reader, "Riprova indicizzazione")

    monkeypatch.setattr("esper.image_text.transcribe_image", lambda _: "")
    monkeypatch.setattr("esper.image_text.describe_image", lambda _: "Un gatto sul divano.")
    QTest.mouseClick(retry, Qt.MouseButton.LeftButton)
    wait_for(lambda: window.documents[0].status == "indexed" and not window._busy)
    if window.reader and window.reader.isVisible():
        window.reader.close()
    window.search_input.setText("gatto")
    window.run_search()
    wait_for(lambda: bool(window.hits) and not window._searching)
    assert window.hits[0].matches[0].source == "caption"
    assert any("Descrizione generata" in label.text() for label in window.findChildren(QLabel))
    window.open_document(doc_id)
    wait_for(lambda: window.reader is not None and window.reader.isVisible())
    passages = window.reader.findChild(QPlainTextEdit, "passages")
    assert "Descrizione generata · Passaggio 1" in passages.toPlainText()


def test_reader_tags_filters_and_confirmed_delete(window, make_file, monkeypatch):
    source = import_note(window, make_file)
    document_id = window.documents[0].id
    window.open_document(document_id)
    wait_for(lambda: window.reader is not None and window.reader.isVisible())
    assert "Caldaia" in window.reader.detail.preview
    window.reader.tags_input.setText("Casa, Spese casa")
    QTest.mouseClick(button(window.reader, "Salva etichette"), Qt.MouseButton.LeftButton)
    wait_for(lambda: window.documents[0].tags == ("casa", "spese-casa"))
    wait_for(lambda: not window._busy)
    window.reader.close()
    window.toggle_tag("casa")
    assert window.active_tags == ["casa"]
    window.open_document(document_id)
    wait_for(lambda: window.reader.isVisible())
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    window.reader._confirm_delete()
    assert len(window.archive.list_documents()) == 1
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.reader._confirm_delete()
    wait_for(lambda: not window.documents)
    assert source.exists()


def test_theme_motion_and_view_are_saved(window):
    window.toggle_theme()
    window.toggle_motion()
    window.toggle_view()
    window.sort.setCurrentIndex(1)
    assert window.settings.value("theme") == "light"
    assert window.settings.value("motion", type=bool) is False
    assert window.settings.value("view") == "list"
    assert window.settings.value("sort") == "name"


def test_long_names_and_tags_fit_small_window_and_remain_actionable(window, make_file):
    from esper.desktop.widgets import ElidedButton, ElidedLabel

    name = "contratto_" * 15 + ".txt"
    tag = "manutenzione-riscaldamento-" * 5
    source = make_file(name, "Spese della casa e del riscaldamento.")
    window.import_files([source])
    wait_for(lambda: window.documents and window.documents[0].status == "indexed")
    document_id = window.documents[0].id
    window.archive.update_tags(document_id, [tag, "casa", "spese", "contratti"])
    window.resize(1040, 650)
    window.navigate("archive")
    wait_for(lambda: all(scroll.widget().width() <= scroll.viewport().width()
                         for scroll in window.findChildren(QScrollArea)))
    for scroll in window.findChildren(QScrollArea):
        assert scroll.widget().width() <= scroll.viewport().width()
    name_button = window.findChild(ElidedButton, "documentName")
    assert "…" in name_button.text()
    assert name_button.toolTip() == name
    tag_button = next(b for b in window.findChildren(ElidedButton) if b.toolTip() == tag)
    QTest.mouseClick(tag_button, Qt.MouseButton.LeftButton)
    assert window.active_tags == [tag]
    window.open_document(document_id)
    wait_for(lambda: window.reader is not None and window.reader.isVisible())
    title = window.reader.findChild(ElidedLabel)
    assert title.toolTip() == name
    assert "…" in title.text()


def test_empty_filter_does_not_describe_existing_archive_as_empty(window, make_file):
    import_note(window, make_file)
    window.set_kind("pdf")
    text = " ".join(label.text() for label in window.cards_widget.findChildren(QLabel))
    assert "filtri selezionati" in text
    assert "archivio inizia qui" not in text
    window.clear_filter()
    assert window.cards.count() == 1


def test_tag_save_failure_is_visible_inside_reader_and_preserves_input(window, make_file, monkeypatch):
    import_note(window, make_file)
    window.open_document(window.documents[0].id)
    wait_for(lambda: window.reader is not None and window.reader.isVisible())

    def fail_update(*args):
        raise OSError("Impossibile salvare le etichette")

    monkeypatch.setattr(window.archive, "update_tags", fail_update)
    window.reader.tags_input.setText("casa, spese")
    QTest.mouseClick(button(window.reader, "Salva etichette"), Qt.MouseButton.LeftButton)
    wait_for(lambda: window.reader.error_label.isVisible())
    assert window.reader.error_label.text() == "Impossibile salvare le etichette"
    assert window.reader.tags_input.text() == "casa, spese"
    assert window.archive.list_documents()[0].tags == ()


def test_pdf_search_opens_matching_page_and_navigates_without_stale_preview(window, tmp_path):
    import pymupdf
    from esper.desktop.service import PDFPage

    path = tmp_path / "heating.pdf"
    with pymupdf.open() as pdf:
        for text in ("Condizioni generali.", "", "Ricevuta caldaia 2400 euro."):
            page = pdf.new_page()
            if text:
                page.insert_text((70, 110), text)
        pdf.save(path)
    window.import_files([path])
    wait_for(lambda: window.documents and window.documents[0].status == "indexed")
    assert window.documents[0].page_count == 3
    assert "2" in window.documents[0].extraction_warning
    QTest.mouseClick(window.mode_buttons["keyword"], Qt.MouseButton.LeftButton)
    window.search_input.setText("caldaia")
    window.run_search()
    wait_for(lambda: window.hits and not window._searching)
    assert window.hits[0].matches[0].page == 3
    window.open_document(window.documents[0].id)
    wait_for(lambda: window.reader is not None and hasattr(window.reader, "pdf_image") and not window.reader.pdf_image.pixmap().isNull())
    assert window.reader.page_selector.value() == 3
    assert window.reader.page_total.text() == "/ 3"
    assert window.reader.pdf_image.pixmap().width() <= window.reader.pdf_preview.viewport().width()
    assert "Pagina 3" in window.reader.tabs.widget(1).toPlainText()
    old_token = window._pdf_seq
    window.reader.request_page(1)
    window._result("pdf_page", old_token, PDFPage(window.selected_id, 3, 3, b"invalid old image"))
    wait_for(lambda: window.reader.page_selector.value() == 1 and not window.reader.pdf_image.pixmap().isNull())
    window.reader.close()
    window._result("pdf_page", window._pdf_seq - 1, PDFPage(1, 1, 3, b"old"))
    assert not window.reader.isVisible()


def test_encrypted_pdf_reports_error_in_reader(window, tmp_path):
    import pymupdf

    path = tmp_path / "locked.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((70, 110), "Locked document")
        pdf.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    window.import_files([path])
    wait_for(lambda: window.documents and window.documents[0].status == "error")
    window.open_document(window.documents[0].id)
    wait_for(lambda: window.reader is not None and window.reader.error_label.isVisible())
    assert "password" in window.reader.error_label.text()


def test_clearing_query_invalidates_a_late_result(window, make_file):
    import_note(window, make_file)
    window.search_input.setText("caldaia")
    token = window._search_seq
    window.search_input.clear()
    window._result("search", token, [object()])
    assert window.hits == []
    assert not window._searching


def test_stale_queued_query_is_skipped_without_model_loading(window):
    window.worker.latest_search(2)
    window.request.emit("search", 1, ("old", (), "hybrid"))
    QTest.qWait(50)
    assert window.archive._embedder is None


def test_unknown_index_metadata_shows_rebuild_guidance(window, make_file, monkeypatch):
    import_note(window, make_file)
    with window.archive.connection() as conn, conn:
        conn.execute("DELETE FROM index_settings")
    window.search_input.setText("caldaia")
    window.run_search()
    wait_for(lambda: window.notice.isVisible())
    assert "Ricostruisci indice" in window.notice_text.text()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.confirm_rebuild()
    wait_for(lambda: window.hits and not window._searching)
    assert window.hits[0].name == "heating.md"


def test_archive_navigation_and_memory_selection(window, make_file):
    import_note(window, make_file)
    window.import_files([make_file("other.txt", "gatto sul divano")])
    wait_for(lambda: len(window.documents) == 2 and all(doc.status == "indexed" for doc in window.documents))
    first = window.memory.selected.id
    QTest.mouseClick(button(window, "›"), Qt.MouseButton.LeftButton)
    assert window.memory.selected.id != first
    window.navigate("archive")
    assert window.workspace == "archive" and window.search_input.text() == ""
    assert window.section_title.text() == "Tutti i documenti · 2"
    assert not window.visual.isVisible()


def test_close_stops_worker_without_terminating_it(window):
    window.close()
    wait_for(lambda: not window.thread.isRunning())
    assert window.worker.stop.is_set()


def test_close_during_inference_finishes_current_document_and_preserves_queue(window, make_file):
    started, release = Event(), Event()

    class SlowEmbedder(FakeEmbedder):
        def embed(self, texts):
            started.set()
            assert release.wait(5)
            return super().embed(texts)

    window.archive._embedder = SlowEmbedder()
    window.import_files([make_file("one.txt", "first"), make_file("two.txt", "second")])
    try:
        wait_for(started.is_set)
        responsive = []
        QTimer.singleShot(0, lambda: responsive.append(True))
        wait_for(lambda: bool(responsive))
        assert window.archive.list_documents()[0].status == "processing"
        window.close()
        assert window.thread.isRunning()
    finally:
        release.set()
    wait_for(lambda: not window.thread.isRunning())
    assert [doc.status for doc in window.archive.list_documents()] == ["indexed", "queued"]


def test_native_image_preview_and_original_opening(window, tmp_path, monkeypatch):
    monkeypatch.setattr("esper.image_text.transcribe_image", lambda _: "Foto campione")
    monkeypatch.setattr("esper.image_text.describe_image", lambda _: "Una foto campione.")
    path = tmp_path / "picture.png"
    image = QImage(100, 80, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.gray)
    assert image.save(str(path))
    window.import_files([path])
    wait_for(lambda: bool(window.documents) and window.documents[0].status == "indexed")
    wait_for(lambda: not window._busy)
    doc = window.documents[0]
    assert doc.kind == "image"
    assert window.memory.selected.id == doc.id
    window.open_document(doc.id)
    wait_for(lambda: window.reader is not None and window.reader.isVisible())
    assert window.reader.tabs.tabText(0) == "Anteprima"
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    QTest.mouseClick(button(window.reader, "Apri originale ↗"), Qt.MouseButton.LeftButton)
    assert opened == [str(doc.path)]


def test_an_active_query_updates_when_imported_documents_finish_indexing(window, make_file):
    window.search_input.setText("caldaia")
    window.run_search()
    wait_for(lambda: not window._searching)
    assert not window.hits
    window.import_files([make_file("new.txt", "caldaia nuova")])
    wait_for(lambda: bool(window.hits) and not window._searching)
    assert window.hits[0].name == "new.txt"


def test_import_shows_activity_and_queued_document_while_model_loads(window, make_file):
    started, release = Event(), Event()

    def slow_model():
        started.set()
        assert release.wait(5)
        return FakeEmbedder()

    window.archive._embedder_factory = slow_model
    window.import_files([make_file("pending.txt", "documento in attesa")])
    assert window.activity.isVisible()
    try:
        wait_for(started.is_set)
        wait_for(lambda: bool(window.documents))
        assert window.documents[0].status == "queued"
        assert window.progress.isVisible()
        assert window.memory.empty_text == "Anteprima in preparazione…"
        assert not window.next_frame.isEnabled()
        assert window.activity_text.text() == "Caricamento del modello di ricerca…"
    finally:
        release.set()
    wait_for(lambda: window.documents[0].status == "indexed" and not window._busy)
    assert not window.activity.isVisible()


def test_partial_image_reader_offers_retry_and_shows_actual_warning(qapp, tmp_path):
    from esper.desktop.reader import DocumentDialog
    from esper.desktop.service import Document, DocumentDetail
    from esper.desktop.widgets import DocumentCard

    doc = Document(7, "photo.jpg", "image/jpeg", 100, "indexed", None,
                   "2026-11-19", (), 1, "testo", tmp_path / "photo.jpg",
                   extraction_warning="Descrizione dell’immagine non disponibile.")
    dialog = DocumentDialog(DocumentDetail(doc, (), "", False))
    card = DocumentCard(doc)
    try:
        assert any("Descrizione dell’immagine non disponibile" in item.text()
                   for item in card.findChildren(QLabel))
        retried = []
        dialog.retry_requested.connect(retried.append)
        button(dialog, "Riprova indicizzazione").click()
        assert retried == [7]
    finally:
        dialog.close()
        card.deleteLater()
        dialog.deleteLater()


def test_activity_tracks_processing_filename_and_queue_with_filters(window, make_file):
    started, release = Event(), Event()

    class SlowEmbedder(FakeEmbedder):
        def embed(self, texts):
            started.set()
            assert release.wait(8)
            return super().embed(texts)

    window.resize(1040, 650)
    window.archive._embedder = SlowEmbedder()
    window.set_kind("pdf")
    window.search_input.setText("non corrisponde")
    name = "documento-" + "molto-lungo-" * 12 + ".txt"
    window.import_files([make_file(name, "first"), make_file("second.txt", "second")])
    try:
        wait_for(started.is_set)
        wait_for(lambda: name in window.activity_text.full_text, timeout=5000)
        assert window.activity_text.full_text == f"Indicizzazione: {name}"
        assert window.activity_text.toolTip() == window.activity_text.full_text
        assert "…" in window.activity_text.text()
        assert window.activity_queue.text() == "1 in coda"
        assert window.activity_queue.geometry().right() < window.activity.width()
    finally:
        release.set()
    wait_for(lambda: all(doc.status == "indexed" for doc in window.documents) and not window._busy)


def test_quick_worker_operation_does_not_show_stale_activity(window):
    window._operation_started("detail")
    window._set_busy(True)
    assert not window.activity.isVisible()
    assert window.activity_text.full_text == ""
    window._set_busy(False)


def test_search_modes_are_visible_and_keyboard_selectable(window, make_file):
    import_note(window, make_file)
    window.search_input.setText("caldaia")
    for mode in ("semantic", "keyword", "hybrid"):
        control = window.mode_buttons[mode]
        assert control.isVisible()
        control.setFocus()
        QTest.keyClick(control, Qt.Key.Key_Space)
        wait_for(lambda: window.hits and not window._searching)
        assert window.mode_group.checkedButton() is control
        assert window.settings.value("mode") == mode
        assert window.hits[0].matches[0].via == ("both" if mode == "hybrid" else mode)


def test_map_from_sidebar_selection_rotation_and_reader(window, make_file):
    import_note(window, make_file)
    window.import_files([make_file("pet.txt", "Il gatto dorme qui.")])
    wait_for(lambda: len(window.documents) == 2 and not window._busy)
    window.resize(1040, 650)
    QTest.mouseClick(window.map_nav, Qt.MouseButton.LeftButton)
    page = window.map_page
    canvas = page.canvas
    wait_for(lambda: len(canvas.screen_points) == 2)
    assert page.isVisible() and window.map_nav.isChecked()
    assert page.geometry().right() < window.width()
    target = window.documents[-1].id
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=canvas.screen_points[target].toPoint())
    assert page.files.currentData() == target
    before = canvas.yaw
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    assert canvas.yaw != before
    QTest.keyClick(canvas, Qt.Key.Key_Plus)
    assert canvas.zoom > 1
    QTest.keyClick(canvas, Qt.Key.Key_Home)
    assert canvas.zoom == 1
    QTest.mouseClick(page.open, Qt.MouseButton.LeftButton)
    wait_for(lambda: window.reader and window.reader.isVisible())
    assert window.reader.detail.document.id == target
    window.reader.close()
    window.focus_search()
    assert window.search_input.isVisible() and window.workspace == "search"


def test_map_updates_after_import_delete_and_lists_unplaced_files(window, make_file):
    window.navigate("map")
    page = window.map_page
    wait_for(lambda: page.canvas.layout_data.revision >= 0)
    window.import_files([make_file("note.txt", "Una nota"), make_file("other.bin", "Unknown format")])
    wait_for(lambda: len(page.canvas.layout_data.positions) == 1 and page.files.count() == 2)
    assert "1 senza posizione" in page.count.text()
    error = next(doc for doc in window.documents if doc.status == "error")
    page.select(error.id)
    assert "Errore" in page.detail.text() and page.open.isEnabled()
    window.submit("delete", next(iter(page.canvas.layout_data.positions)))
    wait_for(lambda: not page.canvas.layout_data.positions and page.files.count() == 1)
    assert page.files.currentData() == error.id
