"""
DFP TakeoffPro – Paint Booth Dry Chemical Designer
Badger Industry Guard Dry Chemical System for Vehicle Spray Booths
Manual P/N 60-900007-001 (Jan 2007) – UL EX 4864 / ULC CEX 515
NFPA 17 / NFPA 33
"""

import math, json, os, sys, datetime

from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QDoubleSpinBox, QFormLayout, QFrame,
    QMessageBox, QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QScrollArea, QTextEdit, QSpinBox, QTabWidget,
    QFileDialog, QMenu, QLineEdit, QCheckBox, QAbstractItemView,
    QSizePolicy, QAction, QToolBar, QInputDialog, QApplication,
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsTextItem,
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetricsF,
    QPainterPath, QPolygonF, QPixmap,
)
from PyQt5.QtCore import Qt, QRectF, QPointF, QSizeF, pyqtSignal, QTimer

try:
    from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
    _PRINT_AVAILABLE = True
except ImportError:
    _PRINT_AVAILABLE = False

try:
    from version import APP_VERSION
except ImportError:
    APP_VERSION = "1.0.0"

# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS — sourced from Badger DIOM P/N 60-900007-001
# ═══════════════════════════════════════════════════════════════════════════════

# Cylinder models (Table 3-1)
CYLINDERS = [
    {"model": "IND-21", "lbs": 21, "part": "486573",        "desc": "21 lb ABC Dry Chemical"},
    {"model": "IND-45", "lbs": 45, "part": "486574",        "desc": "45 lb ABC Dry Chemical"},
    {"model": "IND-70", "lbs": 70, "part": "83-100018-001", "desc": "70 lb ABC Dry Chemical"},
]

# Nozzle types (§3-2.3)
NOZZLE_TF  = "TF"     # Total Flooding – work area   P/N B100005
NOZZLE_DP  = "DP"     # Duct/Plenum                  P/N B100006
NOZZLE_3WY = "3-Way"  # Pit with tunnel               P/N B100037

NOZZLE_PARTS = {NOZZLE_TF: "B100005", NOZZLE_DP: "B100006", NOZZLE_3WY: "B100037"}
NOZZLE_DESC  = {
    NOZZLE_TF:  "Total Flooding – work area overhead",
    NOZZLE_DP:  "Duct/Plenum – exhaust air stream",
    NOZZLE_3WY: "3-Way – pit with tunnel",
}
NOZZLE_COLOR_HEX = {NOZZLE_TF: "#2980b9", NOZZLE_DP: "#27ae60", NOZZLE_3WY: "#e67e22"}

# Zone types
ZONE_WORK = "Work Area"
ZONE_PLEN = "Plenum"
ZONE_DUCT = "Exhaust Duct"

ZONE_FILL = {
    ZONE_WORK: QColor(41, 128, 185, 35),
    ZONE_PLEN: QColor(39, 174, 96,  35),
    ZONE_DUCT: QColor(230, 126, 34, 35),
}
ZONE_BORDER_COL = {
    ZONE_WORK: QColor(41,  128, 185),
    ZONE_PLEN: QColor(39,  174, 96),
    ZONE_DUCT: QColor(230, 126, 34),
}

# Coverage limits (§4-5.1)
MAX_WORK_VOL_FT3   = 1260.0   # ft³ per TF nozzle (§4-5.1.1)
MAX_WORK_HEIGHT_FT = 10.0     # ft — overhead TF nozzle system
MAX_DUCT_LEN_FT    = 28.0     # ft per DP nozzle (§4-5.1.3)
MAX_DUCT_DIA_IN    = 48.0     # inches — round duct
MAX_DUCT_PERIM_IN  = 150.8    # inches — rectangular duct perimeter
MAX_NOZZLE_OFFSET  = 2.75     # ft — nozzle may be offset this far from module centre
NOZZLE_TIP_MAX_IN  = 4.75     # inches from ceiling (TF nozzle)

# Side-wall application limits (§4-5.1.2) — DC-45 with 4 TF nozzles
SIDEWALL_MAX_L, SIDEWALL_MAX_W, SIDEWALL_MAX_H = 28.0, 15.0, 9.17

# Booth types
BOOTH_TYPES = [
    "Cross-Draft – Drive-Through",
    "Cross-Draft – Pant-Leg",
    "Down-Draft – Raised Floor",
    "Down-Draft – Pit",
    "Down-Draft – Side Exhaust",
    "Enclosed Spray Booth",
    "Semi-Down-Draft / Cross-Flow",
]

# Detection devices (§3-2.4 & §3-2.5)
DETECTOR_TYPES = [
    "Fusible Link 165°F (74°C)   – P/N B282661",
    "Fusible Link 212°F (100°C)  – P/N B282662",
    "Fusible Link 286°F (141°C)  – P/N B282663",
    "Fusible Link 360°F (182°C)  – P/N B282664",
    "Thermo-Bulb 165°F (74°C)   – P/N B120095-165",
    "Thermo-Bulb 212°F (100°C)  – P/N B120095-212",
    "Thermo-Bulb 286°F (141°C)  – P/N B120095-286",
    "Thermo-Bulb 360°F (182°C)  – P/N B120095-360",
    "Thermo-Bulb 450°F (232°C)  – P/N B120095-450",
    "Detect-A-Fire 140°F (60°C) – P/N 27121-140",
    "Detect-A-Fire 190°F (88°C) – P/N 27121-190",
    "Detect-A-Fire 225°F (107°C)– P/N 27121-225",
    "Detect-A-Fire 325°F (163°C)– P/N 27121-325",
    "Detect-A-Fire 450°F (232°C)– P/N 27121-450",
    "Detect-A-Fire 600°F (316°C)– P/N 27121-600",
]

# Control/accessory items
ACCESSORIES = {
    "UCH":          ("Universal Control Head",            "B120099"),
    "SVA":          ("System Valve Actuator",             "B120042"),
    "Nitrogen Cart":("System Nitrogen Cartridge",         "B120043"),
    "Actuation Dly":("Actuation Delay Assembly",          "B100035"),
    "Pull Station": ("Remote Manual Release Pull Station","87-120110-001"),
    "Elec Actuator":("Electrical Actuator (optional)",    "B100034"),
    "Discharge Adp":("Discharge Adapter Kit",             "844908"),
    "Flow Rest 3/4":("3/4\" Flow Restrictor",             "B100050"),
    "Flow Rest 1\"": ("1\" Flow Restrictor",              "B100051"),
}

PX_PER_FT = 22.0   # canvas pixels per foot
_PALETTE_DARK   = "#232728"
_PALETTE_ORANGE = "#ff7002"

# ── Isometric 3-D projection helpers (mirrors suppression_designer.py) ────────
_ISO_ANG = math.radians(32)
_ISO_DSF = 0.40   # depth scale factor

def _ddx(depth_ft):
    """Rightward screen-pixel shift per foot of depth."""
    return depth_ft * PX_PER_FT * _ISO_DSF * math.cos(_ISO_ANG)

def _ddy(depth_ft):
    """Upward screen-pixel shift per foot of depth (negative = up on screen)."""
    return -depth_ft * PX_PER_FT * _ISO_DSF * math.sin(_ISO_ANG)

def _nozzle_grid(count):
    """Return (rows, cols) for a roughly-square nozzle grid."""
    if count <= 0:
        return 0, 0
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    return rows, cols


# ═══════════════════════════════════════════════════════════════════════════════
#  Data model
# ═══════════════════════════════════════════════════════════════════════════════

class ZoneData:
    """Represents one suppression zone in the booth."""
    _id_counter = 0

    def __init__(self, zone_type=ZONE_WORK, length=20.0, width=14.0, height=9.0,
                 nozzle_type=None, label="", x=0.0, y=0.0, nozzle_override=None):
        ZoneData._id_counter += 1
        self.uid = ZoneData._id_counter
        self.zone_type   = zone_type
        self.length      = float(length)
        self.width       = float(width)
        self.height      = float(height)
        self.nozzle_type = nozzle_type or self._default_nozzle()
        self.label       = label or f"{zone_type} {self.uid}"
        self.x           = float(x)   # ft from scene origin
        self.y           = float(y)
        self.nozzle_override = nozzle_override  # int or None — override auto count

    def _default_nozzle(self):
        return {ZONE_WORK: NOZZLE_TF, ZONE_PLEN: NOZZLE_DP, ZONE_DUCT: NOZZLE_DP}[self.zone_type]

    @property
    def volume(self):
        return self.length * self.width * self.height

    @property
    def nozzle_count(self):
        if self.nozzle_override is not None:
            return self.nozzle_override
        if self.zone_type == ZONE_WORK:
            return max(1, math.ceil(self.volume / MAX_WORK_VOL_FT3))
        elif self.zone_type == ZONE_DUCT:
            return max(1, math.ceil(self.length / MAX_DUCT_LEN_FT))
        else:  # Plenum — 1 nozzle covers 15ft L × 15ft W per §4-5.1.4
            area = self.length * self.width
            return max(1, math.ceil(area / (15.0 * 15.0)))

    def warnings(self):
        """Return list of warning strings for this zone."""
        w = []
        if self.zone_type == ZONE_WORK:
            if self.height > MAX_WORK_HEIGHT_FT:
                w.append(f"[{self.label}] Height {self.height:.1f} ft exceeds 10 ft max for overhead TF system")
            vol_per = self.volume / max(1, self.nozzle_count)
            if vol_per > MAX_WORK_VOL_FT3:
                w.append(f"[{self.label}] Volume per nozzle {vol_per:.0f} ft³ exceeds 1,260 ft³ max")
        elif self.zone_type == ZONE_DUCT:
            if self.length / max(1, self.nozzle_count) > MAX_DUCT_LEN_FT:
                w.append(f"[{self.label}] Each duct nozzle covers >{MAX_DUCT_LEN_FT:.0f} ft — add another DP nozzle")
        return w

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    @classmethod
    def from_dict(cls, d):
        obj = cls.__new__(cls)
        obj.__dict__.update(d)
        return obj


# ═══════════════════════════════════════════════════════════════════════════════
#  Graphics items
# ═══════════════════════════════════════════════════════════════════════════════

class ZoneItem(QGraphicsItem):
    """Draggable zone drawn in 3-D isometric on the canvas."""

    def __init__(self, zone_data: ZoneData, scene_ref):
        super().__init__()
        self.zone = zone_data
        self._scene_ref = scene_ref
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.setAcceptHoverEvents(True)
        self._hover = False
        self._update_pos()

    def _update_pos(self):
        # Front-top-left of zone at scene (x_ft * PX, 0);
        # scene y=0 is the booth ceiling / top-of-front-wall.
        self.setPos(self.zone.x * PX_PER_FT, 0.0)

    def boundingRect(self):
        z = self.zone
        w_px = z.length * PX_PER_FT
        h_px = z.height * PX_PER_FT
        dx = _ddx(z.width)
        dy = _ddy(z.width)   # negative (up on screen)
        pad = 24
        # x: 0 .. w_px+dx  |  y: dy .. h_px  (dy < 0, so extends above origin)
        return QRectF(0, dy - pad, w_px + dx + pad, h_px - dy + pad)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.zone.x = self.pos().x() / PX_PER_FT
            # Lock vertical position — zones always sit at ceiling (y=0 in scene)
            if self.pos().y() != 0.0:
                self.setPos(self.pos().x(), 0.0)
            if hasattr(self._scene_ref, "_on_zone_moved"):
                self._scene_ref._on_zone_moved()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self._hover = True; self.update()

    def hoverLeaveEvent(self, event):
        self._hover = False; self.update()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        z = self.zone
        w_px = z.length * PX_PER_FT
        h_px = z.height * PX_PER_FT
        dx   = _ddx(z.width)
        dy   = _ddy(z.width)   # negative

        # 8 corners in local space; origin = front-top-left
        ftl = QPointF(0,        0      )   # front top-left
        ftr = QPointF(w_px,     0      )   # front top-right
        fbl = QPointF(0,        h_px   )   # front bottom-left
        fbr = QPointF(w_px,     h_px   )   # front bottom-right
        btl = QPointF(dx,       dy     )   # back  top-left
        btr = QPointF(w_px+dx,  dy     )   # back  top-right
        bbl = QPointF(dx,       h_px+dy)   # back  bottom-left
        bbr = QPointF(w_px+dx,  h_px+dy)   # back  bottom-right

        border = ZONE_BORDER_COL[z.zone_type]
        fill   = ZONE_FILL[z.zone_type]
        sel_col = QColor(_PALETTE_ORANGE)

        # ── Hidden back edges ─────────────────────────────────────────────────
        painter.setPen(QPen(border.lighter(160), 1, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(btl, bbl)
        painter.drawLine(btl, btr)
        painter.drawLine(bbl, bbr)

        # ── Ceiling / top face ────────────────────────────────────────────────
        top_alpha = 110 if z.zone_type == ZONE_WORK else 80
        top_col = QColor(border.red(), border.green(), border.blue(), top_alpha)
        painter.setBrush(QBrush(top_col))
        painter.setPen(QPen(sel_col if self.isSelected() else border.darker(110),
                            2.5 if (self._hover or self.isSelected()) else 1.5))
        painter.drawPolygon(QPolygonF([ftl, ftr, btr, btl]))

        # Draw nozzle grid on ceiling for work-area and plenum zones
        if z.zone_type in (ZONE_WORK, ZONE_PLEN):
            self._draw_ceiling_nozzles(painter, ftl, ftr, btl)

        # ── Right side face ───────────────────────────────────────────────────
        side_col = QColor(border.red(), border.green(), border.blue(), 60)
        painter.setBrush(QBrush(side_col))
        painter.setPen(QPen(border.darker(120), 1.5))
        painter.drawPolygon(QPolygonF([ftr, fbr, bbr, btr]))

        # ── Front face ────────────────────────────────────────────────────────
        front_pen = QPen(sel_col if self.isSelected() else border,
                         2.5 if (self._hover or self.isSelected()) else 1.8)
        if z.zone_type == ZONE_DUCT:
            front_pen.setStyle(Qt.DashLine)
        painter.setBrush(QBrush(fill))
        painter.setPen(front_pen)
        painter.drawPolygon(QPolygonF([ftl, ftr, fbr, fbl]))

        # Duct zone: draw nozzle dots along the front face (horizontal run)
        if z.zone_type == ZONE_DUCT:
            self._draw_duct_nozzles(painter, w_px, h_px, z)

        # ── Front face labels ─────────────────────────────────────────────────
        painter.setPen(QPen(border.darker(150)))
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        painter.drawText(QRectF(5, 4, w_px - 10, 16), Qt.AlignLeft | Qt.AlignVCenter, z.label)

        painter.setFont(QFont("Arial", 7))
        painter.setPen(QPen(border.darker(130)))
        info = f"{z.length:.0f}′ × {z.width:.0f}′ × {z.height:.0f}′"
        painter.drawText(QRectF(5, 20, w_px - 10, 14), Qt.AlignLeft | Qt.AlignVCenter, info)

        noz_txt = f"{z.nozzle_count}× {z.nozzle_type}"
        if z.zone_type == ZONE_WORK:
            noz_txt += f"  ({z.volume:.0f} ft³)"
        painter.drawText(QRectF(5, 33, w_px - 10, 14), Qt.AlignLeft | Qt.AlignVCenter, noz_txt)

        if z.warnings():
            painter.setPen(QPen(QColor("#e74c3c"), 1))
            painter.setFont(QFont("Arial", 7, QFont.Bold))
            painter.drawText(QRectF(5, h_px - 18, w_px - 10, 14),
                             Qt.AlignLeft, "⚠ " + z.warnings()[0])

    # ── Nozzle helpers ────────────────────────────────────────────────────────

    def _draw_ceiling_nozzles(self, painter, ftl, ftr, btl):
        """Place nozzles in a rows×cols grid on the isometric ceiling face."""
        z   = self.zone
        nc  = z.nozzle_count
        if nc <= 0:
            return
        rows, cols = _nozzle_grid(nc)
        n_col  = QColor(NOZZLE_COLOR_HEX[z.nozzle_type])
        R      = 6    # radius of nozzle symbol
        hang   = 10   # px below ceiling for nozzle tip

        # Unit vectors spanning the ceiling parallelogram
        len_x = (ftr.x() - ftl.x()) / (cols + 1)
        len_y = (ftr.y() - ftl.y()) / (cols + 1)
        dep_x = (btl.x() - ftl.x()) / (rows + 1)
        dep_y = (btl.y() - ftl.y()) / (rows + 1)

        placed = 0
        for row in range(rows):
            for col in range(cols):
                if placed >= nc:
                    break
                cx = ftl.x() + len_x * (col + 1) + dep_x * (row + 1)
                cy = ftl.y() + len_y * (col + 1) + dep_y * (row + 1)

                # Stem hanging from ceiling
                painter.setPen(QPen(n_col.darker(130), 1.5))
                painter.drawLine(QPointF(cx, cy), QPointF(cx, cy + hang))

                # Nozzle head
                painter.setBrush(QBrush(n_col))
                painter.setPen(QPen(Qt.white, 1))
                painter.drawEllipse(QPointF(cx, cy + hang), R, R)
                painter.setFont(QFont("Arial", 5, QFont.Bold))
                painter.drawText(QRectF(cx - R, cy + hang - R, R*2, R*2),
                                 Qt.AlignCenter, z.nozzle_type[:2])
                placed += 1

    def _draw_duct_nozzles(self, painter, w_px, h_px, z):
        """Draw DP/3-Way nozzles evenly along the duct (front face, horizontal)."""
        nc    = z.nozzle_count
        if nc <= 0:
            return
        n_col = QColor(NOZZLE_COLOR_HEX[z.nozzle_type])
        R     = 6
        ny    = h_px / 2
        for i in range(nc):
            nx = w_px * (i + 1) / (nc + 1)
            painter.setBrush(QBrush(n_col))
            painter.setPen(QPen(Qt.white, 1))
            painter.drawEllipse(QPointF(nx, ny), R, R)
            painter.setFont(QFont("Arial", 5, QFont.Bold))
            painter.drawText(QRectF(nx - R, ny - R, R*2, R*2),
                             Qt.AlignCenter, z.nozzle_type[:2])

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.addAction("Edit Zone…",   lambda: self._scene_ref._edit_zone(self))
        menu.addAction("Delete Zone",  lambda: self._scene_ref._delete_zone(self))
        menu.exec_(event.screenPos())


class BoothShellItem(QGraphicsItem):
    """3-D isometric outer booth envelope. Non-interactive, drawn behind zones."""

    def __init__(self, L, W, H):
        super().__init__()
        self.L, self.W, self.H = float(L), float(W), float(H)
        self.setZValue(-5)

    def set_dims(self, L, W, H):
        self.prepareGeometryChange()
        self.L, self.W, self.H = float(L), float(W), float(H)
        self.update()

    def boundingRect(self):
        w_px = self.L * PX_PER_FT
        h_px = self.H * PX_PER_FT
        dx = _ddx(self.W); dy = _ddy(self.W)
        pad = 50
        return QRectF(-pad, dy - pad, w_px + dx + 2*pad, h_px - dy + 2*pad)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        L, W, H = self.L, self.W, self.H
        w_px = L * PX_PER_FT
        h_px = H * PX_PER_FT
        dx = _ddx(W); dy = _ddy(W)

        # Corners; local origin = front-top-left of booth
        ftl = QPointF(0,        0       )
        ftr = QPointF(w_px,     0       )
        fbl = QPointF(0,        h_px    )
        fbr = QPointF(w_px,     h_px    )
        btl = QPointF(dx,       dy      )
        btr = QPointF(w_px+dx,  dy      )
        bbl = QPointF(dx,       h_px+dy )
        bbr = QPointF(w_px+dx,  h_px+dy )

        ceiling_col = QColor("#c8d8e8")
        side_col    = QColor("#b0c0d0")
        edge_col    = QColor("#6a7a8a")
        edge_pen    = QPen(edge_col, 1.8)
        dash_pen    = QPen(QColor("#9aaaba"), 1, Qt.DashLine)

        # Back hidden edges
        painter.setPen(dash_pen); painter.setBrush(Qt.NoBrush)
        painter.drawLine(btl, bbl)
        painter.drawLine(btl, btr)
        painter.drawLine(bbl, bbr)

        # Ceiling / top face
        painter.setBrush(QBrush(ceiling_col))
        painter.setPen(edge_pen)
        painter.drawPolygon(QPolygonF([ftl, ftr, btr, btl]))

        # Right side wall
        painter.setBrush(QBrush(side_col))
        painter.drawPolygon(QPolygonF([ftr, fbr, bbr, btr]))

        # Front wall — transparent interior so zones show through
        painter.setBrush(QBrush(QColor(255, 255, 255, 0)))
        painter.setPen(QPen(edge_col, 2.5))
        painter.drawPolygon(QPolygonF([ftl, ftr, fbr, fbl]))

        # Floor
        painter.setPen(QPen(edge_col.darker(120), 1.5))
        painter.drawLine(fbl, fbr)

        # Dimension labels
        painter.setPen(QPen(QColor("#444"), 1))
        painter.setFont(QFont("Arial", 8))
        # Length below front face
        painter.drawText(QRectF(w_px/2 - 40, h_px + 5, 80, 16),
                         Qt.AlignCenter, f"{L:.0f}′ long")
        # Height on left
        painter.save()
        painter.translate(-26, h_px / 2)
        painter.rotate(-90)
        painter.drawText(QRectF(-30, -8, 60, 16), Qt.AlignCenter, f"{H:.0f}′ tall")
        painter.restore()
        # Depth on top-right
        painter.drawText(QRectF(w_px + dx/2 - 25, dy/2 - 8, 70, 16),
                         Qt.AlignLeft, f"{W:.0f}′ deep")


class CylinderItem(QGraphicsItem):
    """Visual cylinder symbol."""

    def __init__(self, label="IND-45", color="#8e44ad"):
        super().__init__()
        self.label = label
        self.color = QColor(color)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def boundingRect(self):
        return QRectF(0, 0, 40, 80)

    def paint(self, painter, option, widget=None):
        # Cylinder body
        painter.setBrush(QBrush(self.color))
        painter.setPen(QPen(self.color.darker(140), 2))
        painter.drawRoundedRect(QRectF(5, 10, 30, 60), 6, 6)
        # Top cap
        painter.drawEllipse(QRectF(5, 5, 30, 14))
        # Label
        painter.setPen(QPen(Qt.white))
        painter.setFont(QFont("Arial", 7, QFont.Bold))
        painter.drawText(QRectF(0, 28, 40, 28), Qt.AlignCenter, self.label)


class DetectorItem(QGraphicsItem):
    """Visual detector symbol (triangle)."""

    def __init__(self, label="Link", color="#e74c3c"):
        super().__init__()
        self.label = label
        self.color = QColor(color)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def boundingRect(self):
        return QRectF(-14, -14, 28, 32)

    def paint(self, painter, option, widget=None):
        poly = QPolygonF([QPointF(0, -13), QPointF(13, 11), QPointF(-13, 11)])
        painter.setBrush(self.color)
        painter.setPen(QPen(self.color.darker(140), 1.5))
        painter.drawPolygon(poly)
        painter.setPen(QPen(Qt.white))
        painter.setFont(QFont("Arial", 6, QFont.Bold))
        painter.drawText(QRectF(-13, -2, 26, 14), Qt.AlignCenter, self.label[:3])


# ═══════════════════════════════════════════════════════════════════════════════
#  Scene
# ═══════════════════════════════════════════════════════════════════════════════

class BoothScene(QGraphicsScene):
    zones_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zone_items: list[ZoneItem] = []
        self._det_items  = []
        self._cyl_items  = []
        self._booth_shell: BoothShellItem = None
        self._booth_L = 0.0
        self._booth_W = 0.0
        self._booth_H = 9.0

    # ── Public API ──────────────────────────────────────────────────────────

    def set_booth_outline(self, length_ft, width_ft, height_ft=9.0):
        self._booth_L = length_ft
        self._booth_W = width_ft
        self._booth_H = height_ft
        if self._booth_shell is None:
            self._booth_shell = BoothShellItem(length_ft, width_ft, height_ft)
            self.addItem(self._booth_shell)
            self._booth_shell.setPos(0, 0)
        else:
            self._booth_shell.set_dims(length_ft, width_ft, height_ft)

    def add_zone(self, zone_data: ZoneData):
        item = ZoneItem(zone_data, self)
        self.addItem(item)
        self._zone_items.append(item)
        self.zones_changed.emit()
        return item

    def remove_zone(self, item: ZoneItem):
        self._zone_items = [z for z in self._zone_items if z is not item]
        self.removeItem(item)
        self.zones_changed.emit()

    def add_cylinder(self, label, color, x_ft, y_ft):
        item = CylinderItem(label, color)
        item.setPos(x_ft * PX_PER_FT, y_ft * PX_PER_FT)
        self.addItem(item)
        self._cyl_items.append(item)

    def add_detector(self, label, color, x_ft, y_ft):
        item = DetectorItem(label, color)
        item.setPos(x_ft * PX_PER_FT, y_ft * PX_PER_FT)
        self.addItem(item)
        self._det_items.append(item)

    def clear_cylinders(self):
        for it in self._cyl_items:
            self.removeItem(it)
        self._cyl_items.clear()

    def all_zones(self) -> list[ZoneData]:
        return [it.zone for it in self._zone_items]

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_zone_moved(self):
        self.zones_changed.emit()

    def _edit_zone(self, item: ZoneItem):
        dlg = ZoneDialog(item.zone, self.views()[0] if self.views() else None)
        if dlg.exec_() == QDialog.Accepted:
            dlg.apply_to(item.zone)
            item.update()
            self.zones_changed.emit()

    def _delete_zone(self, item: ZoneItem):
        if QMessageBox.question(None, "Delete Zone",
            f"Delete zone '{item.zone.label}'?",
            QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.remove_zone(item)


# ═══════════════════════════════════════════════════════════════════════════════
#  View
# ═══════════════════════════════════════════════════════════════════════════════

class BoothCanvas(QGraphicsView):
    def __init__(self, scene: BoothScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#f5f5f5"))
        self.setMinimumSize(400, 300)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            f = 1.15 if event.angleDelta().y() > 0 else 1/1.15
            self.scale(f, f)
        else:
            super().wheelEvent(event)

    def fit(self):
        self.fitInView(self.scene().itemsBoundingRect().adjusted(-20, -20, 20, 20),
                       Qt.KeepAspectRatio)


# ═══════════════════════════════════════════════════════════════════════════════
#  Zone add/edit dialog
# ═══════════════════════════════════════════════════════════════════════════════

class ZoneDialog(QDialog):
    def __init__(self, zone: ZoneData = None, parent=None):
        super().__init__(parent)
        self._editing = zone is not None
        self.setWindowTitle("Edit Zone" if self._editing else "Add Zone")
        self.setMinimumWidth(360)
        self._build(zone)

    def _build(self, z):
        layout = QFormLayout(self)
        layout.setSpacing(8); layout.setContentsMargins(14, 14, 14, 14)

        self.lbl_edit = QLineEdit(z.label if z else "Work Area 1")
        layout.addRow("Label:", self.lbl_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems([ZONE_WORK, ZONE_PLEN, ZONE_DUCT])
        if z:
            self.type_combo.setCurrentText(z.zone_type)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        layout.addRow("Zone Type:", self.type_combo)

        def _spin(val, mn=0.5, mx=999.0):
            sp = QDoubleSpinBox()
            sp.setRange(mn, mx); sp.setDecimals(1); sp.setSuffix(" ft"); sp.setValue(val)
            return sp

        self.sp_L = _spin(z.length if z else 20.0)
        self.sp_W = _spin(z.width  if z else 14.0)
        self.sp_H = _spin(z.height if z else 9.0)
        layout.addRow("Length (L):", self.sp_L)
        self.sp_W_row = layout.addRow("Width (W):",  self.sp_W)
        self.sp_H_row = layout.addRow("Height (H):", self.sp_H)

        self.nozzle_combo = QComboBox()
        self.nozzle_combo.addItems([NOZZLE_TF, NOZZLE_DP, NOZZLE_3WY])
        if z:
            self.nozzle_combo.setCurrentText(z.nozzle_type)
        layout.addRow("Nozzle Type:", self.nozzle_combo)

        self.sp_override = QSpinBox()
        self.sp_override.setRange(0, 50); self.sp_override.setSpecialValueText("Auto")
        self.sp_override.setValue(z.nozzle_override if (z and z.nozzle_override) else 0)
        self.sp_override.setToolTip("0 = auto-calculate from dimensions. Override only if manual design requires.")
        layout.addRow("Nozzle Count Override:", self.sp_override)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); layout.addRow(sep)

        # Info label
        self._info = QLabel()
        self._info.setWordWrap(True)
        self._info.setStyleSheet("color:#888;font-size:11px;")
        layout.addRow(self._info)

        btns = QHBoxLayout()
        ok = QPushButton("OK")
        ok.setStyleSheet(f"background:{_PALETTE_DARK};color:white;padding:6px 16px;")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(cancel); btns.addWidget(ok)
        layout.addRow(btns)

        self._on_type_changed(self.type_combo.currentText())

    def _on_type_changed(self, zone_type):
        is_duct = zone_type == ZONE_DUCT
        # W and H less relevant for duct (width = duct diameter, H = duct height)
        lbl_map = {
            ZONE_WORK: ("Length (L):", "Width (W):",  "Height (H):"),
            ZONE_PLEN: ("Length (L):", "Width (W):",  "Height (H):"),
            ZONE_DUCT: ("Duct Length (L):", "Duct Width/Dia.:", "Duct Height:"),
        }
        lbls = lbl_map.get(zone_type, ("Length:", "Width:", "Height:"))
        # Update labels in form — find by row widget
        for row, lbl in enumerate([lbls[0], lbls[1], lbls[2]]):
            pass  # QFormLayout doesn't expose row labels easily; rely on tooltips
        nozzle_default = {ZONE_WORK: NOZZLE_TF, ZONE_PLEN: NOZZLE_DP, ZONE_DUCT: NOZZLE_DP}
        self.nozzle_combo.setCurrentText(nozzle_default.get(zone_type, NOZZLE_DP))

        tips = {
            ZONE_WORK: "Max 1,260 ft³ per TF nozzle · Max height 10 ft",
            ZONE_PLEN: "Nozzle centered overhead, tip 0-4.75\" from ceiling",
            ZONE_DUCT: "Max 28 ft per DP nozzle · Max round duct Ø 48\"",
        }
        self._info.setText(tips.get(zone_type, ""))

    def apply_to(self, z: ZoneData):
        z.label       = self.lbl_edit.text().strip() or z.label
        z.zone_type   = self.type_combo.currentText()
        z.length      = self.sp_L.value()
        z.width       = self.sp_W.value()
        z.height      = self.sp_H.value()
        z.nozzle_type = self.nozzle_combo.currentText()
        ov = self.sp_override.value()
        z.nozzle_override = ov if ov > 0 else None

    def get_zone(self):
        z = ZoneData(
            zone_type   = self.type_combo.currentText(),
            length      = self.sp_L.value(),
            width       = self.sp_W.value(),
            height      = self.sp_H.value(),
            nozzle_type = self.nozzle_combo.currentText(),
            label       = self.lbl_edit.text().strip(),
        )
        ov = self.sp_override.value()
        z.nozzle_override = ov if ov > 0 else None
        return z


# ═══════════════════════════════════════════════════════════════════════════════
#  BOM / Validation panel
# ═══════════════════════════════════════════════════════════════════════════════

class BOMPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4); layout.setSpacing(6)

        lbl = QLabel("Bill of Materials")
        lbl.setStyleSheet(f"font-weight:bold;font-size:13px;padding:4px;color:{_PALETTE_DARK};")
        layout.addWidget(lbl)

        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["Item", "P/N", "Qty"])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.tbl)

        # Validation area
        warn_lbl = QLabel("Validation")
        warn_lbl.setStyleSheet("font-weight:bold;color:#c0392b;padding:2px 0;")
        layout.addWidget(warn_lbl)

        self.warn_box = QTextEdit()
        self.warn_box.setReadOnly(True)
        self.warn_box.setMaximumHeight(120)
        self.warn_box.setStyleSheet("font-size:11px;background:#fff8f8;")
        layout.addWidget(self.warn_box)

        # Summary
        self.summary_lbl = QLabel()
        self.summary_lbl.setWordWrap(True)
        self.summary_lbl.setStyleSheet("font-size:11px;padding:4px;background:#f0f8ff;border:1px solid #cde;border-radius:3px;")
        layout.addWidget(self.summary_lbl)

    def refresh(self, zones: list[ZoneData], cylinder_model: str, detector_type: str,
                num_pull_stations: int = 1, has_elec_actuator: bool = False):
        # Collect nozzle counts by type
        nozzles = {}
        all_warnings = []
        for z in zones:
            nt = z.nozzle_type
            nozzles[nt] = nozzles.get(nt, 0) + z.nozzle_count
            all_warnings.extend(z.warnings())

        total_nozzles = sum(nozzles.values())

        # Cylinder selection recommendation
        # IND-21 handles up to 2 nozzles; IND-45 up to 4; IND-70 for large single-system
        # This is a simplified recommendation; exact selection requires piping balance check
        cyls_needed = self._recommend_cylinders(zones, cylinder_model)

        # Build BOM
        items = []

        # Cylinders
        for cyl_model, qty in cyls_needed.items():
            c = next((c for c in CYLINDERS if c["model"] == cyl_model), None)
            if c and qty > 0:
                items.append((f"Cylinder & Valve Assy – {c['model']} ({c['lbs']} lb ABC)", c["part"], qty))
                items.append((f"Mounting Bracket – {c['model']}", "B486487/88/100009", qty))
                items.append((f"Discharge Adapter Kit", "844908", qty))
                items.append((f"System Valve Actuator (SVA)", "B120042", qty))

        # UCH and actuation
        num_systems = len(cyls_needed)
        items.append(("Universal Control Head (UCH)", "B120099", num_systems))
        items.append(("System Nitrogen Cartridge", "B120043", num_systems))
        items.append(("Actuation Delay Assembly", "B100035", num_systems))
        items.append(("High-Pressure Nitrogen Tubing", "B120045", num_systems))

        # Nozzles
        for nt, qty in nozzles.items():
            items.append((f"{NOZZLE_DESC[nt]} Nozzle ({nt})", NOZZLE_PARTS[nt], qty))

        # Flow restrictors — needed when nozzle count > 1 in a branch
        if total_nozzles > 1:
            items.append(('3/4" Flow Restrictor', "B100050", total_nozzles))

        # Detection
        if detector_type:
            # Recommend at least 1 link per nozzle in the work area + 1 at each duct entrance
            work_nozzles = nozzles.get(NOZZLE_TF, 0)
            duct_nozzles = nozzles.get(NOZZLE_DP, 0)
            det_qty = work_nozzles + duct_nozzles + 1  # +1 for UCH
            items.append((detector_type, self._det_part(detector_type), det_qty))
            items.append(("Universal-Link Housing Kit", "B120064", det_qty))

        # Accessories
        items.append(("Remote Manual Release Pull Station", "87-120110-001", max(1, num_pull_stations)))
        items.append(('Microswitch Kit (for shutdowns)', "B120039", 2))
        items.append(('1/16" Control Cable (500 ft roll)', "219649", 1))
        items.append(('Crimping Tool', "253538", 1))
        if has_elec_actuator:
            items.append(("Electrical Actuator", "B100034", num_systems))

        # Populate table
        self.tbl.setRowCount(0)
        for name, pn, qty in items:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(name))
            self.tbl.setItem(r, 1, QTableWidgetItem(pn))
            qi = QTableWidgetItem(str(qty)); qi.setTextAlignment(Qt.AlignCenter)
            self.tbl.setItem(r, 2, qi)

        # Warnings
        if all_warnings:
            self.warn_box.setHtml("<br>".join(f"⚠ {w}" for w in all_warnings))
        else:
            self.warn_box.setHtml("<span style='color:green;'>✓ No design warnings</span>")

        # Summary
        cyl_summary = ", ".join(f"{qty}× {m}" for m, qty in cyls_needed.items())
        noz_summary = ", ".join(f"{qty}× {t}" for t, qty in nozzles.items())
        self.summary_lbl.setText(
            f"<b>Cylinders:</b> {cyl_summary or '—'}<br>"
            f"<b>Nozzles:</b> {noz_summary or '—'}<br>"
            f"<b>Total Nozzles:</b> {total_nozzles}"
        )

    def _recommend_cylinders(self, zones, preferred_model):
        """Simple cylinder recommendation: DC-21 per 2 nozzles, DC-45 per 4, DC-70 for large."""
        nozzle_totals = {}
        for z in zones:
            nt = z.nozzle_type
            nozzle_totals[nt] = nozzle_totals.get(nt, 0) + z.nozzle_count
        total = sum(nozzle_totals.values())
        if total == 0:
            return {}
        # User's preferred model governs — report how many needed
        caps = {"IND-21": 2, "IND-45": 4, "IND-70": 4}
        cap = caps.get(preferred_model, 4)
        num = max(1, math.ceil(total / cap))
        return {preferred_model: num}

    def _det_part(self, det_type):
        for d in DETECTOR_TYPES:
            if det_type in d or d in det_type:
                pn_idx = det_type.find("P/N ")
                if pn_idx >= 0:
                    return det_type[pn_idx + 4:].strip()
        return "—"


# ═══════════════════════════════════════════════════════════════════════════════
#  Main designer dialog
# ═══════════════════════════════════════════════════════════════════════════════

class PaintBoothDesigner(QDialog):
    """Top-level Paint Booth Dry Chemical Designer dialog."""

    def __init__(self, parent=None, project_name=""):
        super().__init__(parent)
        self.setWindowTitle(f"Paint Booth Suppression Designer — {project_name}" if project_name
                            else "Paint Booth Suppression Designer")
        self.setMinimumSize(1100, 700)
        self._project_name = project_name
        self._save_path = None

        self._scene = BoothScene()
        self._scene.zones_changed.connect(self._refresh_bom)

        self._build_ui()
        self._apply_booth_dims()

    # ── UI construction ─────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # ── Toolbar ──
        tb = QToolBar(); tb.setMovable(False)
        tb.setStyleSheet(f"QToolBar{{background:{_PALETTE_DARK};spacing:4px;padding:4px;}}"
                         f"QToolButton{{color:white;padding:4px 8px;border-radius:3px;}}"
                         f"QToolButton:hover{{background:#3a3f40;}}")
        for label, slot in [
            ("💾 Save",       self._save),
            ("📂 Open",       self._open),
            ("📄 Export PDF", self._export_pdf),
        ]:
            a = QAction(label, self); a.triggered.connect(slot); tb.addAction(a)
        tb.addSeparator()
        for label, slot in [
            ("＋ Work Area",    lambda: self._add_zone(ZONE_WORK)),
            ("＋ Plenum",       lambda: self._add_zone(ZONE_PLEN)),
            ("＋ Exhaust Duct", lambda: self._add_zone(ZONE_DUCT)),
        ]:
            a = QAction(label, self); a.triggered.connect(slot); tb.addAction(a)
        tb.addSeparator()
        fit_a = QAction("Fit View", self); fit_a.triggered.connect(self._canvas.fit if hasattr(self, "_canvas") else lambda: None)
        tb.addAction(fit_a)
        root.addWidget(tb)

        # ── Main splitter ──
        splitter = QSplitter(Qt.Horizontal)

        # Left: booth settings
        left = self._build_left_panel()
        left.setMinimumWidth(230); left.setMaximumWidth(280)
        splitter.addWidget(left)

        # Centre: canvas
        self._canvas = BoothCanvas(self._scene)
        splitter.addWidget(self._canvas)

        # Right: BOM
        self._bom = BOMPanel()
        self._bom.setMinimumWidth(300); self._bom.setMaximumWidth(380)
        splitter.addWidget(self._bom)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        root.addWidget(splitter)

        # Reconnect fit after canvas is built
        fit_a.triggered.disconnect()
        fit_a.triggered.connect(self._canvas.fit)

    def _build_left_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w); layout.setContentsMargins(8, 8, 8, 8); layout.setSpacing(8)

        lbl = QLabel("Booth Configuration")
        lbl.setStyleSheet(f"font-weight:bold;font-size:13px;color:{_PALETTE_DARK};padding:2px 0;")
        layout.addWidget(lbl)

        form = QFormLayout(); form.setSpacing(6)

        self.sp_booth_L = QDoubleSpinBox(); self.sp_booth_L.setRange(1, 500); self.sp_booth_L.setDecimals(1); self.sp_booth_L.setSuffix(" ft"); self.sp_booth_L.setValue(30.0)
        self.sp_booth_W = QDoubleSpinBox(); self.sp_booth_W.setRange(1, 200); self.sp_booth_W.setDecimals(1); self.sp_booth_W.setSuffix(" ft"); self.sp_booth_W.setValue(14.0)
        self.sp_booth_H = QDoubleSpinBox(); self.sp_booth_H.setRange(1, 40);  self.sp_booth_H.setDecimals(1); self.sp_booth_H.setSuffix(" ft"); self.sp_booth_H.setValue(9.0)
        self.sp_booth_L.valueChanged.connect(self._apply_booth_dims)
        self.sp_booth_W.valueChanged.connect(self._apply_booth_dims)
        self.sp_booth_H.valueChanged.connect(self._apply_booth_dims)

        form.addRow("Booth Length:", self.sp_booth_L)
        form.addRow("Booth Width:",  self.sp_booth_W)
        form.addRow("Booth Height:", self.sp_booth_H)

        self.type_combo = QComboBox(); self.type_combo.addItems(BOOTH_TYPES)
        form.addRow("Booth Type:", self.type_combo)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        form.addRow(sep1)

        self.cyl_combo = QComboBox()
        for c in CYLINDERS:
            self.cyl_combo.addItem(f"{c['model']}  ({c['lbs']} lb)", c["model"])
        self.cyl_combo.setCurrentText("IND-45  (45 lb)")
        self.cyl_combo.currentIndexChanged.connect(self._refresh_bom)
        form.addRow("Cylinder Model:", self.cyl_combo)

        self.det_combo = QComboBox(); self.det_combo.addItems(DETECTOR_TYPES)
        self.det_combo.setCurrentIndex(1)   # default 212°F fusible
        self.det_combo.currentIndexChanged.connect(self._refresh_bom)
        form.addRow("Detection Type:", self.det_combo)

        self.sp_pull = QSpinBox(); self.sp_pull.setRange(1, 10); self.sp_pull.setValue(1)
        self.sp_pull.valueChanged.connect(self._refresh_bom)
        form.addRow("Pull Stations:", self.sp_pull)

        self.chk_elec = QCheckBox("Electrical Actuator")
        self.chk_elec.stateChanged.connect(self._refresh_bom)
        form.addRow("", self.chk_elec)

        layout.addLayout(form)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); layout.addWidget(sep2)

        lbl2 = QLabel("Add Zones")
        lbl2.setStyleSheet("font-weight:bold;color:#555;font-size:11px;")
        layout.addWidget(lbl2)

        for label, zone_type, color in [
            ("＋ Work Area",    ZONE_WORK, _PALETTE_ORANGE),
            ("＋ Plenum",       ZONE_PLEN, "#27ae60"),
            ("＋ Exhaust Duct", ZONE_DUCT, "#e67e22"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(f"background:{color};color:white;padding:6px;font-weight:bold;border-radius:3px;")
            btn.clicked.connect(lambda checked, zt=zone_type: self._add_zone(zt))
            layout.addWidget(btn)

        sep3 = QFrame(); sep3.setFrameShape(QFrame.HLine); layout.addWidget(sep3)

        # Reference notes
        note = QLabel(
            "<b>Coverage Reference (NFPA 17 / DIOM):</b><br>"
            "• TF Nozzle: max <b>1,260 ft³</b>/nozzle<br>"
            "• Max booth height: <b>10 ft</b><br>"
            "• DP Nozzle: max <b>28 ft</b> duct/nozzle<br>"
            "• Pipe: <b>3/4\" NPT</b> min 150 lb fittings<br>"
            "• All systems: balanced piping required<br>"
            "• Verify with AHJ & current DIOM"
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size:10px;color:#666;background:#f9f9f9;padding:6px;border:1px solid #ddd;border-radius:3px;")
        layout.addWidget(note)

        layout.addStretch()
        return w

    # ── Actions ─────────────────────────────────────────────────────────────

    def _apply_booth_dims(self):
        self._scene.set_booth_outline(
            self.sp_booth_L.value(),
            self.sp_booth_W.value(),
            self.sp_booth_H.value(),
        )
        QTimer.singleShot(50, self._canvas.fit)

    def _add_zone(self, zone_type):
        z = ZoneData(
            zone_type = zone_type,
            length    = 20.0 if zone_type != ZONE_DUCT else 14.0,
            width     = self.sp_booth_W.value() if zone_type in (ZONE_WORK, ZONE_PLEN) else 3.0,
            height    = self.sp_booth_H.value(),
        )
        dlg = ZoneDialog(z, self)
        if dlg.exec_() == QDialog.Accepted:
            dlg.apply_to(z)
            self._scene.add_zone(z)
            self._canvas.fit()
            self._refresh_bom()

    def _refresh_bom(self):
        zones = self._scene.all_zones()
        cyl   = self.cyl_combo.currentData() or "IND-45"
        det   = self.det_combo.currentText()
        self._bom.refresh(zones, cyl, det,
                          num_pull_stations=self.sp_pull.value(),
                          has_elec_actuator=self.chk_elec.isChecked())

    # ── Save / Open ─────────────────────────────────────────────────────────

    def _save(self):
        if not self._save_path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Paint Booth Project", _projects_dir(),
                "Paint Booth Project (*.pbp)"
            )
            if not path:
                return
            if not path.lower().endswith(".pbp"):
                path += ".pbp"
            self._save_path = path

        data = {
            "version":      APP_VERSION,
            "project_name": self._project_name,
            "booth_L":      self.sp_booth_L.value(),
            "booth_W":      self.sp_booth_W.value(),
            "booth_H":      self.sp_booth_H.value(),
            "booth_type":   self.type_combo.currentText(),
            "cylinder":     self.cyl_combo.currentData(),
            "detector":     self.det_combo.currentText(),
            "pull_stations":self.sp_pull.value(),
            "elec_actuator":self.chk_elec.isChecked(),
            "zones":        [z.to_dict() for z in self._scene.all_zones()],
        }
        try:
            with open(self._save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(self, "Saved", f"Project saved to:\n{self._save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Paint Booth Project", _projects_dir(),
            "Paint Booth Project (*.pbp)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._load_data(data)
            self._save_path = path
        except Exception as e:
            QMessageBox.critical(self, "Open Error", str(e))

    def _load_data(self, data):
        self.sp_booth_L.setValue(data.get("booth_L", 30.0))
        self.sp_booth_W.setValue(data.get("booth_W", 14.0))
        self.sp_booth_H.setValue(data.get("booth_H", 9.0))
        idx = self.type_combo.findText(data.get("booth_type", ""))
        if idx >= 0: self.type_combo.setCurrentIndex(idx)
        idx = self.cyl_combo.findData(data.get("cylinder", "IND-45"))
        if idx >= 0: self.cyl_combo.setCurrentIndex(idx)
        idx = self.det_combo.findText(data.get("detector", ""))
        if idx >= 0: self.det_combo.setCurrentIndex(idx)
        self.sp_pull.setValue(data.get("pull_stations", 1))
        self.chk_elec.setChecked(data.get("elec_actuator", False))

        # Clear and reload zones
        for item in list(self._scene._zone_items):
            self._scene.remove_zone(item)
        ZoneData._id_counter = 0
        for zd in data.get("zones", []):
            z = ZoneData.from_dict(zd)
            self._scene.add_zone(z)
        self._apply_booth_dims()
        self._refresh_bom()

    # ── PDF Export ──────────────────────────────────────────────────────────

    def _export_pdf(self):
        default = os.path.join(
            _submittals_dir(),
            f"PaintBooth_{self._project_name or 'Design'}_{datetime.date.today()}.pdf"
        )
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", default, "PDF (*.pdf)")
        if not path:
            return
        try:
            self._do_export_pdf(path)
            QMessageBox.information(self, "Exported", f"PDF saved to:\n{path}")
            try:
                os.startfile(path)
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _do_export_pdf(self, path):
        try:
            from reportlab.lib.pagesizes import letter, landscape
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
            _rl = True
        except ImportError:
            _rl = False

        if not _rl:
            # Fallback: save canvas as pixmap
            pixmap = QPixmap(self.size())
            self.render(pixmap)
            # Save as PNG fallback
            png_path = path.replace(".pdf", ".png")
            pixmap.save(png_path)
            QMessageBox.information(self, "Note",
                f"reportlab not installed — saved as PNG:\n{png_path}")
            return

        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        doc = SimpleDocTemplate(path, pagesize=landscape(letter),
                                leftMargin=0.5*inch, rightMargin=0.5*inch,
                                topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story  = []

        # Title
        title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=18,
                                     textColor=colors.HexColor(_PALETTE_DARK))
        story.append(Paragraph("Paint Booth Dry Chemical Suppression Design", title_style))
        story.append(Paragraph(
            f"Project: {self._project_name or '—'}  |  "
            f"Booth Type: {self.type_combo.currentText()}  |  "
            f"Date: {datetime.date.today()}",
            styles["Normal"]
        ))
        story.append(Spacer(1, 0.15*inch))

        # Booth summary
        story.append(Paragraph("<b>Booth Dimensions</b>", styles["Heading2"]))
        booth_data = [
            ["Length", f"{self.sp_booth_L.value():.1f} ft"],
            ["Width",  f"{self.sp_booth_W.value():.1f} ft"],
            ["Height", f"{self.sp_booth_H.value():.1f} ft"],
            ["Cylinder", self.cyl_combo.currentText()],
            ["Detection", self.det_combo.currentText()],
        ]
        t = Table(booth_data, colWidths=[2.0*inch, 4.0*inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#eeeeee")),
            ("FONTNAME",   (0,0), (0,-1), "Helvetica-Bold"),
            ("GRID",       (0,0), (-1,-1), 0.5, colors.grey),
            ("FONTSIZE",   (0,0), (-1,-1), 10),
            ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, colors.HexColor("#f8f8f8")]),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.12*inch))

        # Zones table
        story.append(Paragraph("<b>Suppression Zones</b>", styles["Heading2"]))
        zones = self._scene.all_zones()
        if zones:
            zone_tbl_data = [["Zone", "Type", "L×W×H (ft)", "Volume (ft³)", "Nozzle Type", "Nozzles", "Warnings"]]
            for z in zones:
                warns = "; ".join(z.warnings()) or "✓ OK"
                zone_tbl_data.append([
                    z.label, z.zone_type,
                    f"{z.length:.1f} × {z.width:.1f} × {z.height:.1f}",
                    f"{z.volume:.0f}" if z.zone_type != ZONE_DUCT else "—",
                    z.nozzle_type, str(z.nozzle_count), warns,
                ])
            col_w = [1.4, 1.1, 1.6, 1.0, 1.0, 0.6, 3.0]
            zt = Table(zone_tbl_data, colWidths=[x*inch for x in col_w])
            zt.setStyle(TableStyle([
                ("BACKGROUND",     (0,0), (-1,0), colors.HexColor(_PALETTE_DARK)),
                ("TEXTCOLOR",      (0,0), (-1,0), colors.white),
                ("FONTNAME",       (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",       (0,0), (-1,-1), 9),
                ("GRID",           (0,0), (-1,-1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f5f5f5")]),
            ]))
            story.append(zt)
            story.append(Spacer(1, 0.12*inch))

        # BOM table
        story.append(Paragraph("<b>Bill of Materials</b>", styles["Heading2"]))
        bom_rows = [["Item", "Part Number", "Qty"]]
        for row in range(self._bom.tbl.rowCount()):
            bom_rows.append([
                self._bom.tbl.item(row, 0).text() if self._bom.tbl.item(row, 0) else "",
                self._bom.tbl.item(row, 1).text() if self._bom.tbl.item(row, 1) else "",
                self._bom.tbl.item(row, 2).text() if self._bom.tbl.item(row, 2) else "",
            ])
        bom_t = Table(bom_rows, colWidths=[4.5*inch, 2.0*inch, 0.6*inch])
        bom_t.setStyle(TableStyle([
            ("BACKGROUND",     (0,0), (-1,0), colors.HexColor(_PALETTE_ORANGE)),
            ("TEXTCOLOR",      (0,0), (-1,0), colors.white),
            ("FONTNAME",       (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",       (0,0), (-1,-1), 9),
            ("GRID",           (0,0), (-1,-1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f9f9f9")]),
        ]))
        story.append(bom_t)
        story.append(Spacer(1, 0.15*inch))

        # Compliance note
        story.append(Paragraph(
            "<b>Design Basis:</b> Badger Industry Guard Dry Chemical System for Vehicle Spray Booths, "
            "P/N 60-900007-001 (Jan 2007). UL Listing File No. EX 4864 / ULC CEX 515. "
            "NFPA 17 (Standard for Dry Chemical Systems) / NFPA 33 (Spray Application). "
            "All systems must be designed, installed, inspected, and maintained by qualified personnel. "
            "Verify all quantities and configurations with the current DIOM and AHJ before installation.",
            ParagraphStyle("Note", parent=styles["Normal"], fontSize=8,
                           textColor=colors.HexColor("#666666"))
        ))

        doc.build(story)
