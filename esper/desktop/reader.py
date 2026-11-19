"""Native document reader with original text, passages and archive actions."""

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from esper.desktop.service import DocumentDetail
from esper.desktop.widgets import ElidedLabel, KIND, STATUS, label, passage_prefix, size_text
from esper.extract import IMAGE_MIME_TYPES


class PDFPreview(QScrollArea):
    """Fit a rendered page to the viewport width while retaining vertical scroll."""

    def __init__(self):
        super().__init__()
        self.original = QPixmap()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.image = label("Caricamento della pagina…")
        self.image.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setWidget(self.image)

    def clear(self):
        self.original = QPixmap()
        self.image.clear()
        self.image.setMinimumHeight(0)

    def set_image(self, data: bytes):
        self.original.loadFromData(data)
        self._fit()

    def _fit(self):
        if not self.original.isNull():
            scaled = self.original.scaledToWidth(max(1, min(self.original.width(), self.viewport().width())), Qt.TransformationMode.SmoothTransformation)
            self.image.setPixmap(scaled)
            self.image.setMinimumHeight(scaled.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


class DocumentDialog(QDialog):
    tags_requested = Signal(int, object)
    delete_requested = Signal(int)
    retry_requested = Signal(int)
    page_requested = Signal(int, int)

    def __init__(self, detail: DocumentDetail, parent=None, *, initial_page: int = 1):
        super().__init__(parent)
        self.detail = detail
        self.pdf_page = initial_page
        doc = detail.document
        self.setWindowTitle(doc.name)
        self.setMinimumSize(780, 540)
        self.resize(1040, 740)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 20)
        outer.setSpacing(18)
        title = ElidedLabel(doc.name, "sectionTitle")
        outer.addWidget(title)
        self.error_label = label("", "description", True)
        self.error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.error_label.hide()
        outer.addWidget(self.error_label)
        body = QHBoxLayout()
        tabs = QTabWidget()
        self.tabs = tabs
        if doc.kind in ("text", "markdown") and detail.preview:
            if doc.kind == "markdown":
                preview = QTextEdit()
                preview.setReadOnly(True)
                preview.setMarkdown(detail.preview)
            else:
                preview = QPlainTextEdit(detail.preview)
                preview.setReadOnly(True)
            preview.setObjectName("originalPreview")
            tabs.addTab(preview, "Anteprima")
        elif doc.kind == "pdf":
            preview = QWidget()
            pdf_layout = QVBoxLayout(preview)
            toolbar = QHBoxLayout()
            previous = QPushButton("‹")
            previous.setAccessibleName("Pagina precedente")
            previous.clicked.connect(lambda: self.request_page(self.pdf_page - 1))
            toolbar.addWidget(previous)
            toolbar.addWidget(label("Pagina"))
            self.page_selector = QSpinBox()
            self.page_selector.setAccessibleName("Pagina PDF")
            self.page_selector.setRange(1, doc.page_count or initial_page)
            self.page_selector.setValue(initial_page)
            self.page_selector.valueChanged.connect(self.request_page)
            toolbar.addWidget(self.page_selector)
            self.page_total = label(f"/ {doc.page_count or '…'}")
            toolbar.addWidget(self.page_total)
            following = QPushButton("›")
            following.setAccessibleName("Pagina successiva")
            following.clicked.connect(lambda: self.request_page(self.pdf_page + 1))
            toolbar.addWidget(following)
            toolbar.addStretch()
            pdf_layout.addLayout(toolbar)
            self.pdf_preview = PDFPreview()
            self.pdf_image = self.pdf_preview.image
            pdf_layout.addWidget(self.pdf_preview, 1)
            tabs.addTab(preview, "Anteprima PDF")
            QTimer.singleShot(0, lambda: self.request_page(initial_page))
        elif doc.kind == "image":
            preview = QScrollArea()
            preview.setWidgetResizable(True)
            image = label()
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap(str(doc.path))
            if pixmap.isNull():
                image.setText("Impossibile leggere questa immagine.")
            else:
                image.setPixmap(pixmap.scaled(680, 550, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            preview.setWidget(image)
            tabs.addTab(preview, "Anteprima")
        else:
            preview = label("Apri l’originale nel lettore del sistema.", "description", True)
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tabs.addTab(preview, "Anteprima")
        passages = QPlainTextEdit()
        passages.setObjectName("passages")
        passages.setReadOnly(True)
        passages.setPlainText("\n\n────────────────────\n\n".join(
            passage_prefix(chunk.get("page"), chunk.get("source", "text"))
            + f"Passaggio {chunk['position'] + 1}\n\n{chunk['text']}" for chunk in detail.chunks
        ) or "I passaggi saranno disponibili dopo l’indicizzazione.")
        tabs.addTab(passages, f"Passaggi ({len(detail.chunks)})")
        body.addWidget(tabs, 1)
        inspector = QWidget()
        inspector.setFixedWidth(245)
        info = QVBoxLayout(inspector)
        info.setContentsMargins(16, 8, 0, 0)
        info.setSpacing(16)
        info.addWidget(label("Stato del documento", "muted"))
        info.addWidget(label(STATUS.get(doc.status, doc.status)))
        if doc.error:
            error = ("Questo formato viene conservato nell’archivio. La ricerca supporta TXT, Markdown, PDF con testo, JPEG e PNG."
                     if "UnsupportedFormatError" in doc.error else doc.error)
            info.addWidget(label(error, "description", True))
        if doc.extraction_warning:
            info.addWidget(label(doc.extraction_warning, "description", True))
        if ((doc.error and (doc.kind in ("text", "markdown", "pdf") or doc.mime in IMAGE_MIME_TYPES))
                or (doc.extraction_warning and doc.mime in IMAGE_MIME_TYPES and doc.status == "indexed")):
            retry = QPushButton("Riprova indicizzazione")
            retry.clicked.connect(lambda: self.retry_requested.emit(doc.id))
            info.addWidget(retry)
        info.addWidget(label("Informazioni", "muted"))
        chunk_label = "passaggio" if doc.chunk_count == 1 else "passaggi"
        info.addWidget(label(f"{KIND.get(doc.kind, 'File')}\n{size_text(doc.size)}\n{doc.chunk_count} {chunk_label}\n{doc.created_at[:10]}", "description"))
        info.addWidget(label("Etichette separate da virgole", "muted"))
        self.tags_input = QLineEdit(", ".join(doc.tags))
        self.tags_input.setCursorPosition(0)
        self.tags_input.setAccessibleName("Etichette del documento")
        info.addWidget(self.tags_input)
        save = QPushButton("Salva etichette")
        save.clicked.connect(lambda: self.tags_requested.emit(doc.id, [tag.strip() for tag in self.tags_input.text().split(",") if tag.strip()]))
        info.addWidget(save)
        if detail.truncated:
            info.addWidget(label("Anteprima limitata ai primi 2 MB. L’originale è completo.", "muted", True))
        info.addStretch()
        original = QPushButton("Apri originale ↗")
        original.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(doc.path))))
        info.addWidget(original)
        delete = QPushButton("Elimina documento")
        delete.clicked.connect(self._confirm_delete)
        info.addWidget(delete)
        close = QPushButton("Chiudi")
        close.clicked.connect(self.close)
        info.addWidget(close)
        body.addWidget(inspector)
        outer.addLayout(body, 1)

    def request_page(self, page: int):
        if not 1 <= page <= self.page_selector.maximum():
            return
        self.pdf_page = page
        self.pdf_preview.clear()
        self.pdf_image.setText("Caricamento della pagina…")
        self.page_requested.emit(self.detail.document.id, page)

    def show_pdf_page(self, result):
        if result.page != self.pdf_page:
            return
        self.page_selector.blockSignals(True)
        self.page_selector.setRange(1, result.page_count)
        self.page_selector.setValue(result.page)
        self.page_selector.blockSignals(False)
        self.page_total.setText(f"/ {result.page_count}")
        self.pdf_preview.set_image(result.png)

    def show_error(self, message: str):
        """Keep action failures visible while this modal reader is open."""
        self.error_label.setText(message)
        self.error_label.show()
        if hasattr(self, "pdf_image") and self.pdf_image.pixmap().isNull():
            self.pdf_image.setText("Anteprima non disponibile.")

    def _confirm_delete(self):
        answer = QMessageBox.question(
            self, "Elimina documento",
            "Eliminare la copia archiviata e i relativi dati di ricerca?\nIl file di origine non viene modificato.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.detail.document.id)
