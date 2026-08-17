"""
Floating "snip" reference windows for the main Takeoff window — a pinned
crop of a PDF page (e.g. the symbol legend, sitting on another page) that
stays visible off to the side while working the drawing. See main.py
MainWindow._toggle_snip_mode / _on_snip_rect_selected / _manage_snips.
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDialog,
    QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

import db


class SnipWindow(QWidget):
    """A single floating, freely resizable/movable window showing one
    frozen snapshot crop. Geometry changes are debounced and persisted so
    the window reopens where you left it."""
    closed            = pyqtSignal(int)                  # snip_id
    geometry_changed  = pyqtSignal(int, int, int, int, int)  # snip_id, x, y, w, h

    def __init__(self, snip_id, name, image_bytes, parent=None):
        super().__init__(parent, Qt.Window)
        self.snip_id = snip_id
        self.setWindowTitle(name)
        self._pixmap = QPixmap()
        self._pixmap.loadFromData(image_bytes)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("background:#ffffff;")
        self._label.setMinimumSize(40, 40)
        layout.addWidget(self._label)

        # Debounce geometry saves — resize/move fire many events per drag,
        # and we only need to persist the settled result.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._emit_geometry)

    def set_name(self, name):
        self.setWindowTitle(name)

    def showEvent(self, event):
        super().showEvent(event)
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()
        self._save_timer.start(400)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._save_timer.start(400)

    def _rescale(self):
        if self._pixmap.isNull():
            return
        scaled = self._pixmap.scaled(self._label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._label.setPixmap(scaled)

    def _emit_geometry(self):
        g = self.geometry()
        self.geometry_changed.emit(self.snip_id, g.x(), g.y(), g.width(), g.height())

    def closeEvent(self, event):
        self.closed.emit(self.snip_id)
        super().closeEvent(event)


class ManageSnipsDialog(QDialog):
    """Rename/delete existing snips. Visibility (show/hide) is handled from
    the Snips ▾ toolbar menu, not here — this is for the less-frequent
    housekeeping actions."""
    def __init__(self, project_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Snips")
        self.resize(360, 420)
        self._project_id = project_id
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Rename or delete a saved snip."))
        self._list = QListWidget()
        layout.addWidget(self._list)

        btns = QHBoxLayout()
        rename_btn = QPushButton("Rename")
        rename_btn.clicked.connect(self._rename)
        del_btn = QPushButton("Delete")
        del_btn.setStyleSheet("background:#c02b0a;color:white;")
        del_btn.clicked.connect(self._delete)
        btns.addWidget(rename_btn); btns.addWidget(del_btn); btns.addStretch()
        layout.addLayout(btns)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        close_btn.clicked.connect(self.accept)
        cr = QHBoxLayout(); cr.addStretch(); cr.addWidget(close_btn)
        layout.addLayout(cr)

    def _load(self):
        self._list.clear()
        for s in db.get_snips(self._project_id):
            item = QListWidgetItem(s["name"])
            item.setData(Qt.UserRole, s["id"])
            self._list.addItem(item)

    def _rename(self):
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(self, "Select", "Select a snip to rename.")
            return
        sid = item.data(Qt.UserRole)
        name, ok = QInputDialog.getText(self, "Rename Snip", "Name:", text=item.text())
        if ok and name.strip():
            db.rename_snip(sid, name.strip())
            self._load()

    def _delete(self):
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(self, "Select", "Select a snip to delete.")
            return
        sid = item.data(Qt.UserRole)
        if QMessageBox.question(self, "Delete Snip", f"Delete '{item.text()}'?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            db.delete_snip(sid)
            self._load()
