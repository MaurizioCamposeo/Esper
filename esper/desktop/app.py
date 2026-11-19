"""Esper's native Qt application: local widgets calling the Python archive directly."""

from pathlib import Path
import argparse
import sys

from PySide6.QtCore import QSettings, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLayout, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from esper.config import DATA_DIR
from esper.desktop.map_view import MapPage
from esper.desktop.reader import DocumentDialog
from esper.desktop.service import Archive, Document, ImportReport
from esper.desktop.theme import stylesheet
from esper.desktop.widgets import DocumentCard, ElidedButton, ElidedLabel, MemoryField, label, passage_prefix
from esper.desktop.worker import Worker


def clear_layout(layout):
    """Remove widgets without leaving stale signal-connected cards behind."""
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


class MainWindow(QMainWindow):
    request = Signal(str, int, object)

    def __init__(self, archive: Archive, settings: QSettings | None = None, *, auto_index: bool = True):
        super().__init__()
        self.archive = archive
        self.settings = settings or QSettings(str(archive.data_dir / "desktop.ini"), QSettings.Format.IniFormat)
        self.light = self.settings.value("theme", "dark") == "light"
        self.motion = self.settings.value("motion", True, type=bool)
        self.view = self.settings.value("view", "grid")
        self.workspace = "search"
        self.kind = "all"
        self.active_tags: list[str] = []
        self.documents: list[Document] = []
        self.hits = []
        self._search_seq = 0
        self._map_pending = False
        self._map_revision = None
        self._detail_seq = 0
        self._pdf_seq = 0
        self.selected_page = 1
        self._busy = False
        self._operation = ""
        self._activity_message = ""
        self._closing = False
        self._searching = False
        self.selected_id = None
        self.reader = None
        self.setWindowTitle("Esper — Archivio personale")
        self.setMinimumSize(1040, 650)
        self.resize(1400, 920)
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.setAcceptDrops(True)
        self._build_ui()
        self.worker = Worker(archive)
        self.thread = QThread(self)
        self.thread.setObjectName("esper-archive-worker")
        self.worker.moveToThread(self.thread)
        self.request.connect(self.worker.execute)
        self.worker.result.connect(self._result)
        self.worker.failed.connect(self._failed)
        self.worker.changed.connect(self.refresh)
        self.worker.status.connect(self._status)
        self.worker.started.connect(self._operation_started)
        self.worker.busy.connect(self._set_busy)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(450)
        self.search_timer.timeout.connect(self.run_search)
        self.poll = QTimer(self)
        self.poll.setInterval(500)
        self.poll.timeout.connect(lambda: self.refresh(only_if_changed=True) if self._busy else None)
        self.poll.start()
        self.search_input.textChanged.connect(self._query_changed)
        self._shortcuts()
        self._apply_theme()
        self._apply_motion()
        hints = QApplication.styleHints()
        accessibility = hints.accessibility() if hasattr(hints, "accessibility") else None
        if accessibility and hasattr(accessibility, "motionPreferenceChanged"):
            accessibility.motionPreferenceChanged.connect(self._apply_motion)
        self.refresh()
        if auto_index:
            QTimer.singleShot(0, lambda: self.request.emit("index", 0, None))

    def _button(self, text, callback, name="", checkable=False):
        button = QPushButton(text)
        button.setObjectName(name)
        button.setCheckable(checkable)
        button.clicked.connect(callback)
        return button

    def _build_ui(self):
        root = QWidget()
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(18, 20, 18, 18)
        nav.setSpacing(4)
        nav.addWidget(label("⊕ ESPER", "brand"))
        nav.addSpacing(12)
        self.search_nav = self._button("⌕  Ricerca", lambda: self.navigate("search"), "nav", True)
        self.archive_nav = self._button("▤  Tutti i documenti", lambda: self.navigate("archive"), "nav", True)
        nav.addWidget(self.search_nav)
        nav.addWidget(self.archive_nav)
        self.map_nav = self._button("◇  Mappa 3D", lambda: self.navigate("map"), "nav", True)
        nav.addWidget(self.map_nav)
        nav.addSpacing(12)
        nav.addWidget(label("ESPLORA", "muted"))
        self.kind_buttons = {}
        for key, text in (("pdf", "PDF"), ("image", "Immagini"), ("notes", "Note e testi")):
            button = self._button(text, lambda checked=False, value=key: self.set_kind(value), "nav", True)
            nav.addWidget(button)
            self.kind_buttons[key] = button
        nav.addSpacing(12)
        nav.addWidget(label("ETICHETTE", "muted"))
        tag_scroll = QScrollArea()
        tag_scroll.setWidgetResizable(True)
        tag_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tag_widget = QWidget()
        tag_widget.setObjectName("tagRail")
        self.tag_layout = QVBoxLayout(tag_widget)
        self.tag_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_layout.setSpacing(3)
        self.tag_layout.addStretch()
        tag_scroll.setWidget(tag_widget)
        nav.addWidget(tag_scroll, 1)
        nav.addWidget(self._button("Indicizza in attesa", lambda: self.submit("index")))
        self.rebuild_button = self._button("Ricostruisci indice", self.confirm_rebuild)
        nav.addWidget(self.rebuild_button)
        nav.addSpacing(12)
        nav.addWidget(label("Archivio locale · Privato", "muted"))
        shell.addWidget(sidebar)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(28, 10, 28, 10)
        self.breadcrumb = label("＋   RICERCA", "muted")
        toolbar.addWidget(self.breadcrumb)
        toolbar.addStretch()
        self.motion_button = self._button("Ⅱ", self.toggle_motion)
        self.motion_button.setAccessibleName("Attiva o disattiva le animazioni")
        self.theme_button = self._button("◐", self.toggle_theme)
        self.theme_button.setAccessibleName("Cambia tema")
        toolbar.addWidget(self.motion_button)
        toolbar.addWidget(self.theme_button)
        toolbar.addWidget(self._button("＋  Aggiungi documenti", self.choose_files))
        main_layout.addLayout(toolbar)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        main_layout.addWidget(self.progress)
        self.activity = QFrame()
        self.activity.setObjectName("activity")
        activity_layout = QHBoxLayout(self.activity)
        activity_layout.setContentsMargins(30, 9, 30, 9)
        self.activity_text = ElidedLabel("", "description")
        activity_layout.addWidget(self.activity_text, 1)
        self.activity_queue = label("", "muted")
        activity_layout.addWidget(self.activity_queue)
        self.activity.hide()
        main_layout.addWidget(self.activity)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        page_layout.setContentsMargins(28, 14, 28, 24)
        page_layout.setSpacing(18)
        self.notice = QFrame()
        self.notice.setObjectName("notice")
        notice_layout = QHBoxLayout(self.notice)
        self.notice_text = label("", "description", True)
        notice_layout.addWidget(self.notice_text, 1)
        notice_layout.addWidget(self._button("Chiudi", self.notice.hide))
        self.notice.hide()
        main_layout.addWidget(self.notice)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 16, 22, 16)
        hero_layout.setSpacing(12)
        self.recall = QWidget()
        self.recall.setObjectName("heroContent")
        recall_layout = QHBoxLayout(self.recall)
        recall_layout.setContentsMargins(0, 0, 0, 0)
        recall_layout.setSpacing(28)
        copy = QVBoxLayout()
        self.title = label("Cosa vuoi\nritrovare?", "title")
        copy.addStretch()
        copy.addWidget(self.title)
        self.description = label("Ritrova i tuoi documenti con parole tue.", "description", True)
        copy.addWidget(self.description)
        copy.addStretch()
        recall_layout.addLayout(copy, 1)
        self.visual = QWidget()
        self.visual.setObjectName("heroContent")
        visual = QVBoxLayout(self.visual)
        visual.setContentsMargins(0, 0, 0, 0)
        self.memory = MemoryField()
        self.memory.activated.connect(self.open_document)
        visual.addWidget(self.memory)
        track = QHBoxLayout()
        track.addStretch()
        self.previous_frame = self._button("‹", lambda: self.memory.next_document(-1))
        self.next_frame = self._button("›", lambda: self.memory.next_document(1))
        for button, name in ((self.previous_frame, "Documento precedente"), (self.next_frame, "Documento successivo")):
            button.setAccessibleName(name)
            track.addWidget(button)
        visual.addLayout(track)
        recall_layout.addWidget(self.visual, 1)
        hero_layout.addWidget(self.recall)
        search_row = QHBoxLayout()
        search_row.setSpacing(0)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("search")
        self.search_input.setAccessibleName("Cerca nei documenti con parole tue")
        self.search_input.setPlaceholderText("Descrivi ciò che cerchi…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self.run_search)
        search_row.addWidget(self.search_input, 1)
        self.search_button = self._button("Ricerca →", self.run_search, "searchSubmit")
        search_row.addWidget(self.search_button)
        hero_layout.addLayout(search_row)
        search_options = QHBoxLayout()
        search_options.setSpacing(10)
        search_options.addWidget(label("Cerca per", "description"))
        self.mode_group = QButtonGroup(self)
        self.mode_buttons = {}
        modes = (("Entrambi", "hybrid", "Combina significato e parole chiave"),
                 ("Significato", "semantic", "Trova passaggi che esprimono la stessa idea"),
                 ("Parole chiave", "keyword", "Trova le parole presenti nei passaggi"))
        self.search_mode = self.settings.value("mode", "hybrid")
        if self.search_mode not in {key for _, key, _ in modes}:
            self.search_mode = "hybrid"
        segments = QHBoxLayout()
        segments.setSpacing(0)
        for title, key, hint in modes:
            segment = self._button(title, lambda checked=False, key=key: self._mode_changed(key), "segment", True)
            segment.setAccessibleName(f"Modalità di ricerca · {title}")
            segment.setToolTip(hint)
            self.mode_group.addButton(segment)
            segment.setChecked(key == self.search_mode)
            self.mode_buttons[key] = segment
            segments.addWidget(segment)
        search_options.addLayout(segments)
        search_options.addStretch()
        hero_layout.addLayout(search_options)
        self.examples_widget = QWidget()
        self.examples_widget.setObjectName("heroContent")
        examples = QHBoxLayout(self.examples_widget)
        examples.setContentsMargins(0, 0, 0, 0)
        for text in ("Il contratto della casa", "Le spese per il riscaldamento", "Come funziona una rete neurale"):
            examples.addWidget(self._button(text, lambda checked=False, value=text: self.search_input.setText(value), "chip"))
        examples.addStretch()
        hero_layout.addWidget(self.examples_widget)
        page_layout.addWidget(hero)

        controls = QHBoxLayout()
        self.section_title = label("Documenti recenti", "sectionTitle")
        controls.addWidget(self.section_title, 1)
        self.clear_filters = self._button("Rimuovi filtri", self.clear_filter)
        controls.addWidget(self.clear_filters)
        self.sort = QComboBox()
        self.sort.setAccessibleName("Ordina documenti")
        for text, key in (("Più recenti", "recent"), ("Nome", "name"), ("Dimensione", "size")):
            self.sort.addItem(text, key)
        self.sort.setCurrentIndex(max(0, self.sort.findData(self.settings.value("sort", "recent"))))
        self.sort.currentIndexChanged.connect(self._sort_changed)
        controls.addWidget(self.sort)
        self.view_button = self._button("Elenco" if self.view == "grid" else "Griglia", self.toggle_view)
        controls.addWidget(self.view_button)
        page_layout.addLayout(controls)
        self.cards_widget = QWidget()
        self.cards = QGridLayout(self.cards_widget)
        self.cards.setContentsMargins(0, 0, 0, 0)
        self.cards.setSpacing(16)
        self.cards.setColumnStretch(0, 1)
        self.cards.setColumnStretch(1, 1)
        page_layout.addWidget(self.cards_widget)
        page_layout.addStretch()
        scroll.setWidget(page)
        self.pages = QStackedWidget()
        self.pages.addWidget(scroll)
        self.map_page = MapPage()
        self.map_page.activated.connect(self.open_document)
        self.pages.addWidget(self.map_page)
        main_layout.addWidget(self.pages, 1)
        shell.addWidget(main, 1)
        self.setCentralWidget(root)

    def _shortcuts(self):
        for key in ("Ctrl+K", "Meta+K"):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(self.focus_search)
        slash = QAction(self)
        slash.setShortcut(QKeySequence("/"))
        slash.triggered.connect(self.focus_search)
        self.addAction(slash)
        refresh = QShortcut(QKeySequence("F5"), self)
        refresh.activated.connect(self.refresh)
        escape = QShortcut(QKeySequence("Escape"), self)
        escape.activated.connect(self.search_input.clear)

    def focus_search(self):
        if self.workspace == "map":
            self.navigate("search")
        self.search_input.setFocus()

    def _apply_theme(self):
        self.setStyleSheet(stylesheet(self.light))
        self.map_page.canvas.light = self.light
        self.map_page.canvas.update()
        self.memory.light = self.light
        self.memory.update()
        self.theme_button.setToolTip("Tema scuro" if self.light else "Tema chiaro")

    def toggle_theme(self):
        self.light = not self.light
        self.settings.setValue("theme", "light" if self.light else "dark")
        self._apply_theme()

    def _apply_motion(self):
        hints = QApplication.styleHints()
        accessibility = hints.accessibility() if hasattr(hints, "accessibility") else None
        preference = accessibility.motionPreference() if accessibility and hasattr(accessibility, "motionPreference") else None
        reduced = preference is not None and "reduc" in preference.name.lower()
        self.memory.set_motion(self.motion and not reduced)
        self.motion_button.setText("Ⅱ" if self.motion and not reduced else "▶")
        self.motion_button.setToolTip("Movimento ridotto dal sistema" if reduced else "Pausa animazioni" if self.motion else "Attiva animazioni")

    def toggle_motion(self):
        self.motion = not self.motion
        self.settings.setValue("motion", self.motion)
        self._apply_motion()

    @Slot()
    def refresh(self, *, only_if_changed=False):
        if self._closing:
            return
        try:
            documents = self.archive.list_documents()
            if self.workspace == "map":
                if documents != self.documents or not only_if_changed:
                    self.map_page.set_documents(documents)
                revision = self.archive.map_revision()
                if revision != self._map_revision and not self._map_pending:
                    self._map_pending = True
                    self._map_revision = revision
                    self.submit("map")
            if only_if_changed and documents == self.documents:
                return
            previous = {doc.id: doc.status for doc in self.documents}
            self.documents = documents
            finished = any(doc.status == "indexed" and previous.get(doc.id) != "indexed" for doc in self.documents)
            self.memory.set_documents(self.documents)
            multiple_frames = len(self.memory.documents) > 1
            for button in (self.previous_frame, self.next_frame):
                button.setEnabled(multiple_frames)
                button.setVisible(multiple_frames)
            clear_layout(self.tag_layout)
            for name, count in self.archive.list_tags():
                button = ElidedButton(f"#  {name}   {count}")
                button.setObjectName("nav")
                button.setCheckable(True)
                button.clicked.connect(lambda checked=False, value=name: self.toggle_tag(value))
                button.setChecked(name in self.active_tags)
                self.tag_layout.addWidget(button)
            self.tag_layout.addStretch()
            self._render_cards()
            self._update_activity()
            if finished and self.search_input.text().strip():
                self._query_changed()
            if not self._busy:
                self._status(f"{len(self.documents)} documenti · {sum(doc.chunk_count for doc in self.documents)} passaggi")
        except Exception as exc:
            self.show_error(str(exc))

    def _matches(self, doc: Document) -> bool:
        return set(self.active_tags).issubset(doc.tags) and (
            self.kind == "all" or doc.kind == self.kind or (self.kind == "notes" and doc.kind in ("text", "markdown"))
        )

    def _render_cards(self):
        self.map_nav.setChecked(self.workspace == "map")
        self.pages.setCurrentIndex(int(self.workspace == "map"))
        if self.workspace == "map":
            self.breadcrumb.setText("ARCHIVIO   /   MAPPA 3D")
            self.search_nav.setChecked(False)
            self.archive_nav.setChecked(False)
            for button in self.kind_buttons.values():
                button.setChecked(False)
            return
        clear_layout(self.cards)
        query = self.search_input.text().strip()
        self.recall.setVisible(not query)
        self.title.setText("Cosa vuoi\nritrovare?" if self.workspace == "search" else "Il tuo archivio.")
        self.description.setVisible(self.workspace == "search")
        self.visual.setVisible(self.workspace == "search")
        self.title.setStyleSheet("font-size: 43px;" if self.workspace == "search" else "font-size: 38px;")
        self.examples_widget.setVisible(not query and self.workspace == "search")
        self.sort.setVisible(not query)
        self.view_button.setVisible(not query)
        self.clear_filters.setVisible(bool(self.active_tags) or self.kind != "all")
        self.search_nav.setChecked(self.workspace == "search")
        self.archive_nav.setChecked(self.workspace == "archive" and self.kind == "all")
        self.breadcrumb.setText("ARCHIVIO   /   RICERCA" if self.workspace == "search" else "ARCHIVIO   /   DOCUMENTI")
        for kind, button in self.kind_buttons.items():
            button.setChecked(self.kind == kind)
        by_id = {doc.id: doc for doc in self.documents}
        if query:
            items = [(by_id[hit.document_id], [passage_prefix(match.page, match.source) + match.text for match in hit.matches]) for hit in self.hits
                     if hit.document_id in by_id and self._matches(by_id[hit.document_id])]
            result_label = "risultato" if len(items) == 1 else "risultati"
            self.section_title.setText("Ricerca in corso…" if self._searching else f"{len(items)} {result_label}")
        else:
            docs = [doc for doc in self.documents if self._matches(doc)]
            key = self.sort.currentData()
            docs.sort(key=lambda doc: doc.name.casefold() if key == "name" else doc.size if key == "size" else (doc.created_at, doc.id), reverse=key != "name")
            if self.workspace == "search" and not self.active_tags:
                docs = docs[:6]
            items = [(doc, None) for doc in docs]
            self.section_title.setText("Documenti recenti" if self.workspace == "search" else f"Tutti i documenti · {len(docs)}")
        columns = 2 if self.view == "grid" and not query else 1
        self.cards.setColumnStretch(1, 1 if columns == 2 else 0)
        for i, (doc, passages) in enumerate(items):
            card = DocumentCard(doc, passages)
            card.activated.connect(self.open_document)
            card.tag_clicked.connect(self.toggle_tag)
            self.cards.addWidget(card, i // columns, i % columns)
        if not items and not self._searching:
            text = ("Nessun risultato. Prova un’altra descrizione o rimuovi i filtri." if query else
                    "Nessun documento corrisponde ai filtri selezionati." if self.documents else
                    "Il tuo archivio inizia qui.\nAggiungi o trascina file TXT, Markdown, PDF, JPEG o PNG.")
            empty = label(text, "description", True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(180)
            self.cards.addWidget(empty, 0, 0, 1, columns)

    def navigate(self, workspace: str):
        self.workspace, self.kind, self.active_tags = workspace, "all", []
        self.search_input.clear()
        if workspace == "map":
            self._map_revision = None
        self.refresh()
        if workspace == "search":
            self.search_input.setFocus()

    def set_kind(self, kind: str):
        self.workspace = "archive"
        self.kind = kind
        self._render_cards()

    def toggle_tag(self, name: str):
        if self.workspace == "map":
            self.workspace = "archive"
        if name in self.active_tags:
            self.active_tags.remove(name)
        else:
            self.active_tags.append(name)
        self.refresh()
        if self.search_input.text().strip():
            self._query_changed()

    def clear_filter(self):
        self.active_tags = []
        self.kind = "all"
        self.refresh()
        if self.search_input.text().strip():
            self._query_changed()

    def _mode_changed(self, key):
        if self.search_mode == key:
            return
        self.search_mode = key
        self.settings.setValue("mode", key)
        if self.search_input.text().strip():
            self._query_changed()

    def _sort_changed(self):
        self.settings.setValue("sort", self.sort.currentData())
        self._render_cards()

    def toggle_view(self):
        self.view = "list" if self.view == "grid" else "grid"
        self.settings.setValue("view", self.view)
        self.view_button.setText("Elenco" if self.view == "grid" else "Griglia")
        self._render_cards()

    def _query_changed(self):
        self.search_timer.stop()
        self._search_seq += 1
        self.worker.latest_search(self._search_seq)
        self.hits = []
        self._searching = bool(self.search_input.text().strip())
        self._render_cards()
        if self._searching:
            self.search_timer.start()

    def run_search(self):
        self.search_timer.stop()
        query = self.search_input.text().strip()
        if query and not self._closing:
            self._searching = True
            self._render_cards()
            self.request.emit("search", self._search_seq, (query, tuple(self.active_tags), self.search_mode))

    def submit(self, operation: str, payload=None):
        if not self._closing:
            self.request.emit(operation, 0, payload)

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Aggiungi documenti", "",
            "Documenti (*.txt *.md *.markdown *.pdf *.png *.jpg *.jpeg);;Tutti i file (*)",
        )
        if paths:
            self.import_files([Path(path) for path in paths])

    def import_files(self, paths: list[Path]):
        if paths and not self._closing:
            self.activity_text.set_full_text("Importazione in attesa…" if self._busy else "Importazione dei documenti…")
            self.activity_queue.clear()
            self.activity.show()
            self.submit("import", paths)

    def confirm_rebuild(self):
        if QMessageBox.question(
            self, "Ricostruisci indice",
            "Ricalcolare tutti i dati di ricerca?\nOriginali ed etichette vengono conservati.\nL’indice precedente viene sostituito.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.submit("reindex")

    def open_document(self, document_id: int):
        self.selected_id = document_id
        self.selected_page = next((hit.matches[0].page or 1 for hit in self.hits
                                   if hit.document_id == document_id and hit.matches), 1)
        self._detail_seq += 1
        self.request.emit("detail", self._detail_seq, document_id)

    def _show_reader(self, detail):
        if self.reader:
            self.reader.blockSignals(True)
            self.reader.close()
            self.reader.deleteLater()
        self.reader = DocumentDialog(detail, self, initial_page=self.selected_page)
        self.reader.setWindowModality(Qt.WindowModality.WindowModal)
        self.reader.tags_requested.connect(lambda document_id, tags: self.submit("tags", (document_id, tags)))
        self.reader.delete_requested.connect(lambda document_id: self.submit("delete", document_id))
        self.reader.retry_requested.connect(lambda document_id: self.submit("retry", document_id))
        self.reader.page_requested.connect(self._request_pdf_page)
        self.reader.finished.connect(self._reader_closed)
        self.reader.show()

    def _reader_closed(self):
        self.selected_id = None
        self._detail_seq += 1
        self._pdf_seq += 1

    def _request_pdf_page(self, document_id, page):
        self._pdf_seq += 1
        self.request.emit("pdf_page", self._pdf_seq, (document_id, page))

    @Slot(str, int, object)
    def _result(self, operation, token, value):
        if self._closing:
            return
        if operation == "search":
            if token != self._search_seq:
                return
            self.hits = value
            self._searching = False
            self._render_cards()
        elif operation == "map":
            self._map_pending = False
            self._map_revision = value.revision
            self.map_page.set_data(value)
        elif operation == "detail":
            if token == self._detail_seq and self.selected_id == value.document.id:
                self._show_reader(value)
        elif operation == "pdf_page":
            if token == self._pdf_seq and self.reader and self.reader.isVisible() and self.selected_id == value.document_id:
                self.reader.show_pdf_page(value)
        elif operation == "import":
            report: ImportReport = value
            self._status(f"{report.imported} aggiunti · {report.duplicates} già presenti")
            if report.errors:
                self.show_error("\n".join(report.errors))
            self.refresh()
        elif operation == "delete":
            if self.reader:
                self.reader.close()
            self.refresh()
            if self.search_input.text().strip():
                self._query_changed()
        elif operation in ("index", "reindex", "retry", "tags"):
            self.notice.hide()
            self.refresh()
            if self.selected_id is not None:
                self.open_document(self.selected_id)
            if self.search_input.text().strip():
                self._query_changed()

    @Slot(str, int, str)
    def _failed(self, operation, token, message):
        if self._closing or (operation == "search" and token != self._search_seq) or (operation == "pdf_page" and token != self._pdf_seq):
            return
        if operation == "search":
            self._searching = False
            self._render_cards()
        if operation == "map":
            self._map_pending = False
            self.map_page.canvas.message = "Mappa non disponibile."
            self.map_page.canvas.update()
        if operation in ("tags", "retry", "delete", "pdf_page") and self.reader and self.reader.isVisible():
            self.reader.show_error(message)
        self.show_error(message)

    def show_error(self, message: str):
        if "esper reindex" in message:
            message = "L’indice di ricerca deve essere ricostruito. Usa «Ricostruisci indice» nella barra laterale."
        self.notice_text.setText(message)
        self.notice.show()

    def _update_activity(self):
        if not self._busy:
            return
        active = next((doc for doc in self.documents if doc.status == "processing"), None)
        if self._operation in ("import", "index", "reindex", "retry") and active:
            self.activity_text.set_full_text(f"Indicizzazione: {active.name}")
            queued = sum(doc.status == "queued" for doc in self.documents)
            self.activity_queue.setText(f"{queued} in coda" if queued else "")
            self.activity.show()
        elif self._activity_message:
            self.activity_text.set_full_text(self._activity_message)
            self.activity_queue.clear()
            self.activity.show()

    @Slot(str)
    def _operation_started(self, operation):
        self._operation = operation

    @Slot(str)
    def _status(self, message):
        if not self._closing:
            self.statusBar().showMessage(message)
            if self._busy:
                self._activity_message = message
                self._update_activity()

    @Slot(bool)
    def _set_busy(self, busy):
        self._busy = busy
        self.progress.setVisible(busy)
        self.activity.hide()
        self._activity_message = ""
        self.activity_text.set_full_text("")
        self.activity_queue.clear()
        self.rebuild_button.setEnabled(not busy)
        if not busy and not self._closing:
            self.refresh()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.import_files(paths)
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.thread.isRunning():
            self._closing = True
            self.search_timer.stop()
            self.poll.stop()
            self.worker.stop.set()
            self.thread.quit()
            self.setEnabled(False)
            self.statusBar().showMessage("Chiusura al termine dell’operazione corrente…")
            event.ignore()
        else:
            self.memory.timer.stop()
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.sync()
            event.accept()

    @Slot()
    def _thread_finished(self):
        if self._closing:
            self.close()


def run(data_dir: Path = DATA_DIR) -> int:
    """Open a native window using the existing local archive or an explicit folder."""
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("Esper")
    app.setOrganizationName("Esper")
    app.setStyle("Fusion")
    window = MainWindow(Archive(data_dir))
    window.show()
    return app.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description="Esper native desktop application")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help="local archive folder")
    return run(parser.parse_args().data_dir)
