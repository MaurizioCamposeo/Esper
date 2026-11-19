"""Native optical recall display and document cards; no browser engine."""

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QImageReader, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from esper.desktop.service import Document
from esper.desktop.theme import DARK, LIGHT

STATUS = {"queued": "In coda", "processing": "Elaborazione", "indexed": "Indicizzato", "error": "Errore"}
KIND = {"text": "Testo", "markdown": "Markdown", "pdf": "PDF", "image": "Immagine", "file": "File"}


def passage_prefix(page: int | None, source: str) -> str:
    parts = []
    if page is not None:
        parts.append(f"Pagina {page} · ")
    if source == "caption":
        parts.append("Descrizione generata · ")
    elif source == "ocr":
        parts.append("Testo OCR · ")
    return "".join(parts)


def label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setObjectName(name)
    result.setWordWrap(wrap)
    return result


def size_text(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


class ElidedLabel(QLabel):
    """Display a one-line title with its full text available on hover."""

    def __init__(self, text: str, name: str):
        super().__init__()
        self.full_text = text
        self.setObjectName(name)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setToolTip(text)
        self.setAccessibleName(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def set_full_text(self, text: str):
        self.full_text = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._update_text()

    def _update_text(self):
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideMiddle, self.contentsRect().width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_text()


class ElidedButton(QPushButton):
    """Keep long filenames and tags inside their available width."""

    def __init__(self, text: str):
        super().__init__()
        self.full_text = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._update_text()

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def _update_text(self):
        text = self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideRight, max(0, self.width() - 30))
        # User filenames and tags may contain literal ampersands.
        self.setText(text.replace("&", "&&"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_text()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange) and hasattr(self, "full_text"):
            self._update_text()


class MemoryField(QWidget):
    activated = Signal(int)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(280, 134)
        self.setFixedHeight(146)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Richiamo dei documenti dell’archivio")
        self.documents: list[Document] = []
        self.empty_text = "Nessun documento"
        self.position = 0
        self.light = False
        self.angle = 0.0
        self.image = QImage()
        self._image_id = None
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self._tick)

    def _tick(self):
        self.angle = (self.angle + 0.15) % 360
        self.update()

    def set_documents(self, documents: list[Document]):
        selected = self.selected.id if self.selected else None
        images = [doc for doc in documents if doc.kind == "image"]
        self.documents = (images or [doc for doc in documents if doc.excerpt])[:4]
        if any(doc.status in ("queued", "processing") for doc in documents):
            self.empty_text = "Anteprima in preparazione…"
        else:
            self.empty_text = "Nessuna anteprima disponibile" if documents else "Nessun documento"
        self.position = next((i for i, doc in enumerate(self.documents) if doc.id == selected), 0)
        self._load_image()

    @property
    def selected(self) -> Document | None:
        return self.documents[self.position] if self.documents else None

    def _load_image(self):
        image_id = self.selected.id if self.selected and self.selected.kind == "image" else None
        if image_id != self._image_id:
            self.image = QImage()
            if image_id is not None:
                reader = QImageReader(str(self.selected.path))
                size = reader.size()
                size.scale(1000, 700, Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(size)
                self.image = reader.read().convertToFormat(QImage.Format.Format_Grayscale8)
            self._image_id = image_id
        self.setToolTip(f"Apri {self.selected.name}" if self.selected else self.empty_text)
        self.update()

    def set_motion(self, enabled: bool):
        self.timer.start() if enabled else self.timer.stop()
        self.update()

    def next_document(self, step: int = 1):
        if self.documents:
            self.position = (self.position + step) % len(self.documents)
            self._load_image()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.selected:
            self.activated.emit(self.selected.id)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.next_document(-1 if event.key() == Qt.Key.Key_Left else 1)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space) and self.selected:
            self.activated.emit(self.selected.id)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = LIGHT if self.light else DARK
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(colors["border"]), 1))
        p.drawLine(0, h // 2, w, h // 2)
        p.drawLine(w // 2, 20, w // 2, h - 20)
        p.save()
        p.translate(w / 2, h / 2)
        p.rotate(self.angle)
        p.setPen(QPen(QColor(colors["border"]), 1, Qt.PenStyle.DashLine))
        p.drawEllipse(QRectF(-150, -150, 300, 300))
        p.setPen(QPen(QColor(colors["border"]), 1))
        p.drawEllipse(QRectF(-175, -175, 350, 350))
        p.restore()
        frame = QRectF(27, 13, w - 54, h - 45)
        p.fillRect(frame, QColor(colors["paper"]))
        p.setPen(QPen(QColor(colors["strong"]), 1))
        p.drawRect(frame)
        if not self.image.isNull():
            scaled = self.image.scaled(frame.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            p.drawImage(int(frame.center().x() - scaled.width() / 2), int(frame.center().y() - scaled.height() / 2), scaled)
        else:
            p.setPen(QColor(colors["dim"]))
            p.setFont(QFont("DejaVu Sans", 11))
            content = (passage_prefix(None, self.selected.excerpt_source) + self.selected.excerpt
                       if self.selected else self.empty_text)
            if len(content) > 92:
                content = content[:91].rstrip() + "…"
            p.drawText(frame.adjusted(10, 5, -10, -5), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, content)
        p.setPen(QPen(QColor(colors["dim"]), 1))
        for x, y, dx, dy in ((frame.left() - 6, frame.top() - 6, 1, 1), (frame.right() + 6, frame.top() - 6, -1, 1),
                             (frame.left() - 6, frame.bottom() + 6, 1, -1), (frame.right() + 6, frame.bottom() + 6, -1, -1)):
            p.drawLine(int(x), int(y), int(x + dx * 16), int(y))
            p.drawLine(int(x), int(y), int(x), int(y + dy * 16))
        for i in range(21):
            y = int(30 + i * (h - 60) / 20)
            p.drawLine(0, y, 8 if i % 5 == 0 else 3, y)
        p.setFont(QFont("DejaVu Sans Mono", 9))
        p.setPen(QColor(colors["muted"]))
        name = self.selected.name if self.selected else "Archivio locale"
        p.drawText(34, h - 12, p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, w - 135))
        p.drawText(w - 85, h - 12, f"{self.position + 1 if self.documents else 0:02d} / {len(self.documents):02d}")


class FileMark(QWidget):
    """Small format glyph drawn with the current widget palette."""

    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.setFixedSize(38, 42)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = self.palette().color(self.foregroundRole())
        wash = QColor(ink)
        wash.setAlpha(13)
        p.fillRect(self.rect(), wash)
        p.setPen(QPen(ink, 1.25))
        if self.kind == "image":
            p.drawRect(7, 10, 24, 22)
            p.drawEllipse(21, 14, 4, 4)
            p.drawLine(8, 29, 15, 21)
            p.drawLine(15, 21, 22, 29)
        else:
            p.drawLine(10, 8, 22, 8)
            p.drawLine(22, 8, 28, 14)
            p.drawLine(28, 14, 28, 33)
            p.drawLine(28, 33, 10, 33)
            p.drawLine(10, 33, 10, 8)
            p.drawLine(22, 8, 22, 14)
            p.drawLine(22, 14, 28, 14)
            if self.kind == "pdf":
                p.drawText(QRectF(6, 15, 27, 17), Qt.AlignmentFlag.AlignCenter, "P")
            else:
                for y in (19, 23, 27):
                    p.drawLine(14, y, 23 if y != 27 else 19, y)


class DocumentCard(QFrame):
    activated = Signal(int)
    tag_clicked = Signal(str)

    def __init__(self, doc: Document, passages: list[str] | None = None):
        super().__init__()
        self.setObjectName("card")
        self.document_id = doc.id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 17, 20, 18)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        heading.addWidget(FileMark(doc.kind))
        identity = QVBoxLayout()
        identity.setSpacing(0)
        name = ElidedButton(doc.name)
        name.setObjectName("documentName")
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        name.setStyleSheet("text-align: left; border: none; padding: 0; font-size: 16px; font-weight: 500;")
        name.setToolTip(doc.name)
        name.setAccessibleName(f"Apri {doc.name}")
        name.clicked.connect(lambda: self.activated.emit(doc.id))
        identity.addWidget(name)
        identity.addWidget(label(f"{KIND.get(doc.kind, 'File')} · {size_text(doc.size)} · {STATUS.get(doc.status, doc.status)}", "muted"))
        heading.addLayout(identity, 1)
        open_button = QPushButton("↗")
        open_button.setObjectName("openCard")
        open_button.setAccessibleName(f"Apri {doc.name}")
        open_button.setToolTip(f"Apri {doc.name}")
        open_button.clicked.connect(lambda: self.activated.emit(doc.id))
        heading.addWidget(open_button)
        layout.addLayout(heading)
        excerpts = [passage_prefix(None, doc.excerpt_source) + doc.excerpt] if doc.excerpt else []
        for text in (passages or excerpts)[:2]:
            excerpt = " ".join(text.split())
            layout.addWidget(label(excerpt[:377] + "…" if len(excerpt) > 380 else excerpt, "excerpt", True))
        if doc.status == "error" and not passages:
            layout.addWidget(label("Apri il documento per i dettagli dell’errore.", "muted", True))
        if doc.extraction_warning:
            layout.addWidget(label(f"Ricerca parziale · {doc.extraction_warning}", "muted", True))
        if doc.tags:
            tags = QGridLayout()
            for index, tag in enumerate(doc.tags[:4]):
                chip = ElidedButton(tag)
                chip.setObjectName("chip")
                chip.clicked.connect(lambda checked=False, name=tag: self.tag_clicked.emit(name))
                tags.addWidget(chip, index // 2, index % 2)
            layout.addLayout(tags)
        layout.addStretch()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Wrapped passages must determine the scroll page's minimum height.
        height = self.layout().heightForWidth(event.size().width())
        if height > 0 and self.minimumHeight() != height:
            self.setMinimumHeight(height)
