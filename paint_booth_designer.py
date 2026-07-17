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

try:
    import fitz
    _FITZ_OK = True
except ImportError:
    _FITZ_OK = False


def _submittals_dir():
    if getattr(sys, 'frozen', False):
        base = os.path.join(os.path.expanduser("~"), "Documents", "DFP TakeoffPro")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(base, "Submittals")
    os.makedirs(p, exist_ok=True)
    return p

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

# Zone types — Figure 4-14 / Table 4-13 (DIOM P/N 60-900007-001)
ZONE_WORK   = "Work Area"
ZONE_DUCT   = "Exhaust Duct"
ZONE_PIT    = "Pit (Straight)"             # D/P nozzle, max 40 ft/nozzle
# 6 plenum / pit types from Figure 4-14:
ZONE_CF_BOX = "Cross Flow (Box)"            # row 1 — D/P, 16×4×18 ft/nozzle
ZONE_CF_DT  = "Cross Flow (Drive Thru)"     # row 2 — D/P, 15×4×12 ft/nozzle, U-shape
ZONE_RAISED = "Raised Floor"                # row 3 — D/P, 30×15×1 ft/nozzle
ZONE_SD_EXH = "Side Exhaust"               # row 4 — D/P, 4×4×40 ft/nozzle
ZONE_PIT_T  = "Pit with Tunnel"             # row 5 — 3-Way, legs≤18 ft, tunnel≤18 ft
ZONE_PIT_VT = "Pit w/ Vert. Transition"    # row 6 — 3-Way, legs≤18 ft, vert≤14 ft
# Legacy alias kept for backward compatibility with saved files
ZONE_PLEN   = "Plenum"

ZONE_FILL = {
    ZONE_WORK:   QColor(41,  128, 185, 35),
    ZONE_DUCT:   QColor(230, 126, 34,  35),
    ZONE_PIT:    QColor(120,  80, 40,  50),
    ZONE_CF_BOX: QColor(39,  174, 96,  35),
    ZONE_CF_DT:  QColor(26,  188, 120, 35),
    ZONE_RAISED: QColor(155,  89, 182, 35),
    ZONE_SD_EXH: QColor(52,  152, 219, 35),
    ZONE_PIT_T:  QColor(120,  80, 40,  50),
    ZONE_PIT_VT: QColor(100,  60, 30,  50),
    ZONE_PLEN:   QColor(39,  174, 96,  35),   # legacy
}
ZONE_BORDER_COL = {
    ZONE_WORK:   QColor(41,  128, 185),
    ZONE_DUCT:   QColor(230, 126, 34),
    ZONE_PIT:    QColor(140,  90, 40),
    ZONE_CF_BOX: QColor(39,  174, 96),
    ZONE_CF_DT:  QColor(26,  188, 120),
    ZONE_RAISED: QColor(155,  89, 182),
    ZONE_SD_EXH: QColor(52,  152, 219),
    ZONE_PIT_T:  QColor(140,  90, 40),
    ZONE_PIT_VT: QColor(110,  65, 25),
    ZONE_PLEN:   QColor(39,  174, 96),        # legacy
}

# Per-nozzle module limits from DIOM Table 4-13 / Figure 4-14
# (max_L_ft, max_W_ft, max_H_ft)
PLEN_MODULE = {
    ZONE_CF_BOX: (16.0, 4.0,  18.0),
    ZONE_CF_DT:  (15.0, 4.0,  12.0),
    ZONE_RAISED: (30.0, 15.0,  1.0),
    ZONE_SD_EXH: (40.0, 4.0,   4.0),
    ZONE_PLEN:   (15.0, 15.0, 99.0),   # legacy generic
}

# Coverage limits
MAX_WORK_VOL_FT3    = 1260.0  # ft³ per TF nozzle (§4-5.1.1)
MAX_WORK_HEIGHT_FT  = 24.0    # ft — per DIOM §4-5.1.1 Table 4-2
MAX_DUCT_LEN_FT     = 28.0    # ft per DP nozzle (§4-5.1.3)
MAX_DUCT_DIA_IN     = 48.0    # inches — round duct
MAX_DUCT_PERIM_IN   = 150.8   # inches — rectangular duct perimeter
MAX_NOZZLE_OFFSET   = 2.75    # ft — nozzle may be offset from module centre
NOZZLE_TIP_MAX_IN   = 4.75    # inches from ceiling (TF nozzle)
MAX_PIT_STRAIGHT_FT = 40.0    # ft per DP nozzle — straight pit
MAX_PIT_LEG_FT      = 18.0    # ft per main leg per 3-Way nozzle
MAX_PIT_TUNNEL_FT   = 18.0    # ft per tunnel arm per 3-Way nozzle (Table 4-5)
MAX_PIT_VERT_FT     = 14.0    # ft vertical stack height per 3-Way nozzle
MAX_PIT_CROSS_FT    = 4.0     # ft — standard pit/tunnel cross-section width per single nozzle (Table 4-5)

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
_ISO_DSF = 0.25   # depth scale factor (compressed so deep booths don't stretch)

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


# DIOM Table 4-2 — Module dimensions per booth height
# key = booth height (ft, ceiling to 12); value = [(side2_ft, side1_ft), ...]
# side2 = column header (smaller), side1 = table value (larger)
# Heights 0-12 use the 12-ft row; heights above 24 ft are not permitted.
_TABLE_4_2 = {
    12: [(7.5,14.00),(8.0,13.10),(8.5,12.30),(9.0,11.60),(9.5,11.00),(10.0,10.50)],
    13: [(7.5,12.90),(8.0,12.10),(8.5,11.40),(9.0,10.70),(9.5,10.20),(10.0, 9.60)],
    14: [(7.5,12.00),(8.0,11.20),(8.5,10.50),(9.0,10.00),(9.5, 9.40),(10.0, 9.00)],
    15: [(7.5,11.20),(8.0,10.50),(8.5, 9.80),(9.0, 9.30),(9.5, 8.80),(10.0, 8.40)],
    16: [(7.5,10.50),(8.0, 9.80),(8.5, 9.20),(9.0, 8.70),(9.5, 8.20),(10.0, 7.80)],
    17: [(7.5, 9.80),(8.0, 9.20),(8.5, 8.70),(9.0, 8.20),(9.5, 7.80),(10.0, 7.40)],
    18: [(7.5, 9.30),(8.0, 8.75),(8.5, 8.20),(9.0, 7.70),(9.5, 7.30),(10.0, 7.00)],
    19: [(7.5, 8.80),(8.0, 8.30),(8.5, 7.80),(9.0, 7.30),(9.5, 6.90),(10.0, 6.60)],
    20: [(7.5, 8.40),(8.0, 7.80),(8.5, 7.40),(9.0, 7.00),(9.5, 6.60),(10.0, 6.30)],
    21: [(7.5, 8.00),(8.0, 7.50),(8.5, 7.00),(9.0, 6.70),(9.5, 6.30),(10.0, 6.00)],
    22: [(7.5, 7.60),(8.0, 7.10),(8.5, 6.70),(9.0, 6.30),(9.5, 6.00),(10.0, 5.70)],
    23: [(7.5, 7.30),(8.0, 6.80),(8.5, 6.40),(9.0, 6.00),(9.5, 5.70),(10.0, 5.40)],
    24: [(7.5, 7.00),(8.0, 6.50),(8.5, 6.10),(9.0, 5.80),(9.5, 5.50),(10.0, 5.25)],
}


def _work_area_modules(L: float, W: float, H: float):
    """
    Determine the minimum nozzle/module count for a work area per DIOM Table 4-2.

    Returns (total_nozzles, n_along_L, n_along_W, mod_L_ft, mod_W_ft).
    Both the area constraint (Table 4-2) and the volume constraint (1,260 ft³)
    must be satisfied; this function satisfies both simultaneously.
    """
    H_key = min(24, max(12, math.ceil(H)))
    entries = _TABLE_4_2[H_key]

    best = None
    for s2, s1 in entries:
        # Try each table pair in both orientations (s1 along L or along W)
        for (dim_L, dim_W) in [(s1, s2), (s2, s1)]:
            nL = max(1, math.ceil(L / dim_L))
            nW = max(1, math.ceil(W / dim_W))
            # Honour volume constraint too
            while (L / nL) * (W / nW) * H > MAX_WORK_VOL_FT3 + 0.01:
                if (L / nL) >= (W / nW):
                    nL += 1
                else:
                    nW += 1
            total = nL * nW
            if best is None or total < best[0]:
                best = (total, nL, nW, L / nL, W / nW)

    return best if best else (max(1, math.ceil(L * W * H / MAX_WORK_VOL_FT3)), 1,
                              max(1, math.ceil(L * W * H / MAX_WORK_VOL_FT3)), L, W / 1)


# ═══════════════════════════════════════════════════════════════════════════════
#  Data model
# ═══════════════════════════════════════════════════════════════════════════════

class ZoneData:
    """Represents one suppression zone in the booth."""
    _id_counter = 0

    def __init__(self, zone_type=ZONE_WORK, length=20.0, width=14.0, height=9.0,
                 nozzle_type=None, label="", x=0.0, y=0.0, nozzle_override=None,
                 tunnel_length=18.0, tunnel_width=None):
        ZoneData._id_counter += 1
        self.uid = ZoneData._id_counter
        self.zone_type     = zone_type
        self.length        = float(length)
        self.width         = float(width)
        self.height        = float(height)
        self.tunnel_length = float(tunnel_length)  # ZONE_PIT_T only
        self.tunnel_width  = float(tunnel_width) if tunnel_width is not None else float(width)  # ZONE_PIT_T only
        self.nozzle_type   = nozzle_type or self._default_nozzle()
        self.label         = label or f"{zone_type} {self.uid}"
        self.x             = float(x)   # ft from scene origin
        self.y             = float(y)
        self.nozzle_override = nozzle_override  # int or None — override auto count

    def _default_nozzle(self):
        return {
            ZONE_WORK:   NOZZLE_TF,
            ZONE_DUCT:   NOZZLE_DP,
            ZONE_CF_BOX: NOZZLE_DP,
            ZONE_CF_DT:  NOZZLE_DP,
            ZONE_RAISED: NOZZLE_DP,
            ZONE_SD_EXH: NOZZLE_DP,
            ZONE_PIT_T:  NOZZLE_3WY,
            ZONE_PIT_VT: NOZZLE_3WY,
            ZONE_PLEN:   NOZZLE_DP,
        }.get(self.zone_type, NOZZLE_DP)

    @property
    def volume(self):
        return self.length * self.width * self.height

    @property
    def nozzle_count(self):
        if self.nozzle_override is not None:
            return self.nozzle_override
        if self.zone_type == ZONE_WORK:
            return _work_area_modules(self.length, self.width, self.height)[0]
        elif self.zone_type == ZONE_DUCT:
            return max(1, math.ceil(self.length / MAX_DUCT_LEN_FT))
        elif self.zone_type in PLEN_MODULE:
            # Grid of nozzles based on per-nozzle module dimensions (Table 4-13)
            mL, mW, _ = PLEN_MODULE[self.zone_type]
            nL = max(1, math.ceil(self.length / mL))
            nW = max(1, math.ceil(self.width  / mW))
            return nL * nW
        elif self.zone_type == ZONE_PIT:
            n_len = max(1, math.ceil(self.length / MAX_PIT_STRAIGHT_FT))
            n_wid = max(1, math.ceil(self.width  / MAX_PIT_CROSS_FT))
            return n_len * n_wid
        elif self.zone_type == ZONE_PIT_T:
            tw = getattr(self, "tunnel_width", self.width)
            n_main = (max(1, math.ceil(self.length / (MAX_PIT_LEG_FT * 2)))
                      * max(1, math.ceil(self.width / MAX_PIT_CROSS_FT)))
            n_tun  = (max(1, math.ceil(self.tunnel_length / MAX_PIT_TUNNEL_FT))
                      * max(1, math.ceil(tw / MAX_PIT_CROSS_FT)))
            return max(n_main, n_tun)
        elif self.zone_type == ZONE_PIT_VT:
            n_main = (max(1, math.ceil(self.length / (MAX_PIT_LEG_FT * 2)))
                      * max(1, math.ceil(self.width / MAX_PIT_CROSS_FT)))
            n_vert = max(1, math.ceil(self.tunnel_length / MAX_PIT_VERT_FT))
            return max(n_main, n_vert)
        else:
            return 1

    @property
    def module_info(self):
        """Return (total, n_along_L, n_along_W, mod_L_ft, mod_W_ft) for ZONE_WORK."""
        if self.zone_type != ZONE_WORK:
            return None
        if self.nozzle_override is not None:
            nc = self.nozzle_override
            rows, cols = _nozzle_grid(nc)
            return (nc, cols, rows, self.length / max(1, cols), self.width / max(1, rows))
        return _work_area_modules(self.length, self.width, self.height)

    def warnings(self):
        """Return list of warning strings for this zone."""
        w = []
        if self.zone_type == ZONE_WORK:
            if self.height > 24.0:
                w.append(f"[{self.label}] Height {self.height:.1f} ft exceeds 24 ft max (Table 4-2)")
            vol_per = self.volume / max(1, self.nozzle_count)
            if vol_per > MAX_WORK_VOL_FT3:
                w.append(f"[{self.label}] Volume/nozzle {vol_per:.0f} ft³ exceeds 1,260 ft³ max")
        elif self.zone_type == ZONE_DUCT:
            if self.length / max(1, self.nozzle_count) > MAX_DUCT_LEN_FT:
                w.append(f"[{self.label}] Duct segment exceeds {MAX_DUCT_LEN_FT:.0f} ft max per DP nozzle")
        elif self.zone_type == ZONE_PIT:
            n_len = max(1, math.ceil(self.length / MAX_PIT_STRAIGHT_FT))
            n_wid = max(1, math.ceil(self.width  / MAX_PIT_CROSS_FT))
            seg = self.length / n_len
            seg_w = self.width / n_wid
            if seg > MAX_PIT_STRAIGHT_FT:
                w.append(f"[{self.label}] Pit segment {seg:.0f} ft exceeds {MAX_PIT_STRAIGHT_FT:.0f} ft max per DP nozzle")
            if seg_w > MAX_PIT_CROSS_FT:
                w.append(f"[{self.label}] Pit cross-section {seg_w:.1f} ft wide exceeds {MAX_PIT_CROSS_FT:.0f} ft max per DP nozzle")
        elif self.zone_type in PLEN_MODULE:
            mL, mW, mH = PLEN_MODULE[self.zone_type]
            if self.height > mH:
                w.append(f"[{self.label}] Height {self.height:.1f} ft exceeds {mH:.0f} ft max (Figure 4-14)")
            nL = max(1, math.ceil(self.length / mL))
            nW = max(1, math.ceil(self.width  / mW))
            seg_L = self.length / nL
            seg_W = self.width  / nW
            if seg_L > mL:
                w.append(f"[{self.label}] Module length {seg_L:.1f} ft exceeds {mL:.0f} ft max")
            if seg_W > mW:
                w.append(f"[{self.label}] Module width {seg_W:.1f} ft exceeds {mW:.0f} ft max")
        elif self.zone_type == ZONE_PIT_T:
            tw = getattr(self, "tunnel_width", self.width)
            n_main_len = max(1, math.ceil(self.length / (MAX_PIT_LEG_FT * 2)))
            n_main_wid = max(1, math.ceil(self.width  / MAX_PIT_CROSS_FT))
            leg = self.length / n_main_len / 2
            leg_w = self.width / n_main_wid
            if leg > MAX_PIT_LEG_FT:
                w.append(f"[{self.label}] Pit leg {leg:.0f} ft exceeds {MAX_PIT_LEG_FT:.0f} ft max per 3-Way")
            if leg_w > MAX_PIT_CROSS_FT:
                w.append(f"[{self.label}] Pit cross-section {leg_w:.1f} ft wide exceeds {MAX_PIT_CROSS_FT:.0f} ft max per 3-Way")
            n_tun_len = max(1, math.ceil(self.tunnel_length / MAX_PIT_TUNNEL_FT))
            n_tun_wid = max(1, math.ceil(tw / MAX_PIT_CROSS_FT))
            tun = self.tunnel_length / n_tun_len
            tun_w = tw / n_tun_wid
            if tun > MAX_PIT_TUNNEL_FT:
                w.append(f"[{self.label}] Tunnel {tun:.0f} ft exceeds {MAX_PIT_TUNNEL_FT:.0f} ft max per 3-Way")
            if tun_w > MAX_PIT_CROSS_FT:
                w.append(f"[{self.label}] Tunnel width {tun_w:.1f} ft exceeds {MAX_PIT_CROSS_FT:.0f} ft max per 3-Way")
        elif self.zone_type == ZONE_PIT_VT:
            n_main_len = max(1, math.ceil(self.length / (MAX_PIT_LEG_FT * 2)))
            n_main_wid = max(1, math.ceil(self.width  / MAX_PIT_CROSS_FT))
            leg = self.length / n_main_len / 2
            leg_w = self.width / n_main_wid
            if leg > MAX_PIT_LEG_FT:
                w.append(f"[{self.label}] Pit leg {leg:.0f} ft exceeds {MAX_PIT_LEG_FT:.0f} ft max per 3-Way")
            if leg_w > MAX_PIT_CROSS_FT:
                w.append(f"[{self.label}] Pit cross-section {leg_w:.1f} ft wide exceeds {MAX_PIT_CROSS_FT:.0f} ft max per 3-Way")
            n_vert = max(1, math.ceil(self.tunnel_length / MAX_PIT_VERT_FT))
            vt = self.tunnel_length / n_vert
            if vt > MAX_PIT_VERT_FT:
                w.append(f"[{self.label}] Vert. stack {vt:.0f} ft exceeds {MAX_PIT_VERT_FT:.0f} ft max per 3-Way")
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
        self.setPos(self.zone.x * PX_PER_FT, self.zone.y * PX_PER_FT)

    def boundingRect(self):
        z = self.zone
        w_px = z.length * PX_PER_FT
        h_px = z.height * PX_PER_FT
        dx   = _ddx(z.width)
        dy   = _ddy(z.width)   # negative (up on screen)
        pad  = 24
        if z.zone_type == ZONE_PIT_T:
            # Extend to cover tunnel going deeper, and widen pad if the tunnel
            # is wider than the main shaft (tunnel_width can differ from width)
            tdx = _ddx(z.width + z.tunnel_length)
            tdy = _ddy(z.width + z.tunnel_length)
            tw  = getattr(z, "tunnel_width", z.width)
            extra = max(0.0, (tw - z.width) / 2 * PX_PER_FT)
            return QRectF(0 - extra, min(dy, tdy) - pad,
                          w_px + tdx + pad + extra, h_px - min(dy, tdy) + pad)
        return QRectF(0, dy - pad, w_px + dx + pad, h_px - dy + pad)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            new_pos = self.pos()
            # Delta since last zone position — move associated nozzles with us
            old_x_px = self.zone.x * PX_PER_FT
            old_y_px = self.zone.y * PX_PER_FT
            dx = new_pos.x() - old_x_px
            dy = new_pos.y() - old_y_px
            self.zone.x = new_pos.x() / PX_PER_FT
            self.zone.y = new_pos.y() / PX_PER_FT
            if (dx != 0 or dy != 0) and hasattr(self._scene_ref, "_nozzle_items"):
                for n in self._scene_ref._nozzle_items:
                    if n.zone_uid == self.zone.uid:
                        n.setPos(n.pos().x() + dx, n.pos().y() + dy)
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

        # ── Pit / special plenum zones — delegated renderers ─────────────────
        if z.zone_type in (ZONE_PIT_T, ZONE_PIT_VT):
            self._paint_pit(painter, z)
            return
        if z.zone_type == ZONE_CF_DT:
            self._paint_drive_thru(painter, z)
            return
        if z.zone_type == ZONE_RAISED:
            self._paint_raised_floor(painter, z)
            return
        if z.zone_type == ZONE_SD_EXH:
            self._paint_side_exhaust(painter, z)
            return

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

        # ── Module grid on ceiling (work areas only) ──────────────────────────
        if z.zone_type == ZONE_WORK:
            minfo = z.module_info
            if minfo:
                _, nL, nW, _, _ = minfo
                if nL > 1 or nW > 1:
                    len_x = ftr.x() - ftl.x()
                    len_y = ftr.y() - ftl.y()
                    dep_x = btl.x() - ftl.x()
                    dep_y = btl.y() - ftl.y()
                    grid_pen = QPen(QColor(60, 60, 200, 180), 1.2, Qt.DotLine)
                    painter.setPen(grid_pen)
                    painter.setBrush(Qt.NoBrush)
                    for i in range(1, nL):
                        f = i / nL
                        p1 = QPointF(ftl.x() + len_x * f, ftl.y() + len_y * f)
                        p2 = QPointF(p1.x() + dep_x,       p1.y() + dep_y)
                        painter.drawLine(p1, p2)
                    for j in range(1, nW):
                        f = j / nW
                        p1 = QPointF(ftl.x() + dep_x * f, ftl.y() + dep_y * f)
                        p2 = QPointF(p1.x() + len_x,       p1.y() + len_y)
                        painter.drawLine(p1, p2)

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
            minfo = z.module_info
            if minfo:
                _, nL, nW, mL, mW = minfo
                noz_txt += f"  ({nL}×{nW} modules, {mL:.1f}′×{mW:.1f}′ ea)"
        painter.drawText(QRectF(5, 33, w_px - 10, 14), Qt.AlignLeft | Qt.AlignVCenter, noz_txt)

        if z.warnings():
            painter.setPen(QPen(QColor("#e74c3c"), 1))
            painter.setFont(QFont("Arial", 7, QFont.Bold))
            painter.drawText(QRectF(5, h_px - 18, w_px - 10, 14),
                             Qt.AlignLeft, "⚠ " + z.warnings()[0])

    def _paint_pit(self, painter, z):
        """Draw pit zones as hatched floor-level channels."""
        border  = ZONE_BORDER_COL[z.zone_type]
        fill    = ZONE_FILL[z.zone_type]
        sel_col = QColor(_PALETTE_ORANGE)
        is_sel  = self.isSelected() or self._hover
        pen_w   = 2.5 if is_sel else 1.8

        L_px = z.length * PX_PER_FT
        W_px = z.width  * PX_PER_FT
        dx   = _ddx(z.width)
        dy   = _ddy(z.width)   # negative (up)

        def _flat_quad(x0, y0, l_ft, w_ft):
            """Isometric top-face parallelogram for a ground-plane rectangle."""
            lp = l_ft * PX_PER_FT
            ddx_ = _ddx(w_ft); ddy_ = _ddy(w_ft)
            return QPolygonF([
                QPointF(x0,        y0),
                QPointF(x0 + lp,   y0),
                QPointF(x0 + lp + ddx_, y0 + ddy_),
                QPointF(x0 + ddx_, y0 + ddy_),
            ])

        # Build path from the shaft(s)
        path = QPainterPath()

        # Main shaft
        shaft = _flat_quad(0, 0, z.length, z.width)
        path.addPolygon(shaft)
        path.closeSubpath()

        if z.zone_type == ZONE_PIT_T:
            # Tunnel branches off perpendicular from center of main shaft's far edge.
            # "Far edge" is the back side; tunnel goes further in depth direction.
            t_L  = z.tunnel_length
            t_W  = getattr(z, "tunnel_width", z.width)
            # Center of main shaft along its length
            cx   = L_px / 2 + _ddx(z.width)
            cy   = _ddy(z.width)
            # Tunnel is tunnel_width × tunnel_length, centered on that midpoint
            half = t_W / 2 * PX_PER_FT
            tunnel = QPolygonF([
                QPointF(cx - half,              cy),
                QPointF(cx + half,              cy),
                QPointF(cx + half + _ddx(t_L),  cy + _ddy(t_L)),
                QPointF(cx - half + _ddx(t_L),  cy + _ddy(t_L)),
            ])
            path.addPolygon(tunnel)
            path.closeSubpath()

        # Fill
        fill_col = QColor(border.red(), border.green(), border.blue(), 55)
        painter.setBrush(QBrush(fill_col))
        painter.setPen(QPen(sel_col if is_sel else border.darker(110), pen_w))
        painter.drawPath(path)

        # Cross-hatch to mark it as below-grade
        hatch_pen = QPen(QColor(border.red(), border.green(), border.blue(), 80), 0.8)
        painter.setPen(hatch_pen)
        # Hatch lines along the shaft
        n_lines = max(2, int(z.length / 4))
        for i in range(1, n_lines):
            f = i / n_lines
            x0_ = f * L_px;        y0_ = 0.0
            x1_ = x0_ + dx;        y1_ = dy
            painter.drawLine(QPointF(x0_, y0_), QPointF(x1_, y1_))

        # Labels
        painter.setPen(QPen(border.darker(150)))
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        painter.drawText(QRectF(4, -18, L_px - 8, 16), Qt.AlignLeft | Qt.AlignVCenter, z.label)
        painter.setFont(QFont("Arial", 7))
        painter.setPen(QPen(border.darker(130)))
        if z.zone_type == ZONE_PIT_T:
            tw = getattr(z, "tunnel_width", z.width)
            info = f"Main {z.length:.0f}′ × Tunnel {z.tunnel_length:.0f}′L × {tw:.0f}′W"
        else:
            info = f"{z.length:.0f}′ long × {z.width:.0f}′ wide"
        painter.drawText(QRectF(4, -5, L_px - 8, 14), Qt.AlignLeft | Qt.AlignVCenter, info)
        noz_txt = f"{z.nozzle_count}× {z.nozzle_type}"
        painter.drawText(QRectF(4, 8, L_px - 8, 14), Qt.AlignLeft | Qt.AlignVCenter, noz_txt)
        if z.warnings():
            painter.setPen(QPen(QColor("#e74c3c"), 1))
            painter.setFont(QFont("Arial", 7, QFont.Bold))
            painter.drawText(QRectF(4, 20, L_px - 8, 14), Qt.AlignLeft, "⚠ " + z.warnings()[0])

    def _paint_drive_thru(self, painter, z):
        """Cross Flow Drive-Thru — U-shape (open on two ends, side walls only)."""
        border = ZONE_BORDER_COL.get(z.zone_type, QColor(26, 188, 120))
        is_sel = self.isSelected() or self._hover
        pen_w  = 2.5 if is_sel else 1.8
        sel_col = QColor(_PALETTE_ORANGE)

        L_px = z.length * PX_PER_FT
        H_px = z.height * PX_PER_FT
        dx   = _ddx(z.width)
        dy   = _ddy(z.width)

        # Draw as a standard 3-D box but with dashed front/back faces to show open ends
        fill_col = QColor(border.red(), border.green(), border.blue(), 40)
        painter.setBrush(QBrush(fill_col))
        painter.setPen(QPen(sel_col if is_sel else border.darker(110), pen_w))

        # Top face
        top = QPolygonF([QPointF(0, 0), QPointF(L_px, 0),
                         QPointF(L_px + dx, dy), QPointF(dx, dy)])
        painter.drawPolygon(top)

        # Left side face (solid — closed end)
        left = QPolygonF([QPointF(0, 0), QPointF(0, H_px),
                          QPointF(dx, H_px + dy), QPointF(dx, dy)])
        painter.drawPolygon(left)

        # Right side face (solid — closed end)
        right = QPolygonF([QPointF(L_px, 0), QPointF(L_px, H_px),
                           QPointF(L_px + dx, H_px + dy), QPointF(L_px + dx, dy)])
        painter.drawPolygon(right)

        # Front and back edges drawn dashed to show open ends
        dash_pen = QPen(sel_col if is_sel else border, pen_w, Qt.DashLine)
        painter.setPen(dash_pen)
        painter.drawLine(QPointF(0, 0), QPointF(0, H_px))           # front-left edge
        painter.drawLine(QPointF(L_px, 0), QPointF(L_px, H_px))     # front-right edge
        painter.drawLine(QPointF(dx, dy), QPointF(dx, H_px + dy))   # back-left edge
        painter.drawLine(QPointF(L_px + dx, dy), QPointF(L_px + dx, H_px + dy))  # back-right

        # Label
        painter.setPen(QPen(border.darker(150)))
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        painter.drawText(QRectF(5, 5, L_px - 10, 16), Qt.AlignLeft | Qt.AlignVCenter, z.label)
        painter.setFont(QFont("Arial", 7))
        painter.setPen(QPen(border.darker(130)))
        painter.drawText(QRectF(5, 20, L_px - 10, 14), Qt.AlignLeft,
                         f"{z.length:.0f}′×{z.width:.0f}′×{z.height:.0f}′  {z.nozzle_count}× {z.nozzle_type}")
        if z.warnings():
            painter.setPen(QPen(QColor("#e74c3c"), 1))
            painter.setFont(QFont("Arial", 7, QFont.Bold))
            painter.drawText(QRectF(5, 34, L_px - 10, 14), Qt.AlignLeft, "⚠ " + z.warnings()[0])

    def _paint_raised_floor(self, painter, z):
        """Raised Floor — very flat isometric box."""
        border = ZONE_BORDER_COL.get(z.zone_type, QColor(155, 89, 182))
        is_sel = self.isSelected() or self._hover
        pen_w  = 2.5 if is_sel else 1.8
        sel_col = QColor(_PALETTE_ORANGE)

        L_px = z.length * PX_PER_FT
        H_px = max(z.height * PX_PER_FT, 6.0)   # min visual thickness
        dx   = _ddx(z.width)
        dy   = _ddy(z.width)

        fill_col = QColor(border.red(), border.green(), border.blue(), 50)
        painter.setBrush(QBrush(fill_col))
        painter.setPen(QPen(sel_col if is_sel else border.darker(110), pen_w))

        # Top face (dominant — it's mostly flat)
        top = QPolygonF([QPointF(0, 0), QPointF(L_px, 0),
                         QPointF(L_px + dx, dy), QPointF(dx, dy)])
        painter.drawPolygon(top)

        # Front face (thin)
        front = QPolygonF([QPointF(0, 0), QPointF(L_px, 0),
                           QPointF(L_px, H_px), QPointF(0, H_px)])
        painter.drawPolygon(front)

        # Right face (thin)
        right = QPolygonF([QPointF(L_px, 0), QPointF(L_px + dx, dy),
                           QPointF(L_px + dx, H_px + dy), QPointF(L_px, H_px)])
        painter.drawPolygon(right)

        # Dot grid on top face to suggest floor grating
        dot_pen = QPen(border.darker(130), 1.5)
        painter.setPen(dot_pen)
        cols = max(2, int(z.length / 5))
        rows = max(2, int(z.width  / 5))
        for r in range(1, rows):
            for c in range(1, cols):
                fx = c / cols; fy = r / rows
                px = fx * L_px + _ddx(z.width * fy)
                py = _ddy(z.width * fy)
                painter.drawPoint(QPointF(px, py))

        # Label
        painter.setPen(QPen(border.darker(150)))
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        painter.drawText(QRectF(5, H_px + 2, L_px - 10, 16), Qt.AlignLeft, z.label)
        painter.setFont(QFont("Arial", 7))
        painter.setPen(QPen(border.darker(130)))
        painter.drawText(QRectF(5, H_px + 16, L_px - 10, 14), Qt.AlignLeft,
                         f"{z.length:.0f}′×{z.width:.0f}′×{z.height:.1f}′  {z.nozzle_count}× {z.nozzle_type}")
        if z.warnings():
            painter.setPen(QPen(QColor("#e74c3c"), 1))
            painter.setFont(QFont("Arial", 7, QFont.Bold))
            painter.drawText(QRectF(5, H_px + 30, L_px - 10, 14), Qt.AlignLeft, "⚠ " + z.warnings()[0])

    def _paint_side_exhaust(self, painter, z):
        """Side Exhaust — narrow tall channel drawn as a vertical isometric slab."""
        border = ZONE_BORDER_COL.get(z.zone_type, QColor(52, 152, 219))
        is_sel = self.isSelected() or self._hover
        pen_w  = 2.5 if is_sel else 1.8
        sel_col = QColor(_PALETTE_ORANGE)

        L_px = z.length * PX_PER_FT
        H_px = z.height * PX_PER_FT
        dx   = _ddx(z.width)
        dy   = _ddy(z.width)

        fill_col = QColor(border.red(), border.green(), border.blue(), 40)
        painter.setBrush(QBrush(fill_col))
        painter.setPen(QPen(sel_col if is_sel else border.darker(110), pen_w))

        # Front face (tall, narrow)
        front = QPolygonF([QPointF(0, 0), QPointF(L_px, 0),
                           QPointF(L_px, H_px), QPointF(0, H_px)])
        painter.drawPolygon(front)

        # Top face (shallow depth)
        top = QPolygonF([QPointF(0, 0), QPointF(L_px, 0),
                         QPointF(L_px + dx, dy), QPointF(dx, dy)])
        painter.drawPolygon(top)

        # Right face
        right = QPolygonF([QPointF(L_px, 0), QPointF(L_px + dx, dy),
                           QPointF(L_px + dx, H_px + dy), QPointF(L_px, H_px)])
        painter.drawPolygon(right)

        # Horizontal stripes on front face to suggest louver vents
        stripe_pen = QPen(QColor(border.red(), border.green(), border.blue(), 90), 0.8)
        painter.setPen(stripe_pen)
        n_stripes = max(3, int(z.height / 2))
        for i in range(1, n_stripes):
            y = i / n_stripes * H_px
            painter.drawLine(QPointF(2, y), QPointF(L_px - 2, y))

        # Label
        painter.setPen(QPen(border.darker(150)))
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        painter.drawText(QRectF(5, 5, L_px - 10, 16), Qt.AlignLeft | Qt.AlignVCenter, z.label)
        painter.setFont(QFont("Arial", 7))
        painter.setPen(QPen(border.darker(130)))
        painter.drawText(QRectF(5, 20, L_px - 10, 14), Qt.AlignLeft,
                         f"{z.length:.0f}′×{z.width:.0f}′×{z.height:.0f}′  {z.nozzle_count}× {z.nozzle_type}")
        if z.warnings():
            painter.setPen(QPen(QColor("#e74c3c"), 1))
            painter.setFont(QFont("Arial", 7, QFont.Bold))
            painter.drawText(QRectF(5, 34, L_px - 10, 14), Qt.AlignLeft, "⚠ " + z.warnings()[0])

    def contextMenuEvent(self, event):
        menu = QMenu()
        edit_act = menu.addAction("Edit Zone…")
        del_act  = menu.addAction("Delete Zone")
        chosen   = menu.exec_(event.screenPos())
        # Deferred via QTimer — deleting `self` synchronously while still inside
        # its own contextMenuEvent (which Qt is mid-dispatch on) can crash.
        if chosen == edit_act:
            QTimer.singleShot(0, lambda: self._scene_ref._edit_zone(self))
        elif chosen == del_act:
            QTimer.singleShot(0, lambda: self._scene_ref._delete_zone(self))


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

        edge_col = QColor("#6a7a8a")
        dash_pen = QPen(QColor("#9aaaba"), 1, Qt.DashLine)
        edge_pen = QPen(edge_col, 1.8)

        # All face fills are very light — let the edges do the work
        ceil_fill  = QColor(180, 200, 220, 50)
        side_fill  = QColor(160, 180, 200, 40)

        # Hidden back edges (dashed)
        painter.setPen(dash_pen); painter.setBrush(Qt.NoBrush)
        painter.drawLine(btl, bbl)
        painter.drawLine(btl, btr)
        painter.drawLine(bbl, bbr)
        painter.drawLine(btr, bbr)   # far-right vertical edge

        # Ceiling — very light fill
        painter.setBrush(QBrush(ceil_fill))
        painter.setPen(edge_pen)
        painter.drawPolygon(QPolygonF([ftl, ftr, btr, btl]))

        # Right side — slightly darker light fill
        painter.setBrush(QBrush(side_fill))
        painter.drawPolygon(QPolygonF([ftr, fbr, bbr, btr]))

        # Front face — no fill, just a bold outline so zones show through
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(edge_col, 2.5))
        painter.drawPolygon(QPolygonF([ftl, ftr, fbr, fbl]))

        # Floor front edge
        painter.setPen(QPen(edge_col.darker(120), 1.5))
        painter.drawLine(fbl, fbr)

        # Dimension labels
        painter.setPen(QPen(QColor("#444"), 1))
        painter.setFont(QFont("Arial", 8))
        painter.drawText(QRectF(w_px/2 - 40, h_px + 5, 80, 16),
                         Qt.AlignCenter, f"{L:.0f}′ long")
        painter.save()
        painter.translate(-26, h_px / 2)
        painter.rotate(-90)
        painter.drawText(QRectF(-30, -8, 60, 16), Qt.AlignCenter, f"{H:.0f}′ tall")
        painter.restore()
        painter.drawText(QRectF(w_px + dx/2 - 25, dy/2 - 8, 70, 16),
                         Qt.AlignLeft, f"{W:.0f}′ deep")


class NozzleItem(QGraphicsItem):
    """Standalone draggable nozzle with optional coverage indicator."""
    ITEM_TYPE = "nozzle"
    R = 8   # symbol radius px
    COV_RX = 88   # coverage ellipse half-width px  (≈ 6.7 ft radius at 22px/ft × 0.6)
    COV_RY = 40   # coverage ellipse half-height (isometric compression)

    def __init__(self, nozzle_type=NOZZLE_TF, scene_ref=None, coverage_visible=True):
        super().__init__()
        self.nozzle_type     = nozzle_type
        self._scene_ref      = scene_ref
        self.coverage_visible = coverage_visible
        self.zone_uid        = None   # set when auto-spawned; None = manually placed
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._hover = False

    def boundingRect(self):
        R = self.R + 4
        if self.coverage_visible and self.nozzle_type != NOZZLE_DP:
            return QRectF(-self.COV_RX - 2, -self.COV_RY - 2,
                          (self.COV_RX + 2) * 2, (self.COV_RY + 2) * 2)
        return QRectF(-R, -R, R * 2, R * 2)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        n_col = QColor(NOZZLE_COLOR_HEX[self.nozzle_type])
        R = self.R

        # Coverage zone (behind nozzle symbol)
        if self.coverage_visible and self.nozzle_type != NOZZLE_DP:
            cov_fill = QColor(n_col.red(), n_col.green(), n_col.blue(), 22)
            cov_edge = QColor(n_col.red(), n_col.green(), n_col.blue(), 90)
            painter.setBrush(QBrush(cov_fill))
            painter.setPen(QPen(cov_edge, 1, Qt.DashLine))
            painter.drawEllipse(QPointF(0, 0), self.COV_RX, self.COV_RY)

        # Stem drop-line
        painter.setPen(QPen(n_col.darker(130), 1.5))
        painter.drawLine(QPointF(0, -R - 8), QPointF(0, -R))

        # Nozzle circle
        if self.isSelected():
            painter.setBrush(QBrush(QColor(_PALETTE_ORANGE)))
        else:
            painter.setBrush(QBrush(n_col))
        painter.setPen(QPen(Qt.white, 1.2))
        painter.drawEllipse(QPointF(0, 0), R, R)

        painter.setFont(QFont("Arial", 5, QFont.Bold))
        painter.setPen(QPen(Qt.white))
        painter.drawText(QRectF(-R, -R, R * 2, R * 2), Qt.AlignCenter,
                         self.nozzle_type[:2])

        if self._hover or self.isSelected():
            painter.setPen(QPen(QColor(_PALETTE_ORANGE), 1.5, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), R + 4, R + 4)

    def hoverEnterEvent(self, event): self._hover = True;  self.update()
    def hoverLeaveEvent(self, event): self._hover = False; self.update()

    def contextMenuEvent(self, event):
        menu = QMenu()
        cov_lbl = "Hide Coverage Circle" if self.coverage_visible else "Show Coverage Circle"
        cov_act = menu.addAction(cov_lbl)
        t_menu  = menu.addMenu("Change Type")
        tf_act  = t_menu.addAction(f"TF – Work Area")
        dp_act  = t_menu.addAction(f"DP – Duct / Plenum")
        wy_act  = t_menu.addAction(f"3-Way – Pit / Tunnel")
        menu.addSeparator()
        del_act = menu.addAction("Delete Nozzle")
        chosen  = menu.exec_(event.screenPos())
        if   chosen == cov_act:
            self.coverage_visible = not self.coverage_visible
            self.prepareGeometryChange(); self.update()
        elif chosen == tf_act:  self.nozzle_type = NOZZLE_TF;  self.update()
        elif chosen == dp_act:  self.nozzle_type = NOZZLE_DP;  self.update()
        elif chosen == wy_act:  self.nozzle_type = NOZZLE_3WY; self.update()
        elif chosen == del_act and self._scene_ref:
            # Defer the actual scene removal — deleting `self` synchronously while
            # still inside its own contextMenuEvent can crash Qt's event dispatch.
            QTimer.singleShot(0, lambda: self._scene_ref.remove_nozzle(self))


class LinkItem(QGraphicsItem):
    """Draggable fusible link / detector symbol."""
    ITEM_TYPE = "link"

    def __init__(self, link_type=None, scene_ref=None):
        super().__init__()
        self.link_type  = link_type or DETECTOR_TYPES[1]   # default 212°F
        self._scene_ref = scene_ref
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._hover = False

    def boundingRect(self):
        return QRectF(-14, -14, 110, 32)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        col  = QColor("#e74c3c")
        sel  = self.isSelected() or self._hover
        body = QColor(_PALETTE_ORANGE) if self.isSelected() else col
        poly = QPolygonF([QPointF(0, -12), QPointF(12, 10), QPointF(-12, 10)])
        painter.setBrush(QBrush(body))
        painter.setPen(QPen(col.darker(130), 1.5))
        painter.drawPolygon(poly)
        painter.setPen(QPen(Qt.white))
        painter.setFont(QFont("Arial", 6, QFont.Bold))
        painter.drawText(QRectF(-12, -3, 24, 12), Qt.AlignCenter, "LNK")
        # Short type label beside symbol
        short = ""
        for part in self.link_type.split("–"):
            if "°" in part or "Link" in part or "Bulb" in part or "Fire" in part:
                short = part.strip()[:18]; break
        painter.setPen(QPen(QColor("#333")))
        painter.setFont(QFont("Arial", 7))
        painter.drawText(QRectF(16, -8, 90, 16), Qt.AlignLeft | Qt.AlignVCenter, short)
        if sel:
            painter.setPen(QPen(QColor(_PALETTE_ORANGE), 1.5, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(poly)

    def hoverEnterEvent(self, event): self._hover = True;  self.update()
    def hoverLeaveEvent(self, event): self._hover = False; self.update()

    def contextMenuEvent(self, event):
        menu     = QMenu()
        t_menu   = menu.addMenu("Change Link / Detector Type")
        acts     = [t_menu.addAction(d) for d in DETECTOR_TYPES]
        menu.addSeparator()
        del_act  = menu.addAction("Delete Link")
        chosen   = menu.exec_(event.screenPos())
        if chosen == del_act and self._scene_ref:
            QTimer.singleShot(0, lambda: self._scene_ref.remove_link(self))
        else:
            for act, det in zip(acts, DETECTOR_TYPES):
                if chosen == act:
                    self.link_type = det; self.update(); break


class CylinderItem(QGraphicsItem):
    """Draggable cylinder / bottle symbol."""
    ITEM_TYPE = "cylinder"

    def __init__(self, label="IND-45", scene_ref=None):
        super().__init__()
        self.label      = label
        self._scene_ref = scene_ref
        self.color      = QColor("#8e44ad")
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._hover = False

    def boundingRect(self):
        return QRectF(0, 0, 48, 100)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        col = QColor(_PALETTE_ORANGE) if self.isSelected() else self.color
        # Body
        painter.setBrush(QBrush(col))
        painter.setPen(QPen(col.darker(140), 2))
        painter.drawRoundedRect(QRectF(8, 14, 32, 74), 7, 7)
        # Top ellipse cap
        painter.drawEllipse(QRectF(8, 6, 32, 18))
        # Valve nub
        painter.setBrush(QBrush(col.darker(120)))
        painter.drawRoundedRect(QRectF(18, 2, 12, 10), 3, 3)
        # Label text
        painter.setPen(QPen(Qt.white))
        painter.setFont(QFont("Arial", 7, QFont.Bold))
        painter.drawText(QRectF(4, 34, 40, 40), Qt.AlignCenter, self.label)
        if self._hover or self.isSelected():
            painter.setPen(QPen(QColor(_PALETTE_ORANGE), 1.5, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-2, -2, 2, 2))

    def hoverEnterEvent(self, event): self._hover = True;  self.update()
    def hoverLeaveEvent(self, event): self._hover = False; self.update()

    def contextMenuEvent(self, event):
        menu    = QMenu()
        m_menu  = menu.addMenu("Change Model")
        acts    = [m_menu.addAction(f"{c['model']} ({c['lbs']} lb)") for c in CYLINDERS]
        menu.addSeparator()
        del_act = menu.addAction("Delete Cylinder")
        chosen  = menu.exec_(event.screenPos())
        if chosen == del_act and self._scene_ref:
            QTimer.singleShot(0, lambda: self._scene_ref.remove_cylinder(self))
        else:
            for act, c in zip(acts, CYLINDERS):
                if chosen == act:
                    self.label = c["model"]; self.update(); break


# ═══════════════════════════════════════════════════════════════════════════════
#  Scene
# ═══════════════════════════════════════════════════════════════════════════════

class BoothScene(QGraphicsScene):
    zones_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zone_items: list[ZoneItem]     = []
        self._nozzle_items: list[NozzleItem] = []
        self._link_items: list[LinkItem]     = []
        self._cyl_items: list[CylinderItem]  = []
        self._booth_shell: BoothShellItem    = None
        self._booth_L = 0.0
        self._booth_W = 0.0
        self._booth_H = 9.0
        self._coverage_visible = True

    # ── Booth shell ──────────────────────────────────────────────────────────

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

    # ── Zones ────────────────────────────────────────────────────────────────

    def add_zone(self, zone_data: ZoneData, spawn_nozzles=True):
        item = ZoneItem(zone_data, self)
        self.addItem(item)
        self._zone_items.append(item)
        if spawn_nozzles:
            self._spawn_zone_nozzles(zone_data)
        self.zones_changed.emit()
        return item

    def remove_zone(self, item: ZoneItem):
        self._zone_items = [z for z in self._zone_items if z is not item]
        # Clean up nozzles auto-spawned for this zone — otherwise they're left
        # orphaned in the scene, referencing a zone uid that no longer exists.
        for n in [n for n in self._nozzle_items if n.zone_uid == item.zone.uid]:
            self.removeItem(n)
        self._nozzle_items = [n for n in self._nozzle_items if n.zone_uid != item.zone.uid]
        self.removeItem(item)
        self.zones_changed.emit()

    def all_zones(self) -> list[ZoneData]:
        return [it.zone for it in self._zone_items]

    def _spawn_zone_nozzles(self, z: ZoneData):
        """Auto-place NozzleItems at the calculated grid positions for a zone."""
        nc = z.nozzle_count
        if nc <= 0:
            return
        w_px = z.length * PX_PER_FT
        h_px = z.height * PX_PER_FT
        dx   = _ddx(z.width)
        dy   = _ddy(z.width)   # negative
        sx   = z.x * PX_PER_FT
        sy   = z.y * PX_PER_FT
        hang = 10   # px below ceiling

        if z.zone_type in (ZONE_WORK, ZONE_PLEN):
            if z.zone_type == ZONE_WORK:
                minfo = z.module_info
                nL = minfo[1] if minfo else 1
                nW = minfo[2] if minfo else 1
            else:
                rows, cols = _nozzle_grid(nc)
                nL, nW = cols, rows
            placed = 0
            for row in range(nW):
                for col in range(nL):
                    if placed >= nc:
                        break
                    # Place nozzle at centre of each module on the ceiling plane
                    col_frac = (col + 0.5) / nL
                    row_frac = (row + 0.5) / nW
                    cx = sx + col_frac * w_px + row_frac * dx
                    cy = sy + row_frac * dy    + hang
                    n = self.add_nozzle(z.nozzle_type, cx, cy)
                    n.zone_uid = z.uid
                    placed += 1
        elif z.zone_type == ZONE_DUCT:
            for i in range(nc):
                nx = sx + w_px * (i + 1) / (nc + 1)
                ny = sy + h_px / 2
                n = self.add_nozzle(z.nozzle_type, nx, ny)
                n.zone_uid = z.uid
        elif z.zone_type == ZONE_PIT:
            for i in range(nc):
                f  = (i + 0.5) / nc
                nx = sx + f * w_px + _ddx(z.width) * 0.5
                ny = sy + _ddy(z.width) * 0.5
                n  = self.add_nozzle(z.nozzle_type, nx, ny)
                n.zone_uid = z.uid
        elif z.zone_type in PLEN_MODULE:
            # Grid layout based on DIOM module limits
            mL, mW, _ = PLEN_MODULE[z.zone_type]
            nL = max(1, math.ceil(z.length / mL))
            nW = max(1, math.ceil(z.width  / mW))
            for r in range(nW):
                for c in range(nL):
                    fx = (c + 0.5) / nL
                    fy = (r + 0.5) / nW
                    nx = sx + fx * w_px + _ddx(z.width * fy)
                    ny = sy + fy * _ddy(z.width)
                    n  = self.add_nozzle(z.nozzle_type, nx, ny)
                    n.zone_uid = z.uid
        elif z.zone_type == ZONE_PIT_T:
            # 3-Way nozzles go on whichever branch (main legs or tunnel) needs
            # the most modules — placed along that branch's own direction so
            # a nozzle driven by tunnel width actually sits in the tunnel.
            tw = getattr(z, "tunnel_width", z.width)
            n_main_len = max(1, math.ceil(z.length / (MAX_PIT_LEG_FT * 2)))
            n_main_wid = max(1, math.ceil(z.width  / MAX_PIT_CROSS_FT))
            n_tun_len  = max(1, math.ceil(z.tunnel_length / MAX_PIT_TUNNEL_FT))
            n_tun_wid  = max(1, math.ceil(tw / MAX_PIT_CROSS_FT))

            if n_tun_len * n_tun_wid >= n_main_len * n_main_wid:
                # Place along the tunnel branch (junction of main shaft, extending
                # in the tunnel's own depth direction — same diagonal it's drawn on)
                cx0 = sx + w_px / 2 + _ddx(z.width)
                cy0 = sy + _ddy(z.width)
                t_L = z.tunnel_length
                for r in range(n_tun_wid):
                    for c in range(n_tun_len):
                        fx = (c + 0.5) / n_tun_len
                        fy = (r + 0.5) / n_tun_wid
                        nx = cx0 + _ddx(t_L * fx) + (fy - 0.5) * tw * PX_PER_FT
                        ny = cy0 + _ddy(t_L * fx)
                        n  = self.add_nozzle(z.nozzle_type, nx, ny)
                        n.zone_uid = z.uid
            else:
                for r in range(n_main_wid):
                    for c in range(n_main_len):
                        fx = (c + 0.5) / n_main_len
                        fy = (r + 0.5) / n_main_wid
                        nx = sx + fx * w_px + _ddx(z.width * fy)
                        ny = sy + fy * _ddy(z.width)
                        n  = self.add_nozzle(z.nozzle_type, nx, ny)
                        n.zone_uid = z.uid
        elif z.zone_type == ZONE_PIT_VT:
            # 3-Way nozzles placed at junction points
            for i in range(nc):
                f  = (i + 0.5) / nc
                nx = sx + f * w_px + _ddx(z.width)
                ny = sy + _ddy(z.width)
                n  = self.add_nozzle(z.nozzle_type, nx, ny)
                n.zone_uid = z.uid

    # ── Nozzles ──────────────────────────────────────────────────────────────

    def add_nozzle(self, nozzle_type=NOZZLE_TF, sx=0.0, sy=0.0):
        item = NozzleItem(nozzle_type, self, self._coverage_visible)
        item.setPos(sx, sy)
        self.addItem(item)
        self._nozzle_items.append(item)
        return item

    def remove_nozzle(self, item: NozzleItem):
        self._nozzle_items = [n for n in self._nozzle_items if n is not item]
        self.removeItem(item)

    def clear_nozzles(self):
        for n in list(self._nozzle_items):
            self.removeItem(n)
        self._nozzle_items.clear()

    def all_nozzles(self):
        return list(self._nozzle_items)

    def set_coverage_visible(self, visible: bool):
        self._coverage_visible = visible
        for n in self._nozzle_items:
            n.coverage_visible = visible
            n.prepareGeometryChange()
            n.update()

    # ── Links / detectors ────────────────────────────────────────────────────

    def add_link(self, link_type=None, sx=0.0, sy=0.0):
        item = LinkItem(link_type, self)
        item.setPos(sx, sy)
        self.addItem(item)
        self._link_items.append(item)
        return item

    def remove_link(self, item: LinkItem):
        self._link_items = [l for l in self._link_items if l is not item]
        self.removeItem(item)

    def clear_links(self):
        for l in list(self._link_items):
            self.removeItem(l)
        self._link_items.clear()

    def all_links(self):
        return list(self._link_items)

    # ── Cylinders ────────────────────────────────────────────────────────────

    def add_cylinder(self, label="IND-45", sx=0.0, sy=0.0):
        item = CylinderItem(label, self)
        item.setPos(sx, sy)
        self.addItem(item)
        self._cyl_items.append(item)
        return item

    def remove_cylinder(self, item: CylinderItem):
        self._cyl_items = [c for c in self._cyl_items if c is not item]
        self.removeItem(item)

    def clear_cylinders(self):
        for c in list(self._cyl_items):
            self.removeItem(c)
        self._cyl_items.clear()

    def all_cylinders(self):
        return list(self._cyl_items)

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_zone_moved(self):
        self.zones_changed.emit()

    def _edit_zone(self, item: ZoneItem):
        dlg = ZoneDialog(item.zone, self.views()[0] if self.views() else None)
        if dlg.exec_() == QDialog.Accepted:
            dlg.apply_to(item.zone)
            item.prepareGeometryChange()
            item.update()
            # Remove auto-spawned nozzles for this zone then respawn
            for n in [n for n in self._nozzle_items if n.zone_uid == item.zone.uid]:
                self.removeItem(n)
            self._nozzle_items = [n for n in self._nozzle_items if n.zone_uid != item.zone.uid]
            self._spawn_zone_nozzles(item.zone)
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
        self.type_combo.addItems([
            ZONE_WORK, ZONE_DUCT,
            ZONE_CF_BOX, ZONE_CF_DT, ZONE_RAISED, ZONE_SD_EXH,
            ZONE_PIT, ZONE_PIT_T, ZONE_PIT_VT,
        ])
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
        tl_default = z.tunnel_length if (z and hasattr(z, "tunnel_length")) else 18.0
        self.sp_T = _spin(tl_default, mn=1.0, mx=200.0)
        tw_default = z.tunnel_width if (z and hasattr(z, "tunnel_width")) else (z.width if z else 4.0)
        self.sp_TW = _spin(tw_default, mn=1.0, mx=200.0)
        layout.addRow("Length (L):", self.sp_L)
        self.sp_W_row = layout.addRow("Width (W):",  self.sp_W)
        self.sp_H_row = layout.addRow("Height (H):", self.sp_H)
        self._sp_T_label = QLabel("Tunnel Length:")
        self._sp_T_row   = layout.addRow(self._sp_T_label, self.sp_T)
        self._sp_TW_label = QLabel("Tunnel Width:")
        self._sp_TW_row   = layout.addRow(self._sp_TW_label, self.sp_TW)

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
        nozzle_default = {
            ZONE_WORK:   NOZZLE_TF,
            ZONE_DUCT:   NOZZLE_DP,
            ZONE_CF_BOX: NOZZLE_DP,
            ZONE_CF_DT:  NOZZLE_DP,
            ZONE_RAISED: NOZZLE_DP,
            ZONE_SD_EXH: NOZZLE_DP,
            ZONE_PIT:    NOZZLE_DP,
            ZONE_PIT_T:  NOZZLE_3WY,
            ZONE_PIT_VT: NOZZLE_3WY,
            ZONE_PLEN:   NOZZLE_DP,
        }
        self.nozzle_combo.setCurrentText(nozzle_default.get(zone_type, NOZZLE_DP))

        # Preset sensible defaults for pit cross-section
        is_pit = zone_type in (ZONE_PIT, ZONE_PIT_T, ZONE_PIT_VT)
        if is_pit:
            if self.sp_W.value() > 8.0:
                self.sp_W.setValue(4.0)
            if self.sp_H.value() > 8.0:
                self.sp_H.setValue(4.0)

        # Show/hide tunnel/vert-stack length row
        show_tunnel = zone_type in (ZONE_PIT_T, ZONE_PIT_VT)
        if zone_type == ZONE_PIT_VT:
            self._sp_T_label.setText("Vert. Stack Ht:")
        else:
            self._sp_T_label.setText("Tunnel Length:")
        self.sp_T.setVisible(show_tunnel)
        self._sp_T_label.setVisible(show_tunnel)

        # Tunnel width only applies to the horizontal tunnel (Pit with Tunnel)
        show_tunnel_w = zone_type == ZONE_PIT_T
        self.sp_TW.setVisible(show_tunnel_w)
        self._sp_TW_label.setVisible(show_tunnel_w)

        tips = {
            ZONE_WORK:   "Max 1,260 ft³ per TF nozzle · Max height 24 ft (Table 4-2)",
            ZONE_DUCT:   "Max 28 ft per DP nozzle · Max round duct Ø 48\"",
            ZONE_CF_BOX: "Cross Flow Box · Module per D/P nozzle: 16 ft L × 4 ft W × 18 ft H",
            ZONE_CF_DT:  "Cross Flow Drive-Thru (U-shape) · Module: 15 ft L × 4 ft W × 12 ft H",
            ZONE_RAISED: "Raised Floor · Module per D/P nozzle: 30 ft L × 15 ft W × 1 ft H",
            ZONE_SD_EXH: "Side Exhaust · Module per D/P nozzle: 40 ft L × 4 ft W × 4 ft H",
            ZONE_PIT:    "Straight downdraft pit · Max 40 ft per DP nozzle · Typical cross-section 4×4 ft",
            ZONE_PIT_T:  "Pit with Tunnel · Main legs max 18 ft each · Tunnel max 18 ft per 3-Way nozzle",
            ZONE_PIT_VT: "Pit w/ Vert. Transition · Main legs max 18 ft · Vert. stack max 14 ft per 3-Way nozzle",
            ZONE_PLEN:   "Legacy generic plenum — use a Figure 4-14 type for new designs",
        }
        self._info.setText(tips.get(zone_type, ""))

    def apply_to(self, z: ZoneData):
        z.label         = self.lbl_edit.text().strip() or z.label
        z.zone_type     = self.type_combo.currentText()
        z.length        = self.sp_L.value()
        z.width         = self.sp_W.value()
        z.height        = self.sp_H.value()
        z.tunnel_length = self.sp_T.value()
        z.tunnel_width  = self.sp_TW.value()
        z.nozzle_type   = self.nozzle_combo.currentText()
        ov = self.sp_override.value()
        z.nozzle_override = ov if ov > 0 else None

    def get_zone(self):
        z = ZoneData(
            zone_type     = self.type_combo.currentText(),
            length        = self.sp_L.value(),
            width         = self.sp_W.value(),
            height        = self.sp_H.value(),
            tunnel_length = self.sp_T.value(),
            tunnel_width  = self.sp_TW.value(),
            nozzle_type   = self.nozzle_combo.currentText(),
            label         = self.lbl_edit.text().strip(),
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
        cap = self._MAX_NOZZLES.get(cylinder_model, 4)
        self.summary_lbl.setText(
            f"<b>Cylinders:</b> {cyl_summary or '—'} ({cap} nozzles/cylinder max)<br>"
            f"<b>Nozzles:</b> {noz_summary or '—'}<br>"
            f"<b>Total Nozzles:</b> {total_nozzles}"
        )

    # Max nozzles per cylinder per DIOM §4-5.2 (Tables 4-6 through 4-20).
    # IND-21 = DC-21 (21 lb), IND-45 = DC-45 (45 lb), IND-70 = DC-70 (70 lb).
    _MAX_NOZZLES = {"IND-21": 2, "IND-45": 4, "IND-70": 6}

    def _recommend_cylinders(self, zones, preferred_model):
        """
        Cylinder count = ceil(total_nozzles / max_nozzles_per_cylinder).
        Limits per DIOM: IND-21 → 2 nozzles, IND-45 → 4, IND-70 → 6.
        """
        if not zones:
            return {}
        total_nozzles = sum(z.nozzle_count for z in zones)
        if total_nozzles == 0:
            return {}
        cap = self._MAX_NOZZLES.get(preferred_model, 4)
        num = max(1, math.ceil(total_nozzles / cap))
        return {preferred_model: num}

    def _det_part(self, det_type):
        for d in DETECTOR_TYPES:
            if det_type in d or d in det_type:
                pn_idx = det_type.find("P/N ")
                if pn_idx >= 0:
                    return det_type[pn_idx + 4:].strip()
        return "—"


# ═══════════════════════════════════════════════════════════════════════════════
#  Project info dialog
# ═══════════════════════════════════════════════════════════════════════════════

class PaintBoothProjectInfoDialog(QDialog):
    def __init__(self, meta=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Project Information")
        self.setMinimumWidth(420)
        m = meta or {}
        layout = QVBoxLayout(self); layout.setSpacing(8)

        def _row(label, widget):
            row = QHBoxLayout()
            lbl = QLabel(label); lbl.setFixedWidth(110)
            lbl.setStyleSheet("font-weight:bold;font-size:11px;")
            row.addWidget(lbl); row.addWidget(widget); layout.addLayout(row)

        self._customer = QLineEdit(m.get("customer", ""))
        self._customer.setPlaceholderText("e.g. ABC Auto Body – Main St")
        _row("Customer:", self._customer)

        self._location = QLineEdit(m.get("location", ""))
        self._location.setPlaceholderText("e.g. 123 Main St, Anytown AB")
        _row("Location:", self._location)

        self._job = QLineEdit(m.get("job_number", ""))
        self._job.setPlaceholderText("e.g. DFP-2026-001")
        _row("Job Number:", self._job)

        self._designer = QLineEdit(m.get("designer", ""))
        self._designer.setPlaceholderText("Your name")
        _row("Designer:", self._designer)

        rev_widget = QWidget()
        rev_row = QHBoxLayout(rev_widget); rev_row.setContentsMargins(0,0,0,0); rev_row.setSpacing(6)
        self._revision = QLineEdit(m.get("revision", "A"))
        self._revision.setFixedWidth(50); self._revision.setPlaceholderText("A")
        rev_date_lbl = QLabel("Date:"); rev_date_lbl.setStyleSheet("font-size:11px;")
        self._rev_date = QLineEdit(m.get("rev_date", datetime.date.today().strftime("%Y-%m-%d")))
        self._rev_date.setPlaceholderText("YYYY-MM-DD")
        rev_row.addWidget(self._revision); rev_row.addWidget(rev_date_lbl)
        rev_row.addWidget(self._rev_date); rev_row.addStretch()
        _row("Revision:", rev_widget)

        self._notes = QTextEdit(m.get("notes", ""))
        self._notes.setPlaceholderText("Any additional notes…")
        self._notes.setFixedHeight(72)
        layout.addWidget(QLabel("Notes:")); layout.addWidget(self._notes)

        btns = QHBoxLayout()
        ok = QPushButton("OK"); ok.setDefault(True)
        ok.setStyleSheet(f"background:{_PALETTE_DARK};color:white;font-weight:bold;"
                         "padding:6px 20px;border-radius:3px;")
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet("padding:6px 20px;border-radius:3px;")
        ok.clicked.connect(self.accept); cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(cancel); btns.addWidget(ok)
        layout.addLayout(btns)

    def values(self):
        return {
            "customer":   self._customer.text().strip(),
            "location":   self._location.text().strip(),
            "job_number": self._job.text().strip(),
            "designer":   self._designer.text().strip(),
            "revision":   self._revision.text().strip() or "A",
            "rev_date":   self._rev_date.text().strip(),
            "notes":      self._notes.toPlainText().strip(),
        }


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
        self._project_meta = {}

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
            ("💾 Save",         self._save),
            ("📂 Open",         self._open),
            ("📋 Project Info", self._edit_project_info),
            ("📄 Export PDF",   self._export_pdf),
        ]:
            a = QAction(label, self); a.triggered.connect(slot); tb.addAction(a)
        tb.addSeparator()
        for label, slot in [
            ("＋ Work Area",       lambda: self._add_zone(ZONE_WORK)),
            ("＋ Exhaust Duct",    lambda: self._add_zone(ZONE_DUCT)),
            ("＋ CF Box",          lambda: self._add_zone(ZONE_CF_BOX)),
            ("＋ CF Drive-Thru",   lambda: self._add_zone(ZONE_CF_DT)),
            ("＋ Raised Floor",    lambda: self._add_zone(ZONE_RAISED)),
            ("＋ Side Exhaust",    lambda: self._add_zone(ZONE_SD_EXH)),
            ("＋ Straight Pit",    lambda: self._add_zone(ZONE_PIT)),
            ("＋ Pit w/ Tunnel",   lambda: self._add_zone(ZONE_PIT_T)),
            ("＋ Pit w/ Vert.",    lambda: self._add_zone(ZONE_PIT_VT)),
        ]:
            a = QAction(label, self); a.triggered.connect(slot); tb.addAction(a)
        tb.addSeparator()
        for label, slot in [
            ("＋ TF Nozzle",   lambda: self._add_nozzle(NOZZLE_TF)),
            ("＋ DP Nozzle",   lambda: self._add_nozzle(NOZZLE_DP)),
            ("＋ 3-Way Nozzle",lambda: self._add_nozzle(NOZZLE_3WY)),
            ("＋ Link/Detector",self._add_link),
            ("＋ Cylinder",    self._add_cylinder),
        ]:
            a = QAction(label, self); a.triggered.connect(slot); tb.addAction(a)
        tb.addSeparator()
        self._cov_action = QAction("Coverage: ON", self)
        self._cov_action.setCheckable(True)
        self._cov_action.setChecked(True)
        self._cov_action.triggered.connect(self._toggle_coverage)
        tb.addAction(self._cov_action)
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
        splitter.setSizes([260, 9999, 340])

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
            "• Max booth height: <b>24 ft</b> (Table 4-2)<br>"
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
        _zone_defaults = {
            ZONE_CF_BOX: (16.0, 4.0,  18.0),
            ZONE_CF_DT:  (15.0, 4.0,  12.0),
            ZONE_RAISED: (30.0, 15.0,  1.0),
            ZONE_SD_EXH: (40.0, 4.0,   4.0),
            ZONE_PIT:    (40.0, 4.0,   4.0),
            ZONE_PIT_T:  (36.0, 4.0,   4.0),
            ZONE_PIT_VT: (36.0, 4.0,   4.0),
        }
        if zone_type in _zone_defaults:
            default_L, default_W, default_H = _zone_defaults[zone_type]
        elif zone_type == ZONE_DUCT:
            default_L, default_W, default_H = 14.0, 3.0, 3.0
        else:
            default_L = 20.0
            default_W = self.sp_booth_W.value()
            default_H = self.sp_booth_H.value()
        z = ZoneData(
            zone_type = zone_type,
            length    = default_L,
            width     = default_W,
            height    = default_H,
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

    def _add_nozzle(self, nozzle_type):
        """Drop a nozzle at the centre of the current view."""
        centre = self._canvas.mapToScene(self._canvas.viewport().rect().center())
        self._scene.add_nozzle(nozzle_type, centre.x(), centre.y())

    def _add_link(self):
        centre = self._canvas.mapToScene(self._canvas.viewport().rect().center())
        self._scene.add_link(self.det_combo.currentText(), centre.x(), centre.y())

    def _add_cylinder(self):
        centre = self._canvas.mapToScene(self._canvas.viewport().rect().center())
        model  = self.cyl_combo.currentData() or "IND-45"
        self._scene.add_cylinder(model, centre.x(), centre.y())

    def _toggle_coverage(self, checked):
        self._scene.set_coverage_visible(checked)
        self._cov_action.setText("Coverage: ON" if checked else "Coverage: OFF")

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
            "project_meta": self._project_meta,
            "booth_L":      self.sp_booth_L.value(),
            "booth_W":      self.sp_booth_W.value(),
            "booth_H":      self.sp_booth_H.value(),
            "booth_type":   self.type_combo.currentText(),
            "cylinder":     self.cyl_combo.currentData(),
            "detector":     self.det_combo.currentText(),
            "pull_stations":self.sp_pull.value(),
            "elec_actuator":self.chk_elec.isChecked(),
            "coverage_on":  self._cov_action.isChecked(),
            "zones":        [z.to_dict() for z in self._scene.all_zones()],
            "nozzles":      [{"type": n.nozzle_type, "x": n.pos().x(), "y": n.pos().y(),
                               "cov": n.coverage_visible}
                             for n in self._scene.all_nozzles()],
            "links":        [{"type": l.link_type, "x": l.pos().x(), "y": l.pos().y()}
                             for l in self._scene.all_links()],
            "cylinders":    [{"label": c.label, "x": c.pos().x(), "y": c.pos().y()}
                             for c in self._scene.all_cylinders()],
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
        self._project_meta = data.get("project_meta", {})
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

        # Clear canvas items
        for item in list(self._scene._zone_items):
            self._scene.remove_zone(item)
        self._scene.clear_nozzles()
        self._scene.clear_links()
        self._scene.clear_cylinders()
        ZoneData._id_counter = 0

        # Reload zones (no auto-spawn — nozzles loaded separately)
        for zd in data.get("zones", []):
            z = ZoneData.from_dict(zd)
            self._scene.add_zone(z, spawn_nozzles=False)

        # Reload nozzles
        for nd in data.get("nozzles", []):
            self._scene.add_nozzle(nd.get("type", NOZZLE_TF),
                                   nd.get("x", 0.0), nd.get("y", 0.0))
            self._scene.all_nozzles()[-1].coverage_visible = nd.get("cov", True)

        # Reload links
        for ld in data.get("links", []):
            self._scene.add_link(ld.get("type"), ld.get("x", 0.0), ld.get("y", 0.0))

        # Reload cylinders
        for cd in data.get("cylinders", []):
            self._scene.add_cylinder(cd.get("label", "IND-45"),
                                     cd.get("x", 0.0), cd.get("y", 0.0))

        # Restore coverage toggle
        cov = data.get("coverage_on", True)
        self._cov_action.setChecked(cov)
        self._scene.set_coverage_visible(cov)
        self._cov_action.setText("Coverage: ON" if cov else "Coverage: OFF")

        self._apply_booth_dims()
        self._refresh_bom()

    # ── Project Info ─────────────────────────────────────────────────────────

    def _edit_project_info(self):
        dlg = PaintBoothProjectInfoDialog(self._project_meta, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._project_meta = dlg.values()

    # ── PDF Export ──────────────────────────────────────────────────────────

    def _export_pdf(self):
        try:
            default = os.path.join(
                _submittals_dir(),
                f"PaintBooth_{self._project_name or 'Design'}_{datetime.date.today()}.pdf"
            )
        except Exception:
            default = ""
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", default, "PDF (*.pdf)")
        if not path:
            return
        try:
            ok, result = self._build_submittal_pdf(path)
            if ok:
                QMessageBox.information(self, "Exported", f"PDF saved to:\n{path}")
                try:
                    os.startfile(path)
                except Exception:
                    pass
            else:
                QMessageBox.critical(self, "Export Error", result)
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _build_submittal_pdf(self, path):
        if not _FITZ_OK:
            return False, ("PyMuPDF (fitz) is not installed.\n"
                           "Run: pip install pymupdf")

        import tempfile, datetime as _dt
        from PyQt5.QtCore import QRectF as _QRectF, Qt as _Qt

        meta     = self._project_meta or {}
        customer = meta.get("customer", "") or self._project_name or "—"
        location = meta.get("location", "") or "—"
        job_no   = meta.get("job_number", "") or "—"
        designer = meta.get("designer", "") or "—"
        rev      = meta.get("revision", "A") or "A"
        rev_d    = meta.get("rev_date", "") or ""
        notes    = (meta.get("notes", "") or "").strip()

        zones    = self._scene.all_zones()
        cyl_text = self.cyl_combo.currentText()
        det_text = self.det_combo.currentText()
        booth_L  = self.sp_booth_L.value()
        booth_W  = self.sp_booth_W.value()
        booth_H  = self.sp_booth_H.value()
        booth_tp = self.type_combo.currentText()

        # ── Palette ──
        red  = (0.75, 0.17, 0.11)   # DFP red
        dark = (0.14, 0.17, 0.15)   # near-black
        org  = (1.0,  0.44, 0.01)   # DFP orange

        W, H         = 792, 612                      # landscape letter
        HEADER_H     = 52;  FOOTER_H = 36
        BORDER       = 18;  SIDEBAR_W = 205
        DX1 = BORDER;       DY1 = HEADER_H + BORDER
        DX2 = W - SIDEBAR_W - BORDER
        DY2 = H - FOOTER_H - BORDER
        DRAW_W = DX2 - DX1; DRAW_H = DY2 - DY1
        SX = W - SIDEBAR_W + 6

        tmp_files = []

        try:
            doc = fitz.open()

            # ─────────────────────────────────────────────────────────────────
            # PAGE 1 — Design drawing
            # ─────────────────────────────────────────────────────────────────

            # Render isometric canvas to image
            scene_rect = self._scene.itemsBoundingRect()
            if scene_rect.isNull() or scene_rect.isEmpty():
                scene_rect = _QRectF(0, 0, 800, 600)
            scene_rect = scene_rect.adjusted(-60, -60, 60, 60)

            sw = scene_rect.width(); sh = scene_rect.height() if scene_rect.height() > 0 else 1
            scene_aspect = sw / sh
            draw_aspect  = DRAW_W / DRAW_H
            if scene_aspect >= draw_aspect:
                img_w = max(200, int(DRAW_W * 2))
                img_h = max(150, int(img_w / scene_aspect))
            else:
                img_h = max(150, int(DRAW_H * 2))
                img_w = max(200, int(img_h * scene_aspect))

            from PyQt5.QtGui import QImage
            img = QImage(img_w, img_h, QImage.Format_RGB32)
            img.fill(QColor("white"))
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            self._scene.render(p, _QRectF(0, 0, img_w, img_h), scene_rect, _Qt.IgnoreAspectRatio)
            p.end()
            tmp1 = path + "_tmp0.png"; img.save(tmp1); tmp_files.append(tmp1)

            pg = doc.new_page(width=W, height=H)
            self._pdf_header(pg, W, H, HEADER_H, BORDER, SIDEBAR_W,
                             customer, location, "Paint Booth Suppression System", red, dark)
            pg.draw_rect(fitz.Rect(DX1, DY1, DX2, DY2), color=dark, width=1.2)
            pg.insert_image(fitz.Rect(DX1, DY1, DX2, DY2), filename=tmp1)
            self._pdf_footer(pg, W, H, BORDER, FOOTER_H, SIDEBAR_W,
                             customer, location, 1, 2, rev, red, dark)
            self._pdf_rev_stamp(pg, W, HEADER_H, SIDEBAR_W, BORDER, rev, rev_d, red)

            # ── Sidebar page 1: booth specs + zones ──
            sy = DY1 + 4
            pg.insert_text((SX, sy + 10), "BOOTH SPECIFICATIONS",
                           fontsize=9, color=red, fontname="helv"); sy += 22
            pg.draw_line((SX, sy), (W - BORDER, sy), color=dark, width=0.5); sy += 8

            for label, value in [
                ("Type",      booth_tp),
                ("Length",    f"{booth_L:.1f} ft"),
                ("Width",     f"{booth_W:.1f} ft"),
                ("Height",    f"{booth_H:.1f} ft"),
                ("Cylinder",  cyl_text),
                ("Detection", det_text),
            ]:
                pg.insert_text((SX,      sy), label + ":",
                               fontsize=7, color=(0.3, 0.3, 0.3), fontname="helv")
                pg.insert_text((SX + 60, sy), value,
                               fontsize=7, color=dark, fontname="helv")
                sy += 11

            if zones:
                sy += 6
                pg.draw_line((SX, sy), (W - BORDER, sy), color=dark, width=0.5); sy += 8
                pg.insert_text((SX, sy), "ZONES",
                               fontsize=8, color=dark, fontname="helv"); sy += 12

                for z in zones:
                    if sy > H - FOOTER_H - 10:
                        break
                    label_str = z.label
                    pg.insert_text((SX, sy), label_str,
                                   fontsize=7, color=dark, fontname="helv")
                    pg.insert_text((SX, sy + 9), f"  {z.zone_type}  {z.length:.0f}×{z.width:.0f}×{z.height:.0f} ft",
                                   fontsize=6, color=(0.35, 0.35, 0.35), fontname="helv")
                    pg.insert_text((SX, sy + 17), f"  {z.nozzle_count} nozzle(s)",
                                   fontsize=6, color=(0.35, 0.35, 0.35), fontname="helv")
                    if z.zone_type == ZONE_WORK:
                        mi = z.module_info
                        if mi:
                            tot, nL, nW, mL, mW = mi
                            pg.insert_text((SX, sy + 25),
                                           f"  {nL}×{nW} modules ({mL:.1f}×{mW:.1f} ft)",
                                           fontsize=6, color=(0.25, 0.45, 0.65), fontname="helv")
                            sy += 9
                    sy += 29
                    if sy < H - FOOTER_H - 4:
                        pg.draw_line((SX + 2, sy - 3), (W - BORDER - 2, sy - 3),
                                     color=(0.8, 0.8, 0.8), width=0.3)

            # logo (above footer, bottom of sidebar)
            logo_path = self._get_logo_path()
            if logo_path:
                try:
                    logo_rect = fitz.Rect(SX, H - FOOTER_H - 88, W - BORDER, H - FOOTER_H - 4)
                    pg.insert_image(logo_rect, filename=logo_path, keep_proportion=True)
                except Exception:
                    pass

            # notes
            if notes and sy < H - FOOTER_H - 40:
                sy += 4
                pg.draw_line((SX, sy), (W - BORDER, sy), color=dark, width=0.5); sy += 8
                pg.insert_text((SX, sy), "NOTES", fontsize=8, color=dark, fontname="helv"); sy += 11
                for word_line in notes.split("\n"):
                    words = word_line.split(); line = ""
                    for w in words:
                        if len(line) + len(w) + 1 > 38:
                            if sy > H - FOOTER_H - 10:
                                break
                            pg.insert_text((SX, sy), line.strip(),
                                           fontsize=7, color=(0.2, 0.2, 0.2), fontname="helv")
                            sy += 10; line = ""
                        line += w + " "
                    if line.strip() and sy <= H - FOOTER_H - 10:
                        pg.insert_text((SX, sy), line.strip(),
                                       fontsize=7, color=(0.2, 0.2, 0.2), fontname="helv")
                        sy += 10

            # ─────────────────────────────────────────────────────────────────
            # PAGE 2 — Bill of Materials
            # ─────────────────────────────────────────────────────────────────
            pg2 = doc.new_page(width=W, height=H)
            self._pdf_header(pg2, W, H, HEADER_H, BORDER, SIDEBAR_W,
                             customer, location, "Bill of Materials", red, dark)
            self._pdf_footer(pg2, W, H, BORDER, FOOTER_H, SIDEBAR_W,
                             customer, location, 2, 2, rev, red, dark)
            self._pdf_rev_stamp(pg2, W, HEADER_H, SIDEBAR_W, BORDER, rev, rev_d, red)

            # BOM table body
            bom_x   = BORDER + 4
            bom_y   = DY1 + 8
            col_w_bom = [DRAW_W * 0.58, DRAW_W * 0.26, DRAW_W * 0.16]
            hdrs    = ["Description", "Part Number", "Qty"]
            row_h   = 14

            # Header row
            pg2.draw_rect(fitz.Rect(bom_x, bom_y, bom_x + DRAW_W, bom_y + row_h),
                          color=dark, fill=dark)
            cx = bom_x + 4
            for i, hdr in enumerate(hdrs):
                pg2.insert_text((cx, bom_y + 10), hdr,
                                fontsize=8, color=(1, 1, 1), fontname="helv")
                cx += col_w_bom[i]
            bom_y += row_h

            # Data rows
            for row in range(self._bom.tbl.rowCount()):
                name  = self._bom.tbl.item(row, 0).text() if self._bom.tbl.item(row, 0) else ""
                pn    = self._bom.tbl.item(row, 1).text() if self._bom.tbl.item(row, 1) else ""
                qty   = self._bom.tbl.item(row, 2).text() if self._bom.tbl.item(row, 2) else ""
                fill  = (0.97, 0.97, 0.97) if row % 2 == 0 else (1, 1, 1)
                pg2.draw_rect(fitz.Rect(bom_x, bom_y, bom_x + DRAW_W, bom_y + row_h),
                              color=(0.8, 0.8, 0.8), fill=fill, width=0.3)
                cx = bom_x + 4
                for i, txt in enumerate([name, pn, qty]):
                    pg2.insert_text((cx, bom_y + 10), txt,
                                    fontsize=8, color=dark, fontname="helv")
                    cx += col_w_bom[i]
                bom_y += row_h

            # Project info block on right sidebar of page 2
            sy2 = DY1 + 4
            pg2.insert_text((SX, sy2 + 10), "PROJECT INFORMATION",
                            fontsize=9, color=red, fontname="helv"); sy2 += 22
            pg2.draw_line((SX, sy2), (W - BORDER, sy2), color=dark, width=0.5); sy2 += 8
            for label, value in [
                ("Customer", customer),
                ("Location", location),
                ("Job No.",  job_no),
                ("Designer", designer),
                ("Revision", f"{rev}  {rev_d}"),
                ("Date",     _dt.date.today().strftime("%Y-%m-%d")),
            ]:
                pg2.insert_text((SX,      sy2), label + ":",
                                fontsize=7, color=(0.3, 0.3, 0.3), fontname="helv")
                pg2.insert_text((SX + 54, sy2), value,
                                fontsize=7, color=dark, fontname="helv")
                sy2 += 11

            # Compliance note
            sy2 += 14
            pg2.draw_line((SX, sy2), (W - BORDER, sy2), color=dark, width=0.5); sy2 += 8
            pg2.insert_text((SX, sy2), "DESIGN BASIS", fontsize=8, color=dark, fontname="helv"); sy2 += 12
            note_lines = [
                "Badger Industry Guard",
                "Dry Chemical System",
                "P/N 60-900007-001",
                "(Jan 2007)",
                "UL EX 4864 / ULC CEX 515",
                "NFPA 17 / NFPA 33",
            ]
            for nl in note_lines:
                if sy2 > H - FOOTER_H - 10:
                    break
                pg2.insert_text((SX, sy2), nl, fontsize=6,
                                color=(0.35, 0.35, 0.35), fontname="helv")
                sy2 += 9

            sy2 += 8
            pg2.draw_line((SX, sy2), (W - BORDER, sy2), color=dark, width=0.5); sy2 += 8
            disclaimer = ("All quantities must be verified by a "
                          "qualified installer against current DIOM "
                          "and local AHJ requirements.")
            words2 = disclaimer.split(); line2 = ""
            for w in words2:
                if len(line2) + len(w) + 1 > 34:
                    if sy2 > H - FOOTER_H - 10:
                        break
                    pg2.insert_text((SX, sy2), line2.strip(),
                                    fontsize=6, color=(0.4, 0.4, 0.4), fontname="helv")
                    sy2 += 9; line2 = ""
                line2 += w + " "
            if line2.strip() and sy2 <= H - FOOTER_H - 10:
                pg2.insert_text((SX, sy2), line2.strip(),
                                fontsize=6, color=(0.4, 0.4, 0.4), fontname="helv")

            # logo page 2
            if logo_path:
                try:
                    logo_rect = fitz.Rect(SX, H - FOOTER_H - 88, W - BORDER, H - FOOTER_H - 4)
                    pg2.insert_image(logo_rect, filename=logo_path, keep_proportion=True)
                except Exception:
                    pass

            doc.save(path)
            doc.close()
            return True, path

        except Exception as e:
            return False, str(e)
        finally:
            for tmp in tmp_files:
                try:
                    os.remove(tmp)
                except Exception:
                    pass

    # ── PDF helpers ──────────────────────────────────────────────────────────

    def _get_logo_path(self):
        try:
            import json as _json
            settings_path = os.path.join(
                os.path.expanduser("~"), "Documents", "DFP TakeoffPro", "settings.json"
            )
            if os.path.isfile(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    s = _json.load(f)
                lp = (s.get("logo_path") or "").strip()
                if lp and os.path.isfile(lp):
                    return lp
        except Exception:
            pass
        return None

    @staticmethod
    def _pdf_header(pg, W, H, HEADER_H, BORDER, SIDEBAR_W,
                    customer, location, subtitle, red, dark):
        pg.draw_rect(fitz.Rect(0, 0, W, HEADER_H), color=red, fill=red)
        pg.insert_text((BORDER, 18),  "DEFENSE FIRE PROTECTION",
                       fontsize=13, color=(1, 1, 1), fontname="helv")
        pg.insert_text((BORDER, 35),  subtitle,
                       fontsize=8,  color=(1, 1, 1), fontname="helv")
        sx = W - SIDEBAR_W + 4
        pg.insert_text((sx, 18), f"Customer: {customer}",
                       fontsize=8, color=(1, 1, 1), fontname="helv")
        pg.insert_text((sx, 32), f"Location: {location}",
                       fontsize=7, color=(1, 1, 1), fontname="helv")

    @staticmethod
    def _pdf_footer(pg, W, H, BORDER, FOOTER_H, SIDEBAR_W,
                    customer, location, page_num, total_pages, rev, red, dark):
        import datetime as _dt
        tb_y = H - FOOTER_H
        pg.draw_rect(fitz.Rect(0, tb_y, W, H), color=dark, fill=dark)
        pg.insert_text((BORDER,   tb_y + 13), customer,
                       fontsize=8, color=(1, 1, 1), fontname="helv")
        pg.insert_text((BORDER,   tb_y + 25), location,
                       fontsize=7, color=(0.85, 0.85, 0.85), fontname="helv")
        pg.insert_text((W - 200,  tb_y + 13), "Defense Fire Protection",
                       fontsize=7, color=(1, 1, 1), fontname="helv")
        pg.insert_text((W - 200,  tb_y + 23),
                       _dt.date.today().strftime("Date: %Y-%m-%d"),
                       fontsize=6, color=(0.9, 0.9, 0.9), fontname="helv")
        pg.insert_text((W - 100,  tb_y + 13), f"Page {page_num} of {total_pages}",
                       fontsize=7, color=(1, 1, 1), fontname="helv")
        pg.insert_text((W - 60,   tb_y + 25), f"REV {rev}",
                       fontsize=7, color=(1, 1, 1), fontname="helv")

    @staticmethod
    def _pdf_rev_stamp(pg, W, HEADER_H, SIDEBAR_W, BORDER, rev, rev_d, red):
        pg.draw_rect(fitz.Rect(W - SIDEBAR_W - 80, 4, W - SIDEBAR_W - 4, HEADER_H - 4),
                     color=(1, 1, 1), fill=(1, 1, 1), width=0.8)
        pg.insert_text((W - SIDEBAR_W - 76, 18), f"REV  {rev}",
                       fontsize=11, color=red, fontname="helv")
        if rev_d:
            pg.insert_text((W - SIDEBAR_W - 76, 32), rev_d,
                           fontsize=7, color=(0.3, 0.3, 0.3), fontname="helv")
