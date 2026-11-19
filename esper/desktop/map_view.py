"""Native interactive projection of the archive's saved three-dimensional map."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget,
)

from esper.archive_map import ArchiveMap, MAX_COSINE_DISTANCE, NEIGHBORS
from esper.desktop.theme import DARK, LIGHT
from esper.desktop.widgets import ElidedLabel, KIND, STATUS, label


class MapCanvas(QWidget):
    selected = Signal(int)
    activated = Signal(int)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(220)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Mappa tridimensionale dei documenti")
        self.setAccessibleDescription("Frecce per ruotare, più e meno per lo zoom, Invio per aprire.")
        self.setMouseTracking(True)
        self.light = False
        self.layout_data = ArchiveMap(-1, {}, ())
        self.documents = {}
        self.selected_id = None
        self.hovered = None
        self.screen_points = {}
        self.radius = 1
        self.press = None
        self.dragging = False
        self.message = "Preparazione della mappa…"
        self.view_extent = (2.0, 2.0)
        self.reset_view()

    def reset_view(self):
        self.yaw, self.pitch, self.zoom = -0.32, 0.24, 1.0
        self.update()

    def set_data(self, data):
        self.layout_data = data
        self.radius = max((math.hypot(*p) for p in data.positions.values()), default=1) or 1
        # Fit all projected points at the home angle. Keep this scale fixed
        # through rotation so moving the camera never distorts relative lengths.
        cy, sy = math.cos(-0.32), math.sin(-0.32)
        cp, sp = math.cos(0.24), math.sin(0.24)
        extent_x = extent_y = 0.22
        for point in data.positions.values():
            x, y, z = (value / self.radius for value in point)
            u, v = cy * x + sy * z, -sy * x + cy * z
            factor = 3.8 / (3.8 - sp * y - cp * v)
            extent_x = max(extent_x, abs(u * factor))
            extent_y = max(extent_y, abs((cp * y - sp * v) * factor))
        self.view_extent = (extent_x, extent_y)
        self.screen_points.clear()
        self.hovered = None
        self.message = "Nessun documento con una posizione disponibile."
        self.update()

    def change_zoom(self, factor):
        self.zoom = min(5, max(0.35, self.zoom * factor))
        self.update()

    def rotate(self, dx, dy):
        self.yaw += dx
        self.pitch = min(1.52, max(-1.52, self.pitch + dy))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = LIGHT if self.light else DARK
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(colors["panel"]))
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        scale = min(w * 0.43 / self.view_extent[0], h * 0.43 / self.view_extent[1]) * self.zoom

        def project(x, y, z):
            u, v = cy * x + sy * z, -sy * x + cy * z
            depth = sp * y + cp * v
            perspective = 3.8 / (3.8 - depth)
            return QPointF(w / 2 + scale * u * perspective, h / 2 - scale * (cp * y - sp * v) * perspective), depth

        # A reference plane follows the camera, making rotation and depth visible.
        p.setPen(QPen(QColor(colors["border"]), 0.8))
        for i in range(-5, 6):
            t = i / 5
            p.drawLine(project(t, -0.6, -1)[0], project(t, -0.6, 1)[0])
            p.drawLine(project(-1, -0.6, t)[0], project(1, -0.6, t)[0])
        if not self.layout_data.positions:
            p.setPen(QColor(colors["text"]))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return

        points = {i: project(x / self.radius, y / self.radius, z / self.radius)
                  for i, (x, y, z) in self.layout_data.positions.items()}
        focus = self.hovered if self.hovered is not None else self.selected_id
        for a, b, _ in self.layout_data.edges:
            active = focus in (a, b)
            p.setPen(QPen(QColor(colors["dim" if active else "strong"]), 1.6 if active else 1))
            p.drawLine(points[a][0], points[b][0])

        order = sorted(points, key=lambda key: (key == focus, points[key][1]))
        self.screen_points = {i: points[i][0] for i in order}
        for i in order:
            pt, depth = points[i]
            radius = 4.7 + depth * 1.5
            doc = self.documents.get(i)
            kind = doc.kind if doc else "file"
            p.setPen(QPen(QColor(colors["text"]), 1.4))
            p.setBrush(QColor(colors["text" if i == focus or kind == "image" else "paper"]))
            if kind == "pdf":
                p.drawPolygon(QPolygonF([pt + QPointF(dx, dy) for dx, dy in
                                        ((0, -radius-1), (radius+1, 0), (0, radius+1), (-radius-1, 0))]))
            elif kind == "image":
                p.drawRect(QRectF(pt.x()-radius, pt.y()-radius, 2*radius, 2*radius))
            else:
                p.drawEllipse(pt, radius, radius)
            if i == self.selected_id or i == self.hovered:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(pt, radius + 4, radius + 4)

        # Place a few readable labels, giving the inspected file first choice.
        occupied = []
        fm = p.fontMetrics()
        if self.selected_id in points and self.selected_id in self.documents:
            anchor = points[self.selected_id][0]
            name = fm.elidedText(self.documents[self.selected_id].name, Qt.TextElideMode.ElideMiddle, w // 3)
            tw, th = fm.horizontalAdvance(name) + 18, fm.height() + 8
            # The pinned callout stays readable even when several points coincide.
            side = 10 if anchor.x() >= w / 2 else w - tw - 10
            badge = QRectF(side, 10, tw, th)
            joint = QPointF(badge.center().x(), badge.bottom() + 10)
            p.setPen(QPen(QColor(colors["dim"]), 1, Qt.PenStyle.DashLine))
            p.drawLine(badge.center(), joint)
            p.drawLine(joint, anchor)
            p.fillRect(badge, QColor(colors["accent"]))
            p.setPen(QColor(colors["ink"]))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, name)
            occupied.append(badge.adjusted(-5, -5, 5, 5))
        for i in reversed(order[-64:]):
            if i == self.selected_id or i not in self.documents:
                continue
            pt = points[i][0]
            if not self.rect().contains(pt.toPoint()):
                continue
            name = fm.elidedText(self.documents[i].name, Qt.TextElideMode.ElideMiddle, min(190, w // 3))
            tw, th = fm.horizontalAdvance(name) + 10, fm.height() + 4
            x = pt.x() + 12 if pt.x() + 12 + tw <= w else pt.x() - tw - 12
            rect = QRectF(x, pt.y() - th / 2, tw, th)
            if not any(rect.intersects(other) for other in occupied) and not any(
                rect.contains(other) for other in self.screen_points.values()
            ):
                p.fillRect(rect, QColor(colors["panel"]))
                p.setPen(QColor(colors["text" if i == focus else "dim"]))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, name)
                occupied.append(rect.adjusted(-4, -3, 4, 3))
                if len(occupied) >= 10:
                    break

    def _hit(self, pos):
        return min((i for i in reversed(self.screen_points)
                    if (self.screen_points[i] - pos).manhattanLength() < 15),
                   key=lambda i: (self.screen_points[i] - pos).manhattanLength(), default=None)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press = self.last = event.position()
            self.dragging = False
            self.setFocus()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self.press is not None:
            if (pos - self.press).manhattanLength() >= QApplication.startDragDistance():
                self.dragging = True
            if self.dragging:
                delta = pos - self.last
                self.rotate(delta.x() * 0.012, delta.y() * 0.012)
                self.last = pos
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            self.hovered = self._hit(pos)
            doc = self.documents.get(self.hovered)
            self.setToolTip(doc.name if doc else "")
            self.setCursor(Qt.CursorShape.PointingHandCursor if doc else Qt.CursorShape.OpenHandCursor)
            self.update()

    def leaveEvent(self, event):
        self.hovered = None
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            target = self._hit(event.position())
            if self.press is not None and not self.dragging and target is not None:
                self.selected.emit(target)
            self.press = None
            self.unsetCursor()

    def mouseDoubleClickEvent(self, event):
        target = self._hit(event.position())
        if target is not None and event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(target)

    def wheelEvent(self, event):
        self.change_zoom(1.15 ** (event.angleDelta().y() / 120))
        event.accept()

    def keyPressEvent(self, event):
        key = event.key()
        arrows = {Qt.Key.Key_Left: (-0.12, 0), Qt.Key.Key_Right: (0.12, 0),
                  Qt.Key.Key_Up: (0, -0.12), Qt.Key.Key_Down: (0, 0.12)}
        if key in arrows:
            self.rotate(*arrows[key])
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Minus):
            self.change_zoom(1 / 1.2 if key == Qt.Key.Key_Minus else 1.2)
        elif key == Qt.Key.Key_Home:
            self.reset_view()
        elif key == Qt.Key.Key_Return and self.selected_id is not None:
            self.activated.emit(self.selected_id)
        else:
            super().keyPressEvent(event)


class MapPage(QWidget):
    activated = Signal(int)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 18, 28, 20)
        layout.setSpacing(10)
        layout.addWidget(label("Mappa dei documenti", "mapTitle"))
        layout.addWidget(label("I file vicini hanno contenuti simili. Le linee indicano le affinità più forti.", "description", True))
        panel = QFrame()
        panel.setObjectName("hero")
        stage = QVBoxLayout(panel)
        stage.setContentsMargins(12, 10, 12, 10)
        toolbar = QHBoxLayout()
        self.count = label("", "muted")
        distance = f"{MAX_COSINE_DISTANCE:.2f}".replace(".", ",")
        self.count.setToolTip(f"Ogni file propone fino a {NEIGHBORS} vicini con distanza coseno inferiore a {distance}.")
        toolbar.addWidget(self.count, 1)
        self.canvas = MapCanvas()
        for title, tip, action in (("−", "Riduci zoom", lambda: self.canvas.change_zoom(1/1.2)),
                                   ("+", "Aumenta zoom", lambda: self.canvas.change_zoom(1.2)),
                                   ("Centra", "Ripristina la vista", self.canvas.reset_view)):
            control = QPushButton(title)
            control.setObjectName("mapTool")
            control.setToolTip(tip)
            control.setAccessibleName(tip)
            control.clicked.connect(action)
            toolbar.addWidget(control)
        stage.addLayout(toolbar)
        stage.addWidget(self.canvas, 1)
        stage.addWidget(label("○  Testo     ◇  PDF     ■  Immagine", "muted"))
        layout.addWidget(panel, 1)
        layout.addWidget(label("Trascina per ruotare · Rotella per lo zoom · Doppio clic per aprire", "muted"))
        inspector = QHBoxLayout()
        self.files = QComboBox()
        self.files.setAccessibleName("Seleziona un documento sulla mappa")
        self.files.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        inspector.addWidget(self.files, 1)
        self.open = QPushButton("Apri documento")
        self.open.setObjectName("primary")
        self.open.clicked.connect(self.open_selected)
        inspector.addWidget(self.open)
        layout.addLayout(inspector)
        self.detail = ElidedLabel("", "description")
        layout.addWidget(self.detail)
        self.files.currentIndexChanged.connect(self._selection_changed)
        self.canvas.selected.connect(self.select)
        self.canvas.activated.connect(self.activated)

    def open_selected(self):
        if self.files.currentData() is not None:
            self.activated.emit(self.files.currentData())

    def select(self, doc_id):
        self.files.setCurrentIndex(self.files.findData(doc_id))

    def set_documents(self, docs):
        selected = self.files.currentData()
        self.canvas.documents = {doc.id: doc for doc in docs}
        self.files.blockSignals(True)
        self.files.clear()
        for doc in sorted(docs, key=lambda doc: doc.name.casefold()):
            self.files.addItem(doc.name, doc.id)
        idx = self.files.findData(selected) if selected is not None else -1
        if idx >= 0:
            self.files.setCurrentIndex(idx)
        self.files.blockSignals(False)
        self._selection_changed()

    def set_data(self, data):
        self.canvas.set_data(data)
        hidden = len(self.canvas.documents.keys() - data.positions.keys())
        suffix = f" · {hidden} senza posizione" if hidden else ""
        self.count.setText(f"{len(data.positions)} in mappa · {len(data.edges)} legami{suffix}")
        self._selection_changed()

    def _selection_changed(self):
        key = self.files.currentData()
        doc = self.canvas.documents.get(key)
        self.open.setEnabled(doc is not None)
        self.canvas.selected_id = key
        if doc is None:
            text = "Aggiungi documenti per esplorare la mappa."
        else:
            neighbors = [(distance, b if a == key else a)
                         for a, b, distance in self.canvas.layout_data.edges if key in (a, b)]
            if key in self.canvas.layout_data.positions:
                text = f"{len(neighbors)} " + ("legame" if len(neighbors) == 1 else "legami")
                if neighbors:
                    distance, nearest = min(neighbors)
                    other = self.canvas.documents.get(nearest)
                    if other:
                        value = f"{distance:.2f}".replace(".", ",")
                        text += f" · Più vicino: {other.name} (distanza {value})"
            elif self.canvas.layout_data.revision < 0:
                text = "Posizione in preparazione"
            else:
                text = f'{STATUS[doc.status]} · Senza posizione'
            text = f"{KIND[doc.kind]} · {text}"
        self.detail.set_full_text(text)
        self.canvas.update()
