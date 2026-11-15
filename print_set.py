"""
Print sets — drawings often arrive as several PDFs (E-001.pdf, E-101.pdf, ...).
Pick the folder that holds them all and they're merged into one combined PDF
so the whole set can be worked on at once (one page list, one set of counts).

The combined file is saved in the same folder as
"<project name> - All Prints.pdf". Each page gets a page label naming the
print file it came from, shown next to the page number.
"""
import os, re
import fitz

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QPushButton, QDialogButtonBox, QAbstractItemView)
from PyQt5.QtCore import Qt

COMBINED_SUFFIX = " - All Prints"


def natural_key(name):
    """Sort 'E-2.pdf' before 'E-10.pdf'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def find_prints(folder):
    """PDFs directly in folder, natural-sorted, skipping files this app wrote
    itself (combined sets, page-trim backups, temp files)."""
    out = []
    for f in os.listdir(folder):
        low = f.lower()
        if not low.endswith(".pdf"):
            continue
        stem = os.path.splitext(f)[0]
        if COMBINED_SUFFIX.lower() in stem.lower() or stem.lower().endswith("_backup"):
            continue
        out.append(os.path.join(folder, f))
    return sorted(out, key=lambda p: natural_key(os.path.basename(p)))


def _safe_name(s):
    return re.sub(r'[<>:"/\\|?*]+', "-", s).strip() or "Project"


def combined_path(folder, project_name, in_use):
    """Path for the combined PDF. If a combined file already exists and the
    project has marks on it (in_use(path) -> True), never overwrite it —
    re-merging could shift pages under existing counts — pick a new name."""
    base = os.path.join(folder, _safe_name(project_name) + COMBINED_SUFFIX)
    path, n = base + ".pdf", 1
    while os.path.exists(path) and in_use(path):
        n += 1
        path = f"{base} ({n}).pdf"
    return path


def merge_prints(files, out_path):
    """Merge PDFs in the given order into out_path.
    Returns (page_labels {page_index: label}, skipped [(file, reason)])."""
    out = fitz.open()
    labels, skipped = {}, []
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        try:
            src = fitz.open(f)
        except Exception:
            skipped.append((f, "not a valid PDF / can't be opened")); continue
        if src.needs_pass:
            skipped.append((f, "password protected")); src.close(); continue
        if len(src) == 0:
            skipped.append((f, "no pages")); src.close(); continue
        start = len(out)
        out.insert_pdf(src)
        for i in range(len(src)):
            labels[start + i] = name if len(src) == 1 else f"{name} (p{i + 1})"
        src.close()
    if len(out) == 0:
        out.close()
        raise ValueError("None of the selected PDFs could be read.")
    tmp = out_path + ".tmp"
    out.save(tmp, garbage=3, deflate=True)
    out.close()
    os.replace(tmp, out_path)
    return labels, skipped


class PrintSetDialog(QDialog):
    """Confirm which prints go into the set and in what order."""

    def __init__(self, files, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Combine Prints")
        self.resize(520, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            f"Found {len(files)} PDF(s). They'll be merged into one file in this order.\n"
            "Untick any you don't want, drag (or use Up/Down) to change the order."))
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        for f in files:
            it = QListWidgetItem(os.path.basename(f))
            it.setData(Qt.UserRole, f)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            self.list.addItem(it)
        lay.addWidget(self.list)
        row = QHBoxLayout()
        for text, step in (("Up", -1), ("Down", 1)):
            b = QPushButton(text); b.clicked.connect(lambda _, s=step: self._move(s)); row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Combine && Open")
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _move(self, step):
        r = self.list.currentRow()
        if r < 0 or not (0 <= r + step < self.list.count()):
            return
        it = self.list.takeItem(r)
        self.list.insertItem(r + step, it)
        self.list.setCurrentRow(r + step)

    def selected_files(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]
