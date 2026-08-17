"""
"Manage Pages" dialog for the main Takeoff window — lets the user rename
pages and delete arbitrary (not necessarily consecutive) pages from an
uploaded print before/while doing a takeoff on it. See main.py
MainWindow._manage_pages().
"""

import fitz
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
    QPushButton, QScrollArea, QWidget, QFrame, QMessageBox,
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt

import db


class ManagePagesDialog(QDialog):
    def __init__(self, doc, project_id, pdf_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Pages")
        self.resize(520, 620)
        self._doc = doc
        self._project_id = project_id
        self._pdf_path = pdf_path
        self._orig_labels = db.get_page_labels(project_id, pdf_path)
        self._rows = []   # list of (page_index, QLineEdit, QCheckBox)
        self._kept = None
        self._labels = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Rename pages and check any you want to delete. Deleting overwrites "
            "the print — a backup copy of the original is saved automatically."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        rows_layout = QVBoxLayout(inner)
        rows_layout.setSpacing(6)

        for i in range(len(self._doc)):
            row = QFrame()
            row.setFrameShape(QFrame.StyledPanel)
            h = QHBoxLayout(row)

            thumb_lbl = QLabel()
            thumb_lbl.setPixmap(self._make_thumbnail(i))
            h.addWidget(thumb_lbl)

            v = QVBoxLayout()
            v.addWidget(QLabel(f"Page {i + 1}"))
            name_edit = QLineEdit(self._orig_labels.get(i, ""))
            name_edit.setPlaceholderText("Custom name (optional)")
            v.addWidget(name_edit)
            h.addLayout(v)

            h.addStretch()
            del_chk = QCheckBox("Delete")
            h.addWidget(del_chk)

            rows_layout.addWidget(row)
            self._rows.append((i, name_edit, del_chk))

        rows_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        br = QHBoxLayout()
        ok = QPushButton("OK")
        ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        ok.clicked.connect(self._on_ok)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(cancel); br.addWidget(ok)
        layout.addLayout(br)

    def _make_thumbnail(self, page_index):
        page = self._doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(0.15, 0.15), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        return QPixmap.fromImage(img)

    def _on_ok(self):
        kept = [i for i, _, chk in self._rows if not chk.isChecked()]
        if not kept:
            QMessageBox.warning(self, "No Pages Left",
                                 "At least one page must remain — uncheck at least one Delete box.")
            return
        n_deleted = len(self._rows) - len(kept)
        if n_deleted:
            resp = QMessageBox.question(
                self, "Confirm Delete",
                f"Delete {n_deleted} page(s)? A backup of the original print will be "
                f"saved first.\n\nThis cannot be undone from within the app — use the "
                f"backup file to recover the original if needed.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resp != QMessageBox.Yes:
                return
        self._kept = kept
        self._labels = {}
        for new_idx, old_idx in enumerate(kept):
            edit = next(e for i, e, _ in self._rows if i == old_idx)
            label = edit.text().strip()
            if label:
                self._labels[new_idx] = label
        self.accept()

    def result_data(self):
        """Returns (kept_old_indices, {new_index: label}) — call after exec_() == Accepted."""
        return self._kept, self._labels

    def labels_changed(self):
        """True if any page's custom name differs from what was loaded."""
        for i, edit, _ in self._rows:
            if edit.text().strip() != self._orig_labels.get(i, ""):
                return True
        return False
