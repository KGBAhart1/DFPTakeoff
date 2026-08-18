"""
DFP TakeoffPro - Defense Fire Protection
"""
import sys, os, csv, shutil
import fitz
from version import APP_NAME, APP_VERSION

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QDoubleSpinBox, QComboBox, QSpinBox,
    QScrollArea, QToolBar, QAction, QStatusBar, QAbstractItemView, QInputDialog,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QSlider, QMenu,
    QFrame, QProgressDialog, QShortcut, QSizePolicy, QCheckBox, QGroupBox, QLayout,
    QToolButton, QColorDialog, QTreeWidget, QTreeWidgetItem,
)
from PyQt5.QtGui  import QPixmap, QImage, QPainter, QPen, QColor, QFont, QKeySequence, QPolygonF
from PyQt5.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSize, QThread, pyqtSignal, QTimer

import db, excel_export, estimator

MARK_COLORS = [
    "#e74c3c","#2980b9","#27ae60","#8e44ad","#e67e22",
    "#16a085","#d35400","#1a5276","#196f3d","#6c3483",
    "#935116","#1b4f72","#0e6655","#4a235a","#784212",
]
CATEGORIES = [
    "Detectors","Notification","Control Panels","Modules",
    "Initiating Devices","Suppression","Exit/Emergency","Misc","General",
]

CANDELA_OPTIONS = [15, 30, 75, 110, 135, 177, 185]

# ── Coverage rules: ULC S524 + National Fire Code of Canada (NFC overrides S524) ──
# Radii = √(max_area / π).  NFC 2010 Table 2.5.4.1 / ULC S524 Cl. 6.5 & 6.7.
COVERAGE_RADII_M = {
    "smoke":        5.41,   # 92 m² max area, level smooth ceiling
    "heat":         3.85,   # 46.5 m² max area
    "notification": 4.30,   # ULC S525 15 cd strobe — 6.1 × 6.1 m room
    "beam":         7.50,   # Beam detector half-coverage default
}
COVERAGE_COLORS = {
    "smoke":        "#2980b9",   # blue
    "heat":         "#e74c3c",   # red
    "notification": "#e67e22",   # orange
    "beam":         "#8e44ad",   # purple
}
# Human-readable labels for the toolbar toggle buttons
COVERAGE_LABELS = {
    "smoke":        "Smoke",
    "heat":         "Heat",
    "notification": "Notification",
    "beam":         "Beam",
}
# PDF internal unit: 1 pt = 1/72 inch = 0.352778 mm
_PT_PER_METER = 1000.0 / 0.352778   # ≈ 2834.6  points per metre (at 1:1)


def _infer_coverage_type(product):
    """Derive coverage_type string from product name + category."""
    cat  = (product.get("category") or "").lower()
    name = (product.get("name") or "").lower()
    if cat == "detectors" or "detector" in name:
        if any(k in name for k in ("heat", "thermal", "rate-of-rise", "ror", "fixed")):
            return "heat"
        if "beam" in name:
            return "beam"
        return "smoke"
    if cat == "notification" or any(k in name for k in ("horn", "strobe", "sounder", "speaker")):
        return "notification"
    return ""


def _coverage_for_product(product):
    """Return (coverage_type, radius_m) for a product dict."""
    if product.get("coverage_radius_m", 0) > 0:
        ctype = product.get("coverage_type") or _infer_coverage_type(product)
        return ctype, float(product["coverage_radius_m"])
    ctype = _infer_coverage_type(product)
    return ctype, COVERAGE_RADII_M.get(ctype, 0.0)


def color_for_id(eid):
    return MARK_COLORS[int(eid) % len(MARK_COLORS)]


def _arrow_wings(fx, fy, tx, ty, size=10, spread_deg=25):
    """Given a line from (fx,fy) to (tx,ty), return the two wing-tip points
    of an arrowhead at (tx,ty) — pure geometry, coordinate-system agnostic
    (used both for the on-screen QPainter preview, scaled by zoom, and for
    the unscaled PDF export via fitz)."""
    import math
    dx, dy = tx - fx, ty - fy
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return None
    ux, uy = -dx / length, -dy / length   # unit vector pointing back along the line
    ang = math.radians(spread_deg)
    wings = []
    for sign in (1, -1):
        a = ang * sign
        wx = ux * math.cos(a) - uy * math.sin(a)
        wy = ux * math.sin(a) + uy * math.cos(a)
        wings.append((tx + wx * size, ty + wy * size))
    return wings


def _linear_mat_per_ft(assembly_id):
    """Return total material cost per foot for a linear assembly."""
    items = db.get_assembly_items(assembly_id)
    return sum((item["unit_cost"] or 0.0) * (item["quantity"] or 0.0) for item in items)


# 
# PDF Canvas
# 

class PdfCanvas(QLabel):
    clicked_point        = pyqtSignal(QPointF)
    pan_delta            = pyqtSignal(int, int)
    zoom_requested       = pyqtSignal(int, int, float)
    mark_deleted         = pyqtSignal(int, str, int)   # db_id, entity_type, entity_id
    mark_candela_changed = pyqtSignal(int, float)      # db_id, candela — set independently per placed device
    scale_measured       = pyqtSignal(QPointF, QPointF) # two page-coord points
    linear_run_completed = pyqtSignal(int, float, str)  # assembly_id, footage, points_json
    run_deleted          = pyqtSignal(int, int)         # run_id, assembly_id
    measurement_completed = pyqtSignal(str, float)      # "length"|"area", value (ft or sq ft)
    field_note_placed    = pyqtSignal(QPointF)          # click in note mode -> MainWindow opens style dialog
    field_line_completed = pyqtSignal(str)              # points_json -> MainWindow persists
    field_note_deleted   = pyqtSignal(int)              # db_id
    field_line_deleted   = pyqtSignal(int)              # db_id
    field_note_edit_requested = pyqtSignal(dict)        # note_dict -> MainWindow opens style dialog
    snip_rect_selected   = pyqtSignal(QRectF)           # page-coord rect -> MainWindow captures + names it

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_right_click)
        self.setFocusPolicy(Qt.StrongFocus)
        # Without this, mouseMoveEvent only fires while a button is held
        # down — meaning the dashed preview line for the wire-run/measure
        # tools never followed the cursor during a normal move-then-click
        # placement (no drag), only if you happened to drag between clicks.
        self.setMouseTracking(True)
        self._doc = None
        self._page_index = 0
        self._pdf_path = ""
        self._zoom = 1.5
        self._base_pixmap = None
        self._counting_mode = False
        self._pan_start = None
        self._pending_pt = None
        # {(pdf_path, page_index): [mark_dict, ...]}
        self._page_marks = {}
        self._mark_counter = 0
        self._highlight_rect = None  # QRectF in page coords (for verification)
        # Design-mode state
        self._design_mode    = False
        self._points_per_meter = 0.0  # page-unit (PDF pt) per real-world metre
        self._coverage_visible = {"smoke", "heat", "notification", "beam"}
        self._scale_mode     = False
        self._scale_pt1      = None   # first click in page coords
        # Linear drawing state
        self._linear_mode       = False
        self._linear_assembly_id = None
        self._linear_color      = "#ff7002"
        self._linear_points     = []   # list of QPointF in page coords
        self._linear_preview    = None # current snapped mouse position
        # {(pdf_path, page_index): [run_dict, ...]}
        self._page_runs = {}
        # Ad-hoc ruler/area tool state — a scratch measurement, not a saved
        # takeoff assembly. Cleared per-page, never written to the DB.
        self._measure_mode      = None   # None | "length" | "area"
        self._measure_points    = []     # list of QPointF in page coords
        self._measure_preview   = None
        # {(pdf_path, page_index): [{"type":"length"|"area","points":[...],"value":float}, ...]}
        self._page_measurements = {}
        # Field Notes markup layer — independent of device marks/counts, so
        # it can be shown/hidden and exported separately (see set_field_notes_visible).
        self._field_note_mode = False
        self._field_note_color = "#000000"
        self._field_note_bold  = False
        self._field_note_size  = 10.0
        # {(pdf_path, page_index): [note_dict, ...]}
        self._page_field_notes = {}
        self._field_line_mode  = False
        self._field_line_color = "#000000"
        self._field_line_width = 2.0
        self._field_line_points  = []
        self._field_line_preview = None
        # {(pdf_path, page_index): [line_dict, ...]}
        self._page_field_lines = {}
        self._field_notes_visible = True
        # Snip tool — one-shot drag-rectangle selection to crop a reference
        # image (e.g. a symbol legend) into its own floating window.
        self._snip_mode = False
        self._snip_start = None    # QPointF, page coords
        self._snip_preview = None  # QPointF, page coords

    #  Public API

    def load_page(self, doc, page_index, pdf_path=""):
        self._doc = doc
        self._page_index = page_index
        self._pdf_path = pdf_path
        self._highlight_rect = None
        self._render()

    def set_page(self, page_index):
        if self._doc and 0 <= page_index < len(self._doc):
            self._page_index = page_index
            self._highlight_rect = None
            self._render()

    def set_zoom(self, zoom):
        self._zoom = max(0.3, min(6.0, zoom))
        self._render()

    def get_zoom(self):
        return self._zoom

    def set_counting_mode(self, enabled):
        self._counting_mode = enabled
        self._update_cursor()

    def add_mark(self, page_x, page_y, entity_type, entity_id,
                 color, label, db_id=None, section_id=None, repaint=True,
                 coverage_type="", coverage_radius_m=0.0, candela=0.0):
        self._mark_counter += 1
        mark = dict(
            id=self._mark_counter, db_id=db_id,
            page_x=page_x, page_y=page_y,
            entity_type=entity_type, entity_id=entity_id,
            color=color, label=label, section_id=section_id,
            coverage_type=coverage_type, coverage_radius_m=coverage_radius_m,
            candela=candela,
        )
        key = (self._pdf_path, self._page_index)
        self._page_marks.setdefault(key, []).append(mark)
        if repaint:
            self._paint_overlay()
        return self._mark_counter

    def add_marks_batch(self, marks_data):
        """Add multiple marks and repaint once."""
        key = (self._pdf_path, self._page_index)
        for m in marks_data:
            self._mark_counter += 1
            self._page_marks.setdefault(key, []).append(dict(
                id=self._mark_counter, db_id=m.get("db_id"),
                page_x=m["page_x"], page_y=m["page_y"],
                entity_type=m["entity_type"], entity_id=m["entity_id"],
                color=m["color"], label=m["label"],
                section_id=m.get("section_id"),
                coverage_type=m.get("coverage_type", ""),
                coverage_radius_m=m.get("coverage_radius_m", 0.0),
                candela=m.get("candela", 0.0),
            ))
        self._paint_overlay()

    def load_saved_marks(self, marks_from_db):
        """Populate marks from DB rows (called on project open)."""
        self._page_marks.clear()
        for m in marks_from_db:
            key = (m["pdf_path"], m["page_index"])
            self._mark_counter += 1
            self._page_marks.setdefault(key, []).append(dict(
                id=self._mark_counter, db_id=m["id"],
                page_x=m["page_x"], page_y=m["page_y"],
                entity_type=m["entity_type"], entity_id=m["entity_id"],
                color=m["color"], label=m["label"],
                section_id=m["section_id"],
                coverage_type=m.get("coverage_type", ""),
                coverage_radius_m=m.get("coverage_radius_m", 0.0),
                candela=m.get("candela", 0.0) or 0.0,
            ))
        self._paint_overlay()

    def update_mark_candela(self, mark_id, candela):
        """mark_id here is the DB id (see _find_nearest_mark/_on_right_click),
        not the local per-session counter id."""
        for marks in self._page_marks.values():
            for m in marks:
                if m["db_id"] == mark_id:
                    m["candela"] = candela
        self._paint_overlay()

    def undo_last_mark(self):
        """Remove the most recently placed mark on the current page. Returns mark dict or None."""
        key = (self._pdf_path, self._page_index)
        marks = self._page_marks.get(key, [])
        if marks:
            removed = marks.pop()
            self._paint_overlay()
            return removed
        return None

    def clear_marks_current_page(self):
        self._page_marks.pop((self._pdf_path, self._page_index), None)
        self._paint_overlay()

    def set_highlight(self, page_rect):
        self._highlight_rect = page_rect
        self._paint_overlay()

    def clear_highlight(self):
        self._highlight_rect = None
        self._paint_overlay()

    # ── Design-mode API ───────────────────────────────────────────────────────

    def set_design_mode(self, enabled):
        self._design_mode = enabled
        self._paint_overlay()

    def set_page_scale(self, points_per_meter):
        self._points_per_meter = points_per_meter
        self._paint_overlay()

    def set_coverage_visible(self, ctype, visible):
        if visible:
            self._coverage_visible.add(ctype)
        else:
            self._coverage_visible.discard(ctype)
        self._paint_overlay()

    def set_scale_mode(self, enabled):
        self._scale_mode = enabled
        self._scale_pt1 = None
        self._update_cursor()
        self._paint_overlay()

    # ── Ad-hoc measure (ruler / area) tool API ──────────────────────────────────

    def set_measure_mode(self, mode):
        """mode: None to turn off, else 'length' or 'area'."""
        self._measure_mode = mode
        self._measure_points = []
        self._measure_preview = None
        self._update_cursor()
        self._paint_overlay()

    def clear_measurements_current_page(self):
        self._page_measurements.pop((self._pdf_path, self._page_index), None)
        self._paint_overlay()

    # ── Linear drawing API ────────────────────────────────────────────────────

    def set_linear_mode(self, enabled, assembly_id=None, color="#ff7002"):
        self._linear_mode = enabled
        self._linear_assembly_id = assembly_id
        self._linear_color = color
        self._linear_points = []
        self._linear_preview = None
        self._update_cursor()
        self._paint_overlay()

    def add_linear_run(self, run_dict, repaint=True):
        key = (run_dict["pdf_path"], run_dict["page_index"])
        self._page_runs.setdefault(key, []).append(run_dict)
        if repaint:
            self._paint_overlay()

    def load_saved_runs(self, runs_from_db):
        self._page_runs.clear()
        for r in runs_from_db:
            key = (r["pdf_path"], r["page_index"])
            self._page_runs.setdefault(key, []).append(dict(r))
        self._paint_overlay()

    def delete_run_by_id(self, run_id):
        for key in list(self._page_runs.keys()):
            self._page_runs[key] = [r for r in self._page_runs[key] if r["id"] != run_id]
        self._paint_overlay()

    def cancel_linear_draw(self):
        self._linear_points = []
        self._linear_preview = None
        self._paint_overlay()

    # ── Field Notes API ──────────────────────────────────────────────────────

    def set_field_note_mode(self, enabled, color="#000000", bold=False, font_size=10.0):
        self._field_note_mode = enabled
        self._field_note_color = color
        self._field_note_bold  = bold
        self._field_note_size  = font_size
        self._update_cursor()

    def add_field_note(self, page_x, page_y, text, color, bold, font_size, db_id=None, repaint=True):
        key = (self._pdf_path, self._page_index)
        self._page_field_notes.setdefault(key, []).append(dict(
            id=db_id, db_id=db_id, page_x=page_x, page_y=page_y,
            text=text, color=color, bold=bold, font_size=font_size,
        ))
        if repaint:
            self._paint_overlay()

    def load_saved_field_notes(self, notes_from_db):
        self._page_field_notes.clear()
        for n in notes_from_db:
            key = (n["pdf_path"], n["page_index"])
            self._page_field_notes.setdefault(key, []).append(dict(
                id=n["id"], db_id=n["id"], page_x=n["page_x"], page_y=n["page_y"],
                text=n["text"], color=n["color"], bold=bool(n["bold"]), font_size=n["font_size"],
            ))
        self._paint_overlay()

    def update_field_note_by_id(self, note_id, text, color, bold, font_size):
        for notes in self._page_field_notes.values():
            for n in notes:
                if n["db_id"] == note_id:
                    n["text"], n["color"], n["bold"], n["font_size"] = text, color, bold, font_size
        self._paint_overlay()

    def delete_field_note_by_id(self, note_id):
        for key in list(self._page_field_notes.keys()):
            self._page_field_notes[key] = [n for n in self._page_field_notes[key] if n["db_id"] != note_id]
        self._paint_overlay()

    def set_field_line_mode(self, enabled, color="#000000", width=2.0):
        self._field_line_mode  = enabled
        self._field_line_color = color
        self._field_line_width = width
        self._field_line_points  = []
        self._field_line_preview = None
        self._update_cursor()
        self._paint_overlay()

    def add_field_line(self, line_dict, repaint=True):
        key = (line_dict["pdf_path"], line_dict["page_index"])
        self._page_field_lines.setdefault(key, []).append(line_dict)
        if repaint:
            self._paint_overlay()

    def load_saved_field_lines(self, lines_from_db):
        self._page_field_lines.clear()
        for l in lines_from_db:
            key = (l["pdf_path"], l["page_index"])
            self._page_field_lines.setdefault(key, []).append(dict(l))
        self._paint_overlay()

    def delete_field_line_by_id(self, line_id):
        for key in list(self._page_field_lines.keys()):
            self._page_field_lines[key] = [l for l in self._page_field_lines[key] if l["id"] != line_id]
        self._paint_overlay()

    def cancel_field_line_draw(self):
        self._field_line_points = []
        self._field_line_preview = None
        self._paint_overlay()

    def set_field_notes_visible(self, visible):
        self._field_notes_visible = visible
        self._paint_overlay()

    def set_snip_mode(self, enabled):
        self._snip_mode = enabled
        self._snip_start = None
        self._snip_preview = None
        self._update_cursor()
        self._paint_overlay()

    #  Internal

    def _render(self):
        if not self._doc:
            return
        page = self._doc[self._page_index]
        mat  = fitz.Matrix(self._zoom, self._zoom)
        pix  = page.get_pixmap(matrix=mat, alpha=False)
        img  = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        self._base_pixmap = QPixmap.fromImage(img)
        self._paint_overlay()

    def _paint_overlay(self):
        if self._base_pixmap is None:
            return
        pm = self._base_pixmap.copy()
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._highlight_rect:
            r = self._highlight_rect
            painter.setPen(QPen(QColor("#e74c3c"), 3))
            painter.setBrush(QColor(231, 76, 60, 50))
            painter.drawRect(int(r.x()*self._zoom), int(r.y()*self._zoom),
                             int(r.width()*self._zoom), int(r.height()*self._zoom))

        marks = self._page_marks.get((self._pdf_path, self._page_index), [])

        # ── Coverage rings (drawn under device dots) ──────────────────────────
        if self._design_mode and self._points_per_meter > 0:
            for m in marks:
                r_m   = m.get("coverage_radius_m", 0.0)
                ctype = m.get("coverage_type", "")
                if r_m <= 0 or ctype not in self._coverage_visible:
                    continue
                cx   = int(m["page_x"] * self._zoom)
                cy   = int(m["page_y"] * self._zoom)
                r_px = int(r_m * self._points_per_meter * self._zoom)
                if r_px < 4:
                    continue
                base  = QColor(COVERAGE_COLORS.get(ctype, "#888888"))
                fill  = QColor(base); fill.setAlpha(22)
                border = QColor(base); border.setAlpha(180)
                pen = QPen(border, 2, Qt.CustomDashLine)
                pen.setDashPattern([8.0, 4.0])
                painter.setPen(pen)
                painter.setBrush(fill)
                painter.drawEllipse(cx - r_px, cy - r_px, r_px * 2, r_px * 2)

        # ── Scale measurement first-point indicator ───────────────────────────
        if self._scale_pt1 is not None:
            cx = int(self._scale_pt1.x() * self._zoom)
            cy = int(self._scale_pt1.y() * self._zoom)
            painter.setPen(QPen(QColor("#ff7002"), 3))
            painter.setBrush(QColor("#ff7002"))
            painter.drawEllipse(cx - 7, cy - 7, 14, 14)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(cx - 11, cy, cx + 11, cy)
            painter.drawLine(cx, cy - 11, cx, cy + 11)

        # ── Device marks ──────────────────────────────────────────────────────
        R = max(9, int(11 * self._zoom ** 0.25))
        font = QFont("Arial", max(6, R - 4), QFont.Bold)
        painter.setFont(font)
        for m in marks:
            cx = int(m["page_x"] * self._zoom)
            cy = int(m["page_y"] * self._zoom)
            base = QColor(m["color"])
            glow = QColor(base); glow.setAlpha(45)
            painter.setPen(Qt.NoPen); painter.setBrush(glow)
            painter.drawEllipse(cx-R-4, cy-R-4, (R+4)*2, (R+4)*2)
            fill = QColor(base); fill.setAlpha(185)
            painter.setBrush(fill)
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.drawEllipse(cx-R, cy-R, R*2, R*2)
            if m["label"]:
                painter.setPen(QPen(QColor("#ffffff")))
                painter.drawText(cx-R, cy-R, R*2, R*2, Qt.AlignCenter, m["label"])
            candela = m.get("candela", 0)
            if candela:
                cd_font = QFont("Arial", max(6, R - 5), QFont.Bold)
                painter.setFont(cd_font)
                cd_text = f"{candela:g}cd"
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(cd_text) + 4
                th = fm.height()
                tx, ty = cx + R + 2, cy - th // 2
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 0, 0, 160))
                painter.drawRect(tx, ty, tw, th)
                painter.setPen(QPen(QColor("#ffff00")))
                painter.drawText(tx, ty, tw, th, Qt.AlignCenter, cd_text)
                painter.setFont(font)

        # ── Completed linear runs ─────────────────────────────────────────────
        import json as _json, math as _math
        runs = self._page_runs.get((self._pdf_path, self._page_index), [])
        for run in runs:
            try:
                pts = _json.loads(run["points"])
            except Exception:
                continue
            if len(pts) < 2:
                continue
            color = QColor(run.get("color", "#ff7002"))
            pen = QPen(color, 3)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            for i in range(1, len(pts)):
                x1 = int(pts[i-1]["x"] * self._zoom)
                y1 = int(pts[i-1]["y"] * self._zoom)
                x2 = int(pts[i]["x"] * self._zoom)
                y2 = int(pts[i]["y"] * self._zoom)
                painter.drawLine(x1, y1, x2, y2)
            # Endpoint dots
            painter.setBrush(color)
            for pt in [pts[0], pts[-1]]:
                cx = int(pt["x"] * self._zoom)
                cy = int(pt["y"] * self._zoom)
                painter.drawEllipse(cx - 4, cy - 4, 8, 8)
            # Footage label at midpoint
            ft = run.get("footage", 0.0)
            mid = pts[len(pts) // 2]
            mx = int(mid["x"] * self._zoom)
            my = int(mid["y"] * self._zoom)
            painter.setPen(QPen(QColor("#ffffff")))
            painter.setBrush(QColor(0, 0, 0, 140))
            lbl = f"{ft:.1f} ft"
            fm = painter.fontMetrics()
            lw = fm.horizontalAdvance(lbl) + 6
            lh = fm.height() + 2
            painter.drawRect(mx - lw // 2, my - lh, lw, lh)
            painter.setPen(QPen(QColor("#ffffff")))
            painter.drawText(mx - lw // 2, my - lh, lw, lh, Qt.AlignCenter, lbl)

        # ── In-progress linear run preview ────────────────────────────────────
        if self._linear_mode and self._linear_points:
            draw_pts = self._linear_points[:]
            if self._linear_preview:
                draw_pts.append(self._linear_preview)
            pen = QPen(QColor(self._linear_color), 2, Qt.DashLine)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            for i in range(1, len(draw_pts)):
                x1 = int(draw_pts[i-1].x() * self._zoom)
                y1 = int(draw_pts[i-1].y() * self._zoom)
                x2 = int(draw_pts[i].x() * self._zoom)
                y2 = int(draw_pts[i].y() * self._zoom)
                painter.drawLine(x1, y1, x2, y2)
            painter.setPen(QPen(QColor(self._linear_color), 2))
            painter.setBrush(QColor(self._linear_color))
            for pt in self._linear_points:
                cx = int(pt.x() * self._zoom)
                cy = int(pt.y() * self._zoom)
                painter.drawEllipse(cx - 5, cy - 5, 10, 10)
            # Running footage label
            if self._points_per_meter > 0 and len(draw_pts) >= 2:
                total_ft = 0.0
                for i in range(1, len(draw_pts)):
                    dx = draw_pts[i].x() - draw_pts[i-1].x()
                    dy = draw_pts[i].y() - draw_pts[i-1].y()
                    total_ft += _math.sqrt(dx*dx + dy*dy) / self._points_per_meter * 3.28084
                last = draw_pts[-1]
                lx = int(last.x() * self._zoom) + 10
                ly = int(last.y() * self._zoom) - 10
                painter.setPen(QPen(QColor("#ffffff")))
                painter.setBrush(QColor(0, 0, 0, 160))
                lbl = f"{total_ft:.1f} ft"
                fm = painter.fontMetrics()
                lw = fm.horizontalAdvance(lbl) + 6
                lh = fm.height() + 2
                painter.drawRect(lx, ly - lh, lw, lh)
                painter.setPen(QPen(QColor("#ffff00")))
                painter.drawText(lx, ly - lh, lw, lh, Qt.AlignCenter, lbl)

        # ── Completed scratch measurements (ruler/area tool) ──────────────────
        MEASURE_COLOR = "#17a2b8"   # teal — visually distinct from takeoff-run orange
        measurements = self._page_measurements.get((self._pdf_path, self._page_index), [])
        for meas in measurements:
            pts = meas["points"]
            col = QColor(MEASURE_COLOR)
            if meas["type"] == "area" and len(pts) >= 3:
                poly = QPolygonF([QPointF(p.x()*self._zoom, p.y()*self._zoom) for p in pts])
                fill = QColor(col); fill.setAlpha(45)
                painter.setPen(QPen(col, 2))
                painter.setBrush(fill)
                painter.drawPolygon(poly)
                cx = sum(p.x() for p in pts) / len(pts) * self._zoom
                cy = sum(p.y() for p in pts) / len(pts) * self._zoom
                lbl = f'{meas["value"]:.1f} SF'
            else:
                pen = QPen(col, 2.5); pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(pen); painter.setBrush(Qt.NoBrush)
                for i in range(1, len(pts)):
                    painter.drawLine(int(pts[i-1].x()*self._zoom), int(pts[i-1].y()*self._zoom),
                                      int(pts[i].x()*self._zoom), int(pts[i].y()*self._zoom))
                painter.setBrush(col)
                for p in (pts[0], pts[-1]):
                    painter.drawEllipse(int(p.x()*self._zoom)-4, int(p.y()*self._zoom)-4, 8, 8)
                mid = pts[len(pts)//2]
                cx, cy = mid.x()*self._zoom, mid.y()*self._zoom
                lbl = f'{meas["value"]:.1f} ft'
            painter.setPen(QPen(QColor("#ffffff")))
            painter.setBrush(QColor(0, 0, 0, 150))
            fm = painter.fontMetrics()
            lw = fm.horizontalAdvance(lbl) + 6; lh = fm.height() + 2
            painter.drawRect(int(cx-lw/2), int(cy-lh/2), lw, lh)
            painter.setPen(QPen(col))
            painter.drawText(int(cx-lw/2), int(cy-lh/2), lw, lh, Qt.AlignCenter, lbl)

        # ── In-progress measurement preview ───────────────────────────────────
        if self._measure_mode and self._measure_points:
            draw_pts = self._measure_points[:]
            if self._measure_preview:
                draw_pts.append(self._measure_preview)
            col = QColor(MEASURE_COLOR)
            pen = QPen(col, 2, Qt.DashLine); pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen); painter.setBrush(Qt.NoBrush)
            for i in range(1, len(draw_pts)):
                painter.drawLine(int(draw_pts[i-1].x()*self._zoom), int(draw_pts[i-1].y()*self._zoom),
                                  int(draw_pts[i].x()*self._zoom), int(draw_pts[i].y()*self._zoom))
            if self._measure_mode == "area" and len(draw_pts) >= 2:
                # Dashed closing edge back to the start, so it's clear where
                # clicking near the first point will close the polygon.
                first, last = draw_pts[0], draw_pts[-1]
                painter.drawLine(int(last.x()*self._zoom), int(last.y()*self._zoom),
                                  int(first.x()*self._zoom), int(first.y()*self._zoom))
            painter.setPen(QPen(col, 2)); painter.setBrush(col)
            for pt in self._measure_points:
                painter.drawEllipse(int(pt.x()*self._zoom)-5, int(pt.y()*self._zoom)-5, 10, 10)
            # Start-point highlight for area mode, so the closing target is obvious
            if self._measure_mode == "area" and self._measure_points:
                sp = self._measure_points[0]
                painter.setPen(QPen(QColor("#ffff00"), 2)); painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(int(sp.x()*self._zoom)-9, int(sp.y()*self._zoom)-9, 18, 18)
            if self._points_per_meter > 0 and len(draw_pts) >= 2:
                m_per_pt = 1.0 / self._points_per_meter
                if self._measure_mode == "length":
                    total_ft = 0.0
                    for i in range(1, len(draw_pts)):
                        dx = draw_pts[i].x()-draw_pts[i-1].x(); dy = draw_pts[i].y()-draw_pts[i-1].y()
                        total_ft += _math.sqrt(dx*dx+dy*dy) * m_per_pt * 3.28084
                    lbl = f"{total_ft:.1f} ft"
                elif len(draw_pts) >= 3:
                    n = len(draw_pts)
                    shoelace = 0.0
                    for i in range(n):
                        x1, y1 = draw_pts[i].x(), draw_pts[i].y()
                        x2, y2 = draw_pts[(i+1) % n].x(), draw_pts[(i+1) % n].y()
                        shoelace += x1*y2 - x2*y1
                    area_m2 = (abs(shoelace)/2.0) * (m_per_pt ** 2)
                    lbl = f"{area_m2*10.7639:.1f} SF"
                else:
                    lbl = None
                if lbl:
                    last = draw_pts[-1]
                    lx = int(last.x()*self._zoom) + 10; ly = int(last.y()*self._zoom) - 10
                    painter.setPen(QPen(QColor("#ffffff")))
                    painter.setBrush(QColor(0, 0, 0, 160))
                    fm = painter.fontMetrics()
                    lw = fm.horizontalAdvance(lbl) + 6; lh = fm.height() + 2
                    painter.drawRect(lx, ly - lh, lw, lh)
                    painter.setPen(QPen(QColor("#ffff00")))
                    painter.drawText(lx, ly - lh, lw, lh, Qt.AlignCenter, lbl)

        # ── Field Notes markup layer (independent of counts) ───────────────────
        if self._field_notes_visible:
            lines = self._page_field_lines.get((self._pdf_path, self._page_index), [])
            for ln in lines:
                try:
                    pts = _json.loads(ln["points"])
                except Exception:
                    continue
                if len(pts) < 2:
                    continue
                color = QColor(ln.get("color", "#000000"))
                pen = QPen(color, ln.get("width", 2.0))
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                for i in range(1, len(pts)):
                    painter.drawLine(int(pts[i-1]["x"]*self._zoom), int(pts[i-1]["y"]*self._zoom),
                                     int(pts[i]["x"]*self._zoom), int(pts[i]["y"]*self._zoom))
                # Arrowhead at the final point — trace lines point FROM the
                # note TO whatever they're calling out.
                wings = _arrow_wings(pts[-2]["x"]*self._zoom, pts[-2]["y"]*self._zoom,
                                     pts[-1]["x"]*self._zoom, pts[-1]["y"]*self._zoom,
                                     size=10 + ln.get("width", 2.0))
                if wings:
                    tx, ty = pts[-1]["x"]*self._zoom, pts[-1]["y"]*self._zoom
                    for wx, wy in wings:
                        painter.drawLine(int(tx), int(ty), int(wx), int(wy))

            if self._field_line_mode and self._field_line_points:
                draw_pts = self._field_line_points[:]
                if self._field_line_preview:
                    draw_pts.append(self._field_line_preview)
                pen = QPen(QColor(self._field_line_color), self._field_line_width, Qt.DashLine)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                for i in range(1, len(draw_pts)):
                    painter.drawLine(int(draw_pts[i-1].x()*self._zoom), int(draw_pts[i-1].y()*self._zoom),
                                     int(draw_pts[i].x()*self._zoom), int(draw_pts[i].y()*self._zoom))
                if len(draw_pts) >= 2:
                    wings = _arrow_wings(draw_pts[-2].x()*self._zoom, draw_pts[-2].y()*self._zoom,
                                         draw_pts[-1].x()*self._zoom, draw_pts[-1].y()*self._zoom,
                                         size=10 + self._field_line_width)
                    if wings:
                        tx, ty = draw_pts[-1].x()*self._zoom, draw_pts[-1].y()*self._zoom
                        for wx, wy in wings:
                            painter.drawLine(int(tx), int(ty), int(wx), int(wy))
                painter.setPen(QPen(QColor(self._field_line_color), 2))
                painter.setBrush(QColor(self._field_line_color))
                for pt in self._field_line_points:
                    cx = int(pt.x() * self._zoom)
                    cy = int(pt.y() * self._zoom)
                    painter.drawEllipse(cx - 4, cy - 4, 8, 8)

            notes = self._page_field_notes.get((self._pdf_path, self._page_index), [])
            for n in notes:
                note_color = QColor(n.get("color", "#000000"))
                cx = int(n["page_x"]*self._zoom)
                cy = int(n["page_y"]*self._zoom)
                fsize = max(6, int(n.get("font_size", 10.0) * max(self._zoom, 0.5)))
                f = QFont("Arial", fsize)
                f.setBold(bool(n.get("bold")))
                painter.setFont(f)
                fm = painter.fontMetrics()
                pad = 4
                tw = fm.horizontalAdvance(n["text"]) + pad * 2
                th = fm.height() + pad * 2
                ex, ey = cx - tw // 2, cy - th // 2
                painter.setPen(QPen(note_color, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(ex, ey, tw, th)
                painter.setPen(QPen(note_color))
                painter.drawText(ex, ey, tw, th, Qt.AlignCenter, n["text"])

        # ── In-progress snip selection rectangle ────────────────────────────────
        if self._snip_mode and self._snip_start is not None and self._snip_preview is not None:
            x1, y1 = self._snip_start.x()*self._zoom, self._snip_start.y()*self._zoom
            x2, y2 = self._snip_preview.x()*self._zoom, self._snip_preview.y()*self._zoom
            rx, ry = min(x1, x2), min(y1, y2)
            rw, rh = abs(x2-x1), abs(y2-y1)
            painter.setPen(QPen(QColor("#ff7002"), 2, Qt.DashLine))
            painter.setBrush(QColor(255, 112, 2, 35))
            painter.drawRect(int(rx), int(ry), int(rw), int(rh))

        painter.end()
        self.setPixmap(pm)
        self.resize(pm.size())

    def _canvas_to_page(self, pt):
        return QPointF(pt.x() / self._zoom, pt.y() / self._zoom)

    def _update_cursor(self):
        if self._pan_start is not None:
            self.setCursor(Qt.ClosedHandCursor)
        elif (self._scale_mode or self._counting_mode or self._linear_mode or self._measure_mode
              or self._field_note_mode or self._field_line_mode or self._snip_mode):
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def _snap_linear(self, last, pt, modifiers):
        """Return H/V snapped point; Shift = free diagonal."""
        from PyQt5.QtCore import Qt as _Qt
        if modifiers & _Qt.ShiftModifier:
            return pt
        dx = pt.x() - last.x()
        dy = pt.y() - last.y()
        if abs(dx) >= abs(dy):
            return QPointF(pt.x(), last.y())
        return QPointF(last.x(), pt.y())

    def _finish_linear_run(self):
        import json as _json, math as _math
        pts = self._linear_points
        footage = 0.0
        if self._points_per_meter > 0:
            for i in range(1, len(pts)):
                dx = pts[i].x() - pts[i-1].x()
                dy = pts[i].y() - pts[i-1].y()
                footage += _math.sqrt(dx*dx + dy*dy) / self._points_per_meter * 3.28084
        points_data = [{"x": p.x(), "y": p.y()} for p in pts]
        points_json = _json.dumps(points_data)
        aid = self._linear_assembly_id
        self._linear_points = []
        self._linear_preview = None
        self._paint_overlay()
        self.linear_run_completed.emit(aid, footage, points_json)

    def _finish_field_line(self):
        import json as _json
        pts = self._field_line_points
        points_data = [{"x": p.x(), "y": p.y()} for p in pts]
        points_json = _json.dumps(points_data)
        self._field_line_points = []
        self._field_line_preview = None
        self._paint_overlay()
        self.field_line_completed.emit(points_json)

    def _finish_measurement(self):
        """Compute the scratch length/area measurement and keep it drawn on
        the page (not saved to the DB — this is a ruler/area tool, not a
        takeoff assembly). Requires a scale to already be set."""
        import math as _math
        pts = self._measure_points
        mode = self._measure_mode
        if self._points_per_meter <= 0:
            self._measure_points = []; self._measure_preview = None
            self._paint_overlay()
            return
        m_per_pt = 1.0 / self._points_per_meter
        if mode == "length":
            if len(pts) < 2:
                self._measure_points = []; self._measure_preview = None
                self._paint_overlay(); return
            total_ft = 0.0
            for i in range(1, len(pts)):
                dx = pts[i].x()-pts[i-1].x(); dy = pts[i].y()-pts[i-1].y()
                total_ft += _math.sqrt(dx*dx+dy*dy) * m_per_pt * 3.28084
            value = total_ft
        else:  # "area"
            if len(pts) < 3:
                self._measure_points = []; self._measure_preview = None
                self._paint_overlay(); return
            n = len(pts)
            shoelace = 0.0
            for i in range(n):
                x1, y1 = pts[i].x(), pts[i].y()
                x2, y2 = pts[(i+1) % n].x(), pts[(i+1) % n].y()
                shoelace += x1*y2 - x2*y1
            area_pt2 = abs(shoelace) / 2.0
            area_m2 = area_pt2 * (m_per_pt ** 2)
            value = area_m2 * 10.7639   # sq ft per sq m
        key = (self._pdf_path, self._page_index)
        self._page_measurements.setdefault(key, []).append(
            {"type": mode, "points": list(pts), "value": value})
        self._measure_points = []
        self._measure_preview = None
        self._paint_overlay()
        self.measurement_completed.emit(mode, value)

    def _find_nearest_run(self, canvas_pos, threshold=12):
        import math as _math
        runs = self._page_runs.get((self._pdf_path, self._page_index), [])
        import json as _json
        best, best_dist = None, threshold
        cx, cy = canvas_pos.x(), canvas_pos.y()
        for run in runs:
            try:
                pts = _json.loads(run["points"])
            except Exception:
                continue
            for i in range(1, len(pts)):
                x1 = pts[i-1]["x"] * self._zoom
                y1 = pts[i-1]["y"] * self._zoom
                x2 = pts[i]["x"]   * self._zoom
                y2 = pts[i]["y"]   * self._zoom
                # Distance from point to segment
                dx, dy = x2 - x1, y2 - y1
                seg_len = _math.sqrt(dx*dx + dy*dy)
                if seg_len < 1:
                    continue
                t = max(0, min(1, ((cx-x1)*dx + (cy-y1)*dy) / (seg_len*seg_len)))
                px, py = x1 + t*dx, y1 + t*dy
                d = _math.sqrt((cx-px)**2 + (cy-py)**2)
                if d < best_dist:
                    best_dist, best = d, run
        return best

    def _find_nearest_mark(self, canvas_pos, threshold=20):
        marks = self._page_marks.get((self._pdf_path, self._page_index), [])
        best, best_dist = None, threshold
        for m in marks:
            dx = canvas_pos.x() - m["page_x"] * self._zoom
            dy = canvas_pos.y() - m["page_y"] * self._zoom
            d = (dx*dx + dy*dy) ** 0.5
            if d < best_dist:
                best_dist, best = d, m
        return best

    def _find_nearest_field_note(self, canvas_pos, threshold=20):
        notes = self._page_field_notes.get((self._pdf_path, self._page_index), [])
        best, best_dist = None, threshold
        for n in notes:
            dx = canvas_pos.x() - n["page_x"] * self._zoom
            dy = canvas_pos.y() - n["page_y"] * self._zoom
            d = (dx*dx + dy*dy) ** 0.5
            if d < best_dist:
                best_dist, best = d, n
        return best

    def _find_nearest_field_line(self, canvas_pos, threshold=12):
        import math as _math, json as _json
        lines = self._page_field_lines.get((self._pdf_path, self._page_index), [])
        best, best_dist = None, threshold
        cx, cy = canvas_pos.x(), canvas_pos.y()
        for ln in lines:
            try:
                pts = _json.loads(ln["points"])
            except Exception:
                continue
            for i in range(1, len(pts)):
                x1 = pts[i-1]["x"] * self._zoom
                y1 = pts[i-1]["y"] * self._zoom
                x2 = pts[i]["x"]   * self._zoom
                y2 = pts[i]["y"]   * self._zoom
                dx, dy = x2 - x1, y2 - y1
                seg_len = _math.sqrt(dx*dx + dy*dy)
                if seg_len < 1:
                    continue
                t = max(0, min(1, ((cx-x1)*dx + (cy-y1)*dy) / (seg_len*seg_len)))
                px, py = x1 + t*dx, y1 + t*dy
                d = _math.sqrt((cx-px)**2 + (cy-py)**2)
                if d < best_dist:
                    best_dist, best = d, ln
        return best

    #  Mouse events

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.modifiers() & Qt.ControlModifier:
                self._pan_start = event.globalPos()
                self._update_cursor()
            elif self._scale_mode:
                page_pt = self._canvas_to_page(event.pos())
                if self._scale_pt1 is None:
                    self._scale_pt1 = page_pt
                    self._paint_overlay()
                else:
                    pt1 = self._scale_pt1
                    self._scale_pt1 = None
                    self._scale_mode = False
                    self._update_cursor()
                    self.scale_measured.emit(pt1, page_pt)
            elif self._linear_mode:
                page_pt = self._canvas_to_page(event.pos())
                if self._linear_points:
                    page_pt = self._snap_linear(self._linear_points[-1], page_pt, event.modifiers())
                self._linear_points.append(page_pt)
                self._linear_preview = None
                self._paint_overlay()
            elif self._measure_mode:
                page_pt = self._canvas_to_page(event.pos())
                if self._measure_points:
                    page_pt = self._snap_linear(self._measure_points[-1], page_pt, event.modifiers())
                # Area mode: clicking back near the start point closes the
                # polygon and finishes the measurement (needs >= 3 points).
                if (self._measure_mode == "area" and len(self._measure_points) >= 3):
                    first = self._measure_points[0]
                    dx = (page_pt.x()-first.x())*self._zoom
                    dy = (page_pt.y()-first.y())*self._zoom
                    if (dx*dx+dy*dy) ** 0.5 <= 12:
                        self._finish_measurement()
                        return
                self._measure_points.append(page_pt)
                self._measure_preview = None
                self._paint_overlay()
            elif self._field_line_mode:
                # Free placement — no H/V grid snap, unlike the takeoff
                # linear-run tool. Trace lines are meant to be pointed
                # freely at whatever the note is calling out.
                page_pt = self._canvas_to_page(event.pos())
                self._field_line_points.append(page_pt)
                self._field_line_preview = None
                self._paint_overlay()
            elif self._field_note_mode:
                page_pt = self._canvas_to_page(event.pos())
                self.field_note_placed.emit(page_pt)
            elif self._snip_mode:
                self._snip_start = self._canvas_to_page(event.pos())
                self._snip_preview = self._snip_start
                self._paint_overlay()
            elif self._counting_mode:
                page_pt = self._canvas_to_page(event.pos())
                near = self._find_nearest_mark(event.pos(), threshold=18)
                if near:
                    self._pending_pt = page_pt
                    QTimer.singleShot(0, self._ask_duplicate)
                    return
                self.clicked_point.emit(page_pt)

    def _ask_duplicate(self):
        pt = self._pending_pt
        self._pending_pt = None
        if pt is None: return
        result = QMessageBox.question(
            self.window(), "Already Marked",
            "There is already a mark near here.\nCount anyway?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if result == QMessageBox.Yes:
            self.clicked_point.emit(pt)

    def mouseDoubleClickEvent(self, event):
        if self._linear_mode and event.button() == Qt.LeftButton:
            # The single-click that fired before this double-click already added the final point.
            # Just finish if we have at least 2 points (start + at least one end point).
            if len(self._linear_points) >= 2:
                self._finish_linear_run()
        elif self._measure_mode == "length" and event.button() == Qt.LeftButton:
            if len(self._measure_points) >= 2:
                self._finish_measurement()
        elif self._field_line_mode and event.button() == Qt.LeftButton:
            if len(self._field_line_points) >= 2:
                self._finish_field_line()

    def mouseMoveEvent(self, event):
        if self._pan_start and (event.buttons() & Qt.LeftButton):
            delta = event.globalPos() - self._pan_start
            self._pan_start = event.globalPos()
            self.pan_delta.emit(-delta.x(), -delta.y())
        elif self._linear_mode and self._linear_points:
            page_pt = self._canvas_to_page(event.pos())
            self._linear_preview = self._snap_linear(self._linear_points[-1], page_pt, event.modifiers())
            self._paint_overlay()
        elif self._measure_mode and self._measure_points:
            page_pt = self._canvas_to_page(event.pos())
            self._measure_preview = self._snap_linear(self._measure_points[-1], page_pt, event.modifiers())
            self._paint_overlay()
        elif self._field_line_mode and self._field_line_points:
            self._field_line_preview = self._canvas_to_page(event.pos())
            self._paint_overlay()
        elif self._snip_mode and self._snip_start is not None:
            self._snip_preview = self._canvas_to_page(event.pos())
            self._paint_overlay()

    def keyPressEvent(self, event):
        if self._linear_mode and event.key() == Qt.Key_Escape:
            self._linear_points = []
            self._linear_preview = None
            self._paint_overlay()
        elif self._measure_mode and event.key() == Qt.Key_Escape:
            self._measure_points = []
            self._measure_preview = None
            self._paint_overlay()
        elif self._field_line_mode and event.key() == Qt.Key_Escape:
            self._field_line_points = []
            self._field_line_preview = None
            self._paint_overlay()
        elif self._snip_mode and event.key() == Qt.Key_Escape:
            self._snip_start = None
            self._snip_preview = None
            self._paint_overlay()
        elif (self._measure_mode == "area" and event.key() in (Qt.Key_Return, Qt.Key_Enter)
              and len(self._measure_points) >= 3):
            self._finish_measurement()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pan_start:
            self._pan_start = None
            self._update_cursor()
        elif event.button() == Qt.LeftButton and self._snip_mode and self._snip_start is not None:
            start = self._snip_start
            end = self._canvas_to_page(event.pos())
            self._snip_start = None
            self._snip_preview = None
            rect = QRectF(min(start.x(), end.x()), min(start.y(), end.y()),
                          abs(end.x() - start.x()), abs(end.y() - start.y()))
            # Snip is a one-shot tool — auto-exit after a selection so the
            # user isn't left mid-drag-mode for their next click on the canvas.
            self._snip_mode = False
            self._update_cursor()
            self._paint_overlay()
            if rect.width() > 4 and rect.height() > 4:
                self.snip_rect_selected.emit(rect)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
            self.zoom_requested.emit(event.pos().x(), event.pos().y(), factor)
        else:
            super().wheelEvent(event)

    def _on_right_click(self, pos):
        if self._linear_mode and self._linear_points:
            # Cancel current in-progress run
            self._linear_points = []
            self._linear_preview = None
            self._paint_overlay()
            return
        if self._measure_mode and self._measure_points:
            # Cancel current in-progress measurement
            self._measure_points = []
            self._measure_preview = None
            self._paint_overlay()
            return
        if self._field_line_mode and self._field_line_points:
            # Cancel current in-progress trace line
            self._field_line_points = []
            self._field_line_preview = None
            self._paint_overlay()
            return
        menu = QMenu(self)
        mark = self._find_nearest_mark(pos)
        run  = self._find_nearest_run(pos)
        note = self._find_nearest_field_note(pos)
        line = self._find_nearest_field_line(pos)
        cd = mark.get("candela", 0) if mark else 0
        candela_label = f"Set Candela…  ({cd:g} cd)" if cd else "Set Candela…"
        candela_act  = menu.addAction(candela_label) if mark else None
        del_mark_act = menu.addAction(f"Delete mark  ({mark['label']})") if mark else None
        del_run_act  = menu.addAction(f"Delete run  ({run.get('footage', 0):.1f} ft)") if run else None
        edit_note_act = menu.addAction(f"Edit note…  ({note['text'][:20]})") if note else None
        del_note_act  = menu.addAction("Delete note") if note else None
        del_line_act  = menu.addAction("Delete trace line") if line else None
        if not mark and not run and not note and not line:
            return
        chosen = menu.exec_(self.mapToGlobal(pos))
        if chosen and chosen == candela_act and mark:
            from PyQt5.QtWidgets import QInputDialog
            options = ["N/A"] + [f"{cd} cd" for cd in CANDELA_OPTIONS]
            current = mark.get("candela", 0) or 0
            cur_idx = (CANDELA_OPTIONS.index(int(current)) + 1) if int(current) in CANDELA_OPTIONS else 0
            choice, ok = QInputDialog.getItem(
                self.window(), "Set Candela", "Candela rating for this device:",
                options, cur_idx, editable=False)
            if ok:
                new_cd = 0 if choice == "N/A" else int(choice.split()[0])
                mark["candela"] = new_cd
                self._paint_overlay()
                self.mark_candela_changed.emit(mark["db_id"] or 0, new_cd)
        elif chosen and chosen == del_mark_act and mark:
            key = (self._pdf_path, self._page_index)
            self._page_marks[key] = [m for m in self._page_marks.get(key, [])
                                     if m["id"] != mark["id"]]
            self._paint_overlay()
            self.mark_deleted.emit(mark["db_id"] or 0, mark["entity_type"], mark["entity_id"])
        elif chosen and chosen == del_run_act and run:
            key = (self._pdf_path, self._page_index)
            self._page_runs[key] = [r for r in self._page_runs.get(key, [])
                                    if r["id"] != run["id"]]
            self._paint_overlay()
            self.run_deleted.emit(run["id"], run["assembly_id"])
        elif chosen and chosen == edit_note_act and note:
            self.field_note_edit_requested.emit(note)
        elif chosen and chosen == del_note_act and note:
            key = (self._pdf_path, self._page_index)
            self._page_field_notes[key] = [n for n in self._page_field_notes.get(key, [])
                                           if n["id"] != note["id"]]
            self._paint_overlay()
            self.field_note_deleted.emit(note["db_id"] or 0)
        elif chosen and chosen == del_line_act and line:
            key = (self._pdf_path, self._page_index)
            self._page_field_lines[key] = [l for l in self._page_field_lines.get(key, [])
                                           if l["id"] != line["id"]]
            self._paint_overlay()
            self.field_line_deleted.emit(line["id"])


# 
# Labour Unit Manager dialog
#

class LabourUnitManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Labour Unit Manager")
        self.resize(780, 500)
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.tbl = QTableWidget()
        self.tbl.setColumnCount(6)
        self.tbl.setHorizontalHeaderLabels(["ID","Category","Name","LU Reg (hrs)","LU Diff (hrs)","LU Hard (hrs)"])
        self.tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl.setColumnWidth(0, 40)
        self.tbl.setColumnHidden(0, True)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.tbl)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add")
        add_btn.setStyleSheet("background:#232728;color:white;padding:6px 14px;")
        add_btn.clicked.connect(self._add)
        del_btn = QPushButton("Delete Selected")
        del_btn.setStyleSheet("background:#c02b0a;color:white;padding:6px 14px;")
        del_btn.clicked.connect(self._delete)
        save_btn = QPushButton("Save Changes")
        save_btn.setStyleSheet("background:#ff7002;color:white;padding:6px 14px;font-weight:bold;")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(add_btn); btn_row.addWidget(del_btn)
        btn_row.addStretch(); btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _load(self):
        rows = db.get_labour_units()
        self.tbl.setRowCount(0)
        for r in rows:
            i = self.tbl.rowCount(); self.tbl.insertRow(i)
            self.tbl.setItem(i, 0, QTableWidgetItem(str(r["id"])))
            self.tbl.setItem(i, 1, QTableWidgetItem(r["category"]))
            self.tbl.setItem(i, 2, QTableWidgetItem(r["name"]))
            for col, key in [(3,"lu_reg"),(4,"lu_diff"),(5,"lu_hard")]:
                sp = QDoubleSpinBox(); sp.setDecimals(3); sp.setRange(0,999); sp.setSingleStep(0.1)
                sp.setSuffix(" hrs"); sp.setValue(r[key] or 0)
                self.tbl.setCellWidget(i, col, sp)

    def _add(self):
        i = self.tbl.rowCount(); self.tbl.insertRow(i)
        self.tbl.setItem(i, 0, QTableWidgetItem(""))
        self.tbl.setItem(i, 1, QTableWidgetItem("General"))
        self.tbl.setItem(i, 2, QTableWidgetItem("New Labour Unit"))
        for col in (3, 4, 5):
            sp = QDoubleSpinBox(); sp.setDecimals(3); sp.setRange(0,999); sp.setSingleStep(0.1)
            sp.setSuffix(" hrs")
            self.tbl.setCellWidget(i, col, sp)
        self.tbl.scrollToBottom()
        self.tbl.editItem(self.tbl.item(i, 2))

    def _delete(self):
        row = self.tbl.currentRow()
        if row < 0: return
        name = self.tbl.item(row, 2).text() if self.tbl.item(row, 2) else "this item"
        if QMessageBox.question(self, "Delete", f"Delete '{name}'?\nProducts using it will fall back to their custom LU values.",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        lu_id_item = self.tbl.item(row, 0)
        if lu_id_item and lu_id_item.text():
            db.delete_labour_unit(int(lu_id_item.text()))
        self.tbl.removeRow(row)

    def _save(self):
        for i in range(self.tbl.rowCount()):
            lu_id_item = self.tbl.item(i, 0)
            cat  = self.tbl.item(i, 1).text().strip() if self.tbl.item(i, 1) else "General"
            name = self.tbl.item(i, 2).text().strip() if self.tbl.item(i, 2) else ""
            if not name: continue
            lr = self.tbl.cellWidget(i,3).value() if self.tbl.cellWidget(i,3) else 0
            ld = self.tbl.cellWidget(i,4).value() if self.tbl.cellWidget(i,4) else 0
            lh = self.tbl.cellWidget(i,5).value() if self.tbl.cellWidget(i,5) else 0
            if lu_id_item and lu_id_item.text():
                db.update_labour_unit(int(lu_id_item.text()), name, cat, lr, ld, lh)
            else:
                new_id = db.add_labour_unit(name, cat, lr, ld, lh)
                lu_id_item and lu_id_item.setText(str(new_id))
        QMessageBox.information(self, "Saved", "Labour units saved.")
        self._load()


# Product dialog
#

class ProductDialog(QDialog):
    def __init__(self, parent=None, product=None):
        super().__init__(parent)
        self.setWindowTitle("Add Product" if product is None else "Edit Product")
        self.setMinimumWidth(420)
        self.setMinimumHeight(580)
        self._build_ui()
        if product:
            self._load(product)

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10); layout.setContentsMargins(16,16,16,16)
        self.name_edit = QLineEdit()
        self.code_edit = QLineEdit()
        self.cost_spin = QDoubleSpinBox()
        self.cost_spin.setRange(0,999999); self.cost_spin.setDecimals(2); self.cost_spin.setPrefix("$")
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(sorted(set(CATEGORIES) | set(db.get_distinct_categories())))
        self.cat_combo.setEditable(True)
        self.subcat_combo = QComboBox()
        self.subcat_combo.addItems(db.get_distinct_subcategories())
        self.subcat_combo.setEditable(True)
        self.subcat_combo.lineEdit().setPlaceholderText("Optional — a further sort within Category")
        self.candela_combo = QComboBox()
        self.candela_combo.addItem("N/A", 0)
        for cd in CANDELA_OPTIONS:
            self.candela_combo.addItem(f"{cd} cd", cd)
        self.candela_combo.setCurrentIndex(self.candela_combo.findData(15))  # overridden by _load() when editing
        self.candela_combo.setToolTip(
            "For strobes/horn strobes — just a default that pre-fills when you place\n"
            "a new one on the print. Each placed device's candela is independent and\n"
            "can be changed on its own afterward (right-click the mark -> Set Candela…).")
        dr = QHBoxLayout()
        self.drawing_edit = QLineEdit(); self.drawing_edit.setPlaceholderText("No drawing attached"); self.drawing_edit.setReadOnly(True)
        browse = QPushButton("Browse"); browse.setFixedWidth(72); browse.clicked.connect(self._browse)
        clear  = QPushButton("Clear");  clear.setFixedWidth(52);  clear.clicked.connect(lambda: self.drawing_edit.setText(""))
        dr.addWidget(self.drawing_edit); dr.addWidget(browse); dr.addWidget(clear)

        # Product image row
        img_row = QHBoxLayout()
        self.img_preview = QLabel()
        self.img_preview.setFixedSize(64, 64)
        self.img_preview.setStyleSheet("border:1px solid #ccc; background:#f9f9f9;")
        self.img_preview.setAlignment(Qt.AlignCenter)
        self.img_edit = QLineEdit(); self.img_edit.setPlaceholderText("No image"); self.img_edit.setReadOnly(True)
        img_browse = QPushButton("Browse"); img_browse.setFixedWidth(72); img_browse.clicked.connect(self._browse_img)
        img_clear  = QPushButton("Clear");   img_clear.setFixedWidth(52);  img_clear.clicked.connect(self._clear_img)
        img_row.addWidget(self.img_preview)
        sub = QVBoxLayout(); sub.addWidget(self.img_edit); sub.addWidget(img_browse); sub.addWidget(img_clear)
        img_row.addLayout(sub)

        # Labour units
        self._lu_rows = []  # list of (id, display_name) populated in _build_lu_widgets
        self.lu_reg_spin  = QDoubleSpinBox(); self.lu_reg_spin.setRange(0,999); self.lu_reg_spin.setDecimals(3); self.lu_reg_spin.setSingleStep(0.1); self.lu_reg_spin.setSuffix(" hrs")
        self.lu_diff_spin = QDoubleSpinBox(); self.lu_diff_spin.setRange(0,999); self.lu_diff_spin.setDecimals(3); self.lu_diff_spin.setSingleStep(0.1); self.lu_diff_spin.setSuffix(" hrs")
        self.lu_hard_spin = QDoubleSpinBox(); self.lu_hard_spin.setRange(0,999); self.lu_hard_spin.setDecimals(3); self.lu_hard_spin.setSingleStep(0.1); self.lu_hard_spin.setSuffix(" hrs")

        self.lu_combo = QComboBox()
        self._refresh_lu_combo()
        self.lu_combo.currentIndexChanged.connect(self._on_lu_combo_change)

        from PyQt5.QtWidgets import QWidget as _W
        self._lu_custom_widget = _W()
        _cf = QFormLayout(self._lu_custom_widget); _cf.setContentsMargins(0,0,0,0)
        _cf.addRow("LU – Regular",   self.lu_reg_spin)
        _cf.addRow("LU – Difficult", self.lu_diff_spin)
        _cf.addRow("LU – Hard",      self.lu_hard_spin)

        layout.addRow("Product Name *", self.name_edit)
        layout.addRow("Code / Part #",  self.code_edit)
        layout.addRow("Unit Cost",       self.cost_spin)
        layout.addRow("Category",        self.cat_combo)
        layout.addRow("Subcategory",     self.subcat_combo)
        layout.addRow("Default Candela", self.candela_combo)

        lu_sep = QFrame(); lu_sep.setFrameShape(QFrame.HLine); layout.addRow(lu_sep)
        lu_hdr = QLabel("Labour Unit  (Install Estimate)"); lu_hdr.setStyleSheet("font-weight:bold;color:#ff7002;"); layout.addRow(lu_hdr)
        layout.addRow("Labour Unit:", self.lu_combo)
        layout.addRow("", self._lu_custom_widget)

        layout.addRow("Product Image",   img_row)
        layout.addRow("Shop Drawing",    dr)

        # ── Coverage (Design Mode) ─────────────────────────────────────────
        cov_sep = QFrame(); cov_sep.setFrameShape(QFrame.HLine)
        layout.addRow(cov_sep)
        cov_hdr = QLabel("Coverage  (Design Mode)")
        cov_hdr.setStyleSheet("font-weight:bold;color:#ff7002;")
        layout.addRow(cov_hdr)

        self.cov_type_combo = QComboBox()
        self.cov_type_combo.addItems(["(auto-detect)", "smoke", "heat", "notification", "beam"])
        self.cov_type_combo.setToolTip(
            "Override the auto-detected coverage type.\n"
            "Leave on '(auto-detect)' to infer from the product name."
        )
        layout.addRow("Coverage Type", self.cov_type_combo)

        self.cov_radius_spin = QDoubleSpinBox()
        self.cov_radius_spin.setRange(0.0, 999.0)
        self.cov_radius_spin.setDecimals(2)
        self.cov_radius_spin.setSuffix(" m")
        self.cov_radius_spin.setSpecialValueText("Use default for type")
        self.cov_radius_spin.setValue(0.0)
        self.cov_radius_spin.setToolTip(
            "Custom coverage radius in metres.\n"
            "Set to 0 to use the code-default for the selected type.\n\n"
            "ULC S525 strobe radii:\n"
            "  15 cd → 4.30 m\n"
            "  30 cd → 6.44 m\n"
            "  75 cd → 8.60 m\n"
            "  110 cd → 10.75 m\n"
            "  135 cd → 12.09 m\n"
            "  185 cd → 14.21 m"
        )
        layout.addRow("Custom Radius", self.cov_radius_spin)

        btns = QHBoxLayout()
        save = QPushButton("Save"); save.setStyleSheet("background:#232728;color:white;padding:6px 20px;"); save.clicked.connect(self._save)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(cancel); btns.addWidget(save)
        layout.addRow(btns)

    def _refresh_lu_combo(self):
        self.lu_combo.blockSignals(True)
        self.lu_combo.clear()
        self.lu_combo.addItem("— None (no labour) —", None)
        self.lu_combo.addItem("Custom values…", -1)
        self._lu_rows = []
        for r in db.get_labour_units():
            display = f"{r['category']}  ·  {r['name']}  ({r['lu_reg']:.3f} / {r['lu_diff']:.3f} / {r['lu_hard']:.3f} hrs)"
            self.lu_combo.addItem(display, r["id"])
            self._lu_rows.append(r)
        self.lu_combo.blockSignals(False)

    def _on_lu_combo_change(self):
        val = self.lu_combo.currentData()
        self._lu_custom_widget.setVisible(val == -1)

    def _browse(self):
        p,_ = QFileDialog.getOpenFileName(self,"Select Shop Drawing","","Documents (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp)")
        if p: self.drawing_edit.setText(p)

    def _browse_img(self):
        p,_ = QFileDialog.getOpenFileName(self,"Select Product Image","","Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if p:
            self.img_edit.setText(p)
            self._set_img_preview(p)

    def _clear_img(self):
        self.img_edit.setText("")
        self.img_preview.clear()
        self.img_preview.setText("No image")

    def _set_img_preview(self, path):
        if path and os.path.exists(path):
            pm = QPixmap(path).scaled(62, 62, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img_preview.setPixmap(pm)
        else:
            self.img_preview.clear()

    def _load(self, p):
        self.name_edit.setText(p["name"]); self.code_edit.setText(p["code"] or "")
        self.cost_spin.setValue(p["unit_cost"] or 0.0)
        self.drawing_edit.setText(p["shop_drawing_path"] or "")
        img = p["image_path"] if "image_path" in p.keys() else ""
        self.img_edit.setText(img or "")
        self._set_img_preview(img or "")
        idx = self.cat_combo.findText(p["category"] or "General")
        self.cat_combo.setCurrentIndex(idx) if idx>=0 else self.cat_combo.setCurrentText(p["category"] or "General")
        subcat = p["subcategory"] if "subcategory" in p.keys() else ""
        self.subcat_combo.setCurrentText(subcat or "")
        candela = p["candela"] if "candela" in p.keys() and p["candela"] else 0
        idx = self.candela_combo.findData(candela)
        if idx < 0 and candela:
            # Legacy value from before candela was restricted to the fixed
            # list — keep it selectable rather than silently discarding it.
            self.candela_combo.addItem(f"{candela:g} cd (custom)", candela)
            idx = self.candela_combo.count() - 1
        self.candela_combo.setCurrentIndex(max(idx, 0))
        # Coverage fields
        ctype = p.get("coverage_type") or ""
        cidx  = self.cov_type_combo.findText(ctype) if ctype else 0
        self.cov_type_combo.setCurrentIndex(cidx if cidx >= 0 else 0)
        self.cov_radius_spin.setValue(float(p.get("coverage_radius_m") or 0.0))
        lu_id = p.get("lu_id")
        if lu_id:
            idx = self.lu_combo.findData(lu_id)
            self.lu_combo.setCurrentIndex(idx if idx >= 0 else 0)
        elif p.get("lu_reg") or p.get("lu_diff") or p.get("lu_hard"):
            self.lu_combo.setCurrentIndex(self.lu_combo.findData(-1))
            self.lu_reg_spin.setValue(float(p.get("lu_reg") or 0.0))
            self.lu_diff_spin.setValue(float(p.get("lu_diff") or 0.0))
            self.lu_hard_spin.setValue(float(p.get("lu_hard") or 0.0))
        else:
            self.lu_combo.setCurrentIndex(0)
        self._on_lu_combo_change()

    def _save(self):
        name = self.name_edit.text().strip()
        if not name: QMessageBox.warning(self,"Required","Product name is required."); return
        raw_ctype = self.cov_type_combo.currentText()
        lu_combo_val = self.lu_combo.currentData()
        if lu_combo_val and lu_combo_val != -1:
            lu_id = lu_combo_val
            lu_reg = lu_diff = lu_hard = 0.0
        elif lu_combo_val == -1:
            lu_id = None
            lu_reg  = self.lu_reg_spin.value()
            lu_diff = self.lu_diff_spin.value()
            lu_hard = self.lu_hard_spin.value()
        else:
            lu_id = lu_reg = lu_diff = lu_hard = None

        self.result_data = dict(
            name=name, code=self.code_edit.text().strip(),
            unit_cost=self.cost_spin.value(),
            category=self.cat_combo.currentText().strip() or "General",
            subcategory=self.subcat_combo.currentText().strip(),
            candela=self.candela_combo.currentData(),
            shop_drawing_path=self.drawing_edit.text().strip(),
            image_path=self.img_edit.text().strip(),
            coverage_type="" if raw_ctype == "(auto-detect)" else raw_ctype,
            coverage_radius_m=self.cov_radius_spin.value(),
            lu_id=lu_id, lu_reg=lu_reg or 0.0,
            lu_diff=lu_diff or 0.0, lu_hard=lu_hard or 0.0,
        )
        self.accept()


# 
# Assembly dialog
# 

class AssemblyDialog(QDialog):
    def __init__(self, parent=None, assembly=None):
        super().__init__(parent)
        self.setWindowTitle("Add Assembly" if assembly is None else "Edit Assembly")
        self.setMinimumSize(620, 480)
        self._items = []
        self._build_ui()
        if assembly: self._load(assembly)

    def _build_ui(self):
        layout = QVBoxLayout(self); layout.setContentsMargins(14,14,14,14); layout.setSpacing(8)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(sorted(set(CATEGORIES) | set(db.get_distinct_categories())))
        self.cat_combo.setEditable(True)
        self.desc_edit = QLineEdit(); self.desc_edit.setPlaceholderText("Optional description")
        form.addRow("Assembly Name *", self.name_edit)
        form.addRow("Category", self.cat_combo)
        form.addRow("Description", self.desc_edit)
        layout.addLayout(form)

        # Linear / per-foot toggle
        self.chk_linear = QCheckBox("Linear / Per-Foot Assembly  (conduit runs, wire, cable)")
        self.chk_linear.setStyleSheet("font-weight:bold;color:#ff7002;")
        layout.addWidget(self.chk_linear)

        # Linear fields (shown only when checked)
        self._linear_box = QGroupBox("Linear Assembly Settings")
        lf = QFormLayout(self._linear_box)
        self.sp_wire_count = QSpinBox(); self.sp_wire_count.setRange(1, 50); self.sp_wire_count.setValue(1); self.sp_wire_count.setMinimumWidth(80)
        self.sp_bundle = QDoubleSpinBox(); self.sp_bundle.setRange(0.0, 1.0); self.sp_bundle.setDecimals(2)
        self.sp_bundle.setSingleStep(0.05); self.sp_bundle.setValue(0.35); self.sp_bundle.setMinimumWidth(80)
        self.sp_bundle.setToolTip("Fraction of wire-pull LU for each additional wire (0 = no extra, 1 = full)")
        self.sp_prep_lu = QDoubleSpinBox(); self.sp_prep_lu.setRange(0.0, 100.0); self.sp_prep_lu.setDecimals(3)
        self.sp_prep_lu.setSingleStep(0.05); self.sp_prep_lu.setMinimumWidth(80)
        self.sp_prep_lu.setToolTip("Hours per wire for prep/termination (fixed per wire, not per foot)")

        # LU pickers — dropdown selects from library, spinboxes show/override values
        self._lu_data = {}  # id → (reg, diff, hard)
        lus = list(db.get_labour_units())
        for lu in lus:
            self._lu_data[lu["id"]] = (lu["lu_reg"], lu["lu_diff"], lu["lu_hard"])

        def _make_lu_picker(spins_callback):
            cb = QComboBox(); cb.addItem("— select or enter manually —", None)
            for lu in lus:
                cb.addItem(f"{lu['name']}  (R:{lu['lu_reg']:.4f} D:{lu['lu_diff']:.4f} H:{lu['lu_hard']:.4f})", lu["id"])
            cb.currentIndexChanged.connect(spins_callback)
            return cb

        self.sp_lu_reg  = QDoubleSpinBox(); self.sp_lu_reg.setRange(0,100); self.sp_lu_reg.setDecimals(4); self.sp_lu_reg.setSingleStep(0.005); self.sp_lu_reg.setMinimumWidth(80)
        self.sp_lu_diff = QDoubleSpinBox(); self.sp_lu_diff.setRange(0,100); self.sp_lu_diff.setDecimals(4); self.sp_lu_diff.setSingleStep(0.005); self.sp_lu_diff.setMinimumWidth(80)
        self.sp_lu_hard = QDoubleSpinBox(); self.sp_lu_hard.setRange(0,100); self.sp_lu_hard.setDecimals(4); self.sp_lu_hard.setSingleStep(0.005); self.sp_lu_hard.setMinimumWidth(80)

        def _fill_conduit(_):
            lid = self.cbo_conduit_lu.currentData()
            if lid and lid in self._lu_data:
                r, d, h = self._lu_data[lid]
                self.sp_lu_reg.setValue(r); self.sp_lu_diff.setValue(d); self.sp_lu_hard.setValue(h)
        self.cbo_conduit_lu = _make_lu_picker(_fill_conduit)

        conduit_pick_w = QWidget(); cpl = QVBoxLayout(conduit_pick_w); cpl.setContentsMargins(0,0,0,0); cpl.setSpacing(2)
        cpl.addWidget(self.cbo_conduit_lu)
        conduit_val_w = QWidget(); conduit_row = QHBoxLayout(conduit_val_w); conduit_row.setContentsMargins(0,0,0,0)
        for sp, lbl in [(self.sp_lu_reg,"Reg"),(self.sp_lu_diff,"Diff"),(self.sp_lu_hard,"Hard")]:
            conduit_row.addWidget(QLabel(lbl)); conduit_row.addWidget(sp)
        cpl.addWidget(conduit_val_w)

        self.sp_wlu_reg  = QDoubleSpinBox(); self.sp_wlu_reg.setRange(0,100); self.sp_wlu_reg.setDecimals(4); self.sp_wlu_reg.setSingleStep(0.005); self.sp_wlu_reg.setMinimumWidth(80)
        self.sp_wlu_diff = QDoubleSpinBox(); self.sp_wlu_diff.setRange(0,100); self.sp_wlu_diff.setDecimals(4); self.sp_wlu_diff.setSingleStep(0.005); self.sp_wlu_diff.setMinimumWidth(80)
        self.sp_wlu_hard = QDoubleSpinBox(); self.sp_wlu_hard.setRange(0,100); self.sp_wlu_hard.setDecimals(4); self.sp_wlu_hard.setSingleStep(0.005); self.sp_wlu_hard.setMinimumWidth(80)

        def _fill_wire(_):
            lid = self.cbo_wire_lu.currentData()
            if lid and lid in self._lu_data:
                r, d, h = self._lu_data[lid]
                self.sp_wlu_reg.setValue(r); self.sp_wlu_diff.setValue(d); self.sp_wlu_hard.setValue(h)
        self.cbo_wire_lu = _make_lu_picker(_fill_wire)

        wire_pick_w = QWidget(); wpl = QVBoxLayout(wire_pick_w); wpl.setContentsMargins(0,0,0,0); wpl.setSpacing(2)
        wpl.addWidget(self.cbo_wire_lu)
        wire_val_w = QWidget(); wire_row = QHBoxLayout(wire_val_w); wire_row.setContentsMargins(0,0,0,0)
        for sp, lbl in [(self.sp_wlu_reg,"Reg"),(self.sp_wlu_diff,"Diff"),(self.sp_wlu_hard,"Hard")]:
            wire_row.addWidget(QLabel(lbl)); wire_row.addWidget(sp)
        wpl.addWidget(wire_val_w)

        lf.addRow("Wire count:", self.sp_wire_count)
        lf.addRow("Bundle factor:", self.sp_bundle)
        lf.addRow("Prep LU per wire (hrs):", self.sp_prep_lu)
        lf.addRow("Conduit run LU (hrs/ft):", conduit_pick_w)
        lf.addRow("Wire pull LU (hrs/ft per wire):", wire_pick_w)

        self._linear_box.setVisible(False)
        layout.addWidget(self._linear_box)
        def _toggle_linear(checked):
            self._linear_box.setVisible(checked)
            self.adjustSize()
        self.chk_linear.toggled.connect(_toggle_linear)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); layout.addWidget(sep)
        layout.addWidget(QLabel("Components (include all materials per foot of run):"))
        self.comp_table = QTableWidget(0, 3)
        self.comp_table.setHorizontalHeaderLabels(["Product","Code","Qty / ft"])
        self.comp_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.comp_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.comp_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.comp_table.verticalHeader().setVisible(False)
        layout.addWidget(self.comp_table)
        cb = QHBoxLayout()
        add_c = QPushButton("+ Add Product"); add_c.setStyleSheet("background:#ff7002;color:white;padding:4px 10px;"); add_c.clicked.connect(self._add_comp)
        rm_c  = QPushButton("Remove");        rm_c.setStyleSheet("background:#c02b0a;color:white;padding:4px 10px;"); rm_c.clicked.connect(self._rm_comp)
        cb.addWidget(add_c); cb.addWidget(rm_c); cb.addStretch(); layout.addLayout(cb)
        btns = QHBoxLayout()
        save = QPushButton("Save Assembly"); save.setStyleSheet("background:#232728;color:white;padding:6px 20px;"); save.clicked.connect(self._save)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(cancel); btns.addWidget(save); layout.addLayout(btns)

    def _load(self, a):
        self.name_edit.setText(a["name"])
        idx = self.cat_combo.findText(a["category"] or "General")
        self.cat_combo.setCurrentIndex(idx) if idx>=0 else self.cat_combo.setCurrentText(a["category"] or "General")
        self.desc_edit.setText(a["description"] or "")
        if a.get("is_linear"):
            self.chk_linear.setChecked(True)
            self.sp_wire_count.setValue(a.get("wire_count") or 1)
            self.sp_bundle.setValue(a.get("bundle_factor") or 0.35)
            self.sp_prep_lu.setValue(a.get("prep_lu_per_wire") or 0.0)
            self.sp_lu_reg.setValue(a.get("lu_reg") or 0.0)
            self.sp_lu_diff.setValue(a.get("lu_diff") or 0.0)
            self.sp_lu_hard.setValue(a.get("lu_hard") or 0.0)
            self.sp_wlu_reg.setValue(a.get("wire_lu_reg") or 0.0)
            self.sp_wlu_diff.setValue(a.get("wire_lu_diff") or 0.0)
            self.sp_wlu_hard.setValue(a.get("wire_lu_hard") or 0.0)
        for item in db.get_assembly_items(a["id"]):
            self._items.append([dict(item), item["quantity"]])
        self._refresh_table()

    def _refresh_table(self):
        self.comp_table.setRowCount(len(self._items))
        for r,(p,q) in enumerate(self._items):
            self.comp_table.setItem(r,0,QTableWidgetItem(p["name"]))
            self.comp_table.setItem(r,1,QTableWidgetItem(p["code"] or ""))
            qi = QTableWidgetItem(str(q)); qi.setTextAlignment(Qt.AlignCenter)
            self.comp_table.setItem(r,2,qi)

    def _add_comp(self):
        products = list(db.get_products())
        if not products: QMessageBox.information(self,"No Products","Add products first."); return
        names = [f"{p['name']}  ({p['code'] or ''})" for p in products]
        name, ok = QInputDialog.getItem(self,"Add Component","Select product:",names,0,False)
        if not ok: return
        product = dict(products[names.index(name)])
        for item in self._items:
            if item[0]["id"] == product["id"]: item[1]+=1; self._refresh_table(); return
        qty,ok = QInputDialog.getInt(self,"Quantity",f"Qty of {product['name']}:",1,1,999)
        if ok: self._items.append([product,qty]); self._refresh_table()

    def _rm_comp(self):
        rows = {i.row() for i in self.comp_table.selectedItems()}
        self._items = [item for i,item in enumerate(self._items) if i not in rows]
        self._refresh_table()

    def _save(self):
        name = self.name_edit.text().strip()
        if not name: QMessageBox.warning(self,"Required","Assembly name is required."); return
        is_linear = 1 if self.chk_linear.isChecked() else 0
        if not self._items and not is_linear:
            QMessageBox.warning(self,"Empty","Add at least one component."); return
        self.result_data = dict(
            name=name, category=self.cat_combo.currentText().strip() or "General",
            description=self.desc_edit.text().strip(),
            items=[(item[0]["id"], item[1]) for item in self._items],
            is_linear=is_linear,
            wire_count=self.sp_wire_count.value(),
            bundle_factor=self.sp_bundle.value(),
            prep_lu_per_wire=self.sp_prep_lu.value(),
            lu_reg=self.sp_lu_reg.value(), lu_diff=self.sp_lu_diff.value(), lu_hard=self.sp_lu_hard.value(),
            wire_lu_reg=self.sp_wlu_reg.value(), wire_lu_diff=self.sp_wlu_diff.value(), wire_lu_hard=self.sp_wlu_hard.value(),
        )
        self.accept()


#
# FlowLayout — wraps child widgets onto additional rows instead of squeezing/
# truncating them. Drop-in for QHBoxLayout (supports addWidget/addStretch).
#

class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=6):
        super().__init__(parent)
        self._hspacing = hspacing
        self._vspacing = vspacing
        self._items = []
        if margin >= 0:
            self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def addStretch(self, stretch=0):
        pass  # no-op — FlowLayout has no concept of stretch; items just wrap

    def horizontalSpacing(self):
        return self._hspacing

    def verticalSpacing(self):
        return self._vspacing

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left()+m.right(), m.top()+m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x, y = effective.x(), effective.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._hspacing
            if next_x - self._hspacing > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + self._vspacing
                next_x = x + hint.width() + self._hspacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + bottom


class FlowBar(QWidget):
    """Self-contained button-bar widget: children wrap onto extra rows instead
    of being squeezed/truncated, and the bar keeps its own height in sync with
    the wrapped row count on every resize (Qt's heightForWidth does not
    reliably propagate through nested layouts/QTabWidget on its own)."""
    def __init__(self, parent=None, hspacing=6, vspacing=6, margin=0):
        super().__init__(parent)
        self._flow = FlowLayout(self, hspacing=hspacing, vspacing=vspacing)
        if margin >= 0:
            self._flow.setContentsMargins(margin, margin, margin, margin)
        sp = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def addWidget(self, w):
        self._flow.addWidget(w)

    def addStretch(self, stretch=0):
        pass  # no-op — FlowLayout has no concept of stretch; items just wrap

    def setContentsMargins(self, *a):
        self._flow.setContentsMargins(*a)


MENU_STYLE = ("QMenu { background:#232728; color:#efe6e1; border:1px solid #555; }"
              "QMenu::item { padding:8px 24px; }"
              "QMenu::item:selected { background:#ff7002; color:white; }")


class HoverMenuButton(QToolButton):
    """Toolbar dropdown that opens its menu on hover (mouse-enter) as well as
    click — groups a cluster of related actions (e.g. the 3 designer tools,
    or the 3 quote types) behind one button instead of each sitting as its
    own always-visible toolbar action. Click-to-open still works via
    InstantPopup; hover is layered on top so the group reads as a single
    discoverable menu rather than 3+ separate buttons cluttering the bar."""
    _instances = []

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        HoverMenuButton._instances.append(self)

    def _close_sibling_menus(self):
        # Clicking or hovering onto one dropdown while a sibling's menu is
        # still open let Qt forward that same click into the new popup as
        # part of its native "click outside closes popup" handling, which
        # nested our showMenu() inside the still-unwinding first popup's
        # call stack and crashed. Closing any other open menu of ours
        # synchronously, before Qt gets a chance to do that forwarding,
        # keeps only one of our popups active at a time.
        for other in HoverMenuButton._instances:
            if other is not self:
                m = other.menu()
                if m is not None and m.isVisible():
                    m.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Do NOT call super().mousePressEvent() here — with InstantPopup
            # that calls showMenu() synchronously, and when a sibling's menu
            # is already open, Qt can redeliver this same click into this
            # button while still unwinding the sibling's own popup call
            # stack (the "click one dropdown to switch straight to another"
            # behavior). Opening a second menu synchronously in that window
            # nests one popup's event loop inside the other's and crashes.
            # Deferring to the next event-loop tick lets the sibling's
            # popup finish closing first.
            event.accept()
            self._close_sibling_menus()
            QTimer.singleShot(0, self._open_menu_now)
            return
        super().mousePressEvent(event)

    def _open_menu_now(self):
        menu = self.menu()
        if menu is not None and not menu.isVisible():
            self.showMenu()

    def enterEvent(self, event):
        super().enterEvent(event)
        # Defer to the next event-loop tick instead of calling showMenu()
        # synchronously here — enterEvent can fire while another popup is
        # still tearing down its own mouse-grab, and calling showMenu()
        # inline in that window is what was crashing the app on dismiss.
        QTimer.singleShot(0, self._maybe_show_menu)

    def _maybe_show_menu(self):
        menu = self.menu()
        if menu is not None and not menu.isVisible() and self.underMouse():
            self._close_sibling_menus()
            self.showMenu()


class MultiCheckMenu(QMenu):
    """A QMenu that stays open after clicking a checkable item — for a group
    of independent on/off toggles (e.g. the per-type coverage-circle
    visibility layers) where closing after every single click would make
    turning on/off several of them tedious. Non-checkable items still close
    the menu as normal."""
    def mouseReleaseEvent(self, event):
        action = self.activeAction()
        if action is not None and action.isCheckable():
            action.trigger()
            return
        super().mouseReleaseEvent(event)


#
# Library panel (Products + Assemblies tabs)
#

class LibraryPanel(QWidget):
    product_selected  = pyqtSignal(object)
    assembly_selected = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui(); self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self); layout.setContentsMargins(4,4,4,4); layout.setSpacing(4)
        lbl = QLabel("Library"); lbl.setStyleSheet("font-weight:bold;font-size:13px;padding:4px;"); layout.addWidget(lbl)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._prod_tab(), "Products")
        self.tabs.addTab(self._asm_tab(),  "Assemblies")
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        layout.addWidget(self.tabs)

    def _prod_tab(self):
        w = QWidget(); layout = QVBoxLayout(w); layout.setContentsMargins(2,4,2,2); layout.setSpacing(4)
        self.prod_search = QLineEdit(); self.prod_search.setPlaceholderText("Search"); self.prod_search.textChanged.connect(self._filter)
        layout.addWidget(self.prod_search)
        # Grouped by category — each category is a collapsible node (click the
        # arrow, or the group row, to expand/collapse) so a long device list
        # (e.g. Horn Strobes / Hi-Ca Horn Strobes / Addressable Horn Strobes)
        # doesn't have to sit fully flat. Which group a product lands in is
        # just its Category field (ProductDialog's category combo — editable,
        # so any custom group name works).
        self._group_expanded = {}   # {category: bool} — remembered across refreshes
        self.prod_list = QTreeWidget()
        self.prod_list.setHeaderHidden(True)
        self.prod_list.setIndentation(12)
        self.prod_list.itemClicked.connect(self._on_prod_item_clicked)
        self.prod_list.itemExpanded.connect(
            lambda item: self._group_expanded.__setitem__(item.data(0, Qt.UserRole + 1), True))
        self.prod_list.itemCollapsed.connect(
            lambda item: self._group_expanded.__setitem__(item.data(0, Qt.UserRole + 1), False))
        self.prod_list.setStyleSheet(
            "QTreeWidget::item{padding:5px;border-bottom:1px solid #e0e0e0;}"
            "QTreeWidget::item:selected{background:#232728;color:white;}")
        layout.addWidget(self.prod_list)
        btns = FlowBar(hspacing=4, vspacing=4)
        for lbl2,fn,style in [("+ Add",self._add_prod,"background:#ff7002;color:white;padding:4px;"),
                              ("Edit", self._edit_prod,"padding:4px;"),
                              ("Del",  self._del_prod, "background:#c02b0a;color:white;padding:4px;")]:
            b = QPushButton(lbl2); b.setStyleSheet(style); b.clicked.connect(fn); btns.addWidget(b)
        lu_btn = QPushButton("Labour Units")
        lu_btn.setStyleSheet("background:#2980b9;color:white;padding:4px;")
        lu_btn.setToolTip("Manage shared Labour Unit library")
        lu_btn.clicked.connect(self._manage_labour_units); btns.addWidget(lu_btn)
        more_btn = QPushButton(""); more_btn.setFixedWidth(28); more_btn.setToolTip("CSV import/export")
        more_btn.clicked.connect(self._show_csv_menu); btns.addWidget(more_btn)
        layout.addWidget(btns); return w

    def _show_csv_menu(self):
        menu = QMenu(self)
        menu.addAction("Import products from CSV", self._import_csv)
        menu.addAction("Export CSV template",       self._export_csv_template)
        menu.exec_(self.cursor().pos())

    def _asm_tab(self):
        w = QWidget(); layout = QVBoxLayout(w); layout.setContentsMargins(2,4,2,2); layout.setSpacing(4)
        self.asm_list = QListWidget()
        self.asm_list.itemClicked.connect(lambda i: self.assembly_selected.emit(i.data(Qt.UserRole)))
        self.asm_list.setStyleSheet("QListWidget::item{padding:5px;border-bottom:1px solid #e0e0e0;}QListWidget::item:selected{background:#232728;color:white;}")
        layout.addWidget(self.asm_list)
        btns = FlowBar(hspacing=4, vspacing=4)
        for lbl2,fn,style in [("+ Add",self._add_asm,"background:#232728;color:white;padding:4px;"),
                              ("Edit", self._edit_asm,"padding:4px;"),
                              ("Del",  self._del_asm, "background:#c02b0a;color:white;padding:4px;")]:
            b = QPushButton(lbl2); b.setStyleSheet(style); b.clicked.connect(fn); btns.addWidget(b)
        layout.addWidget(btns); return w

    def refresh(self):
        self._all_products = list(db.get_products())
        self._filter(self.prod_search.text() if hasattr(self,"prod_search") else "")
        self.asm_list.clear()
        for a in db.get_assemblies():
            a = dict(a)
            if a.get("is_linear"):
                sub = f"Linear  ·  {a.get('wire_count',1)} wire(s)  ·  bundle {a.get('bundle_factor',0.35):.2f}"
            else:
                comps = db.get_assembly_items(a["id"])
                sub = ", ".join(f"{c['quantity']} {c['name']}" for c in comps) or "no components"
            item = QListWidgetItem(f"{'⌇ ' if a.get('is_linear') else ''}{a['name']}\n  {sub}")
            item.setData(Qt.UserRole, a); self.asm_list.addItem(item)

    def _on_prod_item_clicked(self, item, column):
        data = item.data(0, Qt.UserRole)
        if data is not None:
            self.product_selected.emit(data)

    def _make_prod_leaf(self, p):
        has_drawing = bool(p["shop_drawing_path"])
        badge = " " if has_drawing else ""
        leaf = QTreeWidgetItem([f"{badge}{p['name']}\n  {p['code'] or ''}"])
        img_path = p["image_path"] if "image_path" in p.keys() else ""
        if img_path and os.path.exists(img_path):
            from PyQt5.QtGui import QIcon
            leaf.setIcon(0, QIcon(QPixmap(img_path).scaled(40,40,Qt.KeepAspectRatio,Qt.SmoothTransformation)))
        leaf.setData(0, Qt.UserRole, dict(p))
        return leaf

    def _make_group_node(self, key, label, count):
        node = QTreeWidgetItem([f"{label}  ({count})"])
        f = node.font(0); f.setBold(True); node.setFont(0, f)
        node.setData(0, Qt.UserRole + 1, key)
        return node

    def _filter(self, text):
        # Remember which product is currently selected so we can restore it
        prev = self.selected_product()
        prev_id = prev["id"] if prev else None

        self.prod_list.clear(); text = text.lower()

        groups = {}
        for p in self._all_products:
            groups.setdefault(p["category"] or "Uncategorized", []).append(p)

        self.prod_list.setIconSize(QSize(40, 40))
        for category in sorted(groups.keys()):
            prods = groups[category]
            if text:
                prods = [p for p in prods
                        if text in p["name"].lower() or text in (p["code"] or "").lower()]
                if not prods:
                    continue

            cat_key = category
            grp_item = self._make_group_node(cat_key, category, len(prods))
            self.prod_list.addTopLevelItem(grp_item)
            grp_item.setExpanded(True if text else self._group_expanded.get(cat_key, True))

            # A second, optional dropdown level within the category — its own
            # Subcategory field on the product — for further sorting a group
            # that's grown too large (e.g. Horn Strobes -> Wall / Ceiling).
            # Products left without a subcategory sit directly under the
            # category, alongside any subcategory subgroups.
            subgroups = {}
            loose = []
            for p in prods:
                sub = p["subcategory"] if "subcategory" in p.keys() else ""
                if sub:
                    subgroups.setdefault(sub, []).append(p)
                else:
                    loose.append(p)

            def add_sorted(parent_widget, plist):
                # Sort by use_count descending so the most-used variant of a
                # device rises to the top of its (sub)group.
                for p in sorted(plist, key=lambda p: -(p["use_count"] if "use_count" in p.keys() else 0)):
                    leaf = self._make_prod_leaf(p)
                    parent_widget.addChild(leaf)
                    if prev_id is not None and p["id"] == prev_id:
                        self.prod_list.blockSignals(True)
                        self.prod_list.setCurrentItem(leaf)
                        self.prod_list.blockSignals(False)

            for sub in sorted(subgroups.keys()):
                sub_key = f"{category}\x1f{sub}"
                sub_item = self._make_group_node(sub_key, sub, len(subgroups[sub]))
                grp_item.addChild(sub_item)
                sub_item.setExpanded(True if text else self._group_expanded.get(sub_key, True))
                add_sorted(sub_item, subgroups[sub])

            add_sorted(grp_item, loose)

    def selected_product(self):
        i = self.prod_list.currentItem()
        return i.data(0, Qt.UserRole) if i else None
    def selected_assembly(self):
        i = self.asm_list.currentItem(); return i.data(Qt.UserRole) if i else None

    def _manage_labour_units(self):
        dlg = LabourUnitManagerDialog(self)
        dlg.exec_()

    def _add_prod(self):
        dlg = ProductDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.result_data
            db.add_product(d["name"], d["code"], d["unit_cost"], d["category"],
                           d.get("shop_drawing_path", ""), d.get("image_path", ""),
                           d.get("coverage_type", ""), d.get("coverage_radius_m", 0.0),
                           d.get("lu_reg", 0.0), d.get("lu_diff", 0.0), d.get("lu_hard", 0.0),
                           d.get("lu_id"), d.get("subcategory", ""), d.get("candela", 0.0))
            self.refresh()

    def _edit_prod(self):
        p = self.selected_product()
        if not p: QMessageBox.information(self,"Select","Select a product to edit."); return
        dlg = ProductDialog(self, p)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.result_data
            db.update_product(p["id"], d["name"], d["code"], d["unit_cost"], d["category"],
                              d.get("shop_drawing_path", ""), d.get("image_path", ""),
                              d.get("coverage_type", ""), d.get("coverage_radius_m", 0.0),
                              d.get("lu_reg", 0.0), d.get("lu_diff", 0.0), d.get("lu_hard", 0.0),
                              d.get("lu_id"), d.get("subcategory", ""), d.get("candela", 0.0))
            self.refresh()

    def _del_prod(self):
        p = self.selected_product()
        if not p: return
        if QMessageBox.question(self,"Delete",f"Delete '{p['name']}'?",QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
            db.delete_product(p["id"]); self.refresh()

    def _export_csv_template(self):
        path,_ = QFileDialog.getSaveFileName(self,"Save CSV Template","products_template.csv","CSV (*.csv)")
        if not path: return
        try:
            with open(path,"w",newline="",encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["name","code","unit_cost","category","subcategory","shop_drawing_path"])
                writer.writerow(["Smoke Detector - Photo","SD-100",85.00,"Detectors","",""])
                writer.writerow(["Horn Strobe - Red","HS-240R",120.00,"Notification","Wall Mount",""])
                writer.writerow(["Pull Station","PS-001",65.00,"Initiating Devices","",""])
            QMessageBox.information(self,"Template Saved",
                f"CSV template saved to:\n{path}\n\nOpen in Excel, fill in your products, save as CSV, then use Import CSV.")
            os.startfile(path)
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    def _import_csv(self):
        path,_ = QFileDialog.getOpenFileName(self,"Import Products CSV","","CSV (*.csv)")
        if not path: return
        added = 0
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("name","").strip() or row.get("Name","").strip()
                    if not name: continue
                    db.add_product(
                        name,
                        row.get("code","").strip() or row.get("Code","").strip(),
                        float(row.get("unit_cost",0) or row.get("Unit Cost",0) or 0),
                        row.get("category","General").strip() or "General",
                        subcategory=row.get("subcategory","").strip() or row.get("Subcategory","").strip(),
                    )
                    added += 1
            self.refresh()
            QMessageBox.information(self,"Imported",f"{added} products imported.")
        except Exception as e:
            QMessageBox.critical(self,"CSV Error",str(e))

    def _add_asm(self):
        dlg = AssemblyDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.result_data
            aid = db.add_assembly(
                d["name"], d["category"], d["description"],
                d["is_linear"], d["wire_count"], d["bundle_factor"], d["prep_lu_per_wire"],
                d["lu_reg"], d["lu_diff"], d["lu_hard"],
                d["wire_lu_reg"], d["wire_lu_diff"], d["wire_lu_hard"],
            )
            db.set_assembly_items(aid, d["items"]); self.refresh()

    def _edit_asm(self):
        a = self.selected_assembly()
        if not a: QMessageBox.information(self,"Select","Select an assembly to edit."); return
        dlg = AssemblyDialog(self, a)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.result_data
            db.update_assembly(
                a["id"], d["name"], d["category"], d["description"],
                d["is_linear"], d["wire_count"], d["bundle_factor"], d["prep_lu_per_wire"],
                d["lu_reg"], d["lu_diff"], d["lu_hard"],
                d["wire_lu_reg"], d["wire_lu_diff"], d["wire_lu_hard"],
            )
            db.set_assembly_items(a["id"], d["items"]); self.refresh()

    def _del_asm(self):
        a = self.selected_assembly()
        if not a: return
        if QMessageBox.question(self,"Delete",f"Delete assembly '{a['name']}'?",QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
            db.delete_assembly(a["id"]); self.refresh()


class SubmittalProductPickerDialog(QDialog):
    """Pick products to include in a shop-drawing submittal directly from the
    catalogue — for when a submittal needs to go out before the takeoff has
    any counts done (e.g. a submittal owed ahead of the quote)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Build Submittal — No Counts")
        self.resize(480, 560)
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Check the products to include. Only products with a "
                                 "shop drawing attached can be selected — select a product "
                                 "below and click \"Attach Shop Drawing…\" to add one on the spot."))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        layout.addWidget(self._list)

        attach_row = QHBoxLayout()
        attach_btn = QPushButton("Attach Shop Drawing…")
        attach_btn.clicked.connect(self._attach_drawing)
        attach_row.addWidget(attach_btn)
        attach_row.addStretch()
        layout.addLayout(attach_row)

        br = QHBoxLayout()
        ok = QPushButton("Build Submittal")
        ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(cancel); br.addWidget(ok)
        layout.addLayout(br)

    def _load(self, reselect_product_id=None, check_ids=None):
        # Remember which products were already checked so re-loading after
        # attaching a drawing (or filtering) doesn't lose the selection.
        if check_ids is None:
            check_ids = {p["id"] for p in self.selected_products()} if self._list.count() else set()
        self._list.clear()
        products = db.get_products()
        last_category = None
        for p in products:
            cat = p["category"] or "General"
            if cat != last_category:
                last_category = cat
                hdr = QListWidgetItem(last_category)
                hdr.setFlags(Qt.NoItemFlags)
                f = hdr.font(); f.setBold(True); hdr.setFont(f)
                hdr.setBackground(QColor("#eeeeee"))
                self._list.addItem(hdr)
            has_drawing = bool(p["shop_drawing_path"]) and os.path.exists(p["shop_drawing_path"] or "")
            label = f"{p['name']}  ({p['code']})" if p["code"] else p["name"]
            if not has_drawing:
                label += "   [no shop drawing]"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, dict(p))
            if has_drawing:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setCheckState(Qt.Checked if p["id"] in check_ids else Qt.Unchecked)
            else:
                # Still selectable (so "Attach Shop Drawing…" can target it),
                # just not checkable until a drawing is attached.
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setForeground(QColor("#999999"))
            self._list.addItem(item)
            if reselect_product_id is not None and p["id"] == reselect_product_id:
                self._list.setCurrentItem(item)

    def _attach_drawing(self):
        item = self._list.currentItem()
        data = item.data(Qt.UserRole) if item else None
        if data is None:
            QMessageBox.information(self, "Select a Product",
                                    "Click a product in the list first, then Attach Shop Drawing…")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Shop Drawing", "",
            "Documents (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp)")
        if not path:
            return
        db.set_product_shop_drawing(data["id"], path)
        self._load(reselect_product_id=data["id"])

    def _apply_filter(self, text):
        text = text.lower().strip()
        for i in range(self._list.count()):
            item = self._list.item(i)
            data = item.data(Qt.UserRole)
            if data is None:
                item.setHidden(bool(text))   # category header — hide while filtering
            else:
                name = data["name"].lower(); code = (data["code"] or "").lower()
                item.setHidden(bool(text) and text not in name and text not in code)

    def selected_products(self):
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.UserRole) is not None and item.checkState() == Qt.Checked:
                result.append(item.data(Qt.UserRole))
        return result


#
# Takeoff Panel
#

class TakeoffPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id = None
        self._active_entity = None
        self._active_section_id = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self); layout.setContentsMargins(4,4,4,4); layout.setSpacing(6)

        self.active_label = QLabel("No item selected")
        self.active_label.setStyleSheet("background:#232728;color:#efe6e1;padding:6px;border-radius:4px;font-weight:bold;")
        self.active_label.setWordWrap(True); layout.addWidget(self.active_label)

        # Section row
        sec_row = QHBoxLayout()
        sec_row.addWidget(QLabel("Section:"))
        self.sec_combo = QComboBox(); self.sec_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.sec_combo.currentIndexChanged.connect(self._on_section_changed)
        sec_row.addWidget(self.sec_combo)
        add_sec = QPushButton("+"); add_sec.setFixedWidth(24); add_sec.setToolTip("Add section"); add_sec.clicked.connect(self._add_section)
        del_sec = QPushButton(""); del_sec.setFixedWidth(24); del_sec.setToolTip("Delete section"); del_sec.clicked.connect(self._del_section)
        sec_row.addWidget(add_sec); sec_row.addWidget(del_sec)
        layout.addLayout(sec_row)

        # Count +/
        count_row = QHBoxLayout()
        minus_btn = QPushButton(""); minus_btn.setFixedSize(36,36)
        minus_btn.setStyleSheet("font-size:20px;background:#c02b0a;color:white;border-radius:4px;")
        minus_btn.clicked.connect(self._decrement)
        self.count_label = QLabel("0"); self.count_label.setAlignment(Qt.AlignCenter)
        self.count_label.setStyleSheet("font-size:32px;font-weight:bold;min-width:60px;")
        plus_btn = QPushButton("+"); plus_btn.setFixedSize(36,36)
        plus_btn.setStyleSheet("font-size:20px;background:#ff7002;color:white;border-radius:4px;")
        plus_btn.clicked.connect(self._increment)
        count_row.addStretch(); count_row.addWidget(minus_btn); count_row.addWidget(self.count_label); count_row.addWidget(plus_btn); count_row.addStretch()
        layout.addLayout(count_row)

        # Tabs: Summary | By Section
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._build_summary_tab(), "Summary")
        self.tab_widget.addTab(self._build_section_tab(), "By Section")
        self.tab_widget.tabBar().setExpanding(False)
        self.tab_widget.tabBar().setUsesScrollButtons(False)
        self.tab_widget.tabBar().setElideMode(Qt.ElideNone)
        layout.addWidget(self.tab_widget)

        export_btn = QPushButton("Export to Excel")
        export_btn.setStyleSheet("background:#232728;color:white;padding:8px;font-size:13px;font-weight:bold;border-radius:4px;")
        export_btn.clicked.connect(self._export); layout.addWidget(export_btn)

        submittal_btn = QPushButton("Job Won  Build Submittal Package")
        submittal_btn.setStyleSheet("background:#ff7002;color:white;padding:8px;font-size:12px;font-weight:bold;border-radius:4px;")
        submittal_btn.clicked.connect(self._build_submittal); layout.addWidget(submittal_btn)

        presub_btn = QPushButton("Build Submittal — No Counts")
        presub_btn.setToolTip(
            "Build a shop-drawing submittal package directly from the product\n"
            "catalogue, without needing any counts done on the takeoff yet —\n"
            "for when a submittal is owed before the quote.")
        presub_btn.setStyleSheet("background:#232728;color:white;padding:8px;font-size:12px;font-weight:bold;border-radius:4px;")
        presub_btn.clicked.connect(self._build_submittal_no_counts); layout.addWidget(presub_btn)

    def _build_summary_tab(self):
        w = QWidget(); layout = QVBoxLayout(w); layout.setContentsMargins(0,4,0,0)
        self.table = QTableWidget(0,4)
        self.table.setHorizontalHeaderLabels(["Product","Code","Qty","Total"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1,2,3): self.table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        self.total_label = QLabel("Total: $0.00  |  Items: 0")
        self.total_label.setStyleSheet("font-weight:bold;font-size:12px;padding:4px;")
        self.total_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.total_label)
        return w

    def _build_section_tab(self):
        w = QWidget(); layout = QVBoxLayout(w); layout.setContentsMargins(0,4,0,0)
        hint = QLabel("Select section(s) below to limit Export/Submittal to just those — "
                      "leave nothing selected to include the whole project.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666;font-size:10px;padding:2px 4px;")
        layout.addWidget(hint)
        self.sec_table = QTableWidget(0,4)
        self.sec_table.setHorizontalHeaderLabels(["Section","Product","Qty","Total"])
        self.sec_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.sec_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (2,3): self.sec_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.sec_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.sec_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.sec_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.sec_table.verticalHeader().setVisible(False)
        self.sec_table.setAlternatingRowColors(True)
        layout.addWidget(self.sec_table)
        return w

    def selected_section_ids(self):
        """Distinct section_ids from selected rows in the By Section tab —
        empty set means no filter (export the whole project)."""
        ids = set()
        for idx in self.sec_table.selectionModel().selectedRows() if self.sec_table.selectionModel() else []:
            item = self.sec_table.item(idx.row(), 0)
            if item is not None:
                sid = item.data(Qt.UserRole)
                if sid is not None:
                    ids.add(sid)
        return ids

    #  Project & section 

    def set_project(self, project_id):
        self._project_id = project_id
        self._active_entity = None
        self._active_section_id = None
        self.active_label.setText("No item selected")
        self.count_label.setText("0")
        self._reload_sections()
        self.refresh_table()

    def _reload_sections(self):
        self.sec_combo.blockSignals(True)
        self.sec_combo.clear()
        self.sec_combo.addItem("All / Unassigned", None)
        if self._project_id:
            for s in db.get_sections(self._project_id):
                self.sec_combo.addItem(s["name"], s["id"])
        self.sec_combo.blockSignals(False)
        self._active_section_id = None

    def _on_section_changed(self, idx):
        self._active_section_id = self.sec_combo.itemData(idx)
        self.refresh_table()
        self._update_count_display()

    def _add_section(self):
        if not self._project_id: return
        name, ok = QInputDialog.getText(self,"New Section","Section name (e.g. Floor 1):")
        if ok and name.strip():
            db.add_section(self._project_id, name.strip())
            self._reload_sections()
            # Select the new section
            for i in range(self.sec_combo.count()):
                if self.sec_combo.itemText(i) == name.strip():
                    self.sec_combo.setCurrentIndex(i); break

    def _del_section(self):
        sid = self.sec_combo.currentData()
        if not sid: return
        name = self.sec_combo.currentText()
        if QMessageBox.question(self,"Delete Section",f"Delete section '{name}'?\nMarks in this section will become unassigned.",
                                QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            db.delete_section(sid)
            self._reload_sections(); self.refresh_table()

    def active_section_id(self):
        return self._active_section_id

    #  Entity selection 

    def _is_linear_active(self):
        e = self._active_entity
        return (e and e["type"] == "assembly" and e["data"].get("is_linear"))

    def set_active_entity(self, entity_type, data):
        self._active_entity = {"type": entity_type, "data": data}
        if entity_type == "product":
            self.active_label.setText(f"Counting: {data['name']}\n{data['code'] or ''}")
        elif data.get("is_linear"):
            self.active_label.setText(
                f"⌇ Linear: {data['name']}\n"
                f"{data.get('wire_count',1)} wire(s)  ·  bundle {data.get('bundle_factor',0.35):.2f}\n"
                "Activate counting, then draw runs on the print"
            )
        else:
            comps = db.get_assembly_items(data["id"])
            comp_str = ", ".join(f"{c['quantity']} {c['name']}" for c in comps)
            self.active_label.setText(f"Assembly: {data['name']}\n{comp_str}")
        self._update_count_display()

    def add_one(self):
        self._increment()

    def subtract_one(self, entity_type, entity_id):
        if not self._project_id: return
        if entity_type == "product":
            db.adjust_item_count(self._project_id, entity_id, -1, self._active_section_id)
        else:
            for item in db.get_assembly_items(entity_id):
                db.adjust_item_count(self._project_id, item["product_id"], -item["quantity"], self._active_section_id)
        self._update_count_display(); self.refresh_table()

    def _increment(self):
        if not self._project_id or not self._active_entity: return
        e = self._active_entity
        if e["type"] == "product":
            db.adjust_item_count(self._project_id, e["data"]["id"], 1, self._active_section_id)
        else:
            for item in db.get_assembly_items(e["data"]["id"]):
                db.adjust_item_count(self._project_id, item["product_id"], item["quantity"], self._active_section_id)
        self._update_count_display(); self.refresh_table()

    def _decrement(self):
        if not self._project_id or not self._active_entity: return
        e = self._active_entity
        if e["type"] == "product":
            db.adjust_item_count(self._project_id, e["data"]["id"], -1, self._active_section_id)
        else:
            for item in db.get_assembly_items(e["data"]["id"]):
                db.adjust_item_count(self._project_id, item["product_id"], -item["quantity"], self._active_section_id)
        self._update_count_display(); self.refresh_table()

    def _update_count_display(self):
        if not self._project_id or not self._active_entity:
            self.count_label.setText("0"); return
        e = self._active_entity
        if self._is_linear_active():
            ft = db.get_assembly_footage(self._project_id, e["data"]["id"])
            self.count_label.setText(f"{ft:.1f}\nft")
            return
        if e["type"] == "product":
            cnt = db.get_item_count(self._project_id, e["data"]["id"], self._active_section_id)
        else:
            comps = db.get_assembly_items(e["data"]["id"])
            if comps:
                q1 = comps[0]["quantity"]
                raw = db.get_item_count(self._project_id, comps[0]["product_id"], self._active_section_id)
                cnt = raw // q1 if q1 else 0
            else:
                cnt = 0
        self.count_label.setText(str(cnt))

    def refresh_table(self):
        if not self._project_id: return
        # Summary tab — point-count items
        items = db.get_all_takeoff_items(self._project_id)
        # Linear run totals
        linear_totals = db.get_linear_run_totals(self._project_id)
        linear_rows = []
        if linear_totals:
            assemblies = {a["id"]: dict(a) for a in db.get_assemblies()}
            for aid, footage in linear_totals.items():
                a = assemblies.get(aid)
                if a:
                    linear_rows.append({"name": a["name"], "footage": footage,
                                        "mat_per_ft": _linear_mat_per_ft(aid)})
        total_rows = len(items) + len(linear_rows)
        self.table.setRowCount(total_rows)
        grand_total, total_qty = 0.0, 0
        for row, item in enumerate(items):
            total = item["count"] * (item["unit_cost"] or 0.0)
            grand_total += total; total_qty += item["count"]
            self.table.setItem(row,0,QTableWidgetItem(item["name"]))
            self.table.setItem(row,1,QTableWidgetItem(item["code"] or ""))
            qi = QTableWidgetItem(str(item["count"])); qi.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row,2,qi)
            ti = QTableWidgetItem(f"${total:,.2f}"); ti.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
            self.table.setItem(row,3,ti)
        for i, lr in enumerate(linear_rows):
            row = len(items) + i
            mat = lr["mat_per_ft"] * lr["footage"]
            grand_total += mat
            self.table.setItem(row,0,QTableWidgetItem(f"⌇ {lr['name']}"))
            self.table.setItem(row,1,QTableWidgetItem("ft"))
            qi = QTableWidgetItem(f"{lr['footage']:.1f}"); qi.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row,2,qi)
            ti = QTableWidgetItem(f"${mat:,.2f}"); ti.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
            self.table.setItem(row,3,ti)
        self.total_label.setText(f"Total: ${grand_total:,.2f}  |  Items: {total_qty}")
        # By Section tab
        breakdown = db.get_section_breakdown(self._project_id)
        self.sec_table.setRowCount(len(breakdown))
        for row, item in enumerate(breakdown):
            total = item["count"] * 0  # no unit_cost in breakdown query; show qty only
            sec_item = QTableWidgetItem(item["section_name"])
            sec_item.setData(Qt.UserRole, item["section_id"])
            self.sec_table.setItem(row,0,sec_item)
            self.sec_table.setItem(row,1,QTableWidgetItem(item["product_name"]))
            qi = QTableWidgetItem(str(item["count"])); qi.setTextAlignment(Qt.AlignCenter)
            self.sec_table.setItem(row,2,qi)
            self.sec_table.setItem(row,3,QTableWidgetItem(""))

    #  Export 

    def _export(self):
        if not self._project_id: QMessageBox.warning(self,"No Project","Open a project first."); return
        section_ids = self.selected_section_ids()
        items = list(db.get_all_takeoff_items(self._project_id, section_ids or None))
        if not items: QMessageBox.information(self,"Empty","No items to export."); return
        proj = next((p for p in db.get_projects() if p["id"]==self._project_id), None)
        pname = proj["name"] if proj else "Takeoff"
        suffix = "_takeoff" if not section_ids else "_takeoff_selected_sections"
        path,_ = QFileDialog.getSaveFileName(self,"Save Excel",f"{pname}{suffix}.xlsx","Excel (*.xlsx)")
        if not path: return
        try:
            candela_breakdown = db.get_candela_breakdown(self._project_id, section_ids or None)
            excel_export.export_takeoff(pname, items, path, candela_breakdown)
            QMessageBox.information(self,"Exported",f"Saved to:\n{path}")
            os.startfile(path)
        except Exception as e:
            QMessageBox.critical(self,"Export Failed",f"Excel export error:\n{e}")

    def _build_submittal(self):
        if not self._project_id: QMessageBox.warning(self,"No Project","Open a project first."); return
        items = list(db.get_all_takeoff_items(self._project_id))
        if not items: QMessageBox.information(self,"Empty","No items in this takeoff."); return

        drawings, skipped = [], []
        for i in items:
            path = i["shop_drawing_path"] if "shop_drawing_path" in i.keys() else ""
            if path and os.path.exists(path):
                drawings.append((dict(i), i["count"]))
            elif i["count"] > 0:
                skipped.append(i["name"])

        if not drawings:
            msg = "No products have shop drawings attached.\nEdit a product and attach a drawing file first."
            if skipped:
                msg += f"\n\nProducts without drawings:\n" + "\n".join(f"   {n}" for n in skipped)
            QMessageBox.information(self,"No Shop Drawings", msg); return

        if skipped:
            msg = (f"{len(skipped)} product(s) have no shop drawing and will be skipped:\n"
                   + "\n".join(f"   {n}" for n in skipped[:10])
                   + ("\n  ..." if len(skipped)>10 else "")
                   + "\n\nContinue with the rest?")
            if QMessageBox.question(self,"Partial Submittal",msg,
                                    QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes:
                return

        proj = next((p for p in db.get_projects() if p["id"]==self._project_id), None)
        pname = proj["name"] if proj else "Submittal"
        self._assemble_submittal_pdf(drawings, pname)

    def _build_submittal_no_counts(self):
        """Build a shop-drawing submittal straight from the product catalogue,
        with no takeoff counts required — for a submittal owed before the quote."""
        dlg = SubmittalProductPickerDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        picked = dlg.selected_products()
        if not picked:
            QMessageBox.information(self, "Nothing Selected", "No products were selected.")
            return
        drawings = [(p, None) for p in picked]
        proj = next((p for p in db.get_projects() if p["id"] == self._project_id), None)
        pname = proj["name"] if proj else "Submittal"
        self._assemble_submittal_pdf(drawings, pname)

    def _assemble_submittal_pdf(self, drawings, pname):
        """drawings: list of (product_dict, qty_or_None). Shared by both the
        counts-based submittal and the no-counts product-picker submittal."""
        # Default to a Submittals subfolder
        default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Submittals")
        os.makedirs(default_dir, exist_ok=True)
        out_path,_ = QFileDialog.getSaveFileName(
            self,"Save Submittal Package",
            os.path.join(default_dir, f"{pname}_Submittal.pdf"), "PDF (*.pdf)")
        if not out_path: return

        prog = QProgressDialog("Building submittal","Cancel",0,len(drawings)+1,self)
        prog.setWindowTitle("Building Submittal"); prog.setMinimumDuration(0); prog.setValue(0)
        try:
            out_doc = fitz.open()
            # Cover page
            cover = out_doc.new_page(width=612, height=792)
            red = (0.75, 0.17, 0.11)
            cover.draw_rect(fitz.Rect(0,0,612,110), color=red, fill=red)
            cover.insert_text((30,55),"DEFENSE FIRE PROTECTION", fontsize=22,color=(1,1,1),fontname="helv")
            cover.insert_text((30,82),"Shop Drawing Submittal Package", fontsize=14,color=(1,1,1),fontname="helv")
            cover.insert_text((30,130),f"Project:  {pname}", fontsize=13,fontname="helv")
            cover.insert_text((30,155),f"Drawings included:  {len(drawings)}", fontsize=11,fontname="helv")
            y = 195
            cover.insert_text((30,y),"Contents:", fontsize=12,fontname="helv",color=(0.17,0.24,0.31)); y+=20
            for i,(p,qty) in enumerate(drawings,1):
                qty_str = f"   qty: {qty}" if qty is not None else ""
                cover.insert_text((30,y),f"  {i}.  {p['name']}  ({p['code'] or ''}){qty_str}",
                                   fontsize=10,fontname="helv"); y+=16
                if y>745: break
            prog.setValue(1)

            known_image_exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
            failed = []
            for i,(p,qty) in enumerate(drawings):
                QApplication.processEvents()
                if prog.wasCanceled(): break
                prog.setValue(i+1)
                drawing_path = p["shop_drawing_path"]
                # One bad/missing/unreadable file shouldn't take down the
                # whole submittal — skip it and report it at the end instead.
                if not drawing_path or not os.path.exists(drawing_path):
                    failed.append(f"{p['name']} — file not found: {drawing_path}")
                    continue
                ext = os.path.splitext(drawing_path)[1].lower()
                try:
                    if ext == ".pdf":
                        src = fitz.open(drawing_path)
                        out_doc.insert_pdf(src); src.close()
                    elif ext in known_image_exts:
                        pg = out_doc.new_page(width=612,height=792)
                        pg.insert_image(fitz.Rect(36,50,576,756), filename=drawing_path)
                        qty_str = f"  (qty: {qty})" if qty is not None else ""
                        pg.insert_text((36,36),f"{p['name']}    {p['code'] or ''}{qty_str}",
                                        fontsize=10,fontname="helv",color=(0.4,0.4,0.4))
                    else:
                        failed.append(f"{p['name']} — unsupported file type: {ext or '(none)'}")
                except Exception as item_err:
                    failed.append(f"{p['name']} — {item_err}")

            prog.setValue(len(drawings)+1)
            out_doc.save(out_path); out_doc.close()
            msg = f"Submittal saved:\n{out_path}"
            if failed:
                msg += "\n\nSkipped (couldn't include):\n" + "\n".join(f"  {f}" for f in failed)
            QMessageBox.information(self,"Done",msg)
            os.startfile(out_path)
        except Exception as e:
            QMessageBox.critical(self,"Error",f"Failed to build submittal:\n{e}")



# ──────────────────────────────────────────────────────────────────────────────
# Scale calibration dialog
# ──────────────────────────────────────────────────────────────────────────────

class ScaleDialog(QDialog):
    """Choose scale by ratio or by known measurement on the drawing."""
    def __init__(self, parent=None, measured_pts=None):
        super().__init__(parent)
        self.setWindowTitle("Set Drawing Scale")
        self.setMinimumWidth(400)
        self._measured_pts = measured_pts  # (QPointF, QPointF) or None
        self.points_per_meter = None       # result
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        hdr = QLabel("Set Drawing Scale")
        hdr.setStyleSheet("font-size:14px;font-weight:bold;color:#ff7002;")
        layout.addWidget(hdr)

        note = QLabel(
            "Coverage circles require a scale so on-screen distances match "
            "real-world metres.  Choose one method below."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # ── Tab 1: Scale ratio ─────────────────────────────────────────────
        tab_ratio = QWidget()
        rl = QFormLayout(tab_ratio)
        rl.setContentsMargins(12, 12, 12, 12)
        rl.setSpacing(10)

        self.scale_edit = QLineEdit("100")
        self.scale_edit.setPlaceholderText("e.g. 100  for 1:100")
        rl.addRow("Scale denominator  (1 : X):", self.scale_edit)

        ratio_note = QLabel(
            "Common architectural scales:\n"
            "  1:50 = enter 50\n"
            "  1:100 = enter 100\n"
            "  1:200 = enter 200\n"
            "  1/4\" = 1:48 ≈ enter 48\n"
            "  1/8\" = 1:96 ≈ enter 96"
        )
        ratio_note.setStyleSheet("color:#666;font-size:11px;")
        rl.addRow(ratio_note)
        self.tabs.addTab(tab_ratio, "Scale Ratio")

        # ── Tab 2: Measure on drawing ──────────────────────────────────────
        tab_meas = QWidget()
        ml = QFormLayout(tab_meas)
        ml.setContentsMargins(12, 12, 12, 12)
        ml.setSpacing(10)

        if self._measured_pts:
            p1, p2 = self._measured_pts
            dx = p2.x() - p1.x(); dy = p2.y() - p1.y()
            self._pixel_dist = (dx*dx + dy*dy) ** 0.5
            dist_lbl = QLabel(f"Measured distance on screen: {self._pixel_dist:.1f} PDF pts")
            ml.addRow(dist_lbl)
        else:
            self._pixel_dist = 0.0
            ml.addRow(QLabel("No measurement taken yet.\nUse 'Measure on Drawing' button first, then click two points."))

        self.real_dist_spin = QDoubleSpinBox()
        self.real_dist_spin.setRange(0.01, 9999)
        self.real_dist_spin.setDecimals(3)
        self.real_dist_spin.setSuffix(" m")
        self.real_dist_spin.setValue(1.0)
        ml.addRow("Real-world length:", self.real_dist_spin)
        self.tabs.addTab(tab_meas, "Measure on Drawing")

        if self._measured_pts:
            self.tabs.setCurrentIndex(1)

        # ── Buttons ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("Apply Scale")
        ok_btn.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        ok_btn.clicked.connect(self._apply)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _apply(self):
        if self.tabs.currentIndex() == 0:
            # Scale ratio method
            try:
                denom = float(self.scale_edit.text().strip())
                if denom <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, "Invalid", "Enter a positive number for the scale denominator.")
                return
            # 1 PDF point = 1/72 inch = 0.352778 mm = 0.000352778 m
            # At scale 1:denom, 1 PDF pt on paper = denom × 0.000352778 m in reality
            # → points_per_meter = 1 / (denom × 0.000352778)
            self.points_per_meter = 1.0 / (denom * 0.000352778)
        else:
            # Measure method
            if self._pixel_dist <= 0:
                QMessageBox.warning(self, "No Measurement", "Use 'Measure on Drawing' first to mark two points.")
                return
            real_m = self.real_dist_spin.value()
            if real_m <= 0:
                QMessageBox.warning(self, "Invalid", "Enter the real-world distance.")
                return
            self.points_per_meter = self._pixel_dist / real_m
        self.accept()


# ──────────────────────────────────────────────────────────────────────────────
# Project manager
# ──────────────────────────────────────────────────────────────────────────────

class ProjectManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Projects"); self.setMinimumSize(480,340)
        self.selected_id = None; self._build_ui(); self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget(); self.list_widget.itemDoubleClicked.connect(self._open); layout.addWidget(self.list_widget)
        btn_row = QHBoxLayout()
        new_btn = QPushButton("New Project"); new_btn.setStyleSheet("background:#ff7002;color:white;padding:6px 14px;"); new_btn.clicked.connect(self._new)
        open_btn = QPushButton("Open Selected"); open_btn.setStyleSheet("background:#232728;color:white;padding:6px 14px;"); open_btn.clicked.connect(self._open)
        del_btn = QPushButton("Delete"); del_btn.setStyleSheet("background:#c02b0a;color:white;padding:6px 14px;"); del_btn.clicked.connect(self._delete)
        cancel_btn = QPushButton("Cancel"); cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(new_btn); btn_row.addWidget(del_btn); btn_row.addStretch(); btn_row.addWidget(cancel_btn); btn_row.addWidget(open_btn)
        layout.addLayout(btn_row)

    def refresh(self):
        self.list_widget.clear()
        for p in db.get_projects():
            item = QListWidgetItem(f"{p['name']}    {p['created_at'][:10]}")
            item.setData(Qt.UserRole, p["id"]); self.list_widget.addItem(item)

    def _new(self):
        name,ok = QInputDialog.getText(self,"New Project","Project name:")
        if ok and name.strip(): self.selected_id=db.create_project(name.strip()); self.accept()

    def _open(self):
        item=self.list_widget.currentItem()
        if item: self.selected_id=item.data(Qt.UserRole); self.accept()

    def _delete(self):
        item=self.list_widget.currentItem()
        if not item: return
        if QMessageBox.question(self,"Delete","Delete this project and all its data?",
                                QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
            db.delete_project(item.data(Qt.UserRole)); self.refresh()


class ExportPdfDialog(QDialog):
    """Lets the user pick which layers go into an exported PDF — in
    particular, Field Notes ON with Marks OFF is how you produce a clean
    print for installers without the internal device-count clutter."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export PDF")
        self.setMinimumWidth(320)
        l = QVBoxLayout(self)
        l.addWidget(QLabel("Include:"))
        self._marks_chk = QCheckBox("Marks (device counts)")
        self._marks_chk.setChecked(True)
        l.addWidget(self._marks_chk)
        self._design_chk = QCheckBox("Design (coverage circles)")
        l.addWidget(self._design_chk)
        self._notes_chk = QCheckBox("Field Notes (markup for installers)")
        l.addWidget(self._notes_chk)

        br = QHBoxLayout()
        ok = QPushButton("Export")
        ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(cancel); br.addWidget(ok)
        l.addLayout(br)

    def selections(self):
        """Returns (draw_marks, draw_design, draw_field_notes)."""
        return self._marks_chk.isChecked(), self._design_chk.isChecked(), self._notes_chk.isChecked()


#
# Main Window
#

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DFP TakeoffPro")
        _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(_icon_path):
            from PyQt5.QtGui import QIcon
            self.setWindowIcon(QIcon(_icon_path))
        self._doc = None
        self._page_index = 0
        self._pdf_path = ""
        self._project_id = None
        self._counting_mode = False
        # Default style for the Field Notes markup layer (independent of counts).
        # Trace lines always match the note color — one shared setting.
        self._last_field_note_color = "#000000"
        self._last_field_note_bold  = False
        self._last_field_note_size  = 10.0
        self._last_field_line_width = 2.0
        self._snip_windows = {}   # {snip_id: SnipWindow} — only currently-open ones
        self._snip_toggle_actions = {}   # {snip_id: QAction} — dynamic Snips ▾ menu entries
        db.init_db()
        self._build_ui()
        QShortcut(QKeySequence("Ctrl+Z"), self, self._undo)

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        self.library_panel = LibraryPanel()
        self.library_panel.setMinimumWidth(260); self.library_panel.setMaximumWidth(340)
        self.library_panel.product_selected.connect(self._on_product_selected)
        self.library_panel.assembly_selected.connect(self._on_assembly_selected)
        splitter.addWidget(self.library_panel)

        centre = QWidget(); cl = QVBoxLayout(centre); cl.setContentsMargins(0,0,0,0); cl.setSpacing(0)
        nav = QHBoxLayout(); nav.setContentsMargins(4,4,4,4)
        self.prev_btn=QPushButton(" Prev"); self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn=QPushButton("Next -"); self.next_btn.clicked.connect(self._next_page)
        self.page_label=QLabel("No PDF loaded"); self.page_label.setAlignment(Qt.AlignCenter)
        zo=QPushButton(""); zo.setFixedWidth(28); zo.clicked.connect(lambda:self.canvas.set_zoom(self.canvas.get_zoom()/1.2))
        zi=QPushButton("+"); zi.setFixedWidth(28); zi.clicked.connect(lambda:self.canvas.set_zoom(self.canvas.get_zoom()*1.2))
        fit=QPushButton("Fit"); fit.setFixedWidth(36); fit.clicked.connect(self._fit_page)
        for w in (self.prev_btn,self.next_btn,self.page_label): nav.addWidget(w)
        nav.addStretch()
        for w in (zo,zi,fit): nav.addWidget(w)
        cl.addLayout(nav)

        self.count_banner = QLabel("COUNTING MODE    Click to count  |  Ctrl+drag to pan  |  Ctrl+scroll to zoom  |  Ctrl+Z to undo")
        self.count_banner.setAlignment(Qt.AlignCenter)
        self.count_banner.setStyleSheet("background:#ff7002;color:white;font-weight:bold;padding:4px;font-size:11px;")
        self.count_banner.setVisible(False); cl.addWidget(self.count_banner)

        self.scroll_area = QScrollArea(); self.scroll_area.setWidgetResizable(False)
        self.canvas = PdfCanvas()
        self.canvas.clicked_point.connect(self._on_canvas_click)
        self.canvas.pan_delta.connect(self._on_pan_delta)
        self.canvas.zoom_requested.connect(self._on_zoom_requested)
        self.canvas.mark_deleted.connect(self._on_mark_deleted)
        self.canvas.mark_candela_changed.connect(self._on_mark_candela_changed)
        self.canvas.linear_run_completed.connect(self._on_linear_run_completed)
        self.canvas.run_deleted.connect(self._on_run_deleted)
        self.canvas.field_note_placed.connect(self._on_field_note_placed)
        self.canvas.field_line_completed.connect(self._on_field_line_completed)
        self.canvas.field_note_deleted.connect(self._on_field_note_deleted)
        self.canvas.field_line_deleted.connect(self._on_field_line_deleted)
        self.canvas.field_note_edit_requested.connect(self._on_field_note_edit_requested)
        self.canvas.snip_rect_selected.connect(self._on_snip_rect_selected)
        self.scroll_area.setWidget(self.canvas); cl.addWidget(self.scroll_area)
        splitter.addWidget(centre)

        self.takeoff_panel = TakeoffPanel()
        self.takeoff_panel.setMinimumWidth(310); self.takeoff_panel.setMaximumWidth(420)
        splitter.addWidget(self.takeoff_panel)

        splitter.setStretchFactor(0,0); splitter.setStretchFactor(1,1); splitter.setStretchFactor(2,0)
        splitter.setSizes([280,880,380])
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._scale_warning = QLabel("  ⚠  Design Mode: no scale set — use 'Set Scale…' or 'Measure on Drawing'  ")
        self._scale_warning.setStyleSheet(
            "color:#ff7002; font-size:11px; font-weight:bold; padding:0 6px;"
        )
        self._scale_warning.setVisible(False)
        sb.addPermanentWidget(self._scale_warning)
        self._build_toolbar()

    def _build_toolbar(self):
        tb = QToolBar("Main"); tb.setMovable(False); self.addToolBar(tb)
        for label, slot in [("Projects", self._open_project_manager), ("Load PDF", self._load_pdf),
                            ("Manage Pages…", self._manage_pages)]:
            a = QAction(label, self); a.triggered.connect(slot); tb.addAction(a)
        tb.addSeparator()
        self.count_action = QAction("Start Counting", self); self.count_action.setCheckable(True)
        self.count_action.triggered.connect(self._toggle_counting); tb.addAction(self.count_action)
        a = QAction("Clear Marks (page)", self); a.triggered.connect(self.canvas.clear_marks_current_page); tb.addAction(a)
        tb.addSeparator()
        a = QAction("Export PDF", self); a.triggered.connect(self._export_pdf_menu); tb.addAction(a)
        tb.addSeparator()
        # "Designers" groups the 3 design tools behind one dropdown (opens on
        # hover or click) instead of each sitting as its own always-visible
        # toolbar button — same idea applied below to "Quotes".
        # Kept as self.* attributes (not locals) so nothing about them is
        # eligible for Python-side garbage collection once _build_toolbar()
        # returns — Qt's C++ parent-child ownership alone is supposed to be
        # enough, but a persisted Python reference is a cheap extra guard
        # against the classic "menu/action + its connected lambda got GC'd
        # out from under Qt" crash class.
        self._designers_btn = HoverMenuButton("Designers ▾")
        self._designers_menu = QMenu(self._designers_btn); self._designers_menu.setStyleSheet(MENU_STYLE)
        a = self._designers_menu.addAction("Suppression Designer")
        a.triggered.connect(self._open_suppression_designer)
        a = self._designers_menu.addAction("Paint Booth Designer")
        a.setToolTip("Design dry chemical suppression for vehicle spray booths (Badger Industry Guard)")
        a.triggered.connect(self._open_paint_booth_designer)
        a = self._designers_menu.addAction("Drawing Designer")
        a.setToolTip("Draw scaled floor plans, place electrical/low-voltage/furniture symbols, "
                     "and export quote-ready PDFs. Includes freeform wiring diagram and fire "
                     "alarm one-line diagram tabs.")
        a.triggered.connect(self._open_drawing_designer)
        a = self._designers_menu.addAction("Fire Plan Builder")
        a.setToolTip("Assemble an AHJ Fire Safety Plan submission package (starting with Calgary): "
                     "Vital Building Information form, base building drawings, fire alarm zone "
                     "drawings, and maintenance certificates, in the required order.")
        a.triggered.connect(self._open_fire_plan_builder)
        self._designers_btn.setMenu(self._designers_menu)
        tb.addWidget(self._designers_btn)

        # ── Estimating ────────────────────────────────────────────────────
        tb.addSeparator()
        self._quotes_btn = HoverMenuButton("Quotes ▾")
        self._quotes_menu = QMenu(self._quotes_btn); self._quotes_menu.setStyleSheet(MENU_STYLE)
        a = self._quotes_menu.addAction("PMA Quote")
        a.setToolTip("Build a PMA inspection quote for all fire protection disciplines")
        a.triggered.connect(self._open_pma_quote)
        a = self._quotes_menu.addAction("Install Estimate")
        a.setToolTip("Build an installation estimate with material takeoff and labour hours")
        a.triggered.connect(self._open_install_estimate)
        a = self._quotes_menu.addAction("Programming")
        a.setToolTip("Calculate programming and V.I. hours and sell price")
        a.triggered.connect(self._open_programming)
        self._quotes_btn.setMenu(self._quotes_menu)
        tb.addWidget(self._quotes_btn)

        # ── Design Mode ────────────────────────────────────────────────────
        tb.addSeparator()
        self.design_action = QAction("Design Mode", self)
        self.design_action.setCheckable(True)
        self.design_action.triggered.connect(self._toggle_design_mode)
        tb.addAction(self.design_action)

        # ── Measure tools ─────────────────────────────────────────────────
        # 5 previously-separate buttons (scale calibration + the ad-hoc
        # ruler/area scratch tools) behind one dropdown. A plain QMenu here
        # (not MultiCheckMenu) closes after each pick — right, since picking
        # one of these is "now go click on the canvas," not "toggle several
        # flags in a row."
        tb.addSeparator()
        self._measure_btn = HoverMenuButton("Measure ▾")
        self._measure_menu = QMenu(self._measure_btn); self._measure_menu.setStyleSheet(MENU_STYLE)

        self.measure_action = QAction("Measure on Drawing", self)
        self.measure_action.setCheckable(True)
        self.measure_action.setToolTip(
            "Click two points on the drawing to measure a known distance, "
            "then enter the real-world length to set the scale."
        )
        self.measure_action.triggered.connect(self._start_measure)
        self._measure_menu.addAction(self.measure_action)

        a = QAction("Set Scale…", self)
        a.setToolTip("Enter a scale ratio (e.g. 1:100) to calibrate coverage circles.")
        a.triggered.connect(self._set_scale_ratio)
        self._measure_menu.addAction(a)

        self._measure_menu.addSeparator()
        self.measure_length_action = QAction("Measure Length", self)
        self.measure_length_action.setCheckable(True)
        self.measure_length_action.setToolTip(
            "Click points along a run, double-click to finish and see the total length.\n"
            "Requires a scale — set one first with 'Measure on Drawing' or 'Set Scale…'.\n"
            "This is a scratch measurement, not a counted takeoff item."
        )
        self.measure_length_action.triggered.connect(lambda c: self._toggle_measure("length", c))
        self._measure_menu.addAction(self.measure_length_action)

        self.measure_area_action = QAction("Measure Area", self)
        self.measure_area_action.setCheckable(True)
        self.measure_area_action.setToolTip(
            "Click each corner of the area, then click back near the first point "
            "(or press Enter) to close it and see the square footage.\n"
            "Requires a scale — set one first with 'Measure on Drawing' or 'Set Scale…'.\n"
            "This is a scratch measurement, not a counted takeoff item."
        )
        self.measure_area_action.triggered.connect(lambda c: self._toggle_measure("area", c))
        self._measure_menu.addAction(self.measure_area_action)

        a = QAction("Clear Measurements (page)", self)
        a.triggered.connect(self.canvas.clear_measurements_current_page)
        self._measure_menu.addAction(a)

        self._measure_btn.setMenu(self._measure_menu)
        tb.addWidget(self._measure_btn)

        self.canvas.measurement_completed.connect(self._on_measurement_completed)

        # Field Notes markup layer — separate dropdown from Coverage since it
        # needs tool-activation actions and color pickers, not just on/off
        # toggles. This is the "clean print for installers" layer: it can be
        # hidden on-screen and left out of exports independently of the
        # device-count marks, so the export doesn't dump internal takeoff
        # info on installers who only need the handwritten-style notes.
        tb.addSeparator()
        self._field_notes_btn = HoverMenuButton("Field Notes ▾")
        self._field_notes_menu = QMenu(self._field_notes_btn); self._field_notes_menu.setStyleSheet(MENU_STYLE)

        self.field_note_action = QAction("Add Note", self)
        self.field_note_action.setCheckable(True)
        self.field_note_action.setToolTip("Click the drawing to place a styled text note (e.g. an address by a device).")
        self.field_note_action.triggered.connect(self._toggle_field_note_mode)
        self._field_notes_menu.addAction(self.field_note_action)

        self.field_line_action = QAction("Trace Line", self)
        self.field_line_action.setCheckable(True)
        self.field_line_action.setToolTip("Click points to draw a trace/leader line, double-click to finish.")
        self.field_line_action.triggered.connect(self._toggle_field_line_mode)
        self._field_notes_menu.addAction(self.field_line_action)

        self._field_notes_menu.addSeparator()
        a = QAction("Note/Line Color…", self)
        a.setToolTip("Default color for new notes and trace lines — trace lines always match the note color.")
        a.triggered.connect(self._pick_field_note_color)
        self._field_notes_menu.addAction(a)

        self.field_note_bold_action = QAction("Bold Notes", self)
        self.field_note_bold_action.setCheckable(True)
        self.field_note_bold_action.setChecked(self._last_field_note_bold)
        self.field_note_bold_action.triggered.connect(self._toggle_field_note_bold_default)
        self._field_notes_menu.addAction(self.field_note_bold_action)

        self._field_notes_menu.addSeparator()
        a = QAction("Clear Field Notes (page)", self); a.triggered.connect(self._clear_field_notes_page)
        self._field_notes_menu.addAction(a)
        a = QAction("Clear Trace Lines (page)", self); a.triggered.connect(self._clear_field_lines_page)
        self._field_notes_menu.addAction(a)

        self._field_notes_menu.addSeparator()
        self.show_field_notes_action = QAction("Show Field Notes", self)
        self.show_field_notes_action.setCheckable(True)
        self.show_field_notes_action.setChecked(True)
        self.show_field_notes_action.triggered.connect(self.canvas.set_field_notes_visible)
        self._field_notes_menu.addAction(self.show_field_notes_action)

        self._field_notes_btn.setMenu(self._field_notes_menu)
        tb.addWidget(self._field_notes_btn)

        # Snips — pinned crops (e.g. the symbol legend sitting on another
        # page) as their own floating, freely resizable/movable windows, so
        # you don't have to flip pages back and forth to check them.
        # MultiCheckMenu so switching several snips on/off in a row doesn't
        # require reopening the dropdown each time — only the per-snip
        # toggles are checkable, so "New Snip"/"Manage Snips…" still close
        # the menu normally on click.
        tb.addSeparator()
        self._snips_btn = HoverMenuButton("Snips ▾")
        self._snips_menu = MultiCheckMenu(self._snips_btn); self._snips_menu.setStyleSheet(MENU_STYLE)
        self._new_snip_action = QAction("New Snip", self)
        self._new_snip_action.setToolTip("Drag a box around anything (e.g. a legend) to pin it in its own window.")
        self._new_snip_action.triggered.connect(self._start_snip_mode)
        self._snips_menu.addAction(self._new_snip_action)
        self._snips_sep_top = self._snips_menu.addSeparator()
        self._snips_sep_bottom = self._snips_menu.addSeparator()
        manage_snips_action = QAction("Manage Snips…", self)
        manage_snips_action.triggered.connect(self._manage_snips)
        self._snips_menu.addAction(manage_snips_action)
        self._snips_btn.setMenu(self._snips_menu)
        tb.addWidget(self._snips_btn)

        # Per-type coverage toggles — MultiCheckMenu so turning several
        # layers on/off doesn't require reopening the dropdown each time.
        tb.addSeparator()
        self._coverage_btn = HoverMenuButton("Coverage ▾")
        self._coverage_menu = MultiCheckMenu(self._coverage_btn); self._coverage_menu.setStyleSheet(MENU_STYLE)
        self._cov_toggles = {}
        for ctype, label in COVERAGE_LABELS.items():
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(True)
            act.triggered.connect(lambda checked, t=ctype: self._toggle_coverage_type(t, checked))
            self._coverage_menu.addAction(act)
            self._cov_toggles[ctype] = act
        self._coverage_btn.setMenu(self._coverage_menu)
        tb.addWidget(self._coverage_btn)

        # Help
        tb.addSeparator()
        a = QAction("Help", self)
        a.triggered.connect(self._show_help)
        tb.addAction(a)

        # Wire up scale-measurement callback
        self.canvas.scale_measured.connect(self._on_scale_measured)

    # ── Design-mode handlers ──────────────────────────────────────────────────

    def _show_help(self):
        from help_system import HelpDialog, TAKEOFF_MANUAL
        dlg = HelpDialog(TAKEOFF_MANUAL, "Takeoff", self)
        dlg.exec_()

    def _toggle_design_mode(self, checked):
        self.canvas.set_design_mode(checked)
        if checked:
            self._load_page_scale()
            self._update_scale_warning()
        else:
            self._scale_warning.setVisible(False)
            self.statusBar().showMessage("Design Mode off.")

    def _update_scale_warning(self):
        no_scale = self.canvas._points_per_meter == 0.0
        self._scale_warning.setVisible(self.design_action.isChecked() and no_scale)

    def _load_page_scale(self):
        if not self._project_id or not self._pdf_path:
            return
        ppm = db.get_page_scale(self._project_id, self._pdf_path, self._page_index)
        self.canvas.set_page_scale(ppm if ppm else 0.0)

    def _toggle_coverage_type(self, ctype, checked):
        self.canvas.set_coverage_visible(ctype, checked)

    def _start_measure(self, checked):
        if checked:
            self.measure_length_action.setChecked(False)
            self.measure_area_action.setChecked(False)
            self.canvas.set_measure_mode(None)
            self.canvas.set_scale_mode(True)
            self.statusBar().showMessage(
                "Measure: click the FIRST point on a known dimension…"
            )
        else:
            self.canvas.set_scale_mode(False)
            self.statusBar().showMessage("Measurement cancelled.")

    def _toggle_measure(self, mode, checked):
        """Ad-hoc ruler/area tool — a scratch measurement (not a counted
        takeoff item) for eyeballing a length or square footage on the
        print. Requires the page scale to already be set."""
        other_action = self.measure_area_action if mode == "length" else self.measure_length_action
        if checked:
            ppm = self.canvas._points_per_meter
            if self._project_id and self._pdf_path:
                ppm = db.get_page_scale(self._project_id, self._pdf_path, self._page_index) or ppm
            if not ppm:
                (self.measure_length_action if mode == "length" else self.measure_area_action).setChecked(False)
                QMessageBox.warning(self, "No Scale Set",
                    "This page has no scale set.\n\n"
                    "Use 'Measure on Drawing' or 'Set Scale…' before measuring length/area.")
                return
            other_action.setChecked(False)
            self.measure_action.setChecked(False)
            self.canvas.set_scale_mode(False)
            if self.count_action.isChecked():
                self.count_action.setChecked(False)
                self._toggle_counting(False)
            if self.field_note_action.isChecked() or self.field_line_action.isChecked():
                self.field_note_action.setChecked(False)
                self.field_line_action.setChecked(False)
                self.canvas.set_field_note_mode(False)
                self.canvas.set_field_line_mode(False)
            self.canvas.set_snip_mode(False)
            self.canvas.set_measure_mode(mode)
            if mode == "length":
                self.statusBar().showMessage(
                    "Measure Length: click each point, double-click to finish  |  "
                    "Shift = diagonal  |  Esc/right-click = cancel")
            else:
                self.statusBar().showMessage(
                    "Measure Area: click each corner, click back near the start "
                    "(or press Enter) to close it  |  Esc/right-click = cancel")
        else:
            self.canvas.set_measure_mode(None)
            self.statusBar().showMessage("Measure tool off.")

    def _on_measurement_completed(self, mode, value):
        unit = "ft" if mode == "length" else "SF"
        self.statusBar().showMessage(f"Measured {mode}: {value:.1f} {unit}", 8000)

    # ── Field Notes markup layer ────────────────────────────────────────────

    def _toggle_field_note_mode(self, checked):
        if checked:
            self.field_line_action.setChecked(False)
            self.canvas.set_field_line_mode(False)
            if self.count_action.isChecked():
                self.count_action.setChecked(False)
                self._toggle_counting(False)
            self.canvas.set_measure_mode(None)
            self.measure_length_action.setChecked(False)
            self.measure_area_action.setChecked(False)
            self.canvas.set_snip_mode(False)
            self.canvas.set_field_note_mode(True, self._last_field_note_color,
                                            self._last_field_note_bold, self._last_field_note_size)
            self.statusBar().showMessage("Add Note: click the drawing to place a text note.")
        else:
            self.canvas.set_field_note_mode(False)
            self.statusBar().showMessage("Add Note off.")

    def _toggle_field_line_mode(self, checked):
        if checked:
            self.field_note_action.setChecked(False)
            self.canvas.set_field_note_mode(False)
            if self.count_action.isChecked():
                self.count_action.setChecked(False)
                self._toggle_counting(False)
            self.canvas.set_measure_mode(None)
            self.measure_length_action.setChecked(False)
            self.measure_area_action.setChecked(False)
            self.canvas.set_snip_mode(False)
            # Trace lines always match the note color — one shared setting.
            self.canvas.set_field_line_mode(True, self._last_field_note_color, self._last_field_line_width)
            self.statusBar().showMessage(
                "Trace Line: click each point, double-click to finish  |  Esc/right-click = cancel")
        else:
            self.canvas.set_field_line_mode(False)
            self.statusBar().showMessage("Trace Line off.")

    def _pick_field_note_color(self):
        c = QColorDialog.getColor(QColor(self._last_field_note_color), self, "Note / Line Color")
        if c.isValid():
            self._last_field_note_color = c.name()
            if self.field_note_action.isChecked():
                self.canvas.set_field_note_mode(True, self._last_field_note_color,
                                                self._last_field_note_bold, self._last_field_note_size)
            if self.field_line_action.isChecked():
                self.canvas.set_field_line_mode(True, self._last_field_note_color, self._last_field_line_width)

    def _toggle_field_note_bold_default(self, checked):
        self._last_field_note_bold = checked
        if self.field_note_action.isChecked():
            self.canvas.set_field_note_mode(True, self._last_field_note_color,
                                            self._last_field_note_bold, self._last_field_note_size)

    def _clear_field_notes_page(self):
        key = (self.canvas._pdf_path, self.canvas._page_index)
        for n in self.canvas._page_field_notes.get(key, []):
            if n["db_id"]:
                db.delete_field_note(n["db_id"])
        self.canvas._page_field_notes.pop(key, None)
        self.canvas._paint_overlay()

    def _clear_field_lines_page(self):
        key = (self.canvas._pdf_path, self.canvas._page_index)
        for l in self.canvas._page_field_lines.get(key, []):
            if l["id"]:
                db.delete_field_line(l["id"])
        self.canvas._page_field_lines.pop(key, None)
        self.canvas._paint_overlay()

    def _on_field_note_placed(self, page_pt):
        from field_note_dialog import FieldNoteDialog
        dlg = FieldNoteDialog(color=self._last_field_note_color, bold=self._last_field_note_bold,
                              font_size=self._last_field_note_size, parent=self)
        if dlg.exec_() != QDialog.Accepted or not dlg.text():
            return
        note_id = db.add_field_note(self._project_id, self._pdf_path, self._page_index,
                                    page_pt.x(), page_pt.y(), dlg.text(), dlg.color(),
                                    int(dlg.bold()), dlg.font_size())
        self.canvas.add_field_note(page_pt.x(), page_pt.y(), dlg.text(), dlg.color(),
                                   dlg.bold(), dlg.font_size(), db_id=note_id)
        self._last_field_note_color = dlg.color()
        self._last_field_note_bold  = dlg.bold()
        self._last_field_note_size  = dlg.font_size()

    def _on_field_note_edit_requested(self, note):
        from field_note_dialog import FieldNoteDialog
        dlg = FieldNoteDialog(text=note["text"], color=note["color"], bold=note["bold"],
                              font_size=note["font_size"], parent=self)
        if dlg.exec_() != QDialog.Accepted or not dlg.text():
            return
        if note["db_id"]:
            db.update_field_note(note["db_id"], dlg.text(), dlg.color(), int(dlg.bold()), dlg.font_size())
        self.canvas.update_field_note_by_id(note["db_id"], dlg.text(), dlg.color(), dlg.bold(), dlg.font_size())

    def _on_field_line_completed(self, points_json):
        line_id = db.add_field_line(self._project_id, self._pdf_path, self._page_index,
                                    points_json, self._last_field_note_color, self._last_field_line_width)
        self.canvas.add_field_line({"id": line_id, "pdf_path": self._pdf_path,
                                    "page_index": self._page_index, "points": points_json,
                                    "color": self._last_field_note_color, "width": self._last_field_line_width})

    def _on_field_note_deleted(self, db_id):
        if db_id:
            db.delete_field_note(db_id)

    def _on_field_line_deleted(self, db_id):
        if db_id:
            db.delete_field_line(db_id)

    # ── Snips — pinned reference windows ────────────────────────────────────

    def _start_snip_mode(self):
        if not self._doc:
            QMessageBox.warning(self, "No PDF", "Load a PDF first.")
            return
        if self.count_action.isChecked():
            self.count_action.setChecked(False)
            self._toggle_counting(False)
        self.canvas.set_measure_mode(None)
        self.measure_length_action.setChecked(False)
        self.measure_area_action.setChecked(False)
        if self.field_note_action.isChecked() or self.field_line_action.isChecked():
            self.field_note_action.setChecked(False)
            self.field_line_action.setChecked(False)
            self.canvas.set_field_note_mode(False)
            self.canvas.set_field_line_mode(False)
        self.canvas.set_snip_mode(True)
        self.statusBar().showMessage(
            "New Snip: drag a box around the area to capture  |  Esc/right-click = cancel")

    def _on_snip_rect_selected(self, rect):
        if not self._project_id or not self._doc:
            return
        name, ok = QInputDialog.getText(self, "Name This Snip", 'Name (e.g. "FA Legend"):')
        if not ok or not name.strip():
            self.statusBar().showMessage("Snip cancelled.")
            return
        name = name.strip()
        page = self._doc[self._page_index]
        clip = fitz.Rect(rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height())
        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=clip, alpha=False)
        png_bytes = pix.tobytes("png")
        snip_id = db.add_snip(self._project_id, name, png_bytes)
        self._open_snip_window(snip_id, name, png_bytes, 80, 80, 320, 240)
        self._rebuild_snips_menu()
        self.statusBar().showMessage(f"Snip '{name}' created.")

    def _open_snip_window(self, snip_id, name, image_bytes, x, y, w, h):
        from snip_window import SnipWindow
        win = SnipWindow(snip_id, name, image_bytes, parent=self)
        win.setGeometry(x, y, w, h)
        win.closed.connect(self._on_snip_window_closed)
        win.geometry_changed.connect(self._on_snip_geometry_changed)
        self._snip_windows[snip_id] = win
        win.show()
        if snip_id in self._snip_toggle_actions:
            act = self._snip_toggle_actions[snip_id]
            act.blockSignals(True); act.setChecked(True); act.blockSignals(False)

    def _on_snip_window_closed(self, snip_id):
        self._snip_windows.pop(snip_id, None)
        db.set_snip_visible(snip_id, False)
        if snip_id in self._snip_toggle_actions:
            act = self._snip_toggle_actions[snip_id]
            act.blockSignals(True); act.setChecked(False); act.blockSignals(False)

    def _on_snip_geometry_changed(self, snip_id, x, y, w, h):
        db.update_snip_geometry(snip_id, x, y, w, h)

    def _toggle_snip_visibility(self, snip_id, checked):
        if checked:
            if snip_id in self._snip_windows:
                return
            img = db.get_snip_image(snip_id)
            row = next((s for s in db.get_snips(self._project_id) if s["id"] == snip_id), None)
            if not img or not row:
                return
            db.set_snip_visible(snip_id, True)
            self._open_snip_window(snip_id, row["name"], img,
                                   row["win_x"], row["win_y"], row["win_w"], row["win_h"])
        else:
            win = self._snip_windows.get(snip_id)
            if win:
                win.close()   # triggers closeEvent -> _on_snip_window_closed
            else:
                db.set_snip_visible(snip_id, False)

    def _rebuild_snips_menu(self):
        for act in list(self._snip_toggle_actions.values()):
            self._snips_menu.removeAction(act)
        self._snip_toggle_actions = {}
        if not self._project_id:
            return
        for s in db.get_snips(self._project_id):
            act = QAction(s["name"], self)
            act.setCheckable(True)
            act.setChecked(s["id"] in self._snip_windows)
            act.triggered.connect(lambda checked, sid=s["id"]: self._toggle_snip_visibility(sid, checked))
            self._snips_menu.insertAction(self._snips_sep_bottom, act)
            self._snip_toggle_actions[s["id"]] = act

    def _manage_snips(self):
        if not self._project_id:
            QMessageBox.warning(self, "No Project", "Open a project first.")
            return
        from snip_window import ManageSnipsDialog
        dlg = ManageSnipsDialog(self._project_id, self)
        dlg.exec_()
        existing = {s["id"]: s["name"] for s in db.get_snips(self._project_id)}
        for sid in list(self._snip_windows.keys()):
            if sid not in existing:
                self._snip_windows[sid].close()
            else:
                self._snip_windows[sid].set_name(existing[sid])
        self._rebuild_snips_menu()

    def _restore_snip_windows(self):
        """Called whenever the open project changes — close whatever snip
        windows belonged to the previous project, then reopen (at their
        saved position/size) whichever snips were left visible for the
        newly opened one."""
        for win in list(self._snip_windows.values()):
            win.close()
        self._snip_windows = {}
        if self._project_id:
            for s in db.get_snips(self._project_id):
                if s["visible"]:
                    img = db.get_snip_image(s["id"])
                    if img:
                        self._open_snip_window(s["id"], s["name"], img,
                                               s["win_x"], s["win_y"], s["win_w"], s["win_h"])
        self._rebuild_snips_menu()

    def _on_scale_measured(self, pt1, pt2):
        """Called after user clicks two points; opens ScaleDialog to enter real distance."""
        self.measure_action.setChecked(False)
        dlg = ScaleDialog(self, measured_pts=(pt1, pt2))
        if dlg.exec_() == QDialog.Accepted and dlg.points_per_meter:
            self._apply_scale(dlg.points_per_meter)

    def _set_scale_ratio(self):
        """Open ScaleDialog in ratio-entry mode."""
        dlg = ScaleDialog(self, measured_pts=None)
        if dlg.exec_() == QDialog.Accepted and dlg.points_per_meter:
            self._apply_scale(dlg.points_per_meter)

    def _apply_scale(self, points_per_meter):
        if self._project_id and self._pdf_path:
            db.set_page_scale(self._project_id, self._pdf_path,
                              self._page_index, points_per_meter)
        self.canvas.set_page_scale(points_per_meter)
        if not self.design_action.isChecked():
            self.design_action.setChecked(True)
            self.canvas.set_design_mode(True)
        self._update_scale_warning()
        self.statusBar().showMessage(
            f"Scale set: {points_per_meter:.1f} PDF pts/m  "
            f"(≈ 1:{round(1.0 / (points_per_meter * 0.000352778))})"
        )

    #  Project & PDF

    def _open_project_manager(self):
        dlg = ProjectManagerDialog(self)
        if dlg.exec_() == QDialog.Accepted and dlg.selected_id:
            self._project_id = dlg.selected_id
            self.takeoff_panel.set_project(self._project_id)
            for p in db.get_projects():
                if p["id"]==self._project_id and p["pdf_path"]:
                    self._open_pdf(p["pdf_path"]); break
            self._restore_snip_windows()
            self._update_title()

    def _load_pdf(self):
        if not self._project_id: QMessageBox.warning(self,"No Project","Open or create a project first."); return
        path,_ = QFileDialog.getOpenFileName(self,"Open PDF","","PDF Files (*.pdf)")
        if path: self._open_pdf(path); db.update_project_pdf(self._project_id,path)

    def _manage_pages(self):
        if not self._doc:
            QMessageBox.warning(self, "No PDF", "Load a PDF first.")
            return
        from manage_pages_dialog import ManagePagesDialog
        dlg = ManagePagesDialog(self._doc, self._project_id, self._pdf_path, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        kept, labels = dlg.result_data()
        if kept == list(range(len(self._doc))) and not dlg.labels_changed():
            return  # nothing changed — skip the file rewrite entirely
        try:
            backup_path = os.path.splitext(self._pdf_path)[0] + "_backup.pdf"
            shutil.copy2(self._pdf_path, backup_path)
            # fitz refuses to save a restructured (select()'d) document back
            # over the exact path it was opened from — write to a scratch
            # file first, then atomically swap it into place.
            tmp_path = self._pdf_path + ".tmp"
            new_doc = fitz.open(self._pdf_path)   # fresh copy — self._doc stays untouched until this succeeds
            new_doc.select(kept)
            new_doc.save(tmp_path)
            new_doc.close()
            self._doc.close()
            os.replace(tmp_path, self._pdf_path)
            db.rewrite_page_data(self._project_id, self._pdf_path, kept)
            for new_idx, label in labels.items():
                db.set_page_label(self._project_id, self._pdf_path, new_idx, label)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update pages:\n{e}")
            return
        self._open_pdf(self._pdf_path)
        self.statusBar().showMessage(f"Pages updated — backup saved to {os.path.basename(backup_path)}")

    def _open_pdf(self, path):
        if not os.path.exists(path): self.statusBar().showMessage(f"PDF not found: {path}"); return
        self._doc = fitz.open(path)
        self._pdf_path = path
        self._page_index = 0
        if self._project_id:
            saved = db.get_marks(self._project_id, path)
            # Enrich marks with coverage data from product catalogue
            products = {p["id"]: dict(p) for p in db.get_products()}
            enriched = []
            for m in saved:
                m = dict(m)
                if m["entity_type"] == "product" and m["entity_id"] in products:
                    ctype, cr_m = _coverage_for_product(products[m["entity_id"]])
                else:
                    ctype, cr_m = "", 0.0
                m["coverage_type"] = ctype
                m["coverage_radius_m"] = cr_m
                enriched.append(m)
            self.canvas.load_saved_marks(enriched)
            # Load saved linear runs
            saved_runs = [dict(r) for r in db.get_linear_runs(self._project_id, path)]
            for r in saved_runs:
                r["color"] = color_for_id(r["assembly_id"])
            self.canvas.load_saved_runs(saved_runs)
            # Restore saved scale for page 0
            ppm = db.get_page_scale(self._project_id, path, 0)
            self.canvas.set_page_scale(ppm if ppm else 0.0)
            # Load saved field notes / trace lines (independent markup layer)
            self.canvas.load_saved_field_notes(db.get_field_notes(self._project_id, path))
            self.canvas.load_saved_field_lines(db.get_field_lines(self._project_id, path))
        self._show_page()
        self.statusBar().showMessage(f"Loaded: {os.path.basename(path)}")

    def _update_page_label(self):
        total = len(self._doc) if self._doc else 0
        text = f"Page {self._page_index+1} of {total}"
        if self._project_id and self._pdf_path:
            lbl = db.get_page_label(self._project_id, self._pdf_path, self._page_index)
            if lbl:
                text += f"  —  {lbl}"
        self.page_label.setText(text)

    def _show_page(self):
        if not self._doc: return
        self.canvas.load_page(self._doc, self._page_index, self._pdf_path)
        total = len(self._doc)
        self._update_page_label()
        self.prev_btn.setEnabled(self._page_index>0)
        self.next_btn.setEnabled(self._page_index<total-1)
        # Restore scale for this page (may differ per page)
        if self._project_id and self._pdf_path:
            ppm = db.get_page_scale(self._project_id, self._pdf_path, self._page_index)
            self.canvas.set_page_scale(ppm if ppm else 0.0)
            self._update_scale_warning()

    def _prev_page(self):
        if self._doc and self._page_index>0:
            self._page_index-=1; self.canvas.set_page(self._page_index)
            self._update_page_label()
            self.prev_btn.setEnabled(self._page_index>0); self.next_btn.setEnabled(True)

    def _next_page(self):
        if self._doc and self._page_index<len(self._doc)-1:
            self._page_index+=1; self.canvas.set_page(self._page_index)
            total=len(self._doc)
            self._update_page_label()
            self.prev_btn.setEnabled(True); self.next_btn.setEnabled(self._page_index<total-1)

    def _fit_page(self):
        if not self._doc: return
        page=self._doc[self._page_index]; rect=page.rect
        self.canvas.set_zoom(min((self.scroll_area.width()-20)/rect.width,
                                 (self.scroll_area.height()-20)/rect.height))

    #  Counting 

    def _toggle_counting(self, checked):
        self._counting_mode = checked
        if checked and (self.measure_length_action.isChecked() or self.measure_area_action.isChecked()):
            self.measure_length_action.setChecked(False)
            self.measure_area_action.setChecked(False)
            self.canvas.set_measure_mode(None)
        if checked and (self.field_note_action.isChecked() or self.field_line_action.isChecked()):
            self.field_note_action.setChecked(False)
            self.field_line_action.setChecked(False)
            self.canvas.set_field_note_mode(False)
            self.canvas.set_field_line_mode(False)
        if checked:
            self.canvas.set_snip_mode(False)
        e = self.takeoff_panel._active_entity
        is_linear = e and e["type"] == "assembly" and e["data"].get("is_linear")

        if is_linear and checked:
            # Check page scale before allowing linear drawing
            if self._project_id and self._pdf_path:
                ppm = db.get_page_scale(self._project_id, self._pdf_path, self._page_index)
                if not ppm:
                    self.count_action.setChecked(False)
                    QMessageBox.warning(self, "No Scale Set",
                        "This page has no scale set.\n\n"
                        "Use 'Measure on Drawing' to set the scale before drawing runs.")
                    return
            color = color_for_id(e["data"]["id"])
            self.canvas.set_linear_mode(True, e["data"]["id"], color)
            self.canvas.set_counting_mode(False)
            self.count_banner.setText(
                "DRAW RUN MODE    Click start → click end → double-click to finish  |  Shift = diagonal  |  Esc / right-click = cancel"
            )
            self.count_banner.setVisible(True)
            self.count_action.setText("Stop Drawing")
        else:
            self.canvas.set_linear_mode(False)
            self.canvas.set_counting_mode(checked and not is_linear)
            self.count_banner.setText(
                "COUNTING MODE    Click to count  |  Ctrl+drag to pan  |  Ctrl+scroll to zoom  |  Ctrl+Z to undo"
            )
            self.count_banner.setVisible(checked)
            self.count_action.setText("Stop Counting" if checked else "Start Counting")

        if checked and not is_linear and self._project_id:
            if self.takeoff_panel.active_section_id() is None:
                sections = db.get_sections(self._project_id)
                if sections:
                    QMessageBox.information(
                        self, "No Section Selected",
                        "No section (floor/area) is selected.\n"
                        "Counts will be recorded as Unassigned.\n\n"
                        "To assign to a section, pick one from the Section\n"
                        "dropdown in the right panel before counting."
                    )

    def _on_canvas_click(self, page_pt):
        if not self._project_id: self.statusBar().showMessage("Open a project first."); return
        section_id = self.takeoff_panel.active_section_id()

        if self.library_panel.tabs.currentIndex() == 0:
            entity = self.library_panel.selected_product()
            if not entity: self.statusBar().showMessage("Select a product first."); return
            etype, eid = "product", entity["id"]
        else:
            entity = self.library_panel.selected_assembly()
            if not entity: self.statusBar().showMessage("Select an assembly first."); return
            etype, eid = "assembly", entity["id"]

        color = color_for_id(eid if etype=="product" else 1000+eid)
        label = entity["name"][0].upper()
        ctype, cr_m = _coverage_for_product(entity) if etype == "product" else ("", 0.0)
        # Default Candela on the product just pre-fills each new placement —
        # the value actually lives on the mark and can be changed per-device
        # afterward (right-click -> Set Candela…), independent of every
        # other plot of the same product.
        candela = (entity.get("candela", 0) or 0.0) if etype == "product" else 0.0

        db_id = db.add_mark(self._project_id, self._pdf_path, self._page_index,
                            page_pt.x(), page_pt.y(), etype, eid, color, label, section_id, candela)
        self.canvas.add_mark(page_pt.x(), page_pt.y(), etype, eid, color, label, db_id, section_id,
                             coverage_type=ctype, coverage_radius_m=cr_m, candela=candela)
        self.takeoff_panel.set_active_entity(etype, entity)
        self.takeoff_panel.add_one()
        if etype == "product":
            db.increment_use_count(eid)
            self.library_panel.refresh()

    def _undo(self):
        if not self._counting_mode: return
        removed = self.canvas.undo_last_mark()
        if removed:
            # Delete from DB
            if removed.get("db_id"): db.delete_mark(removed["db_id"])
            self.takeoff_panel.subtract_one(removed["entity_type"], removed["entity_id"])
            self.statusBar().showMessage("Undo: last mark removed.")

    def _on_mark_deleted(self, db_id, entity_type, entity_id):
        if db_id: db.delete_mark(db_id)
        self.takeoff_panel.subtract_one(entity_type, entity_id)
        self.statusBar().showMessage("Mark deleted  count adjusted.")

    def _on_mark_candela_changed(self, db_id, candela):
        if db_id:
            db.update_mark_candela(db_id, candela)
            self.statusBar().showMessage(f"Candela set to {candela:g} cd.")

    def _on_product_selected(self, p):
        self.takeoff_panel.set_active_entity("product", p)
        self.statusBar().showMessage(f"Active: {p['name']}    toggle 'Start Counting', then click on the drawing")

    def _on_assembly_selected(self, a):
        was_active = self.count_action.isChecked()
        # Stop whichever mode is running for the OLD assembly
        if self.canvas._linear_mode:
            self.canvas.set_linear_mode(False)
        if self.canvas._counting_mode:
            self.canvas.set_counting_mode(False)

        self.takeoff_panel.set_active_entity("assembly", a)

        if was_active:
            # Button was active — re-evaluate for the new assembly (handles linear↔count switch)
            self._toggle_counting(True)
        if a.get("is_linear"):
            self.statusBar().showMessage(
                f"⌇ Linear: {a['name']}  —  activate 'Start Counting' then click points on the print to draw a run")
        else:
            comps = db.get_assembly_items(a["id"])
            comp_str = ", ".join(f"{c['quantity']}x {c['name']}" for c in comps)
            self.statusBar().showMessage(f"Assembly: {a['name']}  ({comp_str})")

    def _on_linear_run_completed(self, assembly_id, footage, points_json):
        if not self._project_id:
            return
        if footage <= 0:
            QMessageBox.warning(self, "No Scale", "Run recorded but footage is 0 — set a page scale first.")
        run_id = db.add_linear_run(
            self._project_id, assembly_id,
            self._pdf_path, self._page_index,
            points_json, footage,
            self.takeoff_panel.active_section_id(),
        )
        a = next((dict(x) for x in db.get_assemblies() if x["id"] == assembly_id), {})
        run_dict = {
            "id": run_id, "assembly_id": assembly_id,
            "pdf_path": self._pdf_path, "page_index": self._page_index,
            "points": points_json, "footage": footage,
            "color": color_for_id(assembly_id),
        }
        self.canvas.add_linear_run(run_dict)
        self.takeoff_panel._update_count_display()
        self.takeoff_panel.refresh_table()
        self.statusBar().showMessage(f"Run saved: {footage:.1f} ft  (total: {db.get_assembly_footage(self._project_id, assembly_id):.1f} ft)")

    def _on_run_deleted(self, run_id, assembly_id):
        db.delete_linear_run(run_id)
        self.takeoff_panel._update_count_display()
        self.takeoff_panel.refresh_table()
        self.statusBar().showMessage("Run deleted.")

    #  Pan / zoom 

    def _on_pan_delta(self, dx, dy):
        self.scroll_area.horizontalScrollBar().setValue(self.scroll_area.horizontalScrollBar().value()+dx)
        self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().value()+dy)

    def _on_zoom_requested(self, cx, cy, factor):
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()

        if factor == 1.0:
            # Pure scroll-to-point
            vw = self.scroll_area.viewport().width()
            vh = self.scroll_area.viewport().height()
            hbar.setValue(cx - vw // 2)
            vbar.setValue(cy - vh // 2)
            return

        # Capture scroll position BEFORE zoom so the canvas resize can't corrupt it
        old_h = hbar.value()
        old_v = vbar.value()
        old_z = self.canvas.get_zoom()

        self.canvas.set_zoom(old_z * factor)
        actual = self.canvas.get_zoom() / old_z

        # Defer one event-loop tick so the scroll area finishes resizing the canvas,
        # then pin the page point that was under the cursor using the pre-zoom values.
        def _pin():
            hbar.setValue(int(old_h + cx * (actual - 1)))
            vbar.setValue(int(old_v + cy * (actual - 1)))
        QTimer.singleShot(0, _pin)

    #  Auto-detect 

    #  Export PDF with marks 

    def _export_pdf_menu(self):
        if not self._doc:
            QMessageBox.warning(self, "No PDF", "Load a PDF first.")
            return
        dlg = ExportPdfDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        draw_marks, draw_design, draw_field_notes = dlg.selections()
        self._do_export_pdf(draw_marks, draw_design, draw_field_notes)

    def _do_export_pdf(self, draw_marks, draw_design, draw_field_notes=False):
        suffix_parts = []
        if draw_marks:       suffix_parts.append("marked")
        if draw_design:      suffix_parts.append("design")
        if draw_field_notes: suffix_parts.append("notes")
        suffix = "_" + "_".join(suffix_parts) if suffix_parts else "_clean"

        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF",
            os.path.splitext(self._pdf_path)[0] + suffix + ".pdf",
            "PDF (*.pdf)")
        if not path:
            return
        try:
            out = fitz.open()
            out.insert_pdf(self._doc)
            all_marks = self.canvas._page_marks
            ppm = self.canvas._points_per_meter
            all_lines = self.canvas._page_field_lines
            all_notes = self.canvas._page_field_notes

            pages_touched = set()
            for (pdf_p, pg_idx) in all_marks.keys():
                if pdf_p == self._pdf_path: pages_touched.add(pg_idx)
            if draw_field_notes:
                for (pdf_p, pg_idx) in all_lines.keys():
                    if pdf_p == self._pdf_path: pages_touched.add(pg_idx)
                for (pdf_p, pg_idx) in all_notes.keys():
                    if pdf_p == self._pdf_path: pages_touched.add(pg_idx)

            for pg_idx in pages_touched:
                marks = all_marks.get((self._pdf_path, pg_idx), [])
                page = out[pg_idx]

                # Coverage circles
                if draw_design and ppm > 0:
                    for m in marks:
                        r_m   = m.get("coverage_radius_m", 0.0)
                        ctype = m.get("coverage_type", "")
                        if r_m <= 0 or ctype not in self.canvas._coverage_visible:
                            continue
                        r_pts = r_m * ppm
                        cx, cy = m["page_x"], m["page_y"]
                        hex_c  = COVERAGE_COLORS.get(ctype, "#888888")
                        qc     = QColor(hex_c)
                        col    = (qc.redF(), qc.greenF(), qc.blueF())
                        page.draw_circle(fitz.Point(cx, cy), r_pts,
                                         color=col, fill=col, fill_opacity=0.06,
                                         dashes="[6 3] 0")

                # Device marks
                if draw_marks:
                    for m in marks:
                        c   = QColor(m["color"])
                        col = (c.redF(), c.greenF(), c.blueF())
                        cx, cy = m["page_x"], m["page_y"]
                        r = 6
                        page.draw_circle(fitz.Point(cx, cy), r,
                                         color=col, fill=col, fill_opacity=0.7)
                        if m["label"]:
                            page.insert_text(fitz.Point(cx - r + 1, cy + r - 1),
                                             m["label"], fontsize=7, color=(1, 1, 1))

                # Field Notes markup layer — trace lines (with arrowhead), then text notes on top
                if draw_field_notes:
                    for ln in all_lines.get((self._pdf_path, pg_idx), []):
                        import json as _json
                        try:
                            pts = _json.loads(ln["points"])
                        except Exception:
                            continue
                        if len(pts) < 2:
                            continue
                        c = QColor(ln.get("color", "#000000"))
                        col = (c.redF(), c.greenF(), c.blueF())
                        width = ln.get("width", 2.0)
                        for i in range(1, len(pts)):
                            page.draw_line(fitz.Point(pts[i-1]["x"], pts[i-1]["y"]),
                                           fitz.Point(pts[i]["x"], pts[i]["y"]),
                                           color=col, width=width)
                        wings = _arrow_wings(pts[-2]["x"], pts[-2]["y"], pts[-1]["x"], pts[-1]["y"],
                                             size=10 + width)
                        if wings:
                            tip = fitz.Point(pts[-1]["x"], pts[-1]["y"])
                            for wx, wy in wings:
                                page.draw_line(tip, fitz.Point(wx, wy), color=col, width=width)
                    for n in all_notes.get((self._pdf_path, pg_idx), []):
                        c = QColor(n.get("color", "#000000"))
                        col = (c.redF(), c.greenF(), c.blueF())
                        fontname = "hebo" if n.get("bold") else "helv"
                        fsize = n.get("font_size", 10.0)
                        pad = 3
                        tw = fitz.get_text_length(n["text"], fontname=fontname, fontsize=fsize) + pad * 2
                        th = fsize * 1.3 + pad * 2
                        cx, cy = n["page_x"], n["page_y"]
                        oval_rect = fitz.Rect(cx - tw/2, cy - th/2, cx + tw/2, cy + th/2)
                        page.draw_oval(oval_rect, color=col, width=1.5)
                        page.insert_text(fitz.Point(cx - tw/2 + pad, cy + fsize/3), n["text"],
                                         fontsize=fsize, color=col, fontname=fontname)

            out.save(path)
            out.close()
            QMessageBox.information(self, "Exported", f"PDF saved:\n{path}")
            os.startfile(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export PDF:\n{e}")

    def _open_paint_booth_designer(self):
        from paint_booth_designer import PaintBoothDesigner
        proj_name = ""
        if self._project_id:
            for p in db.get_projects():
                if p["id"] == self._project_id:
                    proj_name = p["name"]; break
        dlg = PaintBoothDesigner(self, project_name=proj_name)
        self._paint_booth_dlg = dlg
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.showMaximized()
        dlg.raise_()
        dlg.activateWindow()

    def _open_suppression_designer(self):
        from suppression_designer import SuppressionDesigner
        proj_name = ""
        if self._project_id:
            for p in db.get_projects():
                if p["id"] == self._project_id:
                    proj_name = p["name"]; break
        # Use show() (modeless) so nested QFileDialog.exec_() calls don't
        # create a modal-within-modal loop that crashes on Windows builds.
        dlg = SuppressionDesigner(self, project_name=proj_name)
        self._suppression_dlg = dlg  # keep reference so GC doesn't destroy it
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _open_drawing_designer(self):
        from drawing_designer import DrawingDesigner
        proj_name = ""
        if self._project_id:
            for p in db.get_projects():
                if p["id"] == self._project_id:
                    proj_name = p["name"]; break
        # Use show() (modeless) so nested QFileDialog.exec_() calls don't
        # create a modal-within-modal loop that crashes on Windows builds.
        dlg = DrawingDesigner(self, project_name=proj_name)
        self._floor_plan_dlg = dlg  # keep reference so GC doesn't destroy it
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _open_fire_plan_builder(self):
        if not self._project_id:
            QMessageBox.warning(self, "No Project", "Open a project first.")
            return
        from fire_plan_builder import FirePlanBuilderWindow
        proj_name = next((p["name"] for p in db.get_projects() if p["id"] == self._project_id), "")
        # Non-modal, same reasoning as Drawing Designer above — this window
        # opens its own nested dialogs (VBI form, file pickers) and can
        # launch Drawing Designer itself via its "Open Drawing Designer"
        # shortcut, which would be blocked/frozen behind an app-modal loop.
        dlg = FirePlanBuilderWindow(self, self._project_id, proj_name)
        self._fire_plan_dlg = dlg   # keep reference so GC doesn't destroy it
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _open_pma_quote(self):
        dlg = estimator.PmaQuoteDialog(self._project_id or None, parent=self)
        dlg.exec_()

    def _open_install_estimate(self):
        dlg = estimator.InstallEstimateDialog(self._project_id or None, parent=self)
        dlg.exec_()

    def _open_programming(self):
        dlg = estimator.ProgrammingDialog(self._project_id or None, parent=self)
        dlg.exec_()

    def _update_title(self):
        if self._project_id:
            for p in db.get_projects():
                if p["id"]==self._project_id:
                    self.setWindowTitle(f"DFP TakeoffPro    {p['name']}"); return
        self.setWindowTitle("DFP TakeoffPro")

    def closeEvent(self, event):
        for win in list(self._snip_windows.values()):
            win.close()
        super().closeEvent(event)


# 

def _make_splash(app):
    """Draw a branded splash screen and return it."""
    from PyQt5.QtWidgets import QSplashScreen
    from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient
    from PyQt5.QtCore import Qt

    W, H = 540, 300
    pm = QPixmap(W, H)
    pm.fill(QColor("#232728"))

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    # Orange accent bar at top
    p.fillRect(0, 0, W, 8, QColor("#ff7002"))

    # Flame / shield icon placeholder — simple geometric shape
    p.setBrush(QColor("#ff7002")); p.setPen(Qt.NoPen)
    # Outer shield
    pts = [
        (W//2, 60), (W//2 - 40, 80), (W//2 - 40, 115),
        (W//2, 135), (W//2 + 40, 115), (W//2 + 40, 80),
    ]
    from PyQt5.QtGui import QPolygon
    from PyQt5.QtCore import QPoint
    poly = QPolygon([QPoint(x, y) for x, y in pts])
    p.drawPolygon(poly)
    # Inner flame
    p.setBrush(QColor("#232728"))
    inner = [(W//2, 75), (W//2-18, 92), (W//2-18, 115),
             (W//2, 125), (W//2+18, 115), (W//2+18, 92)]
    p.drawPolygon(QPolygon([QPoint(x, y) for x, y in inner]))
    p.setBrush(QColor("#ff7002"))
    flame = [(W//2, 85), (W//2-8, 100), (W//2, 95),
             (W//2+8, 107), (W//2, 120)]
    p.drawPolygon(QPolygon([QPoint(x, y) for x, y in flame]))

    # App name
    p.setPen(QColor("#ff7002"))
    f = QFont("Arial", 30, QFont.Bold); p.setFont(f)
    p.drawText(0, 148, W, 40, Qt.AlignCenter, "DFP TakeoffPro")

    # Company name
    p.setPen(QColor("#efe6e1"))
    f2 = QFont("Arial", 13); p.setFont(f2)
    p.drawText(0, 192, W, 26, Qt.AlignCenter, "Defense Fire Protection")

    # Version
    p.setPen(QColor("#69727d"))
    f3 = QFont("Arial", 10); p.setFont(f3)
    p.drawText(0, 220, W, 20, Qt.AlignCenter, f"Version {APP_VERSION}")

    # Loading text
    p.setPen(QColor("#ff7002"))
    f4 = QFont("Arial", 9); p.setFont(f4)
    p.drawText(0, 268, W, 20, Qt.AlignCenter, "Loading...")

    # Bottom orange bar
    p.fillRect(0, H - 6, W, 6, QColor("#ff7002"))
    p.end()

    splash = QSplashScreen(pm, Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()
    return splash


def _show_license_dialog(parent=None):
    """Show activation dialog. Returns True if licensed."""
    from license import check_activation, activate, get_machine_id
    from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit,
                                  QPushButton, QHBoxLayout, QApplication)

    ok, msg = check_activation()
    if ok:
        return True

    machine_id = get_machine_id()

    dlg = QDialog(parent)
    dlg.setWindowTitle("DFP TakeoffPro - Activation Required")
    dlg.setMinimumWidth(460)
    dlg.setWindowFlag(Qt.WindowCloseButtonHint, False)
    layout = QVBoxLayout(dlg); layout.setSpacing(14); layout.setContentsMargins(24, 24, 24, 24)

    icon_lbl = QLabel("DFP TakeoffPro"); icon_lbl.setAlignment(Qt.AlignCenter)
    icon_lbl.setStyleSheet("font-size:20px;font-weight:bold;color:#ff7002;padding:8px;")
    layout.addWidget(icon_lbl)

    msg_lbl = QLabel(msg); msg_lbl.setWordWrap(True); msg_lbl.setAlignment(Qt.AlignCenter)
    layout.addWidget(msg_lbl)

    layout.addWidget(QLabel("<b>Your Machine ID:</b>"))
    mid_edit = QLineEdit(machine_id); mid_edit.setReadOnly(True)
    mid_edit.setStyleSheet("background:#f0f0f0;padding:6px;font-family:Consolas;font-size:13px;")
    layout.addWidget(mid_edit)

    copy_btn = QPushButton("Copy Machine ID")
    copy_btn.setStyleSheet("padding:4px 12px;")
    copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(machine_id))
    layout.addWidget(copy_btn)

    layout.addWidget(QLabel(
        "Send this Machine ID to your administrator to receive a license key.\n"
        "Contact: kevinh@defensefirepro.com"
    ))

    layout.addWidget(QLabel("<b>License Key:</b>"))
    key_edit = QLineEdit(); key_edit.setPlaceholderText("DFP-XXXXXX-XXXXXX-XXXXXX-XXXXXX")
    key_edit.setStyleSheet("font-family:Consolas;font-size:13px;padding:6px;")
    layout.addWidget(key_edit)

    status_lbl = QLabel(""); status_lbl.setAlignment(Qt.AlignCenter)
    layout.addWidget(status_lbl)

    btn_row = QHBoxLayout()
    exit_btn = QPushButton("Exit"); exit_btn.clicked.connect(dlg.reject)
    act_btn  = QPushButton("Activate"); act_btn.setStyleSheet("background:#ff7002;color:white;padding:8px 24px;font-weight:bold;")

    def _try_activate():
        key = key_edit.text().strip()
        if not key:
            status_lbl.setText("Please enter a license key.")
            return
        ok2, msg2 = activate(key)
        if ok2:
            status_lbl.setStyleSheet("color:#27ae60;font-weight:bold;")
            status_lbl.setText(msg2)
            QTimer.singleShot(1200, dlg.accept)
        else:
            status_lbl.setStyleSheet("color:#c02b0a;font-weight:bold;")
            status_lbl.setText(msg2)

    act_btn.clicked.connect(_try_activate)
    btn_row.addWidget(exit_btn); btn_row.addStretch(); btn_row.addWidget(act_btn)
    layout.addLayout(btn_row)

    result = dlg.exec_()
    return result == QDialog.Accepted


def _show_update_dialog(info: dict):
    """Show an update-available dialog (called from update checker callback)."""
    from PyQt5.QtWidgets import QMessageBox
    msg = QMessageBox()
    msg.setWindowTitle("Update Available")
    msg.setIcon(QMessageBox.Information)
    ver  = info.get("version", "?")
    notes = info.get("notes", "")
    msg.setText(f"Version {ver} of DFP TakeoffPro is available.\n\n{notes}")
    msg.setInformativeText("Would you like to download it now?")
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    msg.setDefaultButton(QMessageBox.Yes)
    if msg.exec_() == QMessageBox.Yes:
        from updater import download_and_install
        download_and_install(info.get("download_url", ""))


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow, QWidget { background: #efe6e1; }
        QDialog { background: #efe6e1; }

        /* Toolbar */
        QToolBar { background: #232728; spacing: 6px; padding: 5px; border: none; }
        QToolBar QToolButton {
            color: #efe6e1; background: #333738;
            padding: 5px 12px; border-radius: 3px; border: none; font-weight: bold;
        }
        QToolBar QToolButton:hover   { background: #ff7002; color: white; }
        QToolBar QToolButton:checked { background: #ff7002; color: white; }
        QToolBar::separator { background: #ff7002; width: 2px; margin: 4px 2px; }

        /* Tabs */
        QTabWidget::pane { border: 1px solid #d0c8c0; background: #efe6e1; }
        QTabBar::tab     { background: #d8cec8; color: #232728; padding: 5px 10px;
                           border-radius: 3px 3px 0 0; margin-right: 2px;
                           font-weight: bold; font-size: 12px; min-width: 72px; }
        QTabBar::tab:selected { background: #ff7002; color: white; }
        QTabBar::tab:hover    { background: #e8a060; color: white; }

        /* Scroll areas and list widgets */
        QScrollArea { border: none; background: #efe6e1; }
        QListWidget { background: white; border: 1px solid #d0c8c0; border-radius: 4px; }
        QListWidget::item { padding: 5px; border-bottom: 1px solid #ede8e4; }
        QListWidget::item:selected { background: #ff7002; color: white; }
        QListWidget::item:hover    { background: #ffe8d0; }

        /* Table */
        QTableWidget { background: white; border: 1px solid #d0c8c0;
                       gridline-color: #ede8e4; border-radius: 4px; }
        QTableWidget::item:selected { background: #ff7002; color: white; }
        QHeaderView::section { background: #232728; color: white; padding: 5px;
                               font-weight: bold; border: none; }

        /* Inputs */
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            background: white; border: 1px solid #d0c8c0; border-radius: 3px;
            padding: 4px; color: #232728;
        }
        QLineEdit:focus, QComboBox:focus { border: 1px solid #ff7002; }

        /* Buttons */
        QPushButton {
            background: #232728; color: #efe6e1; border-radius: 4px;
            padding: 5px 10px; border: none; font-weight: bold;
        }
        QPushButton:hover    { background: #ff7002; color: white; }
        QPushButton:pressed  { background: #c02b0a; color: white; }
        QPushButton:disabled { background: #aaa; color: #eee; }

        /* Labels */
        QLabel { color: #232728; }

        /* Splitter */
        QSplitter::handle { background: #d0c8c0; width: 4px; }

        /* Status bar */
        QStatusBar { background: #232728; color: #efe6e1; padding: 2px 8px; font-size: 11px; }
        QStatusBar QLabel { color: #efe6e1; }
    """)
    # Splash screen
    splash = _make_splash(app)

    # License check (currently open mode — set LICENSING_ENABLED=True in license.py to enforce)
    from license import check_activation
    lic_ok, lic_msg = check_activation()
    if not lic_ok:
        splash.close()
        if not _show_license_dialog():
            sys.exit(0)
        splash = _make_splash(app)  # re-show splash after activation dialog

    # Build main window
    import time; time.sleep(0.8)   # let splash be visible briefly
    win = MainWindow()

    # Check for updates in background (won't block startup)
    try:
        from PyQt5.QtCore import QObject, pyqtSignal
        from updater import check_for_update

        class _UpdateNotifier(QObject):
            found = pyqtSignal(dict)

        _notifier = _UpdateNotifier()
        _notifier.found.connect(_show_update_dialog)

        def _on_update(info):
            if info:
                _notifier.found.emit(info)

        check_for_update(_on_update)
    except Exception:
        pass

    splash.finish(win)
    win.showMaximized()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
