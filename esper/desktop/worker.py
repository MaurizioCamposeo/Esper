"""Serialize archive mutations and inference on a Qt worker thread."""

from threading import Event, Lock

from PySide6.QtCore import QObject, Signal, Slot

from esper.desktop.service import Archive
from esper.indexing import set_status


class Worker(QObject):
    result = Signal(str, int, object)
    failed = Signal(str, int, str)
    changed = Signal()
    status = Signal(str)
    busy = Signal(bool)
    started = Signal(str)

    def __init__(self, archive: Archive):
        super().__init__()
        self.archive = archive
        self.stop = Event()
        self._search_lock = Lock()
        self._latest_search = 0

    def latest_search(self, token: int) -> None:
        """Invalidate queued descriptions using thread-safe, non-widget state."""
        with self._search_lock:
            self._latest_search = token

    def _is_current(self, token: int) -> bool:
        with self._search_lock:
            return token == self._latest_search

    def _progress(self, indexed: int, failed: int) -> None:
        self.status.emit(f"Indicizzazione in corso · {indexed} completati" + (f" · {failed} errori" if failed else ""))
        self.changed.emit()

    def _index(self, rebuild: bool = False):
        return self.archive.index(
            rebuild=rebuild, notify=self.status.emit, progress=self._progress,
            should_stop=self.stop.is_set,
        )

    @Slot(str, int, object)
    def execute(self, operation: str, token: int, payload: object) -> None:
        if self.stop.is_set() or (operation == "search" and not self._is_current(token)):
            return
        self.started.emit(operation)
        self.busy.emit(True)
        try:
            if operation == "import":
                self.status.emit("Importazione dei documenti…")
                value = self.archive.import_paths(payload)
                self.result.emit(operation, token, value)
                self.changed.emit()
                indexed, failed = self._index()
                if failed:
                    self.status.emit(f"Indicizzazione conclusa · {failed} documenti richiedono attenzione")
                return
            if operation in ("index", "reindex"):
                value = self._index(operation == "reindex")
                self.changed.emit()
            elif operation == "search":
                query, tags, mode = payload
                value = self.archive.search(query, tags, mode, self.status.emit)
            elif operation == "map":
                self.status.emit("Preparazione della mappa…")
                value = self.archive.spatial_map()
            elif operation == "detail":
                value = self.archive.detail(payload)
            elif operation == "pdf_page":
                value = self.archive.render_pdf_page(*payload)
            elif operation == "tags":
                document_id, tags = payload
                self.archive.update_tags(document_id, tags)
                value = document_id
                self.changed.emit()
            elif operation == "delete":
                value = self.archive.delete(payload)
                self.changed.emit()
            elif operation == "retry":
                with self.archive.connection() as conn:
                    if conn.execute("SELECT 1 FROM documents WHERE id = ?", (payload,)).fetchone() is None:
                        raise ValueError(f"no document #{payload}")
                    set_status(conn, payload, "queued")
                self.changed.emit()
                value = self._index()
                self.changed.emit()
            else:
                raise ValueError(f"Unknown desktop operation: {operation}")
            self.result.emit(operation, token, value)
        except Exception as exc:
            self.failed.emit(operation, token, str(exc))
        finally:
            self.busy.emit(False)
