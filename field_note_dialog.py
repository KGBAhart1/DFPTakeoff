"""
Style dialog for a single Field Notes markup text item — used by the main
Takeoff window's "Add Note"/"Edit note…" tools (see main.py PdfCanvas).
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QCheckBox, QDoubleSpinBox, QColorDialog,
)
from PyQt5.QtGui import QColor


class FieldNoteDialog(QDialog):
    """Text + color/bold/size controls for one field note."""

    def __init__(self, text="", color="#000000", bold=False, font_size=10.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Field Note")
        self.setMinimumWidth(320)
        self._color = color

        l = QVBoxLayout(self)
        l.addWidget(QLabel("Note text (multiple lines OK):"))
        self._edit = QTextEdit()
        self._edit.setPlainText(text)
        self._edit.setFixedHeight(80)
        l.addWidget(self._edit)

        row = QHBoxLayout()
        row.addWidget(QLabel("Color:"))
        self._color_btn = QPushButton()
        self._color_btn.setFixedWidth(50)
        self._update_swatch()
        self._color_btn.clicked.connect(self._pick_color)
        row.addWidget(self._color_btn)

        self._bold_chk = QCheckBox("Bold")
        self._bold_chk.setChecked(bold)
        row.addWidget(self._bold_chk)

        row.addWidget(QLabel("Size:"))
        self._size_spin = QDoubleSpinBox()
        self._size_spin.setRange(6.0, 24.0)
        self._size_spin.setValue(font_size)
        row.addWidget(self._size_spin)
        row.addStretch()
        l.addLayout(row)

        br = QHBoxLayout()
        ok = QPushButton("OK")
        ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(cancel); br.addWidget(ok)
        l.addLayout(br)

    def _update_swatch(self):
        self._color_btn.setStyleSheet(
            f"background:{self._color};border:1px solid #888;")

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._color), self, "Note Color")
        if c.isValid():
            self._color = c.name()
            self._update_swatch()

    def text(self):
        return self._edit.toPlainText().strip()

    def color(self):
        return self._color

    def bold(self):
        return self._bold_chk.isChecked()

    def font_size(self):
        return self._size_spin.value()
