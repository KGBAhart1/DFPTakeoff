"""
DFP TakeoffPro – Kitchen Suppression Designer (3D View) v3
⚠ Verify ALL flow numbers against current Kidde/Badger design manuals.
"""
import math, os, json, shutil, datetime, sys, traceback

try:
    from version import APP_VERSION
except ImportError:
    APP_VERSION = "1.0.0"



def _app_dir():
    """Return the directory of the running executable (works in PyInstaller and plain Python)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _projects_dir():
    """Return a writable projects directory.
    Installed builds write to Documents/DFP TakeoffPro/Projects to avoid
    Program Files permission errors."""
    if getattr(sys, 'frozen', False):
        base = os.path.join(os.path.expanduser("~"), "Documents", "DFP TakeoffPro")
    else:
        base = _app_dir()
    p = os.path.join(base, "Projects")
    os.makedirs(p, exist_ok=True)
    return p


def _submittals_dir():
    if getattr(sys, 'frozen', False):
        base = os.path.join(os.path.expanduser("~"), "Documents", "DFP TakeoffPro")
    else:
        base = _app_dir()
    p = os.path.join(base, "Submittals")
    os.makedirs(p, exist_ok=True)
    return p


def _settings_path():
    base = os.path.join(os.path.expanduser("~"), "Documents", "DFP TakeoffPro")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "settings.json")

def _load_settings():
    try:
        with open(_settings_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_settings(d):
    try:
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


def _log_error(context, exc):
    """Append error details to a crash log in Documents/DFP TakeoffPro (always writable)."""
    try:
        base = os.path.join(os.path.expanduser("~"), "Documents", "DFP TakeoffPro")
        os.makedirs(base, exist_ok=True)
        log_path = os.path.join(base, "dfp_crash.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] {context}\n")
            f.write(traceback.format_exc())
    except Exception:
        pass

from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QDoubleSpinBox, QFormLayout, QFrame,
    QMessageBox, QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMenu, QApplication, QCheckBox, QLineEdit,
    QComboBox, QScrollArea, QTextEdit, QButtonGroup, QSpinBox,
    QTabWidget, QInputDialog, QFileDialog,
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QImage, QPolygonF,
    QPainterPath, QRadialGradient, QPixmap,
)
from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal
try:
    from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
    _PRINT_AVAILABLE = True
except ImportError:
    _PRINT_AVAILABLE = False
import fitz

# ═══════════════════════════════════════════════════════════════════════════════
#  Constants & data
# ═══════════════════════════════════════════════════════════════════════════════

PX        = 7
ANG       = math.radians(32)
DSF       = 0.40
APP_BOX_H = 10    # inches — cooking-surface box height
PIPE_W      = 3
SNAP_RADIUS = 14   # scene-unit snap distance for pipe endpoints

HOOD_COL  = QColor(215, 218, 222)
PIPE_COL  = QColor(30, 100, 180)

PIPE_COLORS = [          # (display name, hex) for the pipe-colour picker
    ("Blue",   "#1e64b4"),
    ("Black",  "#1a1a1a"),
    ("Red",    "#c0392b"),
    ("Copper", "#b5541d"),
    ("Grey",   "#888888"),
]

# Kidde WHDR nozzle types — per DIOM P/N 87-122000-001 Table 3-1
# Kidde/Badger nozzle types (shared part numbers per respective DIOMs)
# F=Fryer(flow 2)  ADP=All-purpose(flow 1)  R=Range(flow 1)
# GRW=Gas Radiant/Wok(flow 1)  LPF=Low-Prox Fryer(flow 2)  LPR=Low-Prox Range(flow 1)  DM=Mesquite Log(flow 3)
NOZZLE_TYPES = ["F", "ADP", "R", "GRW", "DM", "LPF", "LPR"]

# Flow points per nozzle type (used for free nozzles placed manually on canvas)
NOZZLE_FLOW = {
    # Kidde / Badger
    "F": 2, "ADP": 1, "R": 1, "GRW": 1, "LPF": 2, "LPR": 1, "DM": 3,
    # Buckeye BFR
    "N-1HP": 1, "N-1LP": 1, "N-2HP": 2, "N-2LP": 2, "N-2W": 2,
    # Amerex KP
    "FG(13729)": 2, "Appl(11982)": 1, "SolidFuel(11983)": 1,
    "UBroiler(11984)": 1, "Range(14178)": 1, "Duct(16416)": 1, "BackShelf(16853)": 1,
}

# Per-manufacturer nozzle type lists (used in dialogs)
MFR_NOZZLE_TYPES = {
    "kidde":   ["F", "ADP", "R", "GRW", "DM", "LPF", "LPR"],
    "badger":  ["F", "ADP", "R", "GRW", "DM", "LPF", "LPR"],
    "buckeye": ["N-1HP", "N-1LP", "N-2HP", "N-2LP", "N-2W"],
    "amerex":  ["FG(13729)", "Appl(11982)", "SolidFuel(11983)",
                "UBroiler(11984)", "Range(14178)", "Duct(16416)", "BackShelf(16853)"],
}

# Color coding for Buckeye BFR nozzles
BUCKEYE_NOZZLE_COLORS = {
    "N-1HP": "#c0392b",   # red  — High Pressure 1-flow
    "N-2HP": "#e74c3c",   # red  — High Pressure 2-flow
    "N-1LP": "#2980b9",   # blue — Low Pressure 1-flow
    "N-2LP": "#1a6fa8",   # blue — Low Pressure 2-flow
    "N-2W":  "#27ae60",   # green — Wide spray 2-flow
}

def _nozzle_color(nozzle_type):
    return QColor(BUCKEYE_NOZZLE_COLORS.get(nozzle_type, PIPE_COL.name()
                  if hasattr(PIPE_COL,'name') else "#1e64b4"))

def _nozzle_color_rgb(nozzle_type):
    """Return (r, g, b) tuple in 0-1 range for PDF export."""
    c = _nozzle_color(nozzle_type)
    return (c.redF(), c.greenF(), c.blueF())

# Distinct detector colors keyed by link temperature prefix — no two temps share a color.
# Avoids yellow/light colors that are hard to see on white backgrounds.
_DETECTOR_COLORS = {
    "135": "#8e44ad",   # purple
    "165": "#c0392b",   # red
    "212": "#2980b9",   # blue
    "286": "#27ae60",   # green
    "360": "#d35400",   # orange
    "450": "#1abc9c",   # teal
    "500": "#7f8c8d",   # gray
}

def _detector_color(link_type):
    """Return a QColor for a detector's link type. Unique per temperature rating."""
    temp = link_type.split()[0].strip() if link_type else ""
    return QColor(_DETECTOR_COLORS.get(temp, "#2c3e50"))

def _detector_color_rgb(link_type):
    c = _detector_color(link_type)
    return (c.redF(), c.greenF(), c.blueF())

NOZZLE_DIRS = {
    "Down ↓":        ( 0.0,  1.0),
    "Up ↑":          ( 0.0, -1.0),
    "Left ←":        (-1.0,  0.0),
    "Right →":       ( 1.0,  0.0),
    "Angle-Left ↙":  (-0.707,  0.707),
    "Angle-Right ↘": ( 0.707,  0.707),
}

# ── Cylinder flow capacities keyed by gallons ─────────────────────────────────
# Kidde WHDR: 125=1.25gal/4fp, 260=2.5gal/8fp, 400=4gal/11fp, 600=6gal/16fp
BOTTLE_FLOW = {1.25: 4, 2.5: 8, 4.0: 11, 6.0: 16}

# ── Manufacturer cylinder data ────────────────────────────────────────────────
# Kidde WHDR model numbers sourced from P/N 87-122000-001 (DIOM Rev. BD, 2025)
# Nozzle types per Table 3-1: F(flow 2), ADP(1), R(1), GRW(1), LPF(2), DM(3)
# Badger Range Guard sourced from P/N 60-9127100-000
#   Same nozzle part numbers as Kidde; cylinders differ in max flow
# Buckeye BFR Kitchen Mister sourced from BPN: BFR-TM (ULEX 6885, Rev 6, 2020)
#   Cylinders rated by flow points: BFR-5=5fp, BFR-10=10fp, BFR-15=15fp, BFR-20=20fp
# Amerex KP sourced from P/N 20150 (EX 4658, 2019)
#   Cylinders: 275=2.75gal/8fp, 375=3.75gal/11fp, 475=4.80gal/14fp, 600=6.14gal/18fp
MANUFACTURERS = {
    "kidde": {
        "name": "Kidde WHDR",
        "color": "#2980b9",
        "tanks": [
            {"model": "WHDR-125  (1.25 gal / 4.7 L  —  4 fp)",  "gal": 1.25, "max_flow":  4},
            {"model": "WHDR-260  (2.5 gal  / 9.5 L  —  8 fp)",  "gal": 2.5,  "max_flow":  8},
            {"model": "WHDR-400  (4 gal    / 15 L   — 12 fp)",  "gal": 4.0,  "max_flow": 12},
            {"model": "WHDR-600  (6 gal    / 22.7 L — 18 fp)",  "gal": 6.0,  "max_flow": 18},
        ],
        "nozzle_types": MFR_NOZZLE_TYPES["kidde"],
        "bad_appliances": ["ecology_unit"],
        "bad_reason": "Ecology/precipitator — verify compatibility with Kidde WHDR",
    },
    "badger": {
        "name": "Badger Range Guard",
        "color": "#8e44ad",
        "tanks": [
            {"model": "RG-1.25G  (1.25 gal /  4.7 L —  4 fp)", "gal": 1.25, "max_flow":  4},
            {"model": "RG-2.5G   (2.5 gal  /  9.5 L —  8 fp)", "gal": 2.5,  "max_flow":  8},
            {"model": "RG-4GS/4GM (4 gal   / 15.1 L — 12 fp)", "gal": 4.0,  "max_flow": 12},
            {"model": "RG-6G     (6 gal    / 22.7 L — 18 fp)", "gal": 6.0,  "max_flow": 18},
        ],
        "nozzle_types": MFR_NOZZLE_TYPES["badger"],
        "bad_appliances": ["ecology_unit"],
        "bad_reason": "Ecology/precipitator — verify compatibility with Badger Range Guard",
    },
    "buckeye": {
        "name": "Buckeye BFR",
        "color": "#e67e22",
        "tanks": [
            {"model": "BFR-5   ( 5 flow pts)",  "gal": None, "max_flow":  5},
            {"model": "BFR-10  (10 flow pts)",  "gal": None, "max_flow": 10},
            {"model": "BFR-15  (15 flow pts)",  "gal": None, "max_flow": 15},
            {"model": "BFR-20  (20 flow pts)",  "gal": None, "max_flow": 20},
        ],
        "nozzle_types": MFR_NOZZLE_TYPES["buckeye"],
        "bad_appliances": [],
        "bad_reason": "",  # Buckeye BFR supports electrostatic precipitators (duct nozzles above & below per DIOM p.3-2)
    },
    "amerex": {
        "name": "Amerex KP",
        "color": "#c0392b",
        "tanks": [
            {"model": "Model 275  (2.75 gal / 10.4 L —  8 fp)", "gal": 2.75, "max_flow":  8},
            {"model": "Model 375  (3.75 gal / 14.2 L — 11 fp)", "gal": 3.75, "max_flow": 11},
            {"model": "Model 475  (4.80 gal / 18.2 L — 14 fp)", "gal": 4.80, "max_flow": 14},
            {"model": "Model 600  (6.14 gal / 23.2 L — 18 fp)", "gal": 6.14, "max_flow": 18},
        ],
        "nozzle_types": MFR_NOZZLE_TYPES["amerex"],
        "bad_appliances": ["ecology_unit"],
        "bad_reason": "Ecology/precipitator — verify compatibility with Amerex KP",
    },
}

# ── Per-manufacturer hood plenum & duct nozzle types ─────────────────────────
# Kidde/Badger: ADP plenum nozzle, ADP duct nozzle
# Buckeye BFR: N-1HP plenum (1 fp / 12 ft section), N-1LP duct (≤50" perimeter)
# Amerex KP:   Appl/11982 plenum (1 fp / 10 ft), Duct/16416 duct (1 fp ≤50" perim)
MFR_HOOD_NOZZLE = {
    "kidde":   {"plenum": "ADP",          "duct": "ADP"},
    "badger":  {"plenum": "ADP",          "duct": "ADP"},
    "buckeye": {"plenum": "N-1HP",        "duct": "N-1LP"},
    "amerex":  {"plenum": "Appl(11982)",  "duct": "Duct(16416)"},
}

# ── Per-manufacturer appliance nozzle/flow overrides ─────────────────────────
# Sourced from: Buckeye BFR Kitchen Mister DIOM BPN:BFR-TM (ULEX 6885, Rev 6, 2020)
#               Amerex KP Manual P/N 20150 (EX 4658, 2019)
# Keys: nt=nozzle type label, flow=flow points (may be float for Amerex), nq=nozzle qty
# Kidde and Badger share identical nozzle types/coverage so NO override needed.
MFR_APPLIANCE_OVERRIDES = {
    # ── Buckeye BFR Kitchen Mister ─────────────────────────────────────────────
    "buckeye": {
        # Fryers — N-2HP, 2 fp (DIOM Fig 3-15: 20.25"×24" fryer)
        "fryer_sm":       {"nt":"N-2HP","flow":2,"nq":1},
        "fryer_md":       {"nt":"N-2HP","flow":2,"nq":1},
        "fryer_lg":       {"nt":"N-2HP","flow":4,"nq":2},
        "henny_penny":    {"nt":"N-2HP","flow":2,"nq":1},
        # Griddles — N-1LP, 1 fp (Fig 3-17/3-18: ≤48"×30"); extra-large N-2LP (Fig 3-19: 60"×30")
        "griddle_sm":     {"nt":"N-1LP","flow":1,"nq":1},
        "griddle_lg":     {"nt":"N-2LP","flow":2,"nq":1},
        "round_griddle":  {"nt":"N-1LP","flow":1,"nq":1},
        "clamshell":      {"nt":"N-1LP","flow":1,"nq":1},
        # Tilt Skillet — N-2HP, 2 fp (Fig 3-16)
        "tilt_skillet":   {"nt":"N-2HP","flow":2,"nq":1},
        # Ranges (Fig 3-8 to 3-11)
        "range_2":        {"nt":"N-1LP","flow":1,"nq":1},
        "range_4":        {"nt":"N-1LP","flow":1,"nq":1},
        "range_6":        {"nt":"N-2LP","flow":2,"nq":1},
        "range_8":        {"nt":"N-2LP","flow":4,"nq":2},
        "range_10":       {"nt":"N-2LP","flow":6,"nq":3},
        # Range+Griddle combos — N-1LP 1 fp per 30"×24" module (Fig 3-12)
        "combo_4b_grd_r": {"nt":"N-1LP","flow":2,"nq":2},
        "combo_4b_grd_l": {"nt":"N-1LP","flow":2,"nq":2},
        "combo_2b_grd_r": {"nt":"N-1LP","flow":2,"nq":2},
        "combo_2b_grd_l": {"nt":"N-1LP","flow":2,"nq":2},
        # Woks — N-1HP, 1 fp (Fig 3-14b: 12"–30" dia)
        "wok":            {"nt":"N-1HP","flow":1,"nq":1},
        "wok_2":          {"nt":"N-1HP","flow":2,"nq":2},
        "wok_3":          {"nt":"N-1HP","flow":3,"nq":3},
        "wok_4":          {"nt":"N-1HP","flow":4,"nq":4},
        "wok_5":          {"nt":"N-1HP","flow":5,"nq":5},
        # Charbroilers
        "charbroiler":      {"nt":"N-1HP","flow":1,"nq":1},  # gas/elec radiant (Fig 3-20)
        "lava_charbroiler": {"nt":"N-2HP","flow":2,"nq":1},  # lava rock (Fig 3-21)
        "mesq_charbroiler": {"nt":"N-2HP","flow":2,"nq":1},  # treated as solid fuel / lava
        "elec_charbroiler": {"nt":"N-1HP","flow":1,"nq":1},
        "radiant_gas":      {"nt":"N-1HP","flow":1,"nq":1},
        "grillworks_2":     {"nt":"N-1HP","flow":2,"nq":2},
        "grillworks_3":     {"nt":"N-1HP","flow":3,"nq":3},
        # Broilers
        "chain_broiler_c":  {"nt":"N-1LP","flow":1,"nq":1},
        "chain_broiler_o":  {"nt":"N-2HP","flow":2,"nq":1},
        "chain_pizza_oven": {"nt":"N-1LP","flow":2,"nq":2},
        "upright_broiler":  {"nt":"N-1LP","flow":1,"nq":1},  # Fig 3-22: 36"×24"
        "salamander":       {"nt":"N-1LP","flow":1,"nq":1},
        "cheese_melter":    {"nt":"N-1LP","flow":1,"nq":1},
        # Other
        "soup_stove":       {"nt":"N-1LP","flow":1,"nq":1},
        "bell_10":          {"nt":"N-1LP","flow":1,"nq":1},
        "tandoor_oven":     {"nt":"N-1HP","flow":1,"nq":1},
        "gyro":             {"nt":"N-1HP","flow":1,"nq":1},
        "ecology_unit":     {"nt":"N-1LP","flow":0,"nq":0},   # duct nozzles above+below (design separately)
    },
    # ── Amerex KP ──────────────────────────────────────────────────────────────
    "amerex": {
        # Fryers — FG(13729), 2 fp (Nozzle App. Chart)
        "fryer_sm":       {"nt":"FG(13729)","flow":2,"nq":1},
        "fryer_md":       {"nt":"FG(13729)","flow":2,"nq":1},
        "fryer_lg":       {"nt":"FG(13729)","flow":4,"nq":2},
        "henny_penny":    {"nt":"FG(13729)","flow":2,"nq":1},
        # Griddles
        "griddle_sm":     {"nt":"Appl(11982)","flow":1,"nq":1},   # ≤36"×30" overhead: 11982
        "griddle_lg":     {"nt":"FG(13729)", "flow":2,"nq":1},    # ≤42"×30" overhead: 13729
        "round_griddle":  {"nt":"Appl(11982)","flow":1,"nq":1},
        "clamshell":      {"nt":"Appl(11982)","flow":1,"nq":1},
        # Tilt Skillet — FG(13729), 2 fp
        "tilt_skillet":   {"nt":"FG(13729)","flow":2,"nq":1},
        # Ranges
        "range_2":        {"nt":"Appl(11982)","flow":1,"nq":1},
        "range_4":        {"nt":"Range(14178)","flow":2,"nq":1},
        "range_6":        {"nt":"Range(14178)","flow":4,"nq":2},
        "range_8":        {"nt":"Range(14178)","flow":4,"nq":2},
        "range_10":       {"nt":"Range(14178)","flow":6,"nq":3},
        # Range+Griddle combos
        "combo_4b_grd_r": {"nt":"Range(14178)","flow":3,"nq":2},
        "combo_4b_grd_l": {"nt":"Range(14178)","flow":3,"nq":2},
        "combo_2b_grd_r": {"nt":"Appl(11982)","flow":2,"nq":2},
        "combo_2b_grd_l": {"nt":"Appl(11982)","flow":2,"nq":2},
        # Woks — Appl(11982), 1 fp
        "wok":            {"nt":"Appl(11982)","flow":1,"nq":1},
        "wok_2":          {"nt":"Appl(11982)","flow":2,"nq":2},
        "wok_3":          {"nt":"Appl(11982)","flow":3,"nq":3},
        "wok_4":          {"nt":"Appl(11982)","flow":4,"nq":4},
        "wok_5":          {"nt":"Appl(11982)","flow":5,"nq":5},
        # Charbroilers
        "charbroiler":      {"nt":"SolidFuel(11983)","flow":1.5,"nq":1},  # charcoal solid fuel 1.5 fp
        "lava_charbroiler": {"nt":"SolidFuel(11983)","flow":1.5,"nq":1},  # lava rock = solid fuel 1.5 fp
        "mesq_charbroiler": {"nt":"SolidFuel(11983)","flow":1.5,"nq":1},
        "elec_charbroiler": {"nt":"Appl(11982)","flow":1,"nq":1},
        "radiant_gas":      {"nt":"Appl(11982)","flow":1,"nq":1},
        "grillworks_2":     {"nt":"Appl(11982)","flow":2,"nq":2},
        "grillworks_3":     {"nt":"Appl(11982)","flow":3,"nq":3},
        # Broilers
        "chain_broiler_c":  {"nt":"Appl(11982)","flow":1,"nq":1},
        "chain_broiler_o":  {"nt":"FG(13729)","flow":2,"nq":1},
        "chain_pizza_oven": {"nt":"Appl(11982)","flow":2,"nq":2},
        "upright_broiler":  {"nt":"UBroiler(11984)","flow":1,"nq":2},  # 2 × 0.5 fp = 1 fp
        "salamander":       {"nt":"Appl(11982)","flow":1,"nq":1},
        "cheese_melter":    {"nt":"Appl(11982)","flow":1,"nq":1},
        # Other
        "soup_stove":       {"nt":"Appl(11982)","flow":1,"nq":1},
        "bell_10":          {"nt":"Appl(11982)","flow":1,"nq":1},
        "tandoor_oven":     {"nt":"Appl(11982)","flow":1,"nq":1},
        "gyro":             {"nt":"Appl(11982)","flow":1,"nq":1},
        "ecology_unit":     {"nt":"Duct(16416)","flow":0,"nq":0},
    },
}


def effective_defn(key, mfr_key="kidde"):
    """Return appliance def overlaid with manufacturer-specific nozzle/flow values."""
    base = dict(APPLIANCE_DEFS.get(key, {}))
    overrides = MFR_APPLIANCE_OVERRIDES.get(mfr_key, {}).get(key, {})
    base.update(overrides)
    return base

# ── Appliance definitions ─────────────────────────────────────────────────────
# nt  = Kidde nozzle type label shown on drawing & breakdown table
#       F=Fryer nozzle (flow 2)  ADP=All-purpose (flow 1)  R=Range (flow 1)
#       GRW=Gas Radiant/Wok (flow 1)  DM=Mesquite log (flow 3)
#       LPF=Low-proximity fryer (flow 2)
# flow= flow points per Table 3-1 of Kidde WHDR DIOM P/N 87-122000-001
# nq  = number of nozzles placed per appliance
#
# HOW TO ADD A NEW APPLIANCE:
#   1. Add entry to APPLIANCE_DEFS below (copy a similar one as template)
#      Optional fields: "dh" = custom default height in inches (default is 30 if omitted)
#   2. Add the key to the correct group in APPLIANCE_GROUPS so it appears in the palette
#   3. Add manufacturer overrides in MFR_APPLIANCE_OVERRIDES if nozzle type differs by brand
#   4. Add a paint block in ApplianceItem.paint() — search for "elif k==" to find the section
#      Each appliance key needs its own elif block to draw the icon on the canvas
APPLIANCE_DEFS = {
    # ── Fryers — F nozzle, flow 2 each (DIOM §3-4.1 – 3-4.7) ─────────────────
    "fryer_sm":       {"label":"Fryer\nSmall",    "short":"FRY-S","name":"Fryer Small",       "dw":14.5,"dd":14.5,"flow":2,"nt":"F","nq":1,"r":[],"color":"#c0392b","legs":True},
    "fryer_md":       {"label":"Fryer\nMed",      "short":"FRY-M","name":"Fryer Med",         "dw":14.5,"dd":21,  "flow":2,"nt":"F","nq":1,"r":[],"color":"#c0392b","legs":True},
    "fryer_lg":       {"label":"Fryer\nLarge",    "short":"FRY-L","name":"Fryer Large",       "dw":21,  "dd":24,  "flow":4,"nt":"F","nq":2,"r":[],"color":"#c0392b","legs":True},
    "henny_penny":    {"label":"Henny\nPenny",    "short":"HNP",  "name":"Henny Penny Fryer", "dw":18,  "dd":24,  "flow":2,"nt":"F","nq":1,"r":[],"color":"#a93226","legs":True},
    # ── Griddles — ADP nozzle, flow 1 per nozzle (DIOM §3-4.20) ──────────────
    "griddle_sm":     {"label":"Griddle\n≤30\"",  "short":"GRD-S","name":"Griddle ≤30\"",     "dw":30,  "dd":24,  "flow":1,"nt":"ADP","nq":1,"r":[],"color":"#d35400","legs":True},
    "griddle_lg":     {"label":"Griddle\n>30\"",  "short":"GRD-L","name":"Griddle >30\"",     "dw":48,  "dd":24,  "flow":2,"nt":"ADP","nq":2,"r":[],"color":"#d35400","legs":True},
    "round_griddle":  {"label":"Round\nGriddle",  "short":"RGD",  "name":"Round Griddle",     "dw":36,  "dd":36,  "flow":1,"nt":"ADP","nq":1,"r":[],"color":"#e67e22","legs":True},
    "clamshell":      {"label":"Clam-\nshell",    "short":"CLM",  "name":"Clamshell Griddle", "dw":24,  "dd":24,  "flow":1,"nt":"ADP","nq":1,"r":[],"color":"#ca6f1e","legs":True},
    # ── Tilt Skillet — F nozzle, flow 2 (DIOM §3-4.22) ───────────────────────
    "tilt_skillet":   {"label":"Tilt\nSkillet",   "short":"TSK",  "name":"Tilt Skillet",      "dw":36,  "dd":24,  "flow":2,"nt":"F","nq":1,"r":[],"color":"#935116","legs":True},
    # ── Ranges — R nozzle, flow 1 per nozzle (DIOM §3-4.9 – 3-4.12) ──────────
    # Each pair of burners = 1 R nozzle; 6+ burners use 2 nozzles etc.
    "range_2":        {"label":"Range\n2-Brn",    "short":"RNG2", "name":"Range 2-Burner",    "dw":24,  "dd":24,  "flow":1,"nt":"R","nq":1,"r":[],"color":"#8e44ad","legs":True,"n_burners":2},
    "range_4":        {"label":"Range\n4-Brn",    "short":"RNG4", "name":"Range 4-Burner",    "dw":36,  "dd":24,  "flow":1,"nt":"R","nq":1,"r":[],"color":"#8e44ad","legs":True,"n_burners":4},
    "range_6":        {"label":"Range\n6-Brn",    "short":"RNG6", "name":"Range 6-Burner",    "dw":48,  "dd":24,  "flow":2,"nt":"R","nq":2,"r":[],"color":"#8e44ad","legs":True,"n_burners":6},
    "range_8":        {"label":"Range\n8-Brn",    "short":"RNG8", "name":"Range 8-Burner",    "dw":60,  "dd":24,  "flow":2,"nt":"R","nq":2,"r":[],"color":"#8e44ad","legs":True,"n_burners":8},
    "range_10":       {"label":"Range\n10-Brn",   "short":"RNG10","name":"Range 10-Burner",   "dw":72,  "dd":24,  "flow":3,"nt":"R","nq":3,"r":[],"color":"#8e44ad","legs":True,"n_burners":10},
    # ── Range+Griddle combos — R nozzle (burners) + ADP (griddle) ─────────────
    "combo_4b_grd_r": {"label":"4Brn\n+Grd→",    "short":"C4GR", "name":"4-Brn+Griddle (R)", "dw":60,  "dd":24,  "flow":2,"nt":"R+ADP","nq":2,"r":[],"color":"#7d3c98","legs":True,"n_burners":4,"griddle_side":"right"},
    "combo_4b_grd_l": {"label":"4Brn\n←Grd",     "short":"C4GL", "name":"4-Brn+Griddle (L)", "dw":60,  "dd":24,  "flow":2,"nt":"R+ADP","nq":2,"r":[],"color":"#7d3c98","legs":True,"n_burners":4,"griddle_side":"left"},
    "combo_2b_grd_r": {"label":"2Brn\n+Grd→",    "short":"C2GR", "name":"2-Brn+Griddle (R)", "dw":48,  "dd":24,  "flow":2,"nt":"R+ADP","nq":2,"r":[],"color":"#7d3c98","legs":True,"n_burners":2,"griddle_side":"right"},
    "combo_2b_grd_l": {"label":"2Brn\n←Grd",     "short":"C2GL", "name":"2-Brn+Griddle (L)", "dw":48,  "dd":24,  "flow":2,"nt":"R+ADP","nq":2,"r":[],"color":"#7d3c98","legs":True,"n_burners":2,"griddle_side":"left"},
    # ── Woks — GRW nozzle, flow 1 each (DIOM §3-4.21) ────────────────────────
    "wok":            {"label":"Wok ×1",          "short":"WK1",  "name":"Wok ×1",            "dw":24,  "dd":24,  "flow":1,"nt":"GRW","nq":1,"r":[],"color":"#16a085","legs":True,"n_woks":1},
    "wok_2":          {"label":"Wok ×2",          "short":"WK2",  "name":"Wok ×2",            "dw":48,  "dd":24,  "flow":2,"nt":"GRW","nq":2,"r":[],"color":"#16a085","legs":True,"n_woks":2},
    "wok_3":          {"label":"Wok ×3",          "short":"WK3",  "name":"Wok ×3",            "dw":72,  "dd":24,  "flow":3,"nt":"GRW","nq":3,"r":[],"color":"#16a085","legs":True,"n_woks":3},
    "wok_4":          {"label":"Wok ×4",          "short":"WK4",  "name":"Wok ×4",            "dw":96,  "dd":24,  "flow":4,"nt":"GRW","nq":4,"r":[],"color":"#16a085","legs":True,"n_woks":4},
    "wok_5":          {"label":"Wok ×5",          "short":"WK5",  "name":"Wok ×5",            "dw":120, "dd":24,  "flow":5,"nt":"GRW","nq":5,"r":[],"color":"#16a085","legs":True,"n_woks":5},
    # ── Charbroilers ──────────────────────────────────────────────────────────
    # Natural/mesquite charcoal: ADP, flow 1 (§3-4.16)
    "charbroiler":      {"label":"Char-\nbroiler",    "short":"CHB",  "name":"Charbroiler (Charcoal)",     "dw":24,"dd":24,"flow":1,"nt":"ADP","nq":1,"r":[],"color":"#2c3e50","legs":True},
    # Lava/pumice/ceramic/synthetic rock: F nozzle, flow 2 (§3-4.14)
    "lava_charbroiler": {"label":"Lava\nChrbrln",     "short":"LAVB", "name":"Lava Rock Charbroiler",      "dw":24,"dd":24,"flow":2,"nt":"F",  "nq":1,"r":[],"color":"#2c3e50","legs":True},
    # Mesquite logs: DM nozzle, flow 3 (§3-4.17)
    "mesq_charbroiler": {"label":"Mesquite\nChrbrln", "short":"MQB",  "name":"Mesquite Log Charbroiler",   "dw":30,"dd":24,"flow":3,"nt":"DM", "nq":1,"r":[],"color":"#2c3e50","legs":True},
    # Gas radiant / electric radiant: GRW nozzle, flow 1 (§3-4.15)
    "elec_charbroiler": {"label":"Radiant\nElec Chb", "short":"ELCB", "name":"Radiant Elec Charbroiler",   "dw":24,"dd":24,"flow":1,"nt":"GRW","nq":1,"r":[],"color":"#1a5276","legs":True},
    "radiant_gas":      {"label":"Radiant\nGas Chb",  "short":"RGCB", "name":"Radiant Gas Charbroiler",    "dw":24,"dd":24,"flow":1,"nt":"GRW","nq":1,"r":[],"color":"#2c3e50","legs":True},
    # Grillworks open-hearth: treated as solid-fuel charbroiler — ADP, flow 1 per section
    "grillworks_2":     {"label":"Grill-\nwks ×2",    "short":"GW2",  "name":"Grillworks Double",          "dw":48,"dd":28,"flow":2,"nt":"ADP","nq":2,"r":[],"color":"#922b21","legs":True},
    "grillworks_3":     {"label":"Grill-\nwks ×3",    "short":"GW3",  "name":"Grillworks Triple",          "dw":72,"dd":28,"flow":3,"nt":"ADP","nq":3,"r":[],"color":"#922b21","legs":True},
    # ── Broilers ──────────────────────────────────────────────────────────────
    # Chain broiler closed: 1 ADP into tunnel, flow 1 (§3-4.18)
    "chain_broiler_c":  {"label":"Chain\nBrlr Cls",   "short":"CBRC", "name":"Chain Broiler Closed",       "dw":36,"dd":24,"flow":1,"nt":"ADP","nq":1,"r":[],"color":"#1c2833","legs":True},
    # Chain broiler open: 2 ADP (tunnel + top opening), flow 2 (§3-4.19)
    "chain_broiler_o":  {"label":"Chain\nBrlr Open",  "short":"CBRO", "name":"Chain Broiler Open",         "dw":36,"dd":24,"flow":2,"nt":"ADP","nq":2,"r":[],"color":"#1c2833","legs":True},
    # Chain pizza oven: conveyor tunnel with pizza decks on each side, flow 1 ADP
    "chain_pizza_oven": {"label":"Chain\nPizza Oven", "short":"CPZ",  "name":"Chain Pizza Oven",           "dw":48,"dd":30,"dh":12,"flow":2,"nt":"ADP","nq":2,"r":[],"color":"#1c2833","legs":True,
                         "nz_layout":"sides"},
    # Upright broiler: ADP, flow 1 (§3-4.13)
    "upright_broiler":  {"label":"Upright\nBroiler",  "short":"UPB",  "name":"Upright Broiler",            "dw":24,"dd":24,"flow":1,"nt":"ADP","nq":1,"r":[],"color":"#2e4053","legs":True},
    # Salamander / cheese melter: treated as upright broiler — ADP, flow 1
    "salamander":       {"label":"Sala-\nmander",     "short":"SAL",  "name":"Salamander",                 "dw":36,"dd":20,"flow":1,"nt":"ADP","nq":1,"r":[],"color":"#922b21","legs":False},
    "cheese_melter":    {"label":"Cheese\nMelter",    "short":"CHS",  "name":"Cheese Melter",              "dw":36,"dd":20,"flow":1,"nt":"ADP","nq":1,"r":[],"color":"#7b241c","legs":False},
    # ── Other ─────────────────────────────────────────────────────────────────
    # Soup stove: treated as range — R nozzle, flow 1
    "soup_stove":       {"label":"Soup\nStove",       "short":"SPS",  "name":"Soup Stove",                 "dw":24,"dd":24,"flow":1,"nt":"R",  "nq":1,"r":[],"color":"#1a5276","legs":True},
    # Tandoor oven: solid-fuel style — ADP, flow 1
    "tandoor_oven":     {"label":"Tandoor\nOven",     "short":"TAN",  "name":"Tandoor Oven",               "dw":24,"dd":24,"flow":1,"nt":"ADP","nq":1,"r":[],"color":"#7d6608","legs":True},
    # Gyro: upright radiant — GRW nozzle, flow 1
    "gyro":             {"label":"Gyro",              "short":"GYR",  "name":"Gyro",                       "dw":20,"dd":20,"flow":1,"nt":"GRW","nq":1,"r":[],"color":"#784212","legs":True},
    "ecology_unit":     {"label":"Ecology\nUnit",     "short":"ECO",  "name":"Ecology Unit",               "dw":48,"dd":24,"flow":0,"nt":None, "nq":0,"r":["kidde","badger","amerex"],"color":"#7f8c8d","legs":False},
    # Convection oven: no suppression coverage required — placed for layout reference only
    "convection_oven":  {"label":"Conv.\nOven",       "short":"COV",  "name":"Convection Oven",            "dw":36,"dd":36,"flow":0,"nt":None, "nq":0,"r":[],"color":"#5d6d7e","legs":True},
    # 10" Bell burner: single high-BTU round burner, R nozzle, flow 1
    "bell_10":          {"label":'10"\nBell',         "short":"BL10", "name":'10" Bell Burner',            "dw":16,"dd":16,"flow":1,"nt":"R",  "nq":1,"r":[],"color":"#1a5276","legs":True},
    # Table: layout reference only — no suppression coverage
    "table":            {"label":"Table",             "short":"TBL",  "name":"Table",                      "dw":60,"dd":30,"flow":0,"nt":None, "nq":0,"r":[],"color":"#d5d8dc","legs":True},
}

# Palette groups — (display name, [appliance keys])
APPLIANCE_GROUPS = [
    ("Fryers",         ["fryer_sm","fryer_md","fryer_lg","henny_penny"]),
    ("Griddles",       ["griddle_sm","griddle_lg","round_griddle","clamshell","tilt_skillet"]),
    ("Ranges",         ["range_2","range_4","range_6","range_8","range_10"]),
    ("Rng+Griddle",    ["combo_4b_grd_r","combo_4b_grd_l","combo_2b_grd_r","combo_2b_grd_l"]),
    ("Woks",           ["wok","wok_2","wok_3","wok_4","wok_5"]),
    ("Charbroilers",   ["charbroiler","lava_charbroiler","mesq_charbroiler",
                         "elec_charbroiler","radiant_gas",
                         "grillworks_2","grillworks_3"]),
    ("Broilers",       ["chain_broiler_c","chain_broiler_o","chain_pizza_oven","upright_broiler",
                         "salamander","cheese_melter"]),
    ("Other",          ["soup_stove","bell_10","tandoor_oven","gyro","convection_oven","ecology_unit","table"]),
]

# ═══════════════════════════════════════════════════════════════════════════════
#  3D drawing helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _ddx(d_in): return d_in * PX * DSF * math.cos(ANG)
def _ddy(d_in): return -d_in * PX * DSF * math.sin(ANG)

def draw_box3d(painter, x, y, w, h, d_in, base_col, label="", label_col=None):
    dx=_ddx(d_in); dy=_ddy(d_in)
    ftl=QPointF(x,y); ftr=QPointF(x+w,y); fbl=QPointF(x,y+h); fbr=QPointF(x+w,y+h)
    btl=QPointF(x+dx,y+dy); btr=QPointF(x+w+dx,y+dy)
    bbl=QPointF(x+dx,y+h+dy); bbr=QPointF(x+w+dx,y+h+dy)
    out=QPen(base_col.darker(155),1.2)
    painter.setPen(out); painter.setBrush(QBrush(base_col.lighter(138)))
    painter.drawPolygon(QPolygonF([ftl,ftr,btr,btl]))
    painter.setBrush(QBrush(base_col.darker(118)))
    painter.drawPolygon(QPolygonF([ftr,fbr,bbr,btr]))
    painter.setBrush(QBrush(base_col))
    painter.drawPolygon(QPolygonF([ftl,ftr,fbr,fbl]))
    dp=QPen(base_col.darker(145),0.8,Qt.DashLine); painter.setPen(dp); painter.setBrush(Qt.NoBrush)
    painter.drawLine(bbl,btl); painter.drawLine(bbl,bbr); painter.drawLine(btr,bbr)
    if label:
        lc=label_col or (QColor("white") if base_col.lightness()<155 else QColor("#232728"))
        painter.setPen(lc); fs=max(6,int(min(w,h)/5))
        painter.setFont(QFont("Arial",fs,QFont.Bold))
        painter.drawText(QRectF(x+2,y+2,w-4,h-4),Qt.AlignCenter,label)

def draw_arrow(painter, x1, y1, x2, y2, col=None, width=PIPE_W):
    col=col or PIPE_COL
    painter.setPen(QPen(col,width,Qt.SolidLine,Qt.RoundCap))
    painter.drawLine(QPointF(x1,y1),QPointF(x2,y2))
    ang=math.atan2(y2-y1,x2-x1); sz=width*3.2
    p1=QPointF(x2-sz*math.cos(ang-0.42),y2-sz*math.sin(ang-0.42))
    p2=QPointF(x2-sz*math.cos(ang+0.42),y2-sz*math.sin(ang+0.42))
    painter.setPen(Qt.NoPen); painter.setBrush(QBrush(col))
    painter.drawPolygon(QPolygonF([QPointF(x2,y2),p1,p2]))

def draw_bottle(painter, x, y, w, h, col):
    x,y,w,h=int(x),int(y),int(w),int(h)
    ry=max(3,w//5); nk_w=max(6,w//3); nk_h=max(8,h//9)
    hd_w=max(10,int(w*0.65)); hd_h=max(8,h//9)
    nk_x=x+(w-nk_w)//2; hd_x=x+(w-hd_w)//2
    body_top=y+hd_h+nk_h+ry; body_h=h-hd_h-nk_h-ry*2
    painter.setBrush(QBrush(col)); painter.setPen(QPen(col.darker(155),1.5))
    painter.drawRect(x,body_top,w,body_h)
    painter.drawEllipse(x,y+h-ry*2,w,ry*2)
    painter.setBrush(QBrush(col.lighter(130))); painter.drawEllipse(x,body_top-ry,w,ry*2)
    painter.setBrush(QBrush(col.darker(108))); painter.setPen(QPen(col.darker(155),1.5))
    painter.drawRect(nk_x,y+hd_h,nk_w,nk_h+ry)
    painter.setBrush(QBrush(col.darker(145))); painter.drawRect(hd_x,y,hd_w,hd_h)
    painter.setPen(QPen(QColor(210,215,225),1.5)); mid=y+hd_h//2
    painter.drawLine(hd_x+2,mid,hd_x+hd_w-2,mid)
    gr=max(3,w//7); gx=x+w//4; gy=body_top+body_h//3
    painter.setBrush(QBrush(QColor(240,242,245))); painter.setPen(QPen(col.darker(160),1))
    painter.drawEllipse(gx-gr,gy-gr,gr*2,gr*2)
    painter.setPen(QPen(QColor("#c0392b"),1)); painter.drawLine(gx,gy,gx+gr-2,gy-gr+2)

# ═══════════════════════════════════════════════════════════════════════════════
#  Helper functions
# ═══════════════════════════════════════════════════════════════════════════════

def _item_show_label(item):
    """Global OR per-item label visibility."""
    if item.scene() and not getattr(item.scene(),"show_labels",True): return False
    return getattr(item,"show_label",True)

def _align_duct_back(hood, duct, offset_n=0):
    duct_d=duct.w_in*0.7
    effective_d=max(0, hood.d_in-duct_d)
    hx=hood.scenePos().x(); hy=hood.scenePos().y()
    duct.setPos(hx+_ddx(effective_d)+(hood.w_px-duct.w_px)/2 + offset_n*(duct.w_px+6),
                hy+_ddy(effective_d)-duct.h_px)

def _context_menu_base(item, event, extra_actions=None):
    """Show right-click menu with label toggle + optional extras + delete. Returns chosen action."""
    m=QMenu()
    lbl_act=m.addAction("Hide Label" if getattr(item,"show_label",True) else "Show Label")
    extras=[]
    if extra_actions:
        m.addSeparator()
        for txt in extra_actions: extras.append(m.addAction(txt))
    m.addSeparator()
    del_act=m.addAction("Delete")
    chosen=m.exec_(event.screenPos())
    if chosen==lbl_act:
        item.show_label=not getattr(item,"show_label",True); item.update(); return None
    for act,txt in zip(extras, extra_actions or []):
        if chosen==act: return txt
    if chosen==del_act: return "delete"
    return None

# ═══════════════════════════════════════════════════════════════════════════════
#  Scene items
# ═══════════════════════════════════════════════════════════════════════════════

class HoodItem(QGraphicsItem):
    ITEM_TYPE="hood"
    def __init__(self, w_in, d_in, label="Hood", zone="Zone 1"):
        super().__init__()
        self.w_in=w_in; self.d_in=d_in; self.label=label; self.zone=zone
        self.show_label=False; self.plenum_nozzles=[]
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges); self.setZValue(0)

    @property
    def w_px(self): return self.w_in*PX
    @property
    def h_px(self): return 14*PX

    def boundingRect(self):
        dx=_ddx(self.d_in); dy=_ddy(self.d_in)
        return QRectF(0,dy,self.w_px+dx,self.h_px+abs(dy))

    def shape(self):
        p=QPainterPath(); p.addRect(self.boundingRect()); return p

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        lbl=f"HOOD: {self.label}  {self.w_in:.0f}\"×{self.d_in:.0f}\"" if _item_show_label(self) else ""
        draw_box3d(painter,0,0,self.w_px,self.h_px,self.d_in,HOOD_COL,label=lbl,label_col=QColor("#232728"))
        if self.isSelected():
            painter.setPen(QPen(QColor("#ff7002"),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-2,-2,2,2))

    def itemChange(self, change, value):
        if change==QGraphicsItem.ItemPositionHasChanged and self.scene(): self.scene().update()
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        result=_context_menu_base(self, event, ["Edit Hood…"])
        if result=="Edit Hood…":
            dlg=HoodEditDialog(self)
            if dlg.exec_()==QDialog.Accepted:
                w,d,lbl,zone=dlg.values()
                self.w_in=w; self.d_in=d; self.label=lbl; self.zone=zone
                # reposition plenum nozzles
                sc=self.scene()
                nq=len(self.plenum_nozzles)
                if nq:
                    spacing=self.w_px/(nq+1)
                    for i,nz in enumerate(self.plenum_nozzles):
                        nz.setPos(spacing*(i+1), self.h_px*0.35)
                self.update()
                if sc: sc.layout_changed.emit()
        elif result=="delete":
            sc=self.scene()
            if sc:
                # Remove plenum nozzles first (they're children; scene auto-removes but
                # explicit removal keeps the list clean)
                for nz in list(self.plenum_nozzles):
                    if nz.scene(): sc.removeItem(nz)
                sc.removeItem(self); sc.layout_changed.emit()

    def flow_points(self): return max(1, math.ceil(self.w_in/48.0))
    def pipe_y(self): return self.scenePos().y()+self.h_px*0.52


class DuctItem(QGraphicsItem):
    ITEM_TYPE="duct"
    def __init__(self, w_in=14, h_in=14):
        super().__init__()
        self.w_in=w_in; self.h_in=h_in; self.show_label=False
        self.duct_nozzles=[]
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(0.5)

    @property
    def duct_nozzle(self):
        return self.duct_nozzles[0] if self.duct_nozzles else None

    @property
    def w_px(self): return self.w_in*PX
    @property
    def h_px(self): return self.h_in*PX

    def boundingRect(self):
        d=self.w_in*0.7; return QRectF(0,_ddy(d),self.w_px+_ddx(d),self.h_px+abs(_ddy(d)))

    def shape(self):
        p=QPainterPath(); p.addRect(self.boundingRect()); return p

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        lbl="DUCT" if _item_show_label(self) else ""
        draw_box3d(painter,0,0,self.w_px,self.h_px,self.w_in*0.7,QColor(185,190,198),label=lbl,label_col=QColor("#232728"))
        if self.isSelected():
            painter.setPen(QPen(QColor("#ff7002"),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-2,-2,2,2))

    def itemChange(self, change, value):
        if change==QGraphicsItem.ItemPositionHasChanged and self.scene(): self.scene().update()
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        result=_context_menu_base(self, event, ["Edit Duct…"])
        if result=="Edit Duct…":
            dlg=DuctEditDialog(self)
            if dlg.exec_()==QDialog.Accepted:
                w,h=dlg.values()
                self.w_in=w; self.h_in=h
                # reposition nozzles evenly
                sc=self.scene()
                nq=len(self.duct_nozzles)
                for i,nz in enumerate(self.duct_nozzles):
                    nz.setPos(self.w_px*(i+1)/(nq+1), self.h_px*0.85)
                self.update()
                if sc: sc.layout_changed.emit()
        elif result=="delete":
            sc=self.scene()
            if sc:
                for nz in list(self.duct_nozzles):
                    if nz.scene(): sc.removeItem(nz)
                sc.removeItem(self); sc.layout_changed.emit()


class ApplianceItem(QGraphicsItem):
    ITEM_TYPE="appliance"
    def __init__(self, key, w_in=None, d_in=None, h_in=30, custom_name=None):
        super().__init__()
        self.key=key; self.defn=APPLIANCE_DEFS[key]
        self.w_in=w_in or self.defn["dw"]; self.d_in=d_in or self.defn["dd"]; self.h_in=h_in
        self.custom_name=custom_name; self.show_label=True; self.app_nozzles=[]
        # _nozzles_placed: True once nozzles have been assigned (place, load, or mfr switch).
        # Needed to distinguish "appliance just dropped with 0 nozzles yet" from "user deleted all nozzles".
        # total_flow() and recommendation() use this: if True, count app_nozzles (can be 0);
        # if False, fall back to the definition's default flow so the count isn't zero on first drop.
        self._nozzles_placed=False
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges); self.setZValue(1)

    @property
    def w_px(self): return self.w_in*PX
    @property
    def box_h_px(self): return APP_BOX_H*PX
    @property
    def leg_px(self): return max(0,(self.h_in-APP_BOX_H))*PX if self.defn.get("legs") else 0

    def boundingRect(self):
        dx=_ddx(self.d_in); dy=_ddy(self.d_in)
        return QRectF(0,dy,self.w_px+dx,self.box_h_px+self.leg_px+32+abs(dy))

    def shape(self):
        p=QPainterPath(); p.addRect(self.boundingRect()); return p

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        box_col=QColor(238,238,240); acc=QColor(self.defn["color"])
        k=self.key; w=self.w_px; h=self.box_h_px
        dx=_ddx(self.d_in); dy=_ddy(self.d_in)

        # ── Table: fully custom — skip base box entirely ──────────────────────
        if k=="table":
            col_top  = QColor(215,218,222)   # top surface
            col_edge = QColor(175,178,182)   # front/side edge
            col_leg  = QColor(160,163,167)   # legs
            col_dark = QColor(130,133,137)   # back faces
            pen_out  = QPen(QColor(100,102,105), 1.2)
            pen_dash = QPen(QColor(160,162,165), 0.7, Qt.DashLine)
            lt = max(5, int(w * 0.055))      # leg thickness px
            tt = max(4, int(abs(dy)*0.3+3))  # top slab thickness px

            # isometric top surface (parallelogram)
            top = QPolygonF([QPointF(0,0), QPointF(w,0),
                             QPointF(w+dx, dy), QPointF(dx, dy)])
            painter.setBrush(QBrush(col_top)); painter.setPen(pen_out)
            painter.drawPolygon(top)
            # dashed centre lines on surface
            painter.setPen(pen_dash)
            painter.drawLine(QPointF(w/2, 0), QPointF(w/2+dx, dy))
            painter.drawLine(QPointF(dx/2, dy/2), QPointF(w+dx/2, dy/2))

            # front edge of tabletop slab
            painter.setBrush(QBrush(col_edge)); painter.setPen(pen_out)
            painter.drawRect(QRectF(0, 0, w, tt))

            # right side edge of slab (isometric)
            side = QPolygonF([QPointF(w,0), QPointF(w+dx,dy),
                              QPointF(w+dx,dy+tt), QPointF(w,tt)])
            painter.setBrush(QBrush(col_dark)); painter.setPen(pen_out)
            painter.drawPolygon(side)

            # 4 legs  (front-left, front-right, back-left, back-right)
            leg_top = tt
            leg_len = max(h, self.leg_px) - tt   # grow with h_in
            painter.setBrush(QBrush(col_leg)); painter.setPen(pen_out)
            painter.drawRect(QRectF(0,       leg_top, lt, leg_len))   # front-left
            painter.drawRect(QRectF(w-lt,    leg_top, lt, leg_len))   # front-right
            painter.setBrush(QBrush(col_dark))
            painter.drawRect(QRectF(dx,      leg_top+int(dy), lt, leg_len))   # back-left
            painter.drawRect(QRectF(w+dx-lt, leg_top+int(dy), lt, leg_len))   # back-right

            # label
            if _item_show_label(self):
                painter.setPen(QColor(50,50,50)); painter.setFont(QFont("Arial",7))
                painter.drawText(QRectF(0, h+4, w, 14), Qt.AlignCenter,
                                 self.custom_name or self.defn["name"])
            if self.isSelected():
                painter.setPen(QPen(QColor("#ff7002"),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush)
                painter.drawRect(self.boundingRect().adjusted(-2,-2,2,2))
            return

        # ── Convection oven: solid box, no legs, door on front face ─────────
        if k=="convection_oven":
            total_h = self.box_h_px + self.leg_px
            col_body  = QColor(90,95,100)
            col_side  = col_body.darker(120)
            col_top   = col_body.lighter(115)
            col_door  = QColor(50,52,56)
            pen_out   = QPen(QColor(60,62,66), 1.2)

            # isometric top face
            top = QPolygonF([QPointF(0,0), QPointF(w,0),
                             QPointF(w+dx,dy), QPointF(dx,dy)])
            painter.setBrush(QBrush(col_top)); painter.setPen(pen_out)
            painter.drawPolygon(top)

            # right side face
            side = QPolygonF([QPointF(w,0), QPointF(w+dx,dy),
                              QPointF(w+dx,dy+total_h), QPointF(w,total_h)])
            painter.setBrush(QBrush(col_side)); painter.setPen(pen_out)
            painter.drawPolygon(side)

            # front face (main body)
            painter.setBrush(QBrush(col_body)); painter.setPen(pen_out)
            painter.drawRect(QRectF(0, 0, w, total_h))

            # door panel (inset on front face)
            door_margin_x = max(4, w*0.08)
            door_margin_t = max(4, total_h*0.06)
            door_margin_b = max(4, total_h*0.10)
            door_w = w - door_margin_x*2
            door_h = total_h - door_margin_t - door_margin_b
            painter.setBrush(QBrush(col_door))
            painter.setPen(QPen(QColor(35,36,40), 1))
            painter.drawRect(QRectF(door_margin_x, door_margin_t, door_w, door_h))

            # door window (small rectangle upper portion of door)
            win_w = door_w * 0.55; win_h = door_h * 0.28
            win_x = door_margin_x + (door_w - win_w)/2
            win_y = door_margin_t + door_h*0.12
            painter.setBrush(QBrush(QColor(30,32,35)))
            painter.setPen(QPen(QColor(80,85,90), 1))
            painter.drawRect(QRectF(win_x, win_y, win_w, win_h))
            # window glare
            painter.setBrush(QBrush(QColor(255,255,255,30))); painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(win_x+2, win_y+2, win_w*0.4, win_h*0.35))

            # door handle (horizontal bar lower portion)
            handle_y = door_margin_t + door_h*0.72
            handle_x1 = door_margin_x + door_w*0.25
            handle_x2 = door_margin_x + door_w*0.75
            painter.setPen(QPen(QColor(160,163,168), 2.5, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(handle_x1, handle_y), QPointF(handle_x2, handle_y))

            # label
            if _item_show_label(self):
                painter.setPen(QColor("#232728")); painter.setFont(QFont("Arial",9,QFont.Bold))
                lbl = self.custom_name or self.defn["name"]
                painter.drawText(QRectF(0, total_h+4, w, 22), Qt.AlignCenter, lbl)
            if self.isSelected():
                painter.setPen(QPen(QColor("#ff7002"),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush)
                painter.drawRect(self.boundingRect().adjusted(-2,-2,2,2))
            return

        draw_box3d(painter,0,0,self.w_px,self.box_h_px,self.d_in,box_col)

        # ── Coloured cooking surface on top face ─────────────────────────────
        surf=QColor(acc); surf.setAlpha(180)
        top_poly=QPolygonF([QPointF(0,0),QPointF(self.w_px,0),
                            QPointF(self.w_px+dx,dy),QPointF(dx,dy)])
        painter.setPen(QPen(acc.darker(140),1)); painter.setBrush(QBrush(surf))
        painter.drawPolygon(top_poly)

        # ── Type-specific surface details ────────────────────────────────────
        face_col=acc.darker(160)

        # Helper: map (u=0..1 left-right, v=0..1 front-back) → screen point on top face
        def tp(u, v): return QPointF(u*w + v*dx, v*dy)

        if k in ("fryer_sm","fryer_md","fryer_lg","henny_penny"):
            # ── Deep fryer ───────────────────────────────────────────────────
            # Reference: tall narrow box; top portion is an open vat recessed
            # below a stainless rim/collar, visible from slightly above.
            #
            # TOP FACE — show the open vat mouth
            rim=0.10          # rim inset fraction
            vat_poly=QPolygonF([tp(rim,rim),tp(1-rim,rim),tp(1-rim,1-rim),tp(rim,1-rim)])
            # Inner vat fill (hot oil amber)
            painter.setBrush(QBrush(QColor(185,130,25,220)))
            painter.setPen(QPen(QColor(220,200,180),1.2))
            painter.drawPolygon(vat_poly)
            # Basket grid on the oil surface
            n_bars=5; n_cols=4
            painter.setPen(QPen(QColor(100,75,15,170),0.9))
            for i in range(1,n_bars):
                t=rim+(1-2*rim)*i/n_bars
                painter.drawLine(tp(rim,t), tp(1-rim,t))
            for j in range(1,n_cols):
                t=rim+(1-2*rim)*j/n_cols
                painter.drawLine(tp(t,rim), tp(t,1-rim))
            # Centre basket handle bar (left–right across vat)
            painter.setPen(QPen(QColor(200,185,150),2.0))
            painter.drawLine(tp(0.5,rim-0.02), tp(0.5,1-rim+0.02))
            # Stainless rim highlight
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(210,215,220),1.8))
            painter.drawPolygon(vat_poly)

            # SIDE FACE — extend right isometric face to floor
            full_h = h + self.leg_px
            side_col = QColor(box_col).darker(130)
            side_poly = QPolygonF([QPointF(w,0), QPointF(w+dx,dy),
                                   QPointF(w+dx, dy+full_h), QPointF(w, full_h)])
            painter.setBrush(QBrush(side_col)); painter.setPen(QPen(side_col.darker(120),1))
            painter.drawPolygon(side_poly)

            # FRONT FACE — extends full height to floor (no legs)
            panel_col=QColor(50,52,55)
            painter.setBrush(QBrush(panel_col)); painter.setPen(QPen(face_col.darker(120),1))
            painter.drawRect(QRectF(3,2,w-6,full_h-4))
            # Thermostat knob (upper portion of panel)
            knob_cx=w/2; knob_cy=h*0.48
            painter.setBrush(QBrush(QColor(220,220,225)))
            painter.setPen(QPen(QColor(90,90,95),1))
            painter.drawEllipse(QPointF(knob_cx,knob_cy),6,6)
            painter.setPen(QPen(QColor(180,30,30),1.8))
            painter.drawLine(QPointF(knob_cx,knob_cy+2),QPointF(knob_cx,knob_cy-4))
            # Power LED (green dot)
            painter.setBrush(QBrush(QColor(30,200,80))); painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(w-9, h*0.35),3,3)

            # Henny Penny: add pressure-lid collar strip on front face
            if k=="henny_penny":
                painter.setBrush(QBrush(QColor(80,85,90)))
                painter.setPen(QPen(face_col,0.8))
                painter.drawRect(QRectF(3,2,w-6,5))   # lid gasket band

        elif k in ("griddle_sm","griddle_lg"):
            # ── Standard griddle — reference: plain wide box, flat cooking top ──
            # Top face already filled with accent colour; add subtle polish sheen
            # (diagonal highlight across the top parallelogram)
            shine=QColor(255,255,255,40)
            painter.setBrush(Qt.NoBrush); painter.setPen(QPen(shine,3,Qt.SolidLine,Qt.RoundCap))
            painter.drawLine(tp(0.08,0.1), tp(0.55,0.1))   # front sheen streak

            # Front face: two horizontal grease-channel lines + knobs at bottom
            painter.setPen(QPen(acc.darker(180),1))
            painter.drawLine(QPointF(4,h*0.40),QPointF(w-4,h*0.40))  # upper channel
            painter.drawLine(QPointF(4,h*0.75),QPointF(w-4,h*0.75))  # lower / grease trough
            # Grease trough fill
            painter.setBrush(QBrush(QColor(80,60,30,140))); painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(4,h*0.75,w-8,h*0.20))
            # Control knobs
            n_knobs=min(6,max(2,int(self.w_in//10)))
            kstep=w/(n_knobs+1)
            for ki in range(n_knobs):
                kx=kstep*(ki+1); ky=h*0.55
                painter.setBrush(QBrush(QColor(55,55,58)))
                painter.setPen(QPen(QColor(30,30,32),0.8))
                painter.drawEllipse(QPointF(kx,ky),4,4)
                painter.setPen(QPen(QColor(200,200,205),1))
                painter.drawLine(QPointF(kx,ky),QPointF(kx,ky-3))   # indicator

        elif k=="clamshell":
            # ── Clamshell griddle — reference: box with hinged upper press-lid ──
            # Main body already drawn. Add the clamshell lid as a second box
            # sitting on top, shown open (tilted back slightly).
            lid_h=max(8,h*0.55)
            lid_col=acc.lighter(120)
            # Lid back face (visible because lid is open/tilted back)
            lid_dx=_ddx(self.d_in*0.85); lid_dy=_ddy(self.d_in*0.85)
            # Lid front face — draw as a parallelogram above the main box top
            lid_top_y = dy - lid_h           # above top face
            lid_poly=QPolygonF([
                QPointF(0,       dy),          # top-face front-left
                QPointF(w,       dy),          # top-face front-right
                QPointF(w+lid_dx, lid_top_y+lid_dy),
                QPointF(lid_dx,   lid_top_y+lid_dy),
            ])
            painter.setBrush(QBrush(lid_col)); painter.setPen(QPen(acc.darker(150),1.2))
            painter.drawPolygon(lid_poly)
            # Lid front edge face
            lid_front=QPolygonF([
                QPointF(0, dy),
                QPointF(w, dy),
                QPointF(w, dy-lid_h*0.35),
                QPointF(0, dy-lid_h*0.35),
            ])
            painter.setBrush(QBrush(lid_col.darker(115)))
            painter.drawPolygon(lid_front)
            # Hinge line at back of main top
            painter.setPen(QPen(acc.darker(170),2))
            painter.drawLine(tp(0.0,0.92), tp(1.0,0.92))
            # Heating element lines on lid underside (barely visible)
            painter.setPen(QPen(QColor(200,60,0,120),1.5))
            for ei in range(3):
                ev=0.25+0.25*ei
                painter.drawLine(tp(0.08,ev), tp(0.92,ev))
            # Front face control knob
            painter.setBrush(QBrush(QColor(55,55,58)))
            painter.setPen(QPen(face_col,0.8))
            painter.drawEllipse(QPointF(w/2,h*0.55),5,5)
            painter.setPen(QPen(QColor(200,200,205),1))
            painter.drawLine(QPointF(w/2,h*0.55),QPointF(w/2,h*0.47))

        elif k=="tilt_skillet":
            # ── Tilt skillet — reference: wide low box, open pan, hinged lid ──
            # Main body is already the wide low box.
            # Show the open tilting pan interior on the top face.
            pan_col=QColor(80,75,70,200)   # dark seasoned steel
            pan_poly=QPolygonF([tp(0.06,0.08),tp(0.94,0.08),tp(0.94,0.92),tp(0.06,0.92)])
            painter.setBrush(QBrush(pan_col)); painter.setPen(QPen(QColor(50,50,48),1.2))
            painter.drawPolygon(pan_poly)
            # Sheen on pan
            painter.setPen(QPen(QColor(150,145,140,90),1.5))
            painter.drawLine(tp(0.08,0.12), tp(0.50,0.12))
            # Two divider shelf lines inside front face (as per reference)
            painter.setPen(QPen(acc.darker(160),1.2))
            painter.drawLine(QPointF(4,h*0.35),QPointF(w-4,h*0.35))
            painter.drawLine(QPointF(4,h*0.68),QPointF(w-4,h*0.68))
            # Tilt handle stub on right side
            handle_col=QColor(180,175,170)
            painter.setBrush(QBrush(handle_col)); painter.setPen(QPen(QColor(100,95,90),1))
            painter.drawRect(QRectF(w-4,h*0.2,8,h*0.25))   # handle block on right
            # Control panel left side (two knobs)
            for ky_f in (0.30, 0.60):
                painter.setBrush(QBrush(QColor(55,55,58)))
                painter.setPen(QPen(face_col,0.8))
                painter.drawEllipse(QPointF(10,h*ky_f),4,4)
                painter.setPen(QPen(QColor(200,200,205),1))
                painter.drawLine(QPointF(10,h*ky_f),QPointF(10,h*ky_f-3))

        elif k.startswith("range_") or k=="range":
            # ── Range: N burner rings on top face + oven door ────────────────
            n_burners = self.defn.get("n_burners", 4)
            cols = min(n_burners, 3) if n_burners <= 6 else (4 if n_burners <= 8 else 5)
            rows = math.ceil(n_burners / cols)
            cw = 1.0/cols; ch = 1.0/rows if rows > 1 else 1.0
            bi = 0
            for row in range(rows):
                for col in range(cols):
                    if bi >= n_burners: break
                    u = (col+0.5)*cw; v = (row+0.5)*ch
                    cp = tp(u, v)
                    for r2, bcol in ((9,QColor(35,35,35)),(6,QColor(50,50,50)),(3,QColor(180,40,0))):
                        painter.setPen(QPen(bcol,1.3)); painter.setBrush(Qt.NoBrush)
                        painter.drawEllipse(cp, r2, r2*0.55)
                    bi += 1
            # Oven door lower half of front face
            painter.setBrush(QBrush(QColor(205,208,212))); painter.setPen(QPen(face_col,1))
            painter.drawRect(QRectF(4, h*0.45, w-8, h*0.50))
            painter.setBrush(QBrush(QColor(75,78,82))); painter.setPen(QPen(face_col,0.8))
            painter.drawRect(QRectF(8, h*0.50, w-16, h*0.38))   # window

        elif k.startswith("combo_"):
            # ── Range+Griddle combo: burners one side, flat plate the other ──
            n_burners  = self.defn.get("n_burners", 4)
            gside      = self.defn.get("griddle_side","right")
            # Burner zone fraction of total width
            brn_frac   = n_burners / (n_burners + 2)   # burners take ~2/3 for 4-brn
            if gside == "right":
                brn_u0, brn_u1 = 0.03, brn_frac
                grd_u0, grd_u1 = brn_frac, 0.97
            else:
                grd_u0, grd_u1 = 0.03, 1.0-brn_frac
                brn_u0, brn_u1 = 1.0-brn_frac, 0.97
            # Divider line on top face
            painter.setPen(QPen(acc.darker(170), 1.5))
            div_u = brn_u1 if gside=="right" else grd_u1
            painter.drawLine(tp(div_u, 0.02), tp(div_u, 0.98))
            # Griddle zone — polished flat surface
            grd_col = QColor(acc).lighter(115); grd_col.setAlpha(200)
            grd_poly = QPolygonF([tp(grd_u0,0.04),tp(grd_u1,0.04),tp(grd_u1,0.96),tp(grd_u0,0.96)])
            painter.setBrush(QBrush(grd_col)); painter.setPen(Qt.NoPen)
            painter.drawPolygon(grd_poly)
            painter.setPen(QPen(QColor(255,255,255,50),2))
            painter.drawLine(tp(grd_u0+0.02,0.10), tp(grd_u1-0.02,0.10))  # sheen
            # Burner rings
            cols = 2; rows = math.ceil(n_burners/cols)
            cw = (brn_u1-brn_u0)/cols; ch_v = 1.0/rows if rows>1 else 1.0
            bi = 0
            for row in range(rows):
                for col in range(cols):
                    if bi >= n_burners: break
                    u = brn_u0 + (col+0.5)*cw; v = (row+0.5)*ch_v
                    cp = tp(u, v)
                    for r2, bcol in ((8,QColor(35,35,35)),(5,QColor(50,50,50)),(3,QColor(180,40,0))):
                        painter.setPen(QPen(bcol,1.2)); painter.setBrush(Qt.NoBrush)
                        painter.drawEllipse(cp, r2, r2*0.55)
                    bi += 1
            # Front face: oven door on the burner side
            bx0 = 3 if gside=="left" else int(w*brn_frac)
            bx1 = int(w*(1-brn_frac)) if gside=="left" else w-3
            painter.setBrush(QBrush(QColor(205,208,212))); painter.setPen(QPen(face_col,1))
            painter.drawRect(QRectF(bx0, h*0.45, bx1-bx0, h*0.50))
            painter.setBrush(QBrush(QColor(75,78,82))); painter.setPen(QPen(face_col,0.8))
            painter.drawRect(QRectF(bx0+4, h*0.50, bx1-bx0-8, h*0.38))

        elif k.startswith("wok"):
            # ── Wok station: 1-5 wok bowls side by side on the top face ─────
            n_woks = self.defn.get("n_woks", 1)
            slot_w = 1.0 / n_woks
            for wi in range(n_woks):
                cu = (wi + 0.5) * slot_w   # centre u of this wok slot
                cv = 0.50
                cp = tp(cu, cv)
                rw = slot_w * w * 0.38   # wok bowl radius x
                rh = rw * 0.55           # isometric foreshortening
                # Outer ring (iron ring)
                painter.setPen(QPen(QColor(30,30,30),2)); painter.setBrush(QBrush(QColor(45,45,45,200)))
                painter.drawEllipse(cp, rw, rh)
                # Inner bowl (dark interior)
                painter.setBrush(QBrush(QColor(25,25,25,230)))
                painter.drawEllipse(cp, rw*0.72, rh*0.72)
                # Ring burner (glowing)
                painter.setPen(QPen(QColor(200,80,0,180),1.5)); painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(cp, rw*0.88, rh*0.88)
            # Front face: one control knob per wok
            for wi in range(n_woks):
                kx = w*(wi+0.5)/n_woks
                painter.setBrush(QBrush(QColor(55,55,58)))
                painter.setPen(QPen(face_col,0.8))
                painter.drawEllipse(QPointF(kx, h*0.55), 4, 4)
                painter.setPen(QPen(QColor(200,200,205),1))
                painter.drawLine(QPointF(kx,h*0.55), QPointF(kx,h*0.46))

        elif k=="soup_stove":
            # ── Soup stove: single large open burner well on top ─────────────
            # Reference: small cube with a large circular opening on top
            cp = tp(0.5, 0.5)
            rx = w*0.38; ry = abs(dy)*0.55 + rx*0.15
            # Dark well interior
            painter.setBrush(QBrush(QColor(20,20,20))); painter.setPen(QPen(QColor(40,40,40),1.5))
            painter.drawEllipse(cp, rx, ry)
            # Cast-iron ring (outer lip)
            painter.setBrush(Qt.NoBrush); painter.setPen(QPen(QColor(60,60,60),3))
            painter.drawEllipse(cp, rx*1.05, ry*1.05)
            # Glowing burner ring inside
            painter.setPen(QPen(QColor(210,90,0,200),2)); painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(cp, rx*0.65, ry*0.65)
            painter.setPen(QPen(QColor(240,150,20,130),1)); painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(cp, rx*0.40, ry*0.40)
            # Front panel
            painter.setBrush(QBrush(QColor(50,52,55))); painter.setPen(QPen(face_col,1))
            painter.drawRect(QRectF(4,2,w-8,h-4))
            painter.setBrush(QBrush(QColor(55,55,58))); painter.setPen(QPen(face_col,0.8))
            painter.drawEllipse(QPointF(w/2, h*0.55), 5, 5)   # single knob
            painter.setPen(QPen(QColor(200,200,205),1))
            painter.drawLine(QPointF(w/2,h*0.55),QPointF(w/2,h*0.44))

        elif k=="bell_10":
            # ── 10" Bell burner: round high-BTU burner with bell/cone shape ──
            cp = tp(0.5, 0.5)
            rx = w*0.40; ry = abs(dy)*0.52 + rx*0.14
            # Outer bell rim — cast iron dark ring
            painter.setBrush(QBrush(QColor(35,35,35))); painter.setPen(QPen(QColor(55,55,55),2))
            painter.drawEllipse(cp, rx, ry)
            # Bell cone rings (concentric, lighter toward center = elevated bell shape)
            painter.setBrush(QBrush(QColor(55,55,60))); painter.setPen(QPen(QColor(70,70,75),1.5))
            painter.drawEllipse(cp, rx*0.78, ry*0.78)
            painter.setBrush(QBrush(QColor(75,75,80))); painter.setPen(QPen(QColor(90,90,95),1.2))
            painter.drawEllipse(cp, rx*0.56, ry*0.56)
            painter.setBrush(QBrush(QColor(95,95,100))); painter.setPen(QPen(QColor(110,110,115),1))
            painter.drawEllipse(cp, rx*0.34, ry*0.34)
            # Center flame aperture
            painter.setBrush(QBrush(QColor(15,15,15))); painter.setPen(Qt.NoPen)
            painter.drawEllipse(cp, rx*0.16, ry*0.16)
            # Glowing flame ring
            painter.setBrush(Qt.NoBrush); painter.setPen(QPen(QColor(220,100,0,200),2))
            painter.drawEllipse(cp, rx*0.25, ry*0.25)
            painter.setPen(QPen(QColor(255,160,30,130),1))
            painter.drawEllipse(cp, rx*0.19, ry*0.19)
            # Front panel
            painter.setBrush(QBrush(QColor(48,50,54))); painter.setPen(QPen(face_col,1))
            painter.drawRect(QRectF(4,2,w-8,h-4))
            painter.setBrush(QBrush(QColor(55,55,58))); painter.setPen(QPen(face_col,0.8))
            painter.drawEllipse(QPointF(w/2, h*0.55), 4, 4)
            painter.setPen(QPen(QColor(200,200,205),1))
            painter.drawLine(QPointF(w/2,h*0.55),QPointF(w/2,h*0.44))

        elif k=="round_griddle":
            # ── Round griddle: cylinder (drum) drawn in isometric ────────────
            # Reference: wide low drum, flat top cooking surface
            top_cx = w/2 + dx/2; top_cy = dy/2
            top_rx = w/2 * 0.95; top_ry = max(8, abs(dy)*0.55 + top_rx*0.12)
            # Top cooking surface — flat polished circle
            cook_col = QColor(acc); cook_col.setAlpha(210)
            painter.setBrush(QBrush(cook_col)); painter.setPen(QPen(acc.darker(160),1.5))
            painter.drawEllipse(QPointF(top_cx, top_cy), top_rx, top_ry)
            # Polish sheen streak
            painter.setPen(QPen(QColor(255,255,255,70),3,Qt.SolidLine,Qt.RoundCap))
            painter.drawLine(QPointF(top_cx-top_rx*0.5, top_cy-top_ry*0.2),
                             QPointF(top_cx+top_rx*0.2, top_cy-top_ry*0.2))
            # Stainless rim ring
            painter.setBrush(Qt.NoBrush); painter.setPen(QPen(QColor(200,205,210),2))
            painter.drawEllipse(QPointF(top_cx, top_cy), top_rx, top_ry)
            # Cylinder side — clip to front-facing rectangle, draw bottom arc
            bot_cy = top_cy + h   # centre of bottom ellipse
            bot_col = acc.darker(130)
            painter.setBrush(QBrush(bot_col)); painter.setPen(QPen(acc.darker(160),1))
            # Draw a clipping path for the front-facing side only
            clip = QPainterPath()
            clip.addRect(QRectF(-2, top_cy, w+4, h+top_ry+2))
            painter.setClipPath(clip)
            painter.drawEllipse(QPointF(top_cx, bot_cy), top_rx, top_ry)
            # Side rectangle connecting top and bottom ellipses
            painter.setBrush(QBrush(acc.darker(115))); painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(top_cx-top_rx, top_cy, top_rx*2, h+1))
            painter.setClipping(False)
            # Re-draw top ellipse on top of the side fill
            painter.setBrush(QBrush(cook_col)); painter.setPen(QPen(acc.darker(160),1.5))
            painter.drawEllipse(QPointF(top_cx, top_cy), top_rx, top_ry)
            painter.setBrush(Qt.NoBrush); painter.setPen(QPen(QColor(200,205,210),2))
            painter.drawEllipse(QPointF(top_cx, top_cy), top_rx, top_ry)
            # Grease drain hole at front
            painter.setBrush(QBrush(QColor(40,35,30))); painter.setPen(QPen(face_col,0.8))
            painter.drawEllipse(QPointF(w/2, h*0.6), 4, 4)

        elif k in ("grillworks_2","grillworks_3"):
            # ── Grillworks Open-Hearth Wood-Fire Charbroiler ──────────────────
            # Distinctive open-top stainless steel unit with an angled cooking
            # chamber. Key visual features:
            #   • Open cooking trough on top — angled, not flat
            #   • Diagonal copper/warm radiant bars running across the surface
            #   • Two large hand-wheel cranks at the back-top corners
            #   • Stainless steel walls; open tubular leg frame
            # Double has slightly more radiant bars than single; triple is wider.
            n_bars = 10 if k.endswith("_2") else 14
            ss      = QColor(195,198,205)   # stainless steel
            ss_dk   = QColor(150,153,160)
            copper  = QColor(184,115,51)    # copper radiant bars
            copper_hi = QColor(210,140,70)
            ember   = QColor(220,90,10,80)  # heat glow between bars

            # ── TOP FACE: open cooking chamber with diagonal copper radiants ──
            clip_top = QPainterPath(); clip_top.addPolygon(top_poly)
            painter.save()
            painter.setClipPath(clip_top)

            # Chamber interior — dark charred background
            painter.setBrush(QBrush(QColor(28,24,20))); painter.setPen(Qt.NoPen)
            painter.drawPolygon(top_poly)

            # Ember/heat glow wash across the surface
            painter.setBrush(QBrush(QColor(180,65,5,55))); painter.setPen(Qt.NoPen)
            painter.drawPolygon(top_poly)

            # Diagonal copper radiant bars — run from u=0..1 at a diagonal v offset
            # They go from bottom-left to top-right across the cooking surface
            painter.setPen(QPen(copper, 2.5, Qt.SolidLine, Qt.RoundCap))
            for bi in range(n_bars):
                t_val = bi / (n_bars - 1)
                # Bar goes diagonally: start at left edge, end at right edge,
                # each bar offset in v so they run parallel at ~30° across face
                v_start = 0.05 + t_val * 0.90
                v_end   = v_start - 0.30   # slant upward toward back-right
                u_start, u_end = 0.02, 0.98
                # Clamp v to visible range — clip handles the rest
                p1 = tp(u_start, max(0.0, v_start))
                p2 = tp(u_end,   max(0.0, v_end))
                # Main bar
                painter.setPen(QPen(copper, 2.2, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(p1, p2)
                # Highlight along top edge of each bar
                painter.setPen(QPen(copper_hi, 0.7, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(p1, p2)

            # Narrow grate rods running perpendicular (cross-hatch, subtle)
            painter.setPen(QPen(QColor(80,82,88,120), 0.8))
            for gi in range(8):
                u = 0.06 + gi * 0.88/7
                painter.drawLine(tp(u, 0.02), tp(u, 0.98))

            painter.restore()

            # Stainless rim around cooking chamber opening (inner lip)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(ss_dk, 1.5))
            painter.drawPolygon(top_poly)

            # ── FRONT FACE: open-front cooking chamber view ───────────────────
            # Stainless lower body panel
            painter.setBrush(QBrush(ss)); painter.setPen(QPen(ss_dk, 1))
            painter.drawRect(QRectF(0, 0, w, h))
            # Open cooking zone visible through front — slanted chamber interior
            cz_x = 6; cz_y = 3; cz_w = w-12; cz_h = h-8
            painter.setBrush(QBrush(QColor(30,26,22))); painter.setPen(QPen(ss_dk,1))
            painter.drawRect(QRectF(cz_x, cz_y, cz_w, cz_h))
            # Copper radiant bars visible from front (diagonal lines inside chamber)
            n_front_bars = n_bars // 2
            painter.setPen(QPen(copper, 1.8))
            for bi in range(n_front_bars):
                t_val = bi / max(n_front_bars-1,1)
                bx = cz_x+3 + t_val*(cz_w-6)
                painter.drawLine(QPointF(bx, cz_y+2), QPointF(bx-6, cz_y+cz_h-2))
            # Ember glow at base of chamber
            painter.setBrush(QBrush(QColor(210,80,5,90))); painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(cz_x+2, cz_y+cz_h*0.65, cz_w-4, cz_h*0.30))

            # Stainless outer rim of chamber
            painter.setBrush(Qt.NoBrush); painter.setPen(QPen(ss.lighter(110),1.5))
            painter.drawRect(QRectF(cz_x, cz_y, cz_w, cz_h))

            # ── Hand-wheel cranks at back top corners ─────────────────────────
            # Drawn in top-face space near back corners (v≈0.1, u≈0.08 and 0.92)
            for u_w in (0.09, 0.91):
                wp = tp(u_w, 0.12)
                # Wheel rim
                painter.setBrush(QBrush(ss_dk)); painter.setPen(QPen(QColor(100,102,108),1.2))
                painter.drawEllipse(wp, 5, 3.5)
                # Wheel spokes
                painter.setPen(QPen(ss_dk, 1.0))
                for ang_d in (0, 60, 120):
                    ar = math.radians(ang_d)
                    painter.drawLine(
                        QPointF(wp.x()+5*math.cos(ar)*0.4, wp.y()+3.5*math.sin(ar)*0.4),
                        QPointF(wp.x()+5*math.cos(ar)*0.9, wp.y()+3.5*math.sin(ar)*0.9))
                # Hub
                painter.setBrush(QBrush(QColor(120,122,128)))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(wp, 1.8, 1.3)

        elif k=="lava_charbroiler":
            # ── Lava Rock Charbroiler ─────────────────────────────────────────
            # Rocks are clipped strictly to the top-face parallelogram so none
            # spill over the edges.
            rock_col_a = QColor(90,60,40,220)
            rock_col_b = QColor(120,80,55,200)
            # Clip painter to the top-face polygon before drawing rocks
            clip_path = QPainterPath(); clip_path.addPolygon(top_poly)
            painter.save()
            painter.setClipPath(clip_path)
            painter.setPen(QPen(QColor(55,35,22),0.8))
            rr = 4
            # Iterate in top-face (u,v) space — guaranteed to stay inside
            nu = max(4, int(w / (rr*2.2)))
            nv = max(3, int(abs(dy) / (rr*1.8)))
            for vi in range(nv):
                for ui in range(nu):
                    u = 0.04 + (ui + (0.5 if vi%2 else 0)) * 0.92 / nu
                    v = 0.06 + vi * 0.88 / max(nv-1,1)
                    if u > 0.98: continue
                    pt_r = tp(u, v)
                    rcol = rock_col_a if (ui+vi)%2==0 else rock_col_b
                    painter.setBrush(QBrush(rcol))
                    painter.drawEllipse(pt_r, rr, rr*0.62)
            painter.restore()
            # Front face: firebox with glow (charcoal/lava)
            painter.setBrush(QBrush(QColor(28,28,28))); painter.setPen(QPen(face_col,1))
            painter.drawRect(QRectF(5,3,w-10,h-6))
            painter.setBrush(QBrush(QColor(195,65,0,120))); painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(7,5,w-14,h-10))

        elif k=="mesq_charbroiler":
            # ── Mesquite Charbroiler ──────────────────────────────────────────
            # Reference: standard box; top face shows heavy grill grates seen
            # from above (dense horizontal bars), and the wood/mesquite chips
            # visible between the bars as a warm brown.
            # Fill between grate bars with mesquite wood colour
            wood_col = QColor(100,65,30,180)
            wood_poly = QPolygonF([tp(0.03,0.03),tp(0.97,0.03),tp(0.97,0.97),tp(0.03,0.97)])
            painter.setBrush(QBrush(wood_col)); painter.setPen(Qt.NoPen)
            painter.drawPolygon(wood_poly)
            # Dense horizontal grate bars (left-right lines at tight spacing)
            n_bars = 12
            painter.setPen(QPen(QColor(28,28,28),2.8,Qt.SolidLine,Qt.RoundCap))
            for i in range(n_bars):
                v = 0.04 + 0.92*i/(n_bars-1)
                painter.drawLine(tp(0.03,v), tp(0.97,v))
            # Bar sheen highlight
            painter.setPen(QPen(QColor(155,155,160,130),0.8))
            for i in range(n_bars):
                v = 0.04 + 0.92*i/(n_bars-1)
                painter.drawLine(tp(0.04,v-0.005), tp(0.96,v-0.005))
            # Front face: firebox with wood-smoke glow
            painter.setBrush(QBrush(QColor(28,28,28))); painter.setPen(QPen(face_col,1))
            painter.drawRect(QRectF(5,3,w-10,h-6))
            painter.setBrush(QBrush(QColor(190,90,20,100))); painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(7,5,w-14,h-10))

        elif k=="elec_charbroiler":
            # ── Radiant Electric Charbroiler ──────────────────────────────────
            # Reference: standard box; top face has evenly-spaced wide stripes
            # (the electric radiant heating panels/elements).
            n_panels = 7
            for i in range(n_panels):
                v0 = i/n_panels
                v1 = v0 + 0.80/n_panels
                # Panel fill (radiant element — glowing warm)
                panel_col = QColor(200,80,10,150) if i%2==0 else QColor(150,55,0,90)
                panel_poly = QPolygonF([tp(0.02,v0),tp(0.98,v0),tp(0.98,v1),tp(0.02,v1)])
                painter.setBrush(QBrush(panel_col)); painter.setPen(Qt.NoPen)
                painter.drawPolygon(panel_poly)
            # Panel divider lines (the frame strips between elements)
            painter.setPen(QPen(QColor(50,50,55),1.5))
            for i in range(1,n_panels):
                v = i/n_panels
                painter.drawLine(tp(0.02,v), tp(0.98,v))
            # Outer element frame
            frame_poly = QPolygonF([tp(0.02,0.02),tp(0.98,0.02),tp(0.98,0.98),tp(0.02,0.98)])
            painter.setBrush(Qt.NoBrush); painter.setPen(QPen(QColor(70,70,75),1.5))
            painter.drawPolygon(frame_poly)
            # Top horizontal sheen lines on each panel
            painter.setPen(QPen(QColor(240,180,120,60),0.8))
            for i in range(n_panels):
                v = i/n_panels + 0.02/n_panels
                painter.drawLine(tp(0.04,v), tp(0.96,v))
            # Front face: electric element visible on face
            painter.setBrush(QBrush(QColor(40,42,48))); painter.setPen(QPen(face_col,1))
            painter.drawRect(QRectF(5,3,w-10,h-6))
            # Horizontal element bars on front face
            n_fe = 5
            painter.setPen(QPen(QColor(200,75,10),1.5))
            for fi in range(n_fe):
                fy = 5 + fi*(h-8)/(n_fe-1)
                painter.drawLine(QPointF(7,fy), QPointF(w-7,fy))

        elif k=="radiant_gas":
            # ── Radiant Gas Charbroiler ───────────────────────────────────────
            # Reference: box with DIAGONAL hatching on top face (\\\\\ pattern)
            # distinguishing it from radiant electric (horizontal) and mesquite.
            # Amber base fill already applied via top_poly.
            # Diagonal lines: travel from top-right to bottom-left in top-face space
            # i.e. u+v = constant lines across the top parallelogram.
            n_diag = 14
            painter.setPen(QPen(QColor(30,30,30),2.2,Qt.SolidLine,Qt.RoundCap))
            for i in range(n_diag*2+1):
                c = (i - n_diag) / n_diag  # ranges -1 to +1
                # line from (0, c) to (1, c-1) clipped to [0,1]²
                u0,v0 = max(0.0, c), max(0.0,-c)
                u1,v1 = min(1.0,1+c), min(1.0,1-c)
                if u0 < u1:
                    painter.drawLine(tp(u0,v0), tp(u1,v1))
            # Sheen on the bars
            painter.setPen(QPen(QColor(160,160,165,120),0.8))
            for i in range(n_diag*2+1):
                c = (i - n_diag) / n_diag + 0.01
                u0,v0 = max(0.0,c), max(0.0,-c)
                u1,v1 = min(1.0,1+c), min(1.0,1-c)
                if u0 < u1:
                    painter.drawLine(tp(u0,v0), tp(u1,v1))
            # Front face: gas firebox with glow
            painter.setBrush(QBrush(QColor(28,28,28))); painter.setPen(QPen(face_col,1))
            painter.drawRect(QRectF(5,3,w-10,h-6))
            painter.setBrush(QBrush(QColor(200,80,0,130))); painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(7,5,w-14,h-10))
            # Gas flame ports (small circles at base of front face)
            n_ports = max(3, int(w//16))
            painter.setBrush(QBrush(QColor(30,180,255,180))); painter.setPen(Qt.NoPen)
            for pi in range(n_ports):
                px = 10 + pi*(w-20)/(n_ports-1)
                painter.drawEllipse(QPointF(px, h-8), 2.5, 2.5)

        elif k=="tandoor_oven":
            # ── Tandoor Oven ──────────────────────────────────────────────────
            # Reference: box with a large clay cylinder (the tandoor pot) inside;
            # top face shows the oval opening of the clay pot; front face shows
            # the cylindrical wall visible through the box opening.
            pot_col = QColor(165,90,45)  # terracotta clay
            # TOP FACE — large oval opening with rim
            cx_top = w/2 + dx/2;  cy_top = dy/2
            or_x = w*0.40;  or_y = max(10, abs(dy)*0.65)
            # Clay rim (outer)
            painter.setBrush(QBrush(pot_col)); painter.setPen(QPen(pot_col.darker(160),1.5))
            painter.drawEllipse(QPointF(cx_top,cy_top), or_x, or_y)
            # Interior opening (dark)
            ir_x = or_x*0.72;  ir_y = or_y*0.72
            painter.setBrush(QBrush(QColor(20,15,10))); painter.setPen(QPen(pot_col.darker(180),1))
            painter.drawEllipse(QPointF(cx_top,cy_top), ir_x, ir_y)
            # Heat glow inside the opening
            painter.setBrush(QBrush(QColor(210,90,10,60))); painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx_top,cy_top), ir_x*0.75, ir_y*0.75)
            # FRONT FACE — cylindrical pot walls visible inside the box
            cyl_x = w*0.12;  cyl_w = w*0.76;  cyl_y = 3;  cyl_h = h-6
            painter.setBrush(QBrush(pot_col.darker(108)))
            painter.setPen(QPen(pot_col.darker(155),1.2))
            painter.drawRect(QRectF(cyl_x, cyl_y, cyl_w, cyl_h))
            # Clay texture — subtle horizontal ring lines on cylinder
            painter.setPen(QPen(pot_col.darker(135),0.7))
            for ri in range(1,5):
                ry = cyl_y + cyl_h*ri/5
                painter.drawLine(QPointF(cyl_x+1,ry), QPointF(cyl_x+cyl_w-1,ry))
            # Cylindrical top curve (oval rim at top of front face)
            painter.setBrush(QBrush(pot_col.lighter(115)))
            painter.setPen(QPen(pot_col.darker(155),1.2))
            painter.drawEllipse(QRectF(cyl_x, cyl_y-6, cyl_w, 12))
            # Heat shimmer dots
            painter.setBrush(QBrush(QColor(230,100,20,80))); painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(w/2, cyl_y+8), cyl_w*0.28, 5)

        elif k=="charbroiler":
            # Ember glow fill on top
            glow_poly=QPolygonF([tp(0.05,0.05),tp(0.95,0.05),tp(0.95,0.95),tp(0.05,0.95)])
            painter.setBrush(QBrush(QColor(220,70,0,70))); painter.setPen(Qt.NoPen)
            painter.drawPolygon(glow_poly)
            # Heavy grate bars left-right across top
            n_grates=6
            painter.setPen(QPen(QColor(30,30,30),2.5,Qt.SolidLine,Qt.RoundCap))
            for i in range(1,n_grates):
                v=0.05+0.90*i/n_grates
                painter.drawLine(tp(0.04,v), tp(0.96,v))
            # Cross-bars front-to-back
            n_cross=max(3,int(self.w_in//8))
            painter.setPen(QPen(QColor(30,30,30),1.2))
            for j in range(1,n_cross):
                u=0.04+0.92*j/n_cross
                painter.drawLine(tp(u,0.04), tp(u,0.96))
            # Grate sheen
            painter.setPen(QPen(QColor(160,160,165,140),0.8))
            for i in range(1,n_grates):
                v=0.05+0.90*i/n_grates
                painter.drawLine(tp(0.05,v-0.01), tp(0.95,v-0.01))
            # Firebox on front face
            painter.setBrush(QBrush(QColor(30,30,30))); painter.setPen(QPen(face_col,1))
            painter.drawRect(QRectF(6,2,w-12,h-4))
            painter.setBrush(QBrush(QColor(200,70,0,160))); painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(8,4,w-16,h-8))

        elif k in ("salamander","cheese_melter"):
            # ── Salamander / Cheese Melter ────────────────────────────────────
            # Reference: wide low box; large rectangular cavity opening on front
            # face with shelf and overhead heating elements
            op_x=6; op_y=4; op_w=w-12; op_h=h-8
            # Cavity interior (dark)
            painter.setBrush(QBrush(QColor(22,22,22))); painter.setPen(QPen(face_col,1.5))
            painter.drawRect(QRectF(op_x, op_y, op_w, op_h))
            # Ambient glow from elements
            glow=QColor(220,90,0,28)
            painter.setBrush(QBrush(glow)); painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(op_x+1, op_y+1, op_w-2, op_h*0.55))
            # Overhead heating elements (3 bars near top of cavity)
            elem_y = op_y + op_h*0.22
            n_elem = max(3, int(op_w//22))
            step_e = op_w / (n_elem+1)
            painter.setPen(QPen(QColor(210,55,0),2.0))
            for ei in range(n_elem):
                ex = op_x+4 + ei*(op_w-8)/(n_elem-1) if n_elem>1 else op_x+op_w/2
                painter.drawLine(QPointF(ex, op_y+3), QPointF(ex, op_y+op_h*0.42))
            # Horizontal shelf / rack bar
            shelf_y = op_y + op_h*0.58
            painter.setPen(QPen(QColor(150,150,158),1.8))
            painter.drawLine(QPointF(op_x+2, shelf_y), QPointF(op_x+op_w-2, shelf_y))
            # Shelf support pins
            n_pins = max(2, int(op_w//30))
            for pi in range(n_pins):
                px = op_x+8 + pi*(op_w-16)/(max(1,n_pins-1))
                painter.drawLine(QPointF(px, shelf_y), QPointF(px, op_y+op_h-2))
            if k=="cheese_melter":
                # Cheese drip / product pan on shelf
                painter.setBrush(QBrush(QColor(220,185,55,160)))
                painter.setPen(QPen(QColor(180,145,30),1))
                painter.drawRect(QRectF(op_x+4, shelf_y+2, op_w-8, op_h*0.35))

        elif k in ("chain_broiler_c","chain_broiler_o"):
            # ── Chain / Conveyor Broiler ──────────────────────────────────────
            # Reference: wide low box; front face shows a horizontal slot with
            # large circular rollers (drive sprockets) at each end and the
            # conveyor belt/chain running between them.
            is_open = k.endswith("_o")
            slot_y = h*0.28; slot_h = h*0.38; slot_x = 4; slot_w = w-8
            roller_r = slot_h * 0.50   # roller fills the slot height

            # Slot background (dark interior)
            painter.setBrush(QBrush(QColor(20,20,20))); painter.setPen(QPen(face_col,1.5))
            painter.drawRect(QRectF(slot_x, slot_y, slot_w, slot_h))
            # Glow inside slot
            painter.setBrush(QBrush(QColor(220,80,0,35))); painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(slot_x+roller_r, slot_y+1, slot_w-2*roller_r, slot_h-2))
            # Chain belt lines (top and bottom strands)
            belt_col = QColor(90,88,80)
            for strand_y in (slot_y+slot_h*0.28, slot_y+slot_h*0.72):
                painter.setPen(QPen(belt_col,1.5,Qt.DashLine))
                painter.drawLine(QPointF(slot_x+roller_r, strand_y),
                                 QPointF(slot_x+slot_w-roller_r, strand_y))
            # Drive rollers (circles at each end of slot)
            for rx, flip in ((slot_x+roller_r, -1), (slot_x+slot_w-roller_r, 1)):
                ry_c = slot_y + slot_h/2
                # Roller body
                painter.setBrush(QBrush(QColor(125,125,130)))
                painter.setPen(QPen(face_col.lighter(120),1.2))
                painter.drawEllipse(QPointF(rx, ry_c), roller_r, roller_r)
                # Roller hub
                painter.setBrush(QBrush(QColor(80,80,85)))
                painter.drawEllipse(QPointF(rx, ry_c), roller_r*0.38, roller_r*0.38)
                # Spoke lines
                painter.setPen(QPen(face_col,0.8))
                for ang in (0, 60, 120):
                    ang_r = math.radians(ang)
                    painter.drawLine(
                        QPointF(rx + roller_r*0.38*math.cos(ang_r), ry_c + roller_r*0.38*math.sin(ang_r)),
                        QPointF(rx + roller_r*0.85*math.cos(ang_r), ry_c + roller_r*0.85*math.sin(ang_r)))
            if is_open:
                # Open-top variant: show the open cavity on the top face
                open_poly = QPolygonF([tp(0.06,0.08),tp(0.94,0.08),tp(0.94,0.92),tp(0.06,0.92)])
                painter.setBrush(QBrush(QColor(20,20,20,200)))
                painter.setPen(QPen(face_col,1))
                painter.drawPolygon(open_poly)
                # Rollers visible from above as isometric ellipses
                for uv, side in ((0.12, "L"),(0.88, "R")):
                    rcp = tp(uv, 0.50)
                    painter.setBrush(QBrush(QColor(125,125,130)))
                    painter.setPen(QPen(face_col,1))
                    painter.drawEllipse(rcp, roller_r*0.6, roller_r*0.35)
                # Chain belt lines across the top
                painter.setPen(QPen(belt_col,1.2,Qt.DashLine))
                for tv in (0.30, 0.70):
                    painter.drawLine(tp(0.12,tv), tp(0.88,tv))

        elif k=="chain_pizza_oven":
            # ── Chain Pizza Oven ──────────────────────────────────────────────
            # Conveyor tunnel (same roller/belt as chain broiler) in the centre,
            # with a flat pizza-catch deck extending from each side.
            deck_w   = w * 0.20          # deck width each side
            tunnel_x = deck_w
            tunnel_w = w - 2 * deck_w
            slot_y   = h * 0.28; slot_h = h * 0.38
            roller_r = slot_h * 0.50

            # Left deck
            deck_col = QColor(185, 182, 175)
            painter.setBrush(QBrush(deck_col)); painter.setPen(QPen(face_col.darker(130), 1.2))
            painter.drawRect(QRectF(0, slot_y - slot_h*0.10, deck_w, slot_h * 1.20))
            # Deck surface lines (pizza rests)
            painter.setPen(QPen(face_col.darker(150), 0.8))
            for ly in (slot_y + slot_h*0.25, slot_y + slot_h*0.60):
                painter.drawLine(QPointF(2, ly), QPointF(deck_w - 2, ly))

            # Right deck
            painter.setBrush(QBrush(deck_col)); painter.setPen(QPen(face_col.darker(130), 1.2))
            painter.drawRect(QRectF(tunnel_x + tunnel_w, slot_y - slot_h*0.10, deck_w, slot_h * 1.20))
            painter.setPen(QPen(face_col.darker(150), 0.8))
            for ly in (slot_y + slot_h*0.25, slot_y + slot_h*0.60):
                painter.drawLine(QPointF(tunnel_x + tunnel_w + 2, ly), QPointF(w - 2, ly))

            # Tunnel slot (dark interior)
            painter.setBrush(QBrush(QColor(20, 20, 20))); painter.setPen(QPen(face_col, 1.5))
            painter.drawRect(QRectF(tunnel_x, slot_y, tunnel_w, slot_h))
            # Glow inside tunnel
            painter.setBrush(QBrush(QColor(220, 80, 0, 35))); painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(tunnel_x + roller_r, slot_y + 1, tunnel_w - 2*roller_r, slot_h - 2))
            # Belt strands
            belt_col = QColor(90, 88, 80)
            for strand_y in (slot_y + slot_h*0.28, slot_y + slot_h*0.72):
                painter.setPen(QPen(belt_col, 1.5, Qt.DashLine))
                painter.drawLine(QPointF(tunnel_x + roller_r, strand_y),
                                 QPointF(tunnel_x + tunnel_w - roller_r, strand_y))
            # Drive rollers
            for rx in (tunnel_x + roller_r, tunnel_x + tunnel_w - roller_r):
                ry_c = slot_y + slot_h / 2
                painter.setBrush(QBrush(QColor(125, 125, 130)))
                painter.setPen(QPen(face_col.lighter(120), 1.2))
                painter.drawEllipse(QPointF(rx, ry_c), roller_r, roller_r)
                painter.setBrush(QBrush(QColor(80, 80, 85)))
                painter.drawEllipse(QPointF(rx, ry_c), roller_r*0.38, roller_r*0.38)
                painter.setPen(QPen(face_col, 0.8))
                for ang in (0, 60, 120):
                    ang_r = math.radians(ang)
                    painter.drawLine(
                        QPointF(rx + roller_r*0.38*math.cos(ang_r), ry_c + roller_r*0.38*math.sin(ang_r)),
                        QPointF(rx + roller_r*0.85*math.cos(ang_r), ry_c + roller_r*0.85*math.sin(ang_r)))

            # Top face: deck surfaces isometric on each side of the tunnel
            deck_frac = deck_w / w
            for u0, u1 in ((0.0, deck_frac), (1.0 - deck_frac, 1.0)):
                deck_poly = QPolygonF([tp(u0, 0.05), tp(u1, 0.05), tp(u1, 0.95), tp(u0, 0.95)])
                painter.setBrush(QBrush(QColor(deck_col).lighter(108))); painter.setPen(QPen(face_col.darker(130), 0.8))
                painter.drawPolygon(deck_poly)

        elif k=="upright_broiler":
            # ── Upright Broiler ───────────────────────────────────────────────
            # Reference: tall narrow box; large rectangular window on the upper
            # front face (the broiling cavity); control panel below.
            win_x=5; win_y=3; win_w=w-10; win_h=h*0.62
            # Cavity (dark interior)
            painter.setBrush(QBrush(QColor(22,22,22))); painter.setPen(QPen(face_col,1.5))
            painter.drawRect(QRectF(win_x, win_y, win_w, win_h))
            # Cavity glow
            painter.setBrush(QBrush(QColor(215,80,0,30))); painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(win_x+1, win_y+1, win_w-2, win_h-2))
            # Top and bottom heating element bars
            painter.setPen(QPen(QColor(215,55,0),2))
            for ey in (win_y+4, win_y+win_h-5):
                painter.drawLine(QPointF(win_x+3, ey), QPointF(win_x+win_w-3, ey))
            # Vertical rack guides
            painter.setPen(QPen(QColor(100,100,108),1))
            for gx in (win_x+win_w*0.25, win_x+win_w*0.75):
                painter.drawLine(QPointF(gx, win_y+4), QPointF(gx, win_y+win_h-4))
            # Control panel below window
            ctrl_y = win_y+win_h+2; ctrl_h = h-win_h-win_y-4
            painter.setBrush(QBrush(QColor(50,52,55))); painter.setPen(QPen(face_col,1))
            painter.drawRect(QRectF(4, ctrl_y, w-8, ctrl_h))
            # Two knobs on control panel
            for kx_f in (0.32, 0.68):
                painter.setBrush(QBrush(QColor(220,220,225)))
                painter.setPen(QPen(QColor(80,80,85),1))
                painter.drawEllipse(QPointF(w*kx_f, ctrl_y+ctrl_h*0.5), 5, 5)
                painter.setPen(QPen(QColor(190,190,195),1.2))
                painter.drawLine(QPointF(w*kx_f,ctrl_y+ctrl_h*0.5),
                                 QPointF(w*kx_f,ctrl_y+ctrl_h*0.18))

        elif k=="gyro":
            # ── Gyro machine ──────────────────────────────────────────────────
            # Reference: tall box; vertical spit rod centered, prominent oval
            # (drip tray / meat base) near bottom. Glass front with heating
            # element on the right side.
            # Glass front panel (light blue tint over the whole face)
            painter.setBrush(QBrush(QColor(180,210,240,55)))
            painter.setPen(QPen(face_col.lighter(130),1))
            painter.drawRect(QRectF(4,3,w-8,h-6))
            # Heating element on right side (vertical coil representation)
            he_x = w-7
            painter.setPen(QPen(QColor(210,55,0),2.0))
            coil_step = max(5,(h-10)/8)
            for ci in range(8):
                cy1=5+ci*coil_step; cy2=cy1+coil_step*0.6
                painter.drawLine(QPointF(he_x-2,cy1),QPointF(he_x+2,cy1+coil_step*0.5))
            # Vertical spit rod (centred, full height, thick chrome rod)
            spit_x = w/2
            painter.setPen(QPen(QColor(200,200,205),3.0))
            painter.drawLine(QPointF(spit_x, 5), QPointF(spit_x, h-5))
            # Meat stack — horizontal layers (wider at bottom, narrower at top)
            meat_top = h*0.15; meat_bot = h*0.68
            n_layers = 10
            for li in range(n_layers):
                t = li/n_layers
                my = meat_top + t*(meat_bot-meat_top)
                mw = w*0.14 + t*w*0.14   # wider toward bottom
                mcol = QColor(175,85,35) if li%2==0 else QColor(145,65,25)
                painter.setBrush(QBrush(mcol)); painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(spit_x,my), mw, mw*0.30)
            # Drip tray / oval base (prominent, like reference)
            tray_y = h*0.72
            painter.setBrush(QBrush(QColor(55,50,45))); painter.setPen(QPen(face_col,1.5))
            painter.drawEllipse(QPointF(spit_x,tray_y), w*0.36, 7)
            # Spit tip detail (top and bottom)
            painter.setBrush(QBrush(QColor(200,200,205))); painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(spit_x,5), 3, 3)
            painter.drawEllipse(QPointF(spit_x,h-5), 3, 3)

        elif k=="ecology_unit":
            n_panels=max(2,int(self.w_in//16)); pw=(w-6)/n_panels
            for pi in range(n_panels):
                px=3+pi*pw
                pcol=QColor(130,140,150) if pi%2==0 else QColor(100,110,118)
                painter.setBrush(QBrush(pcol)); painter.setPen(QPen(QColor(70,80,88),1))
                panel_rect = QRectF(px+1,2,pw-2,h-4)
                painter.drawRect(panel_rect)
                painter.save()
                painter.setClipRect(panel_rect)
                painter.setPen(QPen(QColor(150,160,170,160),0.7))
                for hi in range(int((h+pw)/6)):
                    hx=hi*6
                    painter.drawLine(QPointF(px+1,2+hx), QPointF(px+1+hx,2))
                painter.restore()

        # ── Legs ─────────────────────────────────────────────────────────────
        _no_legs = {"fryer_sm","fryer_md","fryer_lg","henny_penny"}
        if self.defn.get("legs") and self.leg_px and k not in _no_legs:
            h_=self.box_h_px; lh=self.leg_px
            lp=QPen(QColor(120,120,128),2); painter.setPen(lp)
            for cx_,cy_ in [(6,h_),(self.w_px-6,h_),
                             (self.w_px-6+dx,h_+dy),(6+dx,h_+dy)]:
                painter.drawLine(QPointF(cx_,cy_),QPointF(cx_,cy_+lh))
            # Cross-brace
            painter.setPen(QPen(QColor(120,120,128),1))
            painter.drawLine(QPointF(6,h_+lh),QPointF(self.w_px-6,h_+lh))

        # ── Label ─────────────────────────────────────────────────────────────
        if _item_show_label(self):
            painter.setPen(QColor("#232728"))
            painter.setFont(QFont("Arial", 9, QFont.Bold))
            lbl=self.custom_name or self.defn["name"]
            painter.drawText(QRectF(0,self.box_h_px+self.leg_px+4,self.w_px,22),Qt.AlignCenter,lbl)
            if self.scene() and getattr(self.scene(),"show_dimensions",False):
                painter.setPen(QColor("#888")); painter.setFont(QFont("Arial", 7))
                painter.drawText(QRectF(0,self.box_h_px+self.leg_px+26,self.w_px,14),Qt.AlignCenter,
                                 f'{self.w_in:.0f}"W × {self.d_in:.0f}"D × {self.h_in:.0f}"H')
        if self.isSelected():
            painter.setPen(QPen(QColor("#ff7002"),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-2,-2,2,2))

    def itemChange(self, change, value):
        if change==QGraphicsItem.ItemPositionHasChanged and self.scene(): self.scene().update()
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        result=_context_menu_base(self, event, ["Edit Appliance…", "Edit Nozzles…", "Bring to Front", "Send to Back"])
        if result=="Bring to Front":
            sc=self.scene()
            others=[i for i in sc.items() if getattr(i,"ITEM_TYPE","")=="appliance" and i is not self]
            top=max((i.zValue() for i in others), default=1.0)
            self.setZValue(top+1)
            if sc: sc.layout_changed.emit()
            return
        elif result=="Send to Back":
            sc=self.scene()
            others=[i for i in sc.items() if getattr(i,"ITEM_TYPE","")=="appliance" and i is not self]
            bot=min((i.zValue() for i in others), default=1.0)
            self.setZValue(bot-1)
            if sc: sc.layout_changed.emit()
            return
        if result=="Edit Appliance…":
            dlg=ApplianceEditDialog(self)
            if dlg.exec_()==QDialog.Accepted:
                w,d,h,lbl=dlg.values()
                self.prepareGeometryChange()
                self.w_in=w; self.d_in=d; self.h_in=h
                default_name=self.defn["name"]
                self.custom_name=lbl if lbl and lbl!=default_name else None
                sc=self.scene()
                self.update()
                if sc: sc.update(); sc.layout_changed.emit()
        elif result=="Edit Nozzles…":
            if self.app_nozzles:
                nz = self.app_nozzles[0]
                dlg = NozzleEditDialog(nz.nozzle_type, nz.direction)
                if dlg.exec_() == QDialog.Accepted:
                    for nz2 in self.app_nozzles:
                        nz2.nozzle_type = dlg.nozzle_type()
                        nz2.direction   = dlg.direction()
                        nz2.update()
        elif result=="delete":
            sc=self.scene()
            if sc:
                for nz in self.app_nozzles: sc.removeItem(nz)
                sc.removeItem(self); sc.layout_changed.emit()


class AppNozzleItem(QGraphicsItem):
    """Nozzle positioned at pipe level inside the hood — movable and editable."""
    ITEM_TYPE="app_nozzle"
    ARROW_LEN=22

    def __init__(self, nozzle_type="1N", direction="Down ↓"):
        super().__init__()
        self.nozzle_type=nozzle_type; self.direction=direction; self.show_label=True
        self.label_offset=(0.0, 0.0)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable); self.setZValue(3)

    def flow_points(self): return NOZZLE_FLOW.get(self.nozzle_type, 1)

    def _vec(self): return NOZZLE_DIRS.get(self.direction,(0,1))

    def _label_pos(self):
        dx,dy=[v*self.ARROW_LEN for v in self._vec()]
        if dx < -1:
            lx, ly = dx - 62, dy - 8
        elif dx > 1:
            lx, ly = dx + 4, dy - 8
        elif dy < -1:
            lx, ly = dx + 4, dy - 18
        else:
            lx, ly = dx + 4, dy + 4
        return lx + self.label_offset[0], ly + self.label_offset[1]

    def boundingRect(self):
        dx,dy=[v*self.ARROW_LEN for v in self._vec()]
        lx, ly = self._label_pos()
        xs = [0, dx, lx, lx+58]; ys = [0, dy, ly, ly+16]
        pad=6
        return QRectF(min(xs)-pad, min(ys)-pad, max(xs)-min(xs)+pad*2, max(ys)-min(ys)+pad*2)

    def shape(self):
        p=QPainterPath(); p.addRect(self.boundingRect()); return p

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        col = _nozzle_color(self.nozzle_type)
        dx,dy=[v*self.ARROW_LEN for v in self._vec()]
        # Base dot at connection point
        painter.setBrush(QBrush(col)); painter.setPen(Qt.NoPen)
        painter.drawEllipse(-5,-5,10,10)
        # Direction arrow
        draw_arrow(painter,0,0,dx,dy,col,width=3)
        # Label
        if _item_show_label(self):
            lx, ly = self._label_pos()
            painter.setPen(col); painter.setFont(QFont("Arial", 9, QFont.Bold))
            painter.drawText(QRectF(lx,ly,58,16),Qt.AlignLeft,self.nozzle_type)
        if self.isSelected():
            painter.setPen(QPen(QColor("#ff7002"),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect())

    def contextMenuEvent(self, event):
        m=QMenu()
        lbl_act=m.addAction("Hide Label" if getattr(self,"show_label",True) else "Show Label")
        nudge_menu=m.addMenu("Nudge Label")
        nup=nudge_menu.addAction("↑ Up"); ndn=nudge_menu.addAction("↓ Down")
        nlt=nudge_menu.addAction("← Left"); nrt=nudge_menu.addAction("→ Right")
        nudge_menu.addSeparator()
        nrst=nudge_menu.addAction("Reset Position")
        m.addSeparator()
        edit_act=m.addAction("Edit Nozzle…")
        del_act =m.addAction("Delete Nozzle")
        chosen=m.exec_(event.screenPos())
        if chosen==lbl_act: self.show_label=not getattr(self,"show_label",True); self.update()
        elif chosen==nup: self.label_offset=(self.label_offset[0], self.label_offset[1]-8); self.prepareGeometryChange(); self.update()
        elif chosen==ndn: self.label_offset=(self.label_offset[0], self.label_offset[1]+8); self.prepareGeometryChange(); self.update()
        elif chosen==nlt: self.label_offset=(self.label_offset[0]-10, self.label_offset[1]); self.prepareGeometryChange(); self.update()
        elif chosen==nrt: self.label_offset=(self.label_offset[0]+10, self.label_offset[1]); self.prepareGeometryChange(); self.update()
        elif chosen==nrst: self.label_offset=(0.0, 0.0); self.prepareGeometryChange(); self.update()
        elif chosen==edit_act:
            dlg=NozzleEditDialog(self.nozzle_type, self.direction)
            if dlg.exec_()==QDialog.Accepted:
                self.nozzle_type=dlg.nozzle_type(); self.direction=dlg.direction(); self.update()
        elif chosen==del_act:
            sc=self.scene()
            if sc:
                par=self.parentItem()
                if par:
                    if hasattr(par,'app_nozzles'):
                        try: par.app_nozzles.remove(self)
                        except ValueError: pass
                    if hasattr(par,'plenum_nozzles'):
                        try: par.plenum_nozzles.remove(self)
                        except ValueError: pass
                    if hasattr(par, 'duct_nozzles') and self in par.duct_nozzles:
                        par.duct_nozzles.remove(self)
                sc.removeItem(self)
                sc.layout_changed.emit()


class FreeNozzleItem(QGraphicsItem):
    ITEM_TYPE="free_nozzle"
    ARROW_LEN=26
    def __init__(self, nozzle_type="1N", direction="Down ↓"):
        super().__init__()
        self.nozzle_type=nozzle_type; self.direction=direction; self.show_label=True
        self.label_offset=(0.0, 0.0)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable); self.setZValue(3)

    def flow_points(self): return NOZZLE_FLOW.get(self.nozzle_type, 1)

    def _vec(self): return NOZZLE_DIRS.get(self.direction,(0,1))

    def _label_pos(self):
        dx,dy=[v*self.ARROW_LEN for v in self._vec()]
        if dx < -1:
            lx, ly = dx - 62, dy - 8
        elif dx > 1:
            lx, ly = dx + 4, dy - 8
        elif dy < -1:
            lx, ly = dx + 4, dy - 18
        else:
            lx, ly = dx + 4, dy + 4
        return lx + self.label_offset[0], ly + self.label_offset[1]

    def boundingRect(self):
        dx,dy=[v*self.ARROW_LEN for v in self._vec()]
        lx, ly = self._label_pos()
        xs = [0, dx, lx, lx+58]; ys = [0, dy, ly, ly+16]
        pad=6
        return QRectF(min(xs)-pad, min(ys)-pad, max(xs)-min(xs)+pad*2, max(ys)-min(ys)+pad*2)

    def shape(self):
        p=QPainterPath(); p.addRect(self.boundingRect()); return p

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        col = _nozzle_color(self.nozzle_type)
        dx,dy=[v*self.ARROW_LEN for v in self._vec()]
        painter.setBrush(QBrush(col)); painter.setPen(Qt.NoPen)
        painter.drawEllipse(-4,-4,8,8)
        draw_arrow(painter,0,0,dx,dy,col,width=3)
        if _item_show_label(self):
            lx, ly = self._label_pos()
            painter.setPen(col); painter.setFont(QFont("Arial", 9, QFont.Bold))
            painter.drawText(QRectF(lx,ly,58,16),Qt.AlignLeft,self.nozzle_type)
        if self.isSelected():
            painter.setPen(QPen(QColor("#ff7002"),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect())

    def contextMenuEvent(self, event):
        m=QMenu()
        lbl_act=m.addAction("Hide Label" if getattr(self,"show_label",True) else "Show Label")
        nudge_menu=m.addMenu("Nudge Label")
        nup=nudge_menu.addAction("↑ Up"); ndn=nudge_menu.addAction("↓ Down")
        nlt=nudge_menu.addAction("← Left"); nrt=nudge_menu.addAction("→ Right")
        nudge_menu.addSeparator()
        nrst=nudge_menu.addAction("Reset Position")
        m.addSeparator()
        edit_act=m.addAction("Edit Nozzle…")
        m.addSeparator()
        del_act=m.addAction("Delete")
        chosen=m.exec_(event.screenPos())
        if chosen==lbl_act: self.show_label=not getattr(self,"show_label",True); self.update()
        elif chosen==nup: self.label_offset=(self.label_offset[0], self.label_offset[1]-8); self.prepareGeometryChange(); self.update()
        elif chosen==ndn: self.label_offset=(self.label_offset[0], self.label_offset[1]+8); self.prepareGeometryChange(); self.update()
        elif chosen==nlt: self.label_offset=(self.label_offset[0]-10, self.label_offset[1]); self.prepareGeometryChange(); self.update()
        elif chosen==nrt: self.label_offset=(self.label_offset[0]+10, self.label_offset[1]); self.prepareGeometryChange(); self.update()
        elif chosen==nrst: self.label_offset=(0.0, 0.0); self.prepareGeometryChange(); self.update()
        elif chosen==edit_act:
            dlg=NozzleEditDialog(self.nozzle_type, self.direction)
            if dlg.exec_()==QDialog.Accepted:
                self.nozzle_type=dlg.nozzle_type(); self.direction=dlg.direction(); self.update()
        elif chosen==del_act:
            sc=self.scene()
            if sc: sc.removeItem(self)


class BottleItem(QGraphicsItem):
    ITEM_TYPE="bottle"
    def __init__(self, gal=4.0, label="", max_flow=None, mfr_key="kidde"):
        super().__init__()
        self.gal=gal
        self.mfr_key = mfr_key or "kidde"
        # max_flow provided explicitly (from manufacturer-specific tank data)
        # fall back to legacy BOTTLE_FLOW lookup for old save files
        if max_flow is not None:
            self.max_flow = max_flow
        elif gal is not None:
            self.max_flow = BOTTLE_FLOW.get(gal, 11)
        else:
            self.max_flow = 10
        mfr = MANUFACTURERS.get(self.mfr_key, {})
        default_label = (f"{gal} GAL" if gal else f"{self.max_flow} fp")
        self.label = label or default_label
        self.show_label = True
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable); self.setZValue(1)

    def _mfr_color(self):
        return QColor(MANUFACTURERS.get(self.mfr_key,{}).get("color","#aab0bf"))

    def boundingRect(self): return QRectF(0,0,62,150)
    def shape(self):
        p=QPainterPath(); p.addRect(self.boundingRect()); return p

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        col = self._mfr_color()
        draw_bottle(painter,8,4,46,110,col)
        # Manufacturer badge strip on bottle body
        painter.setPen(Qt.NoPen); painter.setBrush(QBrush(col.darker(140)))
        painter.drawRect(QRectF(10,48,42,18))
        mfr_name = MANUFACTURERS.get(self.mfr_key,{}).get("name","")
        painter.setPen(QColor("white")); painter.setFont(QFont("Arial",6,QFont.Bold))
        painter.drawText(QRectF(10,48,42,18),Qt.AlignCenter,mfr_name[:10])
        if _item_show_label(self):
            painter.setPen(QColor("#232728")); painter.setFont(QFont("Arial",7,QFont.Bold))
            painter.drawText(QRectF(0,120,62,16),Qt.AlignCenter,self.label)
            painter.setPen(QColor("#555")); painter.setFont(QFont("Arial",6))
            painter.drawText(QRectF(0,134,62,13),Qt.AlignCenter,f"({self.max_flow} flow pts)")
        if self.isSelected():
            painter.setPen(QPen(QColor("#ff7002"),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-2,-2,2,2))

    def contextMenuEvent(self, event):
        result=_context_menu_base(self,event)
        if result=="delete":
            sc=self.scene()
            if sc: sc.removeItem(self)


CTRL_HEAD_OPTIONS = [
    ("hvac",    "System connected to HVAC"),
    ("facp",    "System connected to building FACP"),
    ("bell",    "System utilizes a local bell"),
    ("visual",  "System utilizes a local visual indicator"),
]

class ControlHeadOptionsDialog(QDialog):
    def __init__(self, current=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Control Head Options")
        self.setMinimumWidth(340)
        l = QVBoxLayout(self)
        l.setSpacing(10); l.setContentsMargins(16,16,16,16)
        l.addWidget(QLabel("Select system connections:"))
        self._checks = {}
        cur = current or {}
        for key, label in CTRL_HEAD_OPTIONS:
            cb = QCheckBox(label)
            cb.setChecked(cur.get(key, False))
            l.addWidget(cb)
            self._checks[key] = cb
        br = QHBoxLayout()
        ok = QPushButton("OK"); ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(cancel); br.addWidget(ok)
        l.addLayout(br)

    def values(self):
        return {k: cb.isChecked() for k, cb in self._checks.items()}


class ControlHeadItem(QGraphicsItem):
    ITEM_TYPE="control_head"
    def __init__(self, options=None):
        super().__init__()
        self.show_label=True
        self.options = options or {}
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable); self.setZValue(1)

    def notes_lines(self):
        lines = []
        for key, label in CTRL_HEAD_OPTIONS:
            if self.options.get(key):
                lines.append(label)
        return lines

    def boundingRect(self): return QRectF(0,0,52,38)
    def shape(self):
        p=QPainterPath(); p.addRect(self.boundingRect()); return p

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        draw_box3d(painter,0,0,50,28,2,QColor(75,95,115))
        painter.setPen(Qt.NoPen); painter.setBrush(QBrush(QColor("#27ae60")))
        painter.drawEllipse(4,4,8,8)
        if _item_show_label(self):
            painter.setPen(QColor("white")); painter.setFont(QFont("Arial",6,QFont.Bold))
            painter.drawText(QRectF(14,2,32,24),Qt.AlignCenter,"CTRL\nHEAD")
        if self.isSelected():
            painter.setPen(QPen(QColor("#ff7002"),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-2,-2,2,2))

    def contextMenuEvent(self, event):
        result=_context_menu_base(self,event,["Edit Options…"])
        if result=="Edit Options…":
            dlg = ControlHeadOptionsDialog(self.options)
            if dlg.exec_() == QDialog.Accepted:
                self.options = dlg.values()
        elif result=="delete":
            sc=self.scene()
            if sc: sc.removeItem(self)


class PullStationItem(QGraphicsItem):
    ITEM_TYPE="pull_station"
    def __init__(self):
        super().__init__()
        self.show_label=True
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable); self.setZValue(1)

    def boundingRect(self): return QRectF(0,0,38,44)
    def shape(self):
        p=QPainterPath(); p.addRect(self.boundingRect()); return p

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        draw_box3d(painter,0,4,36,28,2,QColor(180,30,30))
        painter.setBrush(QBrush(QColor(220,60,60))); painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(8,14,20,8))
        if _item_show_label(self):
            painter.setPen(QColor("white")); painter.setFont(QFont("Arial",6,QFont.Bold))
            painter.drawText(QRectF(0,4,36,12),Qt.AlignCenter,"PULL")
        if self.isSelected():
            painter.setPen(QPen(QColor("#ff7002"),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-2,-2,2,2))

    def contextMenuEvent(self, event):
        result=_context_menu_base(self,event)
        if result=="delete":
            sc=self.scene()
            if sc: sc.removeItem(self)


class AlarmBellItem(QGraphicsItem):
    """Fire alarm notification bell — red dome with yellow label centre."""
    ITEM_TYPE="alarm_bell"
    R=20  # radius

    def __init__(self):
        super().__init__()
        self.show_label=True
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable); self.setZValue(1)

    def boundingRect(self): return QRectF(-self.R-2, -self.R-2, (self.R+2)*2, (self.R+2)*2+12)
    def shape(self):
        p=QPainterPath(); p.addEllipse(QPointF(0,0), self.R+2, self.R+2); return p

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        R=self.R
        # Outer red dome
        grad=QRadialGradient(QPointF(-R*0.3,-R*0.3), R*1.6)
        grad.setColorAt(0, QColor(220,60,50))
        grad.setColorAt(0.6, QColor(185,30,25))
        grad.setColorAt(1, QColor(120,15,10))
        painter.setBrush(QBrush(grad)); painter.setPen(QPen(QColor(90,10,8),1.5))
        painter.drawEllipse(QPointF(0,0), R, R)
        # Highlight sheen
        painter.setBrush(QBrush(QColor(255,255,255,55))); painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(-R*0.28,-R*0.32), R*0.38, R*0.22)
        # Centre label disc (yellow)
        painter.setBrush(QBrush(QColor(230,200,40))); painter.setPen(QPen(QColor(160,130,20),1))
        painter.drawEllipse(QPointF(0,0), R*0.38, R*0.38)
        painter.setPen(QColor(60,40,0)); painter.setFont(QFont("Arial",5,QFont.Bold))
        painter.drawText(QRectF(-R*0.36,-R*0.36,R*0.72,R*0.72), Qt.AlignCenter, "BELL")
        # Label below
        if _item_show_label(self):
            painter.setPen(QColor(40,40,40)); painter.setFont(QFont("Arial",7))
            painter.drawText(QRectF(-R, R+2, R*2, 12), Qt.AlignCenter, "Alarm Bell")
        if self.isSelected():
            painter.setPen(QPen(QColor("#ff7002"),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-2,-2,2,2))

    def contextMenuEvent(self, event):
        result=_context_menu_base(self,event)
        if result=="delete":
            sc=self.scene()
            if sc: sc.removeItem(self); sc.layout_changed.emit()


# ──────────────────────────────────────────────────────────────────────────────
class GasValveItem(QGraphicsItem):
    """Gas shut-off valve symbol — rotatable via right-click menu."""
    ITEM_TYPE = "gas_valve"
    W = 44; H = 28   # bounding box in px

    def __init__(self):
        super().__init__()
        self.show_label = True
        self.label_offset = (0.0, 0.0)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(3)
        self.setTransformOriginPoint(self.W/2, self.H/2)

    def boundingRect(self):
        return QRectF(-2, -2, self.W+4, self.H+16)

    def paint(self, painter, option, widget=None):
        w, h = self.W, self.H
        cx, cy = w/2, h/2
        sel = self.isSelected()
        # Valve body (rectangle)
        body_col = QColor("#c0392b") if not sel else QColor("#e74c3c")
        painter.setBrush(QBrush(body_col))
        painter.setPen(QPen(QColor("#7b241c"), 1.5))
        painter.drawRect(QRectF(6, cy-7, w-12, 14))
        # Pipe stubs left & right
        painter.setBrush(QBrush(QColor("#888")))
        painter.setPen(QPen(QColor("#555"), 1))
        painter.drawRect(QRectF(0, cy-3.5, 8, 7))
        painter.drawRect(QRectF(w-8, cy-3.5, 8, 7))
        # Wheel handle (circle with cross)
        painter.setBrush(QBrush(QColor("#f0c040")))
        painter.setPen(QPen(QColor("#b8860b"), 1.5))
        painter.drawEllipse(QPointF(cx, cy), 8, 8)
        painter.setPen(QPen(QColor("#7a5c00"), 1.5))
        painter.drawLine(QPointF(cx-8, cy), QPointF(cx+8, cy))
        painter.drawLine(QPointF(cx, cy-8), QPointF(cx, cy+8))
        # Label — stays horizontal regardless of rotation
        if _item_show_label(self):
            painter.save()
            rot = self.rotation()
            if rot:
                painter.rotate(-rot)
            lx = self.label_offset[0]
            ly = h + 2 + self.label_offset[1]
            painter.setPen(QPen(QColor("#222")))
            painter.setFont(QFont("Arial", 7, QFont.Bold))
            painter.drawText(QRectF(lx - w/2, ly - h/2, w * 2, 12), Qt.AlignHCenter|Qt.AlignTop, "Gas Valve")
            painter.restore()
        # Selection highlight
        if sel:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#ff7002"), 1.5, Qt.DashLine))
            painter.drawRect(self.boundingRect().adjusted(1,1,-1,-1))

    def contextMenuEvent(self, event):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu()
        lbl_act = menu.addAction("Hide Label" if getattr(self,"show_label",True) else "Show Label")
        nudge_menu = menu.addMenu("Nudge Label")
        nup=nudge_menu.addAction("↑ Up"); ndn=nudge_menu.addAction("↓ Down")
        nlt=nudge_menu.addAction("← Left"); nrt=nudge_menu.addAction("→ Right")
        nudge_menu.addSeparator()
        nrst=nudge_menu.addAction("Reset Position")
        menu.addSeparator()
        r90  = menu.addAction("Rotate 90°")
        r180 = menu.addAction("Rotate 180°")
        r270 = menu.addAction("Rotate 270°")
        menu.addSeparator()
        dele = menu.addAction("Delete")
        act = menu.exec_(event.screenPos())
        if act == lbl_act: self.show_label = not getattr(self,"show_label",True); self.update()
        elif act==nup: self.label_offset=(self.label_offset[0], self.label_offset[1]-8); self.prepareGeometryChange(); self.update()
        elif act==ndn: self.label_offset=(self.label_offset[0], self.label_offset[1]+8); self.prepareGeometryChange(); self.update()
        elif act==nlt: self.label_offset=(self.label_offset[0]-10, self.label_offset[1]); self.prepareGeometryChange(); self.update()
        elif act==nrt: self.label_offset=(self.label_offset[0]+10, self.label_offset[1]); self.prepareGeometryChange(); self.update()
        elif act==nrst: self.label_offset=(0.0, 0.0); self.prepareGeometryChange(); self.update()
        elif act == r90:   self.setRotation((self.rotation()+90)%360)
        elif act == r180: self.setRotation((self.rotation()+180)%360)
        elif act == r270: self.setRotation((self.rotation()+270)%360)
        elif act == dele:
            sc = self.scene()
            if sc: sc.removeItem(self)


# ──────────────────────────────────────────────────────────────────────────────
LINK_TYPES = [
    "165 - ML Style",
    "212 - ML Style",
    "286 - ML Style",
    "360 - ML Style",
    "500 - ML Style",
    "360 - A Style",
    "165 - Standard Thermo-Bulb",
    "212 - Standard Thermo-Bulb",
    "286 - Standard Thermo-Bulb",
    "450 - Standard Thermo-Bulb",
    "500 - Standard Thermo-Bulb",
    "165 - Rapid Thermo-Bulb",
    "212 - Rapid Thermo-Bulb",
    "286 - Rapid Thermo-Bulb",
    "360 - Rapid Thermo-Bulb",
    "500 - Rapid Thermo-Bulb",
    "GLOBE 360 - A Style",
    "GLOBE 135 - K Style",
    "GLOBE 165 - K Style",
    "GLOBE 212 - K Style",
    "GLOBE 280 - K Style",
    "GLOBE 360 - K Style",
    "GLOBE 450 - K Style",
    "GLOBE 165 - ML Style",
    "GLOBE 212 - ML Style",
    "GLOBE 280 - ML Style",
    "GLOBE 360 - ML Style",
    "GLOBE 450 - ML Style",
    "GLOBE 500 - ML Style",
]


class DetectorItem(QGraphicsItem):
    """Fusible link / heat detector — circle symbol with link type label."""
    ITEM_TYPE = "detector"
    def __init__(self, link_type="165 - ML Style"):
        super().__init__()
        self.link_type = link_type
        self.label_offset = (0.0, 0.0)
        self.show_label = True
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(3)

    def _label_pos(self):
        return -30 + self.label_offset[0], 10 + self.label_offset[1]

    def boundingRect(self):
        lx, ly = self._label_pos()
        xs = [-16, 16, lx, lx+60]; ys = [-11, 11, ly, ly+13]
        return QRectF(min(xs)-2, min(ys)-2, max(xs)-min(xs)+4, max(ys)-min(ys)+4)

    def paint(self, painter, option, widget=None):
        sel = self.isSelected()
        W, H = 26, 16   # rounded rect body
        body_col = _detector_color(self.link_type)
        if sel: body_col = body_col.lighter(130)
        painter.setBrush(QBrush(body_col))
        painter.setPen(QPen(body_col.darker(160), 1.5))
        painter.drawRoundedRect(QRectF(-W/2, -H/2, W, H), 4, 4)
        # Two white circles side by side inside the rectangle
        painter.setBrush(QBrush(Qt.white))
        painter.setPen(Qt.NoPen)
        cr = H/2 - 3
        for cx in (-W/4, W/4):
            painter.drawEllipse(QPointF(cx, 0), cr, cr)
        # Label
        if _item_show_label(self):
            lx, ly = self._label_pos()
            painter.setPen(QPen(body_col.darker(120)))
            painter.setFont(QFont("Arial", 6))
            painter.drawText(QRectF(lx, ly, 60, 13), Qt.AlignHCenter|Qt.AlignTop, self.link_type)
        # Selection highlight
        if sel:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#ff7002"), 1.5, Qt.DashLine))
            painter.drawRoundedRect(QRectF(-W/2-2, -H/2-2, W+4, H+4), 4, 4)

    def contextMenuEvent(self, event):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu()
        lbl_act = menu.addAction("Hide Label" if getattr(self,"show_label",True) else "Show Label")
        nudge_menu = menu.addMenu("Nudge Label")
        nup=nudge_menu.addAction("↑ Up"); ndn=nudge_menu.addAction("↓ Down")
        nlt=nudge_menu.addAction("← Left"); nrt=nudge_menu.addAction("→ Right")
        nudge_menu.addSeparator()
        nrst=nudge_menu.addAction("Reset Position")
        menu.addSeparator()
        edit_act = menu.addAction("Edit Link Type…")
        menu.addSeparator()
        dele = menu.addAction("Delete")
        act = menu.exec_(event.screenPos())
        if act == lbl_act: self.show_label = not getattr(self,"show_label",True); self.update()
        elif act==nup: self.label_offset=(self.label_offset[0], self.label_offset[1]-8); self.prepareGeometryChange(); self.update()
        elif act==ndn: self.label_offset=(self.label_offset[0], self.label_offset[1]+8); self.prepareGeometryChange(); self.update()
        elif act==nlt: self.label_offset=(self.label_offset[0]-10, self.label_offset[1]); self.prepareGeometryChange(); self.update()
        elif act==nrt: self.label_offset=(self.label_offset[0]+10, self.label_offset[1]); self.prepareGeometryChange(); self.update()
        elif act==nrst: self.label_offset=(0.0, 0.0); self.prepareGeometryChange(); self.update()
        elif act == edit_act:
            dlg = LinkTypeDialog()
            idx = dlg._cb.findText(self.link_type)
            if idx >= 0: dlg._cb.setCurrentIndex(idx)
            if dlg.exec_() == QDialog.Accepted:
                self.link_type = dlg.link_type(); self.update()
        elif act == dele:
            sc = self.scene()
            if sc: sc.removeItem(self)


class PipeSegmentItem(QGraphicsItem):
    """User-drawn pipe segment — straight or drag-to-curve Bezier."""
    ITEM_TYPE = "pipe_segment"
    HANDLE_R  = 7   # midpoint drag-handle radius in scene px

    def __init__(self, p1, p2, color=None, width=None):
        super().__init__()
        self._p1    = QPointF(p1); self._p2 = QPointF(p2)
        self._curved= False
        self._ctrl  = self._default_ctrl()
        self._hdrag = None       # QPointF: where user last dragged (visual handle pos)
        self._dragging = False
        self._color = color if color else QColor(PIPE_COL)
        self._width = width if width else PIPE_W
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(1.5)

    def _default_ctrl(self):
        mx=(self._p1.x()+self._p2.x())/2; my=(self._p1.y()+self._p2.y())/2
        dx=self._p2.x()-self._p1.x(); dy=self._p2.y()-self._p1.y()
        length=max(1,(dx*dx+dy*dy)**0.5)
        offset=min(55,length*0.35)
        # Always bow downward (positive Y = down in Qt screen coords)
        return QPointF(mx, my + offset)

    def _midpoint(self):
        return QPointF((self._p1.x()+self._p2.x())/2, (self._p1.y()+self._p2.y())/2)

    def _path(self):
        path=QPainterPath(self._p1)
        if self._curved: path.quadTo(self._ctrl, self._p2)
        else: path.lineTo(self._p2)
        return path

    def boundingRect(self):
        pts=[self._p1,self._p2]
        if self._curved: pts.append(self._ctrl)
        if self._hdrag:  pts.append(self._hdrag)
        xs=[p.x() for p in pts]; ys=[p.y() for p in pts]
        pad=max(12, self.HANDLE_R+4)
        return QRectF(min(xs)-pad,min(ys)-pad,max(xs)-min(xs)+pad*2,max(ys)-min(ys)+pad*2)

    def shape(self):
        from PyQt5.QtGui import QPainterPathStroker
        st=QPainterPathStroker(); st.setWidth(max(14, self._width+8))
        return st.createStroke(self._path())

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        col = QColor("#ff7002") if self.isSelected() else self._color
        painter.setPen(QPen(col, self._width, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self._path())
        exporting = getattr(self.scene(), "_exporting", False)
        if not exporting:
            # Endpoint dots
            painter.setPen(Qt.NoPen); painter.setBrush(QBrush(col))
            r = max(3, self._width-1)
            for pt in (self._p1, self._p2): painter.drawEllipse(pt, r, r)
        # Midpoint drag handle
        if not exporting:
            hp = self._hdrag if self._hdrag else self._midpoint()
            if self.isSelected():
                painter.setPen(QPen(QColor("#ff7002"), 2))
                painter.setBrush(QBrush(QColor(255,112,2,90)))
                painter.drawEllipse(hp, self.HANDLE_R, self.HANDLE_R)
                for oy in (-1, 1):
                    tip = QPointF(hp.x(), hp.y() + oy*(self.HANDLE_R+6))
                    painter.setPen(QPen(QColor("#ff7002"), 1.5))
                    painter.drawLine(QPointF(hp.x()-3, hp.y()+oy*self.HANDLE_R),
                                     QPointF(hp.x(),   tip.y()))
                    painter.drawLine(QPointF(hp.x()+3, hp.y()+oy*self.HANDLE_R),
                                     QPointF(hp.x(),   tip.y()))
                if self._curved:
                    painter.setPen(QPen(QColor("#aaa"), 1, Qt.DashLine))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawLine(self._p1, self._ctrl)
                    painter.drawLine(self._p2, self._ctrl)
            else:
                painter.setPen(QPen(self._color.lighter(160), 1))
                painter.setBrush(QBrush(QColor(255,255,255,60)))
                painter.drawEllipse(hp, 5, 5)

    # ── Drag-to-curve: click and drag the midpoint handle ────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            hp = self._hdrag if self._hdrag else self._midpoint()
            delta = event.pos() - hp
            if (delta.x()**2 + delta.y()**2) <= (self.HANDLE_R*2)**2:
                self._dragging = True
                event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            drag = event.pos()
            # Compute quadratic Bezier control point so curve passes through drag at t=0.5
            # B(0.5) = 0.25*p1 + 0.5*ctrl + 0.25*p2 = drag  →  ctrl = 2*drag - 0.5*(p1+p2)
            self._ctrl = QPointF(
                2*drag.x() - 0.5*(self._p1.x()+self._p2.x()),
                2*drag.y() - 0.5*(self._p1.y()+self._p2.y())
            )
            self._hdrag  = drag
            self._curved = True
            self.prepareGeometryChange(); self.update()
            event.accept(); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            event.accept(); return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        m=QMenu()
        curve_act=m.addAction("Make Straight" if self._curved else "Make Curved  (or drag mid-handle)")
        del_act=m.addAction("Delete Pipe")
        chosen=m.exec_(event.screenPos())
        if chosen==curve_act:
            self._curved=not self._curved
            self._hdrag=None
            if self._curved: self._ctrl=self._default_ctrl()
            self.prepareGeometryChange(); self.update()
        elif chosen==del_act:
            sc=self.scene()
            if sc: sc.removeItem(self)


class PipeOverlay(QGraphicsItem):
    ITEM_TYPE="pipe_overlay"
    def __init__(self):
        super().__init__()
        self.setZValue(2)
        self.setFlag(QGraphicsItem.ItemIsSelectable,False)
        self.setFlag(QGraphicsItem.ItemIsMovable,False)
        self.setAcceptedMouseButtons(Qt.NoButton)

    def boundingRect(self): return QRectF(-500,-500,5000,4000)
    def shape(self): return QPainterPath()

    def paint(self, painter, option, widget):
        pass  # Auto-pipe removed — user draws pipes manually


# ═══════════════════════════════════════════════════════════════════════════════
#  Scene
# ═══════════════════════════════════════════════════════════════════════════════

class SuppressionScene(QGraphicsScene):
    layout_changed=pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setSceneRect(-150,-300,4000,2500)
        # NoIndex forces Qt to repaint the full dirty region when items move,
        # eliminating the "ghost trail" artifact when dragging items.
        self.setItemIndexMethod(QGraphicsScene.NoIndex)
        self._mode="select"; self._pending=None; self.show_labels=True; self.show_dimensions=False
        self._active_mfr = "kidde"   # currently-selected design manufacturer
        self.snap_to_grid = False    # toggled by toolbar button
        self.grid_size    = 14      # 2 inches at PX=7 (14 px) — visible snapping, good alignment
        # Pipe-draw state
        self._pipe_draw   = False
        self._pipe_start  = None   # QPointF or None (start of segment being drawn)
        self._pipe_preview= None   # QPointF current mouse position
        self._pipe_color  = QColor(PIPE_COL)
        self._pipe_width  = PIPE_W

    @property
    def active_mfr(self): return self._active_mfr

    def set_active_mfr(self, mk):
        if mk not in MANUFACTURERS or mk == self._active_mfr:
            return
        self._active_mfr = mk
        # Re-apply nozzle types for every placed appliance
        for appl in self.appliances():
            self._refresh_appliance_nozzles(appl, mk)
        # Re-apply plenum nozzle type for every hood
        hood_nz = MFR_HOOD_NOZZLE.get(mk, MFR_HOOD_NOZZLE["kidde"])
        for hood in self.hoods():
            for nz in getattr(hood, "plenum_nozzles", []):
                nz.nozzle_type = hood_nz["plenum"]
                nz.update()
        # Re-apply duct nozzle type for every duct
        for item in self.items():
            if getattr(item, "ITEM_TYPE", "") == "duct":
                for nz in getattr(item, "duct_nozzles", []):
                    nz.nozzle_type = hood_nz["duct"]
                    nz.update()
        self.layout_changed.emit()

    def _refresh_appliance_nozzles(self, appl, mk):
        """Update or replace the child nozzles of an ApplianceItem for manufacturer mk."""
        ed  = effective_defn(appl.key, mk)
        nt  = ed["nt"] or "1N"
        nq  = ed["nq"]
        existing = list(getattr(appl, "app_nozzles", []))

        # Keep vertical position from first existing nozzle (preserves hood alignment)
        if existing:
            nz_local_y = existing[0].pos().y()
        else:
            # fallback — 120 px above appliance origin (no-hood case)
            nz_local_y = -120

        # If only the type changed (same count) — just relabel, keep positions
        if len(existing) == nq:
            for nz in existing:
                nz.nozzle_type = nt
                nz.update()
            return

        # Count changed — remove all and re-place
        for nz in existing:
            self.removeItem(nz)
        appl.app_nozzles = []

        if nq == 0:
            return

        base_defn = APPLIANCE_DEFS.get(appl.key, {})
        nz_layout = base_defn.get("nz_layout")
        if nz_layout == "sides":
            mid_y = appl.leg_px + appl.box_h_px * 0.5
            nz_l = AppNozzleItem(nt, "Right →")
            nz_l.setParentItem(appl)
            nz_l.setPos(-20, mid_y)
            appl.app_nozzles.append(nz_l)
            nz_r = AppNozzleItem(nt, "Left ←")
            nz_r.setParentItem(appl)
            nz_r.setPos(appl.w_px + 20, mid_y)
            appl.app_nozzles.append(nz_r)
        else:
            if   nq == 1: offsets = [0.0]
            elif nq == 2: offsets = [-appl.w_px*0.22,  appl.w_px*0.22]
            elif nq == 3: offsets = [-appl.w_px*0.30, 0.0, appl.w_px*0.30]
            elif nq == 4: offsets = [-appl.w_px*0.34, -appl.w_px*0.11,
                                       appl.w_px*0.11,  appl.w_px*0.34]
            else:         offsets = [appl.w_px*(i/(nq-1)-0.5)*0.70 for i in range(nq)]

            for off in offsets:
                nz = AppNozzleItem(nt, "Down ↓")
                nz.setParentItem(appl)
                nz.setPos(appl.w_px*0.5 + off, nz_local_y)
                appl.app_nozzles.append(nz)
        appl._nozzles_placed = True

    def set_mode_place(self,item_type,spec=None):
        self._mode="place"; self._pending={"type":item_type,"spec":spec or {}}

    def set_mode_select(self):
        self._mode="select"; self._pending=None

    def _hood_pipe_y(self):
        hs=self.hoods()
        return hs[0].pipe_y() if hs else 150

    def add_hood(self, w_in, d_in, label, has_duct, duct_w_in, duct_h_in, zone="Zone 1"):
        n=len(self.hoods())
        hood=HoodItem(w_in,d_in,label,zone); hood.setPos(40+n*25,120+n*18)
        self.addItem(hood)
        # Hood plenum nozzles — evenly spaced, pointing right, children of hood
        hood_nz = MFR_HOOD_NOZZLE.get(self._active_mfr, MFR_HOOD_NOZZLE["kidde"])
        n_nz=hood.flow_points()
        spacing=hood.w_px/(n_nz+1)
        for i in range(n_nz):
            nz=AppNozzleItem(hood_nz["plenum"],"Right →")
            nz.setParentItem(hood)              # moves with hood automatically
            nz.setPos(spacing*(i+1), hood.h_px*0.35)  # local hood coords
            hood.plenum_nozzles.append(nz)
        if has_duct:
            self._create_duct_on_hood(hood,duct_w_in,duct_h_in)
        self.layout_changed.emit()
        return hood

    def _create_duct_on_hood(self, hood, w_in=14, h_in=14):
        duct=DuctItem(w_in,h_in); self.addItem(duct)
        _align_duct_back(hood,duct)
        self._add_duct_nozzles(duct)
        return duct

    def _add_duct_nozzles(self, duct, nozzle_data=None):
        """Add 2 nozzles to a duct. If nozzle_data is given, restore from save."""
        hood_nz = MFR_HOOD_NOZZLE.get(self._active_mfr, MFR_HOOD_NOZZLE["kidde"])
        if nozzle_data:
            for nd in nozzle_data:
                nz=AppNozzleItem(nd.get("nozzle_type", hood_nz["duct"]), nd.get("direction","Up ↑"))
                nz.setParentItem(duct)
                nz.setPos(nd["lx"], nd["ly"])
                if "lbl_off" in nd: nz.label_offset=tuple(nd["lbl_off"])
                duct.duct_nozzles.append(nz)
        else:
            for i in range(2):
                nz=AppNozzleItem(hood_nz["duct"],"Up ↑")
                nz.setParentItem(duct)
                nz.setPos(duct.w_px*(i+1)/3, duct.h_px*0.85)
                duct.duct_nozzles.append(nz)

    def add_duct(self, w_in=14, h_in=14):
        hs=self.hoods()
        duct=DuctItem(w_in,h_in); self.addItem(duct)
        existing=len([i for i in self.items() if getattr(i,"ITEM_TYPE","")=="duct"])
        if hs: _align_duct_back(hs[0],duct,offset_n=existing-1)
        else:  duct.setPos(200,60)
        self._add_duct_nozzles(duct)
        self.layout_changed.emit()

    def _place_at(self, pt):
        sp=self._pending
        if not sp: return
        t=sp["type"]; spec=sp.get("spec",{})
        if t=="appliance":
            item=ApplianceItem(spec["key"],spec["w_in"],spec["d_in"],spec.get("h_in",30),spec.get("name"))
            hs=self.hoods()
            app_y=(hs[0].scenePos().y()+hs[0].h_px+160) if hs else pt.y()
            item.setPos(pt.x()-item.w_px/2, app_y)
            self.addItem(item)
            # Nozzles as children — sit just inside the hood bottom face (or well above appliance if no hood)
            hood_nz_scene = (hs[0].scenePos().y() + hs[0].h_px - 8) if hs else item.scenePos().y() - 120
            nz_local_y = hood_nz_scene - item.scenePos().y()   # negative = above item origin
            defn=effective_defn(spec["key"], self._active_mfr); nq=defn["nq"]; nt=defn["nt"] or "1N"
            base_defn = APPLIANCE_DEFS.get(spec["key"], {})
            nz_layout = base_defn.get("nz_layout")
            if nz_layout == "sides":
                mid_y = item.leg_px + item.box_h_px * 0.5
                nz_l = AppNozzleItem(nt, "Right →")
                nz_l.setParentItem(item)
                nz_l.setPos(-20, mid_y)
                item.app_nozzles.append(nz_l)
                nz_r = AppNozzleItem(nt, "Left ←")
                nz_r.setParentItem(item)
                nz_r.setPos(item.w_px + 20, mid_y)
                item.app_nozzles.append(nz_r)
            else:
                # Spread nozzles evenly across appliance width for any count
                if   nq==1: offsets=[0.0]
                elif nq==2: offsets=[-item.w_px*0.22, item.w_px*0.22]
                elif nq==3: offsets=[-item.w_px*0.30, 0.0, item.w_px*0.30]
                elif nq==4: offsets=[-item.w_px*0.34,-item.w_px*0.11, item.w_px*0.11, item.w_px*0.34]
                else:       offsets=[item.w_px*(i/(nq-1)-0.5)*0.70 for i in range(nq)]
                for off in offsets:
                    nz=AppNozzleItem(nt,"Down ↓")
                    nz.setParentItem(item)
                    nz.setPos(item.w_px*0.5 + off, nz_local_y)
                    item.app_nozzles.append(nz)
            item._nozzles_placed = True
        elif t=="free_nozzle":
            item=FreeNozzleItem(spec.get("nozzle_type","1N"),spec.get("direction","Down ↓"))
            item.setPos(pt)
        elif t=="bottle":
            item=BottleItem(gal=spec.get("gal"), label=spec.get("label",""),
                            max_flow=spec.get("max_flow"), mfr_key=spec.get("mfr_key","kidde"))
            item.setPos(pt)
        elif t=="control_head":
            item=ControlHeadItem(options=spec.get("options")); item.setPos(pt)
        elif t=="pull_station":
            item=PullStationItem(); item.setPos(pt)
        elif t=="alarm_bell":
            item=AlarmBellItem(); item.setPos(pt)
        elif t=="gas_valve":
            item=GasValveItem(); item.setPos(pt)
        elif t=="detector":
            item=DetectorItem(link_type=spec.get("link_type","165 - ML Style")); item.setPos(pt)
        else: return
        if t!="appliance": self.addItem(item)
        self.set_mode_select(); self.layout_changed.emit()

    # ── Pipe-draw helpers ────────────────────────────────────────────────────────

    def _snap_point(self, pt):
        """Return nearest nozzle scene position if within SNAP_RADIUS, else pt."""
        best, best_d = None, SNAP_RADIUS
        for item in self.items():
            if getattr(item,"ITEM_TYPE","") in ("app_nozzle","free_nozzle"):
                sp=item.scenePos()
                d=((sp.x()-pt.x())**2+(sp.y()-pt.y())**2)**0.5
                if d<best_d: best_d,best=d,sp
        return best if best else pt

    @staticmethod
    def _ortho(start, end):
        """Constrain end to horizontal or vertical from start."""
        dx=abs(end.x()-start.x()); dy=abs(end.y()-start.y())
        if dx>=dy: return QPointF(end.x(), start.y())
        return QPointF(start.x(), end.y())

    # ── Mouse / keyboard ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._pipe_draw and event.button()==Qt.LeftButton:
            raw=event.scenePos()
            if self._pipe_start is not None:
                ctrl=event.modifiers()&Qt.ControlModifier
                raw=raw if ctrl else self._ortho(self._pipe_start,raw)
            pt=self._snap_point(raw)
            if self._pipe_start is None:
                self._pipe_start=pt
            else:
                seg=PipeSegmentItem(self._pipe_start, pt,
                                    color=QColor(self._pipe_color),
                                    width=self._pipe_width)
                self.addItem(seg)
                self._pipe_start=pt   # chain: next segment starts here
                self.layout_changed.emit()
            return
        if self._pipe_draw and event.button()==Qt.RightButton:
            self._pipe_start=None; self.update(); return
        if self._mode=="place" and event.button()==Qt.LeftButton:
            self._place_at(event.scenePos()); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pipe_draw:
            self._pipe_preview=event.scenePos()
            # Trigger viewport repaint for crosshair
            for v in self.views(): v.viewport().update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        moved = bool(self.selectedItems())
        # Snap selected movable items to grid after a drag.
        # Snap the item's CENTRE to the grid so that items of different widths
        # placed at the same visual position all snap to the same grid line.
        if self.snap_to_grid and event.button() == Qt.LeftButton:
            g = self.grid_size
            for item in self.selectedItems():
                try:
                    if not (item.flags() & QGraphicsItem.ItemIsMovable):
                        continue
                    p  = item.pos()
                    br = item.boundingRect()
                    cx = p.x() + br.center().x()   # scene centre X
                    cy = p.y() + br.center().y()   # scene centre Y
                    # Y only — snap vertical row alignment but leave X free
                    # so adjacent appliances don't overlap each other.
                    # Snap pos().y() directly (not center) so items placed on
                    # the same hood row always share the same snap line regardless
                    # of their individual depth/height.
                    item.setPos(p.x(), round(p.y() / g) * g)
                except Exception:
                    pass
        # Always notify on mouse-up with selection — items may have moved,
        # which needs to update clearance warnings and the system panel.
        if moved and event.button() == Qt.LeftButton:
            self.layout_changed.emit()

    def keyPressEvent(self, event):
        if event.key()==Qt.Key_Escape:
            if self._pipe_draw and self._pipe_start is not None:
                self._pipe_start=None; self.update()
            else:
                self.set_mode_select()
        elif event.key()==Qt.Key_A and event.modifiers()==Qt.ControlModifier:
            for item in self.items():
                if getattr(item,"ITEM_TYPE","") not in ("","pipe_overlay") and not item.parentItem():
                    item.setSelected(True)
        elif event.key()==Qt.Key_Delete:
            for item in list(self.selectedItems()):
                it=getattr(item,"ITEM_TYPE","")
                if it in ("","pipe_overlay"): continue
                if not item.scene(): continue
                # Clean up parent back-references for nozzles
                if it=="app_nozzle":
                    par=item.parentItem()
                    if par:
                        if hasattr(par,'app_nozzles'):
                            try: par.app_nozzles.remove(item)
                            except ValueError: pass
                        if hasattr(par,'plenum_nozzles'):
                            try: par.plenum_nozzles.remove(item)
                            except ValueError: pass
                        if hasattr(par, 'duct_nozzles') and item in par.duct_nozzles:
                            par.duct_nozzles.remove(item)
                self.removeItem(item)  # children (nozzles) auto-removed with parent
            self.layout_changed.emit()
        super().keyPressEvent(event)

    def hoods(self):      return [i for i in self.items() if getattr(i,"ITEM_TYPE","")=="hood"]
    def appliances(self): return [i for i in self.items() if getattr(i,"ITEM_TYPE","")=="appliance"]
    def bottles(self):    return [i for i in self.items() if getattr(i,"ITEM_TYPE","")=="bottle"]
    def bottle_capacity(self): return sum(b.max_flow for b in self.bottles())

    def total_flow(self):
        f = 0.0
        for a in self.appliances():
            if a._nozzles_placed:
                f += sum(nz.flow_points() for nz in a.app_nozzles)
            else:
                f += effective_defn(a.key, self._active_mfr)["flow"]
        # hood plenum nozzles
        for h in self.hoods():
            f+=sum(nz.flow_points() for nz in h.plenum_nozzles)
        # duct nozzles
        for item in self.items():
            if getattr(item,"ITEM_TYPE","")=="duct":
                f+=sum(nz.flow_points() for nz in getattr(item,"duct_nozzles",[]))
        # free-standing nozzles
        f+=sum(i.flow_points() for i in self.items() if getattr(i,"ITEM_TYPE","")=="free_nozzle")
        return round(f, 2)

    def restricted_systems(self):
        bad=set()
        for a in self.appliances(): bad.update(a.defn.get("r",[]))
        return bad

    def recommendation(self,mk):
        mfr=MANUFACTURERS[mk]
        if mk in self.restricted_systems():
            return {"compatible":False,"reason":mfr["bad_reason"],"total_flow":self.total_flow()}
        # Compute flow using actual placed nozzles (same logic as total_flow)
        flow = 0.0
        for a in self.appliances():
            if a._nozzles_placed:
                flow += sum(nz.flow_points() for nz in a.app_nozzles)
            else:
                flow += effective_defn(a.key, mk)["flow"]
        for h in self.hoods():
            flow += sum(nz.flow_points() for nz in h.plenum_nozzles)
        for item in self.items():
            if getattr(item, "ITEM_TYPE", "") == "duct":
                flow += sum(nz.flow_points() for nz in getattr(item, "duct_nozzles", []))
        flow += sum(i.flow_points() for i in self.items() if getattr(i, "ITEM_TYPE", "") == "free_nozzle")
        flow = round(flow, 2)
        tanks=mfr["tanks"]
        ok=[t for t in tanks if t["max_flow"]>=flow]
        if not ok:
            big=tanks[-1]; n=math.ceil(flow/big["max_flow"])
            return {"compatible":True,"total_flow":flow,"tank":big,"tanks_needed":n,"margin_pct":0,"over_capacity":True,"alternatives":[]}
        best=ok[0]; margin=(best["max_flow"]-flow)/best["max_flow"]*100
        return {"compatible":True,"total_flow":flow,"tank":best,"tanks_needed":1,"margin_pct":margin,"over_capacity":False,"alternatives":ok[1:]}

    # ── Serialisation ────────────────────────────────────────────────────────
    def to_dict(self):
        """Return a JSON-serialisable dict of every scene item."""
        out = []
        for item in self.items():
            t = getattr(item, "ITEM_TYPE", "")
            if t == "hood":
                pnozzles = []
                for nz in getattr(item,"plenum_nozzles",[]):
                    pnozzles.append({"nozzle_type":nz.nozzle_type,"direction":nz.direction,
                                     "lx":nz.pos().x(),"ly":nz.pos().y(),
                                     "lbl_off":list(getattr(nz,"label_offset",(0,0)))})
                out.append({"type":"hood","x":item.x(),"y":item.y(),
                             "w_in":item.w_in,"d_in":item.d_in,"label":item.label,
                             "zone":getattr(item,"zone","Zone 1"),
                             "nozzles":pnozzles})
            elif t == "duct":
                nozzles=[{"nozzle_type":nz.nozzle_type,"direction":nz.direction,
                          "lx":nz.pos().x(),"ly":nz.pos().y(),
                          "lbl_off":list(getattr(nz,"label_offset",(0,0)))}
                         for nz in getattr(item,"duct_nozzles",[])]
                out.append({"type":"duct","x":item.x(),"y":item.y(),
                             "w_in":item.w_in,"h_in":item.h_in,"nozzles":nozzles})
            elif t == "appliance":
                nozzles = []
                for nz in getattr(item,"app_nozzles",[]):
                    nozzles.append({"nozzle_type":nz.nozzle_type,
                                    "direction":nz.direction,
                                    "lx":nz.pos().x(),"ly":nz.pos().y(),
                                    "lbl_off":list(getattr(nz,"label_offset",(0,0)))})
                out.append({"type":"appliance","key":item.key,
                             "w_in":item.w_in,"d_in":item.d_in,"h_in":item.h_in,
                             "name":item.custom_name,
                             "x":item.x(),"y":item.y(),
                             "z":item.zValue(),
                             "nozzles":nozzles})
            elif t == "free_nozzle":
                out.append({"type":"free_nozzle","x":item.x(),"y":item.y(),
                             "nozzle_type":item.nozzle_type,"direction":item.direction,
                             "lbl_off":list(getattr(item,"label_offset",(0,0)))})
            elif t == "bottle":
                out.append({"type":"bottle","x":item.x(),"y":item.y(),
                             "gal":item.gal,"max_flow":item.max_flow,
                             "mfr_key":item.mfr_key,"label":item.label})
            elif t == "control_head":
                out.append({"type":"control_head","x":item.x(),"y":item.y(),
                             "options":item.options})
            elif t == "pull_station":
                out.append({"type":"pull_station","x":item.x(),"y":item.y()})
            elif t == "alarm_bell":
                out.append({"type":"alarm_bell","x":item.x(),"y":item.y()})
            elif t == "gas_valve":
                out.append({"type":"gas_valve","x":item.x(),"y":item.y(),
                             "rotation":item.rotation(),
                             "lbl_off":list(getattr(item,"label_offset",(0,0)))})
            elif t == "detector":
                out.append({"type":"detector","x":item.x(),"y":item.y(),
                             "link_type":getattr(item,"link_type","165 - ML Style"),
                             "lbl_off":list(getattr(item,"label_offset",(0,0)))})
            elif t == "pipe_segment":
                out.append({"type":"pipe_segment",
                             "x1":item._p1.x(),"y1":item._p1.y(),
                             "x2":item._p2.x(),"y2":item._p2.y(),
                             "curved":item._curved,
                             "ctrl_x":item._ctrl.x(),"ctrl_y":item._ctrl.y(),
                             "color":item._color.name(),"width":item._width})
        return out

    def load_dict(self, data):
        """Clear the scene and reconstruct all items from a serialised dict."""
        # Remove everything except the pipe overlay
        for item in list(self.items()):
            if getattr(item,"ITEM_TYPE","") not in ("","pipe_overlay"):
                self.removeItem(item)
        for d in data:
            t = d.get("type")
            if t == "hood":
                item = HoodItem(d["w_in"], d["d_in"], d.get("label","Hood"), d.get("zone","Zone 1"))
                item.setPos(d["x"], d["y"]); self.addItem(item)
                saved_pnz = d.get("nozzles")
                if saved_pnz:
                    for nz_d in saved_pnz:
                        nz = AppNozzleItem(nz_d["nozzle_type"], nz_d["direction"])
                        nz.setParentItem(item)
                        nz.setPos(nz_d["lx"], nz_d["ly"])
                        if "lbl_off" in nz_d: nz.label_offset=tuple(nz_d["lbl_off"])
                        item.plenum_nozzles.append(nz)
                else:
                    hood_nz = MFR_HOOD_NOZZLE.get(self._active_mfr, MFR_HOOD_NOZZLE["kidde"])
                    n_nz=item.flow_points()
                    spacing=item.w_px/(n_nz+1)
                    for i in range(n_nz):
                        nz=AppNozzleItem(hood_nz["plenum"],"Right →")
                        nz.setParentItem(item)
                        nz.setPos(spacing*(i+1), item.h_px*0.35)
                        item.plenum_nozzles.append(nz)
            elif t == "duct":
                item = DuctItem(d["w_in"], d["h_in"])
                item.setPos(d["x"], d["y"]); self.addItem(item)
                saved_nz = d.get("nozzles")
                self._add_duct_nozzles(item, nozzle_data=saved_nz if saved_nz else None)
            elif t == "appliance":
                item = ApplianceItem(d["key"], d["w_in"], d["d_in"],
                                     d.get("h_in",30), d.get("name"))
                item.setPos(d["x"], d["y"]); self.addItem(item)
                if "z" in d: item.setZValue(d["z"])
                for nz_d in d.get("nozzles",[]):
                    nz = AppNozzleItem(nz_d["nozzle_type"], nz_d["direction"])
                    nz.setParentItem(item)
                    nz.setPos(nz_d["lx"], nz_d["ly"])
                    if "lbl_off" in nz_d: nz.label_offset=tuple(nz_d["lbl_off"])
                    item.app_nozzles.append(nz)
                if d.get("nozzles") is not None:
                    item._nozzles_placed = True
            elif t == "free_nozzle":
                item = FreeNozzleItem(d["nozzle_type"], d["direction"])
                if "lbl_off" in d: item.label_offset=tuple(d["lbl_off"])
                item.setPos(d["x"], d["y"]); self.addItem(item)
            elif t == "bottle":
                item = BottleItem(d.get("gal",4.0),
                                  label=d.get("label",""),
                                  max_flow=d.get("max_flow"),
                                  mfr_key=d.get("mfr_key","kidde"))
                item.setPos(d["x"], d["y"]); self.addItem(item)
            elif t == "control_head":
                item = ControlHeadItem(options=d.get("options")); item.setPos(d["x"],d["y"]); self.addItem(item)
            elif t == "pull_station":
                item = PullStationItem(); item.setPos(d["x"],d["y"]); self.addItem(item)
            elif t == "alarm_bell":
                item = AlarmBellItem(); item.setPos(d["x"],d["y"]); self.addItem(item)
            elif t == "gas_valve":
                item = GasValveItem(); item.setPos(d["x"],d["y"])
                item.setRotation(d.get("rotation",0))
                if "lbl_off" in d: item.label_offset=tuple(d["lbl_off"])
                self.addItem(item)
            elif t == "detector":
                item = DetectorItem(link_type=d.get("link_type","165 - ML Style"))
                if "lbl_off" in d: item.label_offset=tuple(d["lbl_off"])
                item.setPos(d["x"],d["y"]); self.addItem(item)
            elif t == "pipe_segment":
                item = PipeSegmentItem(
                    QPointF(d["x1"],d["y1"]), QPointF(d["x2"],d["y2"]),
                    color=QColor(d.get("color","#1e64b4")), width=d.get("width",3))
                item._curved = d.get("curved",False)
                item._ctrl   = QPointF(d.get("ctrl_x",0),d.get("ctrl_y",0))
                self.addItem(item)
        self.layout_changed.emit()


# ═══════════════════════════════════════════════════════════════════════════════
#  Canvas
# ═══════════════════════════════════════════════════════════════════════════════

class SuppressionCanvas(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor("white")))
        self.setStyleSheet("border:1px solid #ccc;")
        # FullViewportUpdate repaints the entire viewport on every change,
        # eliminating ghost/trail artifacts when items are dragged.
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self._panning   = False
        self._pan_start = None

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        sc = self.scene()
        if not sc or not getattr(sc, 'snap_to_grid', False):
            return
        g = getattr(sc, 'grid_size', 42)
        painter.setPen(QPen(QColor(220, 220, 230), 0.5, Qt.DotLine))
        l = int(rect.left())  - (int(rect.left())  % g) - g
        t = int(rect.top())   - (int(rect.top())   % g) - g
        x = l
        while x <= rect.right() + g:
            painter.drawLine(x, int(rect.top()-g), x, int(rect.bottom()+g)); x += g
        y = t
        while y <= rect.bottom() + g:
            painter.drawLine(int(rect.left()-g), y, int(rect.right()+g), y); y += g

    def wheelEvent(self,e):
        f=1.15 if e.angleDelta().y()>0 else 1/1.15; self.scale(f,f)

    def mousePressEvent(self,e):
        pipe_mode = getattr(self.scene(),'_pipe_draw',False)
        # Middle-click always pans; Ctrl+LeftDrag pans when NOT in pipe-draw mode
        if e.button()==Qt.MiddleButton or (
                e.button()==Qt.LeftButton and
                (e.modifiers() & Qt.ControlModifier) and
                not pipe_mode):
            self._panning=True; self._pan_start=e.pos()
            self.setCursor(Qt.ClosedHandCursor); return
        super().mousePressEvent(e)

    def mouseMoveEvent(self,e):
        if self._panning and self._pan_start:
            d=e.pos()-self._pan_start; self._pan_start=e.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()-d.y()); return
        if getattr(self.scene(),'_pipe_draw',False):
            self.viewport().update()   # keep crosshair/preview fresh
        super().mouseMoveEvent(e)

    def drawForeground(self, painter, rect):
        """Draw crosshair and pipe-preview overlay in viewport coords."""
        sc=self.scene()
        if not getattr(sc,'_pipe_draw',False): return
        preview=getattr(sc,'_pipe_preview',None)
        if preview is None: return

        vpt=self.mapFromScene(preview)
        vw=self.viewport().width(); vh=self.viewport().height()

        painter.save()
        painter.resetTransform()   # switch to viewport (pixel) coordinates

        # Full-canvas crosshair
        pen=QPen(QColor(60,120,200,90),1,Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(0,int(vpt.y()),vw,int(vpt.y()))
        painter.drawLine(int(vpt.x()),0,int(vpt.x()),vh)

        # Pipe preview line from _pipe_start to current position
        start=getattr(sc,'_pipe_start',None)
        if start is not None:
            vstart=self.mapFromScene(start)
            ctrl=QApplication.keyboardModifiers()&Qt.ControlModifier
            if not ctrl:
                dx=abs(preview.x()-start.x()); dy=abs(preview.y()-start.y())
                end_scene=QPointF(preview.x(),start.y()) if dx>=dy else QPointF(start.x(),preview.y())
            else:
                end_scene=preview
            vend=self.mapFromScene(end_scene)
            painter.setPen(QPen(PIPE_COL,2,Qt.DashLine))
            painter.drawLine(int(vstart.x()),int(vstart.y()),int(vend.x()),int(vend.y()))
            # Start-point dot
            painter.setPen(Qt.NoPen); painter.setBrush(QBrush(PIPE_COL))
            painter.drawEllipse(int(vstart.x())-4,int(vstart.y())-4,8,8)

        # Snap indicator ring
        snapped=sc._snap_point(preview)
        if (snapped.x()!=preview.x() or snapped.y()!=preview.y()):
            vs=self.mapFromScene(snapped)
            painter.setPen(QPen(QColor("#ff7002"),2)); painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(int(vs.x())-9,int(vs.y())-9,18,18)

        painter.restore()

    def mouseReleaseEvent(self,e):
        if e.button() in (Qt.MiddleButton, Qt.LeftButton) and self._panning:
            self._panning=False; self.setCursor(Qt.ArrowCursor); return
        super().mouseReleaseEvent(e)

    def fit_all(self):
        items=[i for i in self.scene().items() if getattr(i,"ITEM_TYPE","") not in ("","pipe_overlay") and i.parentItem() is None]
        if not items: return
        r=items[0].sceneBoundingRect()
        for i in items[1:]: r=r.united(i.sceneBoundingRect())
        self.fitInView(r.adjusted(-60,-60,120,120),Qt.KeepAspectRatio)


# ═══════════════════════════════════════════════════════════════════════════════
#  Left palette
# ═══════════════════════════════════════════════════════════════════════════════

class AppliancePalette(QWidget):
    appliance_clicked = pyqtSignal(str)
    equip_clicked     = pyqtSignal(str)

    # Style constants
    _HDR_STYLE = ("QPushButton{background:#3a3d3e;color:#efe6e1;border:none;"
                  "border-radius:3px;padding:4px 2px;font-size:10px;font-weight:bold;"
                  "text-align:left;padding-left:6px;}"
                  "QPushButton:hover{background:#555;}"
                  "QPushButton:checked{background:#2c2f30;color:#ff7002;"
                  "border-left:3px solid #ff7002;}")

    def __init__(self):
        super().__init__()
        self.setFixedWidth(138)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scrollable inner panel
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:#f5f0ec;}"
                             "QScrollBar:vertical{width:8px;background:#e0d8d2;}"
                             "QScrollBar::handle:vertical{background:#aaa;border-radius:4px;}"
                             "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0px;}")
        inner = QWidget(); inner.setStyleSheet("background:#f5f0ec;")
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        self._btns  = {}   # appliance key → QPushButton
        self._ebtns = {}   # equip key → QPushButton

        # ── Top-level "Appliances" header (non-collapsible label) ──────────
        lbl = QLabel("Appliances")
        lbl.setStyleSheet("font-weight:bold;font-size:10px;color:#232728;"
                          "background:#c8bfb8;padding:3px;border-radius:3px;")
        lbl.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(lbl)

        # ── Collapsible appliance groups ───────────────────────────────────
        for grp_name, keys in APPLIANCE_GROUPS:
            self._add_group(grp_name, keys)

        # ── Equipment section ──────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#ccc;margin-top:4px;margin-bottom:2px;")
        self._layout.addWidget(sep)
        lbl2 = QLabel("Equipment")
        lbl2.setStyleSheet("font-weight:bold;font-size:10px;color:#232728;"
                           "background:#c8bfb8;padding:3px;border-radius:3px;")
        lbl2.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(lbl2)

        equip_items = [
            ("nozzle",       "Nozzle",      "#2980b9"),
            ("bottle",       "Bottle",      "#7f8c8d"),
            ("control_head", "Ctrl Head",   "#1a5276"),
            ("pull_station", "Pull Stn",    "#c0392b"),
            ("alarm_bell",   "Alarm Bell",  "#c0392b"),
            ("gas_valve",    "Gas Valve",   "#c0392b"),
            ("detector",     "Detector",    "#1a472a"),
        ]
        for key, lbl_txt, col in equip_items:
            c = QColor(col)
            btn = QPushButton(lbl_txt); btn.setCheckable(True)
            btn.setStyleSheet(
                f"QPushButton{{background:{col};color:white;border-radius:4px;"
                f"padding:4px 2px;font-size:10px;font-weight:bold;}}"
                f"QPushButton:checked{{border:3px solid #ff7002;}}"
                f"QPushButton:hover{{background:{c.lighter(115).name()};}}")
            btn.clicked.connect(lambda chk, k=key: self._on_equip(k, chk))
            self._layout.addWidget(btn)
            self._ebtns[key] = btn

        tip = QLabel("Click group ▶ to expand\n\nClick item then\nclick canvas\n\nRight-click options\nDel = remove")
        tip.setStyleSheet("font-size:9px;color:#888;margin-top:6px;")
        tip.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(tip)
        self._layout.addStretch()

    def _add_group(self, name, keys):
        """Add a collapsible group header + button container."""
        # Filter to keys that actually exist
        valid_keys = [k for k in keys if k in APPLIANCE_DEFS]
        if not valid_keys:
            return

        # Toggle header button
        hdr = QPushButton(f"▶ {name}")
        hdr.setCheckable(True)
        hdr.setChecked(False)
        hdr.setStyleSheet(self._HDR_STYLE)
        self._layout.addWidget(hdr)

        # Container widget for the appliance buttons in this group
        container = QWidget()
        container.setStyleSheet("background:#f5f0ec;")
        clay = QVBoxLayout(container)
        clay.setContentsMargins(4, 0, 0, 2)
        clay.setSpacing(2)
        container.setVisible(False)   # collapsed by default

        for key in valid_keys:
            d = APPLIANCE_DEFS[key]
            c = QColor(d["color"])
            btn = QPushButton(d["label"]); btn.setCheckable(True)
            btn.setStyleSheet(
                f"QPushButton{{background:{d['color']};color:white;border-radius:4px;"
                f"padding:4px 2px;font-size:10px;font-weight:bold;}}"
                f"QPushButton:checked{{border:3px solid #ff7002;}}"
                f"QPushButton:hover{{background:{c.lighter(115).name()};}}")
            btn.clicked.connect(lambda chk, k=key: self._on_app(k, chk))
            clay.addWidget(btn)
            self._btns[key] = btn

        self._layout.addWidget(container)

        # Wire toggle
        def _toggle(checked, h=hdr, ct=container, n=name):
            ct.setVisible(checked)
            h.setText(f"{'▼' if checked else '▶'} {n}")
        hdr.toggled.connect(_toggle)

    def _on_app(self, key, checked):
        for k, b in {**self._btns, **self._ebtns}.items():
            if k != key: b.setChecked(False)
        self.appliance_clicked.emit(key if checked else "")

    def _on_equip(self, key, checked):
        for k, b in {**self._btns, **self._ebtns}.items():
            if k != key: b.setChecked(False)
        self.equip_clicked.emit(key if checked else "")

    def clear_all(self):
        for b in {**self._btns, **self._ebtns}.values():
            b.setChecked(False)


# ═══════════════════════════════════════════════════════════════════════════════
#  System panel
# ═══════════════════════════════════════════════════════════════════════════════

class SystemPanel(QWidget):
    mfr_changed = pyqtSignal(str)   # emitted when user picks a different manufacturer

    def __init__(self):
        super().__init__()
        self.setMinimumWidth(220); self.setMaximumWidth(270)
        l=QVBoxLayout(self); l.setContentsMargins(6,6,6,6); l.setSpacing(6)

        # ── Manufacturer selector (always-visible button group) ──────────────
        lbl = QLabel("Design for:")
        lbl.setStyleSheet("font-size:10px;font-weight:bold;color:#efe6e1;")
        l.addWidget(lbl)
        self._mfr_keys = list(MANUFACTURERS.keys())
        self._mfr_btns = {}
        self._mfr_btn_grp = QButtonGroup(self)
        self._mfr_btn_grp.setExclusive(True)
        _BTN_BASE = ("QPushButton{{text-align:left;padding:5px 8px;border-radius:4px;"
                     "border:2px solid {col};background:#2c2f30;color:#efe6e1;"
                     "font-size:10px;font-weight:bold;}}"
                     "QPushButton:hover{{background:#3a3d3e;}}"
                     "QPushButton:checked{{background:{col};color:white;}}")
        for mk in self._mfr_keys:
            mfr = MANUFACTURERS[mk]
            btn = QPushButton(mfr["name"])
            btn.setCheckable(True)
            btn.setStyleSheet(_BTN_BASE.format(col=mfr["color"]))
            btn.setProperty("mfr_key", mk)
            self._mfr_btn_grp.addButton(btn)
            self._mfr_btns[mk] = btn
            l.addWidget(btn)
        self._mfr_btns[self._mfr_keys[0]].setChecked(True)
        self._mfr_btn_grp.buttonClicked.connect(
            lambda btn: self.mfr_changed.emit(btn.property("mfr_key")))

        self._flow_lbl=QLabel("Flow: 0")
        self._flow_lbl.setStyleSheet("font-size:12px;font-weight:bold;color:#232728;"
                                     "background:#e0d8d2;padding:6px;border-radius:4px;")
        l.addWidget(self._flow_lbl)
        self._warn=QLabel(); self._warn.setWordWrap(True)
        self._warn.setStyleSheet("color:white;background:#c0392b;padding:5px;"
                                 "border-radius:4px;font-size:10px;")
        self._warn.setVisible(False); l.addWidget(self._warn)
        self._mw={}
        for mk,mfr in MANUFACTURERS.items():
            g=QGroupBox(mfr["name"])
            g.setStyleSheet(f"QGroupBox{{font-weight:bold;color:{mfr['color']};"
                            f"border:2px solid {mfr['color']};border-radius:4px;"
                            f"margin-top:8px;padding:4px;}}"
                            f"QGroupBox::title{{subcontrol-origin:margin;left:8px;padding:0 4px;}}")
            gl=QVBoxLayout(g); gl.setSpacing(2)
            sl=QLabel("—"); sl.setWordWrap(True); sl.setStyleSheet("font-size:11px;")
            rl=QLabel();    rl.setWordWrap(True); rl.setStyleSheet("font-size:10px;color:#555;")
            gl.addWidget(sl); gl.addWidget(rl); l.addWidget(g); self._mw[mk]=(sl,rl)
        l.addWidget(QLabel("── Breakdown ──"))
        self._tbl=QTableWidget(0,3)
        self._tbl.setHorizontalHeaderLabels(["Appliance","Nozzle","Flow"])
        self._tbl.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self._tbl.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self._tbl.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self._tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl.setMaximumHeight(160); self._tbl.setStyleSheet("font-size:10px;")
        l.addWidget(self._tbl)
        note=QLabel("⚠ Verify flow numbers\nagainst design manuals.")
        note.setStyleSheet("color:#e67e22;font-size:9px;padding:4px;"
                           "background:#fff8f0;border-radius:3px;")
        note.setAlignment(Qt.AlignCenter); l.addWidget(note); l.addStretch()

    def refresh(self, scene):
        mk = scene.active_mfr
        # Keep button group in sync with scene's active manufacturer
        if mk in self._mfr_btns:
            btn = self._mfr_btns[mk]
            if not btn.isChecked():
                self._mfr_btn_grp.blockSignals(True)
                btn.setChecked(True)
                self._mfr_btn_grp.blockSignals(False)
        total=scene.total_flow(); capacity=scene.bottle_capacity()
        if capacity:
            rem=capacity-total; col="#27ae60" if rem>=0 else "#c0392b"
            status="OK" if rem>=0 else f"OVER by {abs(rem)}"
            self._flow_lbl.setText(f"Used: {total}  /  Available: {capacity}  ({status})")
            self._flow_lbl.setStyleSheet(f"font-size:12px;font-weight:bold;color:{col};"
                                         f"background:#e0d8d2;padding:6px;border-radius:4px;")
        else:
            self._flow_lbl.setText(f"Flow needed: {total}  (no bottle yet)")
            self._flow_lbl.setStyleSheet("font-size:12px;font-weight:bold;color:#232728;"
                                         "background:#e0d8d2;padding:6px;border-radius:4px;")
        bad=scene.restricted_systems()
        warnings=[]
        if bad:
            warnings.append(f"⚠ Ecology unit — incompatible: "
                            f"{', '.join(MANUFACTURERS[k]['name'] for k in bad if k in MANUFACTURERS)}")
        # Clearance check: appliances whose centre falls outside every hood's X span
        # Use sceneBoundingRect() so depth/perspective offsets are accounted for.
        hoods = scene.hoods()
        if hoods:
            hood_rects = [h.sceneBoundingRect() for h in hoods]
            for appl in scene.appliances():
                ar = appl.sceneBoundingRect()
                ax = (ar.left() + ar.right()) / 2   # appliance centre X in scene
                covered = any(hr.left() <= ax <= hr.right() for hr in hood_rects)
                if not covered:
                    warnings.append(f"⚠ {appl.custom_name or appl.defn['name']} outside hood coverage")
        if warnings:
            self._warn.setText("\n".join(warnings))
            self._warn.setVisible(True)
        else:
            self._warn.setVisible(False)
        for mk in MANUFACTURERS:
            sl,rl=self._mw[mk]; rec=scene.recommendation(mk)
            if not rec["compatible"]:
                sl.setText("⛔  Not compatible"); sl.setStyleSheet("color:#c0392b;font-weight:bold;font-size:11px;"); rl.setText(rec["reason"])
            elif rec.get("over_capacity"):
                sl.setText(f"⚠  {rec['tanks_needed']}× {rec['tank']['model']}")
                sl.setStyleSheet("color:#e67e22;font-weight:bold;font-size:11px;")
                rl.setText(f"Flow {rec['total_flow']} exceeds single tank.")
            else:
                t=rec["tank"]; m=rec["margin_pct"]; col="#27ae60" if m>=20 else "#e67e22"
                sl.setText(f"✔  {t['model']}"); sl.setStyleSheet(f"color:{col};font-weight:bold;font-size:11px;")
                alts=", ".join(x["model"] for x in rec["alternatives"])
                rl.setText(f"{rec['total_flow']}/{t['max_flow']} pts  ({m:.0f}% spare)"+(f"\nAlt: {alts}" if alts else ""))
        rows=[]
        for a in scene.appliances():
            if a._nozzles_placed:
                nq = len(a.app_nozzles)
                nt = a.app_nozzles[0].nozzle_type if a.app_nozzles else "—"
                flow_val = sum(nz.flow_points() for nz in a.app_nozzles)
            else:
                ed = effective_defn(a.key, mk)
                nq = ed["nq"]; nt = ed["nt"] or "—"; flow_val = ed["flow"]
            flow_str = str(int(flow_val)) if flow_val == int(flow_val) else str(flow_val)
            rows.append((a.custom_name or a.defn["name"],
                         f"{nq}× {nt}",
                         flow_str))
        hood_nz = MFR_HOOD_NOZZLE.get(mk, MFR_HOOD_NOZZLE["kidde"])
        for hn in scene.hoods():
            p = len(hn.plenum_nozzles)
            rows.append((f"Hood: {hn.label}", f"{p}× {hood_nz['plenum']} plenum", str(p)))
        for item in scene.items():
            if getattr(item, "ITEM_TYPE", "") == "duct":
                nq = len(getattr(item, "duct_nozzles", []))
                rows.append((f"Duct ({item.w_in}\"×{item.h_in}\")", f"{nq}× {hood_nz['duct']}", str(nq)))
        self._tbl.setRowCount(len(rows))
        for r,(n,nz,fl) in enumerate(rows):
            self._tbl.setItem(r,0,QTableWidgetItem(n)); self._tbl.setItem(r,1,QTableWidgetItem(nz)); self._tbl.setItem(r,2,QTableWidgetItem(fl))


# ═══════════════════════════════════════════════════════════════════════════════
#  Dialogs
# ═══════════════════════════════════════════════════════════════════════════════

class AppSettingsDialog(QDialog):
    """Company settings — logo upload and other global options."""
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("DFP TakeoffPro Settings"); self.setMinimumWidth(400)
        s = _load_settings()
        l = QFormLayout(self); l.setSpacing(10); l.setContentsMargins(16,16,16,16)

        # Logo path row
        self._logo_path = QLineEdit(s.get("logo_path",""))
        self._logo_path.setPlaceholderText("No logo selected")
        self._logo_path.setReadOnly(True)
        browse = QPushButton("Browse…"); browse.clicked.connect(self._browse_logo)
        clear  = QPushButton("Clear");   clear.clicked.connect(lambda: self._logo_path.setText(""))
        row = QHBoxLayout(); row.addWidget(self._logo_path,1); row.addWidget(browse); row.addWidget(clear)
        l.addRow("Company Logo (PNG/JPG):", row)

        # Preview label
        self._preview = QLabel(); self._preview.setFixedSize(160,60)
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setStyleSheet("border:1px solid #ccc;background:#f8f8f8;")
        self._preview.setText("No logo")
        l.addRow("Preview:", self._preview)
        self._refresh_preview()
        self._logo_path.textChanged.connect(self._refresh_preview)

        br = QHBoxLayout()
        ok = QPushButton("Save"); ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        ok.clicked.connect(self._save); ca = QPushButton("Cancel"); ca.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(ca); br.addWidget(ok); l.addRow(br)

    def _browse_logo(self):
        try:
            path, _ = QFileDialog.getOpenFileName(self, "Select Logo", "", "Images (*.png *.jpg *.jpeg *.bmp)", options=QFileDialog.DontUseNativeDialog)
            if path: self._logo_path.setText(path)
        except Exception:
            _log_error("_browse_logo", None)

    def _refresh_preview(self):
        try:
            p = self._logo_path.text().strip()
            if p and os.path.isfile(p):
                px = QPixmap(p).scaled(156, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._preview.setPixmap(px); self._preview.setText("")
            else:
                self._preview.setPixmap(QPixmap()); self._preview.setText("No logo")
        except Exception:
            _log_error("_refresh_preview", None)

    def _save(self):
        s = _load_settings()
        s["logo_path"] = self._logo_path.text().strip()
        _save_settings(s)
        self.accept()


class HoodDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Add Hood"); self.setMinimumWidth(320)
        l=QFormLayout(self); l.setSpacing(10); l.setContentsMargins(16,16,16,16)
        self.lbl=QLineEdit("Hood 1")
        self.w_sp=QDoubleSpinBox(); self.w_sp.setRange(12,480); self.w_sp.setValue(96); self.w_sp.setSuffix("  in")
        self.d_sp=QDoubleSpinBox(); self.d_sp.setRange(12,120); self.d_sp.setValue(36); self.d_sp.setSuffix("  in")
        self.duct=QCheckBox("Add duct (default centre-back)"); self.duct.setChecked(True)
        self.dw=QDoubleSpinBox(); self.dw.setRange(6,48); self.dw.setValue(14); self.dw.setSuffix("  in")
        self.dh=QDoubleSpinBox(); self.dh.setRange(6,48); self.dh.setValue(14); self.dh.setSuffix("  in")
        self.zone=QLineEdit("Zone 1"); self.zone.setPlaceholderText("e.g. Zone 1, Main Line")
        self.duct.toggled.connect(self.dw.setEnabled); self.duct.toggled.connect(self.dh.setEnabled)
        l.addRow("Hood label:",self.lbl); l.addRow("Zone:",self.zone)
        l.addRow("Width (L-R):",self.w_sp); l.addRow("Depth (F-B):",self.d_sp)
        l.addRow(self.duct); l.addRow("Duct width:",self.dw); l.addRow("Duct depth:",self.dh)
        br=QHBoxLayout()
        ok=QPushButton("Add Hood"); ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;"); ok.clicked.connect(self.accept)
        ca=QPushButton("Cancel"); ca.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(ca); br.addWidget(ok); l.addRow(br)

    def values(self):
        return {"w_in":self.w_sp.value(),"d_in":self.d_sp.value(),
                "label":self.lbl.text().strip() or "Hood",
                "zone": self.zone.text().strip() or "Zone 1",
                "has_duct":self.duct.isChecked(),"duct_w_in":self.dw.value(),"duct_h_in":self.dh.value()}


class ApplianceSizeDialog(QDialog):
    def __init__(self, key, parent=None):
        super().__init__(parent); d=APPLIANCE_DEFS[key]
        self.setWindowTitle(f"Place: {d['name']}"); self.setMinimumWidth(280)
        l=QFormLayout(self); l.setSpacing(10); l.setContentsMargins(16,16,16,16)
        self.nm=QLineEdit(); self.nm.setPlaceholderText("Custom label (optional)")
        self.ws=QDoubleSpinBox(); self.ws.setRange(6,240); self.ws.setValue(d["dw"]); self.ws.setSuffix("  in")
        self.ds=QDoubleSpinBox(); self.ds.setRange(6,120); self.ds.setValue(d["dd"]); self.ds.setSuffix("  in")
        default_h = d.get("dh", 30)
        self.hs=QDoubleSpinBox(); self.hs.setRange(1,96);  self.hs.setValue(default_h); self.hs.setSuffix("  in")
        l.addRow("Label:",self.nm); l.addRow("Width:",self.ws); l.addRow("Depth:",self.ds); l.addRow("Height:",self.hs)
        l.addRow(QLabel(f"Default: {d['dw']}\"W × {d['dd']}\"D  |  Height default {default_h}\""))
        br=QHBoxLayout()
        ok=QPushButton("Place"); ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;"); ok.clicked.connect(self.accept)
        ca=QPushButton("Cancel"); ca.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(ca); br.addWidget(ok); l.addRow(br)

    def values(self):
        return {"w_in":self.ws.value(),"d_in":self.ds.value(),"h_in":self.hs.value(),
                "custom_name":self.nm.text().strip() or None}


def _all_nozzle_types():
    """Return combined list of nozzle types from all manufacturers (no duplicates)."""
    seen = set(); out = []
    for types in MFR_NOZZLE_TYPES.values():
        for t in types:
            if t not in seen:
                seen.add(t); out.append(t)
    return out

ALL_NOZZLE_TYPES = _all_nozzle_types()


class LinkTypeDialog(QDialog):
    """Choose a fusible link type before placing a detector."""
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Select Link Type"); self.setMinimumWidth(320)
        l=QFormLayout(self); l.setSpacing(10); l.setContentsMargins(16,16,16,16)
        self._cb=QComboBox(); self._cb.addItems(LINK_TYPES)
        l.addRow("Link type:",self._cb)
        br=QHBoxLayout()
        ok=QPushButton("Place"); ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;"); ok.clicked.connect(self.accept)
        ca=QPushButton("Cancel"); ca.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(ca); br.addWidget(ok); l.addRow(br)
    def link_type(self): return self._cb.currentText()


class NozzleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Add Nozzle"); self.setMinimumWidth(320)
        l=QFormLayout(self); l.setSpacing(10); l.setContentsMargins(16,16,16,16)

        # Manufacturer filter
        self._mfr_combo = QComboBox()
        self._mfr_combo.addItem("All manufacturers", "all")
        for mk, mfr in MANUFACTURERS.items():
            self._mfr_combo.addItem(mfr["name"], mk)
        self._mfr_combo.setCurrentIndex(0)

        self.tc=QComboBox(); self.tc.addItems(ALL_NOZZLE_TYPES)
        self.dc=QComboBox(); self.dc.addItems(list(NOZZLE_DIRS.keys()))

        l.addRow("Manufacturer filter:", self._mfr_combo)
        l.addRow("Nozzle type:", self.tc)
        l.addRow("Direction:", self.dc)

        info = QLabel("Kidde/Badger: F ADP R GRW DM LPF\n"
                      "Buckeye: N-1HP N-1LP N-2HP N-2LP N-2W\n"
                      "Amerex: FG(13729)  Appl(11982)  SolidFuel(11983)\n"
                      "        UBroiler(11984)  Range(14178)  Duct(16416)  BackShelf(16853)")
        info.setStyleSheet("color:#777;font-size:9px;"); l.addRow(info)

        br=QHBoxLayout()
        ok=QPushButton("Place"); ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;"); ok.clicked.connect(self.accept)
        ca=QPushButton("Cancel"); ca.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(ca); br.addWidget(ok); l.addRow(br)

        self._mfr_combo.currentIndexChanged.connect(self._filter_nozzles)

    def _filter_nozzles(self):
        mk = self._mfr_combo.currentData()
        if mk == "all":
            types = ALL_NOZZLE_TYPES
        else:
            types = MFR_NOZZLE_TYPES.get(mk, ALL_NOZZLE_TYPES)
        cur = self.tc.currentText()
        self.tc.clear(); self.tc.addItems(types)
        idx = self.tc.findText(cur)
        if idx >= 0: self.tc.setCurrentIndex(idx)

    def nozzle_type(self): return self.tc.currentText()
    def direction(self): return self.dc.currentText()


class NozzleEditDialog(QDialog):
    def __init__(self, current_type="1N", current_dir="Down ↓", parent=None):
        super().__init__(parent); self.setWindowTitle("Edit Nozzle"); self.setMinimumWidth(300)
        l=QFormLayout(self); l.setSpacing(10); l.setContentsMargins(16,16,16,16)
        self.tc=QComboBox(); self.tc.addItems(ALL_NOZZLE_TYPES)
        idx=self.tc.findText(current_type)
        if idx>=0: self.tc.setCurrentIndex(idx)
        self.dc=QComboBox(); self.dc.addItems(list(NOZZLE_DIRS.keys()))
        didx=self.dc.findText(current_dir)
        if didx>=0: self.dc.setCurrentIndex(didx)
        l.addRow("Nozzle type:",self.tc); l.addRow("Direction:",self.dc)
        br=QHBoxLayout()
        ok=QPushButton("Apply"); ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;"); ok.clicked.connect(self.accept)
        ca=QPushButton("Cancel"); ca.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(ca); br.addWidget(ok); l.addRow(br)

    def nozzle_type(self): return self.tc.currentText()
    def direction(self): return self.dc.currentText()


class ApplianceEditDialog(QDialog):
    """Edit an already-placed appliance: width, depth, height, custom label."""
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Appliance — {item.defn['name']}")
        self.setMinimumWidth(300)
        l=QFormLayout(self); l.setSpacing(10); l.setContentsMargins(18,18,18,18)

        self._w=QDoubleSpinBox(); self._w.setRange(6,240); self._w.setSuffix(" in")
        self._w.setDecimals(1); self._w.setValue(item.w_in)

        self._d=QDoubleSpinBox(); self._d.setRange(6,120); self._d.setSuffix(" in")
        self._d.setDecimals(1); self._d.setValue(item.d_in)

        self._h=QDoubleSpinBox(); self._h.setRange(0,96); self._h.setSuffix(" in")
        self._h.setDecimals(1); self._h.setValue(item.h_in)

        self._lbl=QLineEdit(item.custom_name or item.defn["name"])

        l.addRow("Width:", self._w)
        l.addRow("Depth:", self._d)
        l.addRow("Height:", self._h)
        l.addRow("Label:", self._lbl)

        br=QHBoxLayout()
        ok=QPushButton("Apply")
        ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        ok.clicked.connect(self.accept)
        ca=QPushButton("Cancel"); ca.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(ca); br.addWidget(ok)
        l.addRow(br)

    def values(self):
        return self._w.value(), self._d.value(), self._h.value(), self._lbl.text().strip()


class HoodEditDialog(QDialog):
    """Edit an already-placed hood: label, width, depth, zone."""
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Hood"); self.setMinimumWidth(300)
        l=QFormLayout(self); l.setSpacing(10); l.setContentsMargins(18,18,18,18)
        self._lbl=QLineEdit(item.label)
        self._w=QDoubleSpinBox(); self._w.setRange(12,480); self._w.setSuffix("  in"); self._w.setValue(item.w_in)
        self._d=QDoubleSpinBox(); self._d.setRange(12,120); self._d.setSuffix("  in"); self._d.setValue(item.d_in)
        self._zone=QLineEdit(getattr(item,"zone","Zone 1"))
        l.addRow("Label:", self._lbl); l.addRow("Zone:", self._zone)
        l.addRow("Width (L-R):", self._w); l.addRow("Depth (F-B):", self._d)
        br=QHBoxLayout()
        ok=QPushButton("Apply"); ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;"); ok.clicked.connect(self.accept)
        ca=QPushButton("Cancel"); ca.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(ca); br.addWidget(ok); l.addRow(br)

    def values(self):
        return self._w.value(), self._d.value(), self._lbl.text().strip() or "Hood", self._zone.text().strip() or "Zone 1"


class DuctEditDialog(QDialog):
    """Edit an already-placed duct: width and height."""
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Duct"); self.setMinimumWidth(260)
        l=QFormLayout(self); l.setSpacing(10); l.setContentsMargins(18,18,18,18)
        self._w=QDoubleSpinBox(); self._w.setRange(6,48); self._w.setSuffix("  in"); self._w.setValue(item.w_in)
        self._h=QDoubleSpinBox(); self._h.setRange(6,48); self._h.setSuffix("  in"); self._h.setValue(item.h_in)
        l.addRow("Width:", self._w); l.addRow("Height:", self._h)
        br=QHBoxLayout()
        ok=QPushButton("Apply"); ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;"); ok.clicked.connect(self.accept)
        ca=QPushButton("Cancel"); ca.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(ca); br.addWidget(ok); l.addRow(br)

    def values(self):
        return self._w.value(), self._h.value()


class _SaveDialog(QDialog):
    """Simple save dialog — no QFileDialog, no shell APIs."""
    def __init__(self, folder, default_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Project As"); self.setMinimumWidth(420)
        self._folder = folder
        v = QVBoxLayout(self); v.setSpacing(8); v.setContentsMargins(16,16,16,16)
        v.addWidget(QLabel(f"Save to:  {folder}"))
        v.addWidget(QLabel("Filename:"))
        self._edit = QLineEdit(default_name); v.addWidget(self._edit)
        br = QHBoxLayout()
        ok = QPushButton("Save"); ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        ca = QPushButton("Cancel")
        ok.clicked.connect(self._accept); ca.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(ca); br.addWidget(ok); v.addLayout(br)

    def _accept(self):
        if self._edit.text().strip(): self.accept()

    def selected_path(self):
        name = self._edit.text().strip()
        if not name.endswith(".dfp"): name += ".dfp"
        return os.path.join(self._folder, name)


class _OpenDialog(QDialog):
    """Simple open dialog — lists .dfp files in the Projects folder."""
    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Project"); self.setMinimumWidth(420)
        self._folder = folder; self._path = None
        v = QVBoxLayout(self); v.setSpacing(8); v.setContentsMargins(16,16,16,16)
        v.addWidget(QLabel(f"Projects folder:  {folder}"))
        self._list = QListWidget(); v.addWidget(self._list)
        files = sorted(f for f in os.listdir(folder) if f.endswith(".dfp")) if os.path.isdir(folder) else []
        if files:
            for f in files:
                self._list.addItem(f)
            self._list.setCurrentRow(0)
        else:
            v.addWidget(QLabel("No .dfp project files found."))
        self._list.itemDoubleClicked.connect(self._accept)
        br = QHBoxLayout()
        ok = QPushButton("Open"); ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        ca = QPushButton("Cancel")
        ok.clicked.connect(self._accept); ca.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(ca); br.addWidget(ok); v.addLayout(br)

    def _accept(self):
        item = self._list.currentItem()
        if item:
            self._path = os.path.join(self._folder, item.text())
            self.accept()

    def selected_path(self): return self._path


class BottleSizeDialog(QDialog):
    """Manufacturer-aware cylinder selector.

    Returns selected manufacturer key, tank dict (model/gal/max_flow).
    """
    def __init__(self, parent=None, locked_mfr=None):
        super().__init__(parent)
        self.setMinimumWidth(400)
        l = QFormLayout(self); l.setSpacing(10); l.setContentsMargins(16,16,16,16)

        # Manufacturer selector — locked to active_mfr when provided
        self._mfr_combo = QComboBox()
        self._mfr_keys  = list(MANUFACTURERS.keys())
        for mk in self._mfr_keys:
            self._mfr_combo.addItem(MANUFACTURERS[mk]["name"], mk)

        if locked_mfr and locked_mfr in MANUFACTURERS:
            idx = self._mfr_combo.findData(locked_mfr)
            self._mfr_combo.setCurrentIndex(idx)
            self._mfr_combo.setEnabled(False)   # locked to active design manufacturer
            self.setWindowTitle(f"Add Cylinder — {MANUFACTURERS[locked_mfr]['name']}")
        else:
            self._mfr_combo.setCurrentIndex(0)
            self.setWindowTitle("Add Cylinder")

        # Cylinder selector (dynamically populated)
        self._tank_combo = QComboBox()
        l.addRow("Manufacturer:", self._mfr_combo)
        l.addRow("Cylinder:",     self._tank_combo)

        self._note = QLabel()
        self._note.setStyleSheet("color:#e67e22;font-size:9px;")
        self._note.setWordWrap(True); l.addRow(self._note)

        br = QHBoxLayout()
        ok = QPushButton("Place")
        ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        ok.clicked.connect(self.accept)
        ca = QPushButton("Cancel"); ca.clicked.connect(self.reject)
        br.addStretch(); br.addWidget(ca); br.addWidget(ok); l.addRow(br)

        self._mfr_combo.currentIndexChanged.connect(self._refresh_tanks)
        self._refresh_tanks()

    def _refresh_tanks(self):
        mk = self._mfr_combo.currentData()
        mfr = MANUFACTURERS.get(mk, {})
        self._tank_combo.clear()
        tanks = mfr.get("tanks", [])
        for t in tanks:
            self._tank_combo.addItem(t["model"])
        # Set sensible default (mid-range tank)
        default = len(tanks) // 2
        self._tank_combo.setCurrentIndex(default)
        # Reference note per manufacturer
        notes = {
            "kidde":   "⚠  Ref: Kidde WHDR DIOM P/N 87-122000-001",
            "badger":  "⚠  Ref: Badger Range Guard DIOM P/N 60-9127100-000",
            "buckeye": "⚠  Ref: Buckeye BFR Kitchen Mister DIOM BPN: BFR-TM (ULEX 6885)",
            "amerex":  "⚠  Ref: Amerex KP Manual P/N 20150 (EX 4658)",
        }
        self._note.setText(notes.get(mk, "⚠  Verify against manufacturer DIOM"))

    def mfr_key(self):
        return self._mfr_combo.currentData()

    def selected_tank(self):
        mk = self.mfr_key()
        tanks = MANUFACTURERS.get(mk, {}).get("tanks", [])
        idx   = self._tank_combo.currentIndex()
        return tanks[idx] if 0 <= idx < len(tanks) else tanks[-1]

    # Legacy helpers kept for backward compat
    def gal(self):
        return self.selected_tank().get("gal")

    def max_flow(self):
        return self.selected_tank().get("max_flow", 11)


# ═══════════════════════════════════════════════════════════════════════════════
#  PDF export  — blueprint style, fits entire drawing
# ═══════════════════════════════════════════════════════════════════════════════

def export_submittal_pdf(systems, path, project_name="", project_meta=None, show_scale=False):
    """systems: list of (name, scene) tuples — one drawing page per system, then combined material list."""
    try:
        import datetime as _dt
        from PyQt5.QtCore import Qt as _Qt, QRectF as _QRectF
        DRAW_TYPES=("hood","duct","appliance","app_nozzle","free_nozzle",
                    "bottle","control_head","pull_station","detector")

        def _item_full_rect(item):
            sr=item.sceneBoundingRect()
            for child in item.childItems():
                sr=sr.united(child.sceneBoundingRect())
                for grandchild in child.childItems():
                    sr=sr.united(grandchild.sceneBoundingRect())
            return sr

        # Filter to systems that have content
        active=[]
        for sys_name, scene in systems:
            items=[i for i in scene.items() if getattr(i,"ITEM_TYPE","") in DRAW_TYPES]
            if items:
                active.append((sys_name, scene, items))
        if not active:
            return False, "Nothing on canvas."

        W,H=792,612
        HEADER_H=52; FOOTER_H=36; BORDER=18; SIDEBAR_W=195
        DX1=BORDER; DY1=HEADER_H+BORDER
        DX2=W-SIDEBAR_W-BORDER; DY2=H-FOOTER_H-BORDER
        DRAW_W=DX2-DX1; DRAW_H=DY2-DY1
        RENDER_DPI=2
        total_pages=len(active)

        doc=fitz.open()
        red=(0.75,0.17,0.11); dark=(0.14,0.17,0.15)
        meta=project_meta or {}
        customer=meta.get("customer","") or project_name or "—"
        location=meta.get("location","") or "—"
        rev=meta.get("revision","A") or "A"
        rev_d=meta.get("rev_date","") or ""
        tmp_files=[]

        for pg_idx,(sys_name,scene,items) in enumerate(active):
            # Bounding rect of scene content
            r=_item_full_rect(items[0])
            for i in items[1:]:
                r=r.united(_item_full_rect(i))
            r=r.adjusted(-70,-70,70,70)

            # Render scene to image — preserve aspect ratio of scene content
            sw=r.width(); sh=r.height() if r.height()>0 else 1
            scene_aspect=sw/sh
            draw_aspect=DRAW_W/DRAW_H
            if scene_aspect>=draw_aspect:
                img_w=max(200,DRAW_W*RENDER_DPI)
                img_h=max(150,int(img_w/scene_aspect))
            else:
                img_h=max(150,DRAW_H*RENDER_DPI)
                img_w=max(200,int(img_h*scene_aspect))
            img=QImage(img_w,img_h,QImage.Format_RGB32)
            img.fill(QColor("white"))
            p=QPainter(img); p.setRenderHint(QPainter.Antialiasing)
            scene._exporting=True
            scene.render(p,_QRectF(0,0,img_w,img_h),r,_Qt.IgnoreAspectRatio)
            scene._exporting=False
            p.end()
            tmp=path+f"_tmp{pg_idx}.png"; img.save(tmp); tmp_files.append(tmp)

            pg=doc.new_page(width=W,height=H)

            # Header
            pg.draw_rect(fitz.Rect(0,0,W,HEADER_H),color=red,fill=red)
            pg.insert_text((BORDER,18),"DEFENSE FIRE PROTECTION",fontsize=13,color=(1,1,1),fontname="helv")
            pg.insert_text((BORDER,35),"Kitchen Fire Suppression System",fontsize=8,color=(1,1,1),fontname="helv")
            pg.insert_text((W-SIDEBAR_W+4,18),f"Customer: {customer}",fontsize=8,color=(1,1,1),fontname="helv")
            pg.insert_text((W-SIDEBAR_W+4,32),f"Location: {location}",fontsize=7,color=(1,1,1),fontname="helv")

            # Drawing area
            pg.draw_rect(fitz.Rect(DX1,DY1,DX2,DY2),color=dark,width=1.2)
            pg.insert_image(fitz.Rect(DX1,DY1,DX2,DY2),filename=tmp)

            # Sidebar
            sx2=W-SIDEBAR_W+6; sy2=DY1+4
            pg.insert_text((sx2,sy2+10),sys_name.upper(),fontsize=9,color=red,fontname="helv"); sy2+=20
            pg.draw_line((sx2,sy2),(W-BORDER,sy2),color=dark,width=0.5); sy2+=8

            amk=scene.active_mfr
            amfr=MANUFACTURERS[amk]
            rec=scene.recommendation(amk)
            pg.insert_text((sx2,sy2),"SYSTEM",fontsize=8,color=dark,fontname="helv"); sy2+=13
            pg.insert_text((sx2,sy2),amfr["name"],fontsize=8,color=dark,fontname="helv"); sy2+=13
            bottles=[i for i in scene.items() if getattr(i,"ITEM_TYPE","")=="bottle"]
            if bottles:
                from collections import Counter
                bottle_counts=Counter(b.label for b in bottles)
                for blabel,cnt in bottle_counts.items():
                    line_text=f"{cnt}× {blabel}" if cnt>1 else blabel
                    pg.insert_text((sx2+4,sy2),line_text,fontsize=7,color=dark,fontname="helv"); sy2+=11
            sy2+=8
            pg.draw_line((sx2,sy2),(W-BORDER,sy2),color=dark,width=0.5); sy2+=8
            pg.insert_text((sx2,sy2),"APPLIANCE / NOZZLE LIST",fontsize=8,color=dark,fontname="helv"); sy2+=12
            for a in scene.appliances():
                if sy2>H-FOOTER_H-10: break
                ed=effective_defn(a.key,scene.active_mfr)
                pg.insert_text((sx2,sy2),f"{a.custom_name or a.defn['short']}",fontsize=7,color=dark,fontname="helv")
                pg.insert_text((sx2+55,sy2),f"{ed['nq']}×{ed['nt'] or '—'}  {ed['flow']}fp",fontsize=7,color=(0.3,0.3,0.3),fontname="helv")
                sy2+=10
            _hnz=MFR_HOOD_NOZZLE.get(scene.active_mfr,MFR_HOOD_NOZZLE["kidde"])
            for hn in scene.hoods():
                if sy2>H-FOOTER_H-10: break
                fp=hn.flow_points()
                pg.insert_text((sx2,sy2),f"Hood: {hn.label}",fontsize=7,color=dark,fontname="helv")
                pg.insert_text((sx2+55,sy2),f"{fp}×{_hnz['plenum']}  {fp}fp",fontsize=7,color=(0.3,0.3,0.3),fontname="helv"); sy2+=10
            nd=len([i for i in scene.items() if getattr(i,"ITEM_TYPE","")=="duct"])
            if nd and sy2<H-FOOTER_H-10:
                pg.insert_text((sx2,sy2),f"{nd}× Duct",fontsize=7,color=dark,fontname="helv")
                pg.insert_text((sx2+55,sy2),f"{nd}×{_hnz['duct']}  {nd}fp",fontsize=7,color=(0.3,0.3,0.3),fontname="helv"); sy2+=10
            sy2+=4
            total_fp=scene.total_flow(); cap=scene.bottle_capacity()
            pg.draw_line((sx2,sy2),(W-BORDER,sy2),color=dark,width=0.5); sy2+=8
            pg.insert_text((sx2,sy2),f"Total flow: {total_fp} fp",fontsize=7,color=dark,fontname="helv"); sy2+=10
            if cap:
                rem=cap-total_fp; c=(0.1,0.5,0.1) if rem>=0 else red
                pg.insert_text((sx2,sy2),f"Available: {cap} fp",fontsize=7,color=c,fontname="helv"); sy2+=10
                pg.insert_text((sx2,sy2),f"Spare: {rem} fp",fontsize=7,color=c,fontname="helv"); sy2+=10

            # Zone breakdown
            hoods=scene.hoods()
            if hoods and sy2<H-FOOTER_H-30:
                sy2+=6
                pg.draw_line((sx2,sy2),(W-BORDER,sy2),color=dark,width=0.5); sy2+=8
                pg.insert_text((sx2,sy2),"ZONES",fontsize=8,color=dark,fontname="helv"); sy2+=11
                zone_map={}
                for hn in hoods:
                    z=getattr(hn,"zone","Zone 1") or "Zone 1"
                    zone_map.setdefault(z,[]).append(hn)
                for zname,zhoods in zone_map.items():
                    if sy2>H-FOOTER_H-10: break
                    pg.insert_text((sx2,sy2),f"{zname}",fontsize=7,color=dark,fontname="helv")
                    pg.insert_text((sx2+70,sy2),f"{len(zhoods)} hood(s)",fontsize=7,color=(0.3,0.3,0.3),fontname="helv"); sy2+=10

            # Legend
            nozzle_types_used=[]; seen_nt=set()
            det_types_used=[]; seen_dt=set()
            for it in scene.items():
                nt=getattr(it,"nozzle_type","")
                if nt and nt not in seen_nt:
                    seen_nt.add(nt); nozzle_types_used.append(nt)
                if getattr(it,"ITEM_TYPE","")=="detector":
                    lt=it.link_type
                    if lt not in seen_dt:
                        seen_dt.add(lt); det_types_used.append(lt)
            has_legend = nozzle_types_used or det_types_used
            if has_legend and sy2<H-FOOTER_H-30:
                sy2+=6
                pg.draw_line((sx2,sy2),(W-BORDER,sy2),color=dark,width=0.5); sy2+=8
                pg.insert_text((sx2,sy2),"LEGEND",fontsize=8,color=dark,fontname="helv"); sy2+=11
                for nt in nozzle_types_used:
                    if sy2>H-FOOTER_H-10: break
                    col=_nozzle_color_rgb(nt)
                    pg.draw_circle((sx2+4,sy2-3),4,color=col,fill=col)
                    pg.insert_text((sx2+12,sy2),f"Nozzle {nt}",fontsize=7,color=dark,fontname="helv"); sy2+=10
                for lt in det_types_used:
                    if sy2>H-FOOTER_H-10: break
                    col=_detector_color_rgb(lt)
                    # Draw mini detector symbol: colored rounded rect with two white circles
                    lx0=sx2; ly0=sy2-6; lw=12; lh=8
                    pg.draw_rect(fitz.Rect(lx0,ly0,lx0+lw,ly0+lh),color=col,fill=col)
                    cr=2
                    pg.draw_circle((lx0+lw*0.3, ly0+lh/2), cr, color=(1,1,1), fill=(1,1,1))
                    pg.draw_circle((lx0+lw*0.7, ly0+lh/2), cr, color=(1,1,1), fill=(1,1,1))
                    pg.insert_text((sx2+16,sy2),f"{lt}",fontsize=7,color=dark,fontname="helv"); sy2+=10

            # Notes (only on first page)
            if pg_idx==0:
                # Gather control head connection notes
                ctrl_notes = []
                for it in scene.items():
                    if getattr(it,"ITEM_TYPE","")=="control_head":
                        ctrl_notes.extend(it.notes_lines())
                user_notes = (meta.get("notes","") or "").strip()
                all_notes = "\n".join(ctrl_notes)
                if user_notes:
                    all_notes = (all_notes + "\n" + user_notes) if all_notes else user_notes
                all_notes = all_notes.strip()
                if all_notes and sy2<H-FOOTER_H-30:
                    sy2+=6
                    pg.draw_line((sx2,sy2),(W-BORDER,sy2),color=dark,width=0.5); sy2+=8
                    pg.insert_text((sx2,sy2),"NOTES",fontsize=8,color=dark,fontname="helv"); sy2+=11
                    for note_line in all_notes.split("\n"):
                        words=note_line.split(); line=""
                        for w in words:
                            if len(line)+len(w)+1>42:
                                if sy2>H-FOOTER_H-10: break
                                pg.insert_text((sx2,sy2),line.strip(),fontsize=7,color=(0.2,0.2,0.2),fontname="helv"); sy2+=10; line=""
                            line+=w+" "
                        if line.strip() and sy2<=H-FOOTER_H-10:
                            pg.insert_text((sx2,sy2),line.strip(),fontsize=7,color=(0.2,0.2,0.2),fontname="helv"); sy2+=10

            # Company logo (bottom-right of sidebar, above footer)
            if pg_idx==0:
                logo_path=(_load_settings().get("logo_path","") or "").strip()
                if logo_path and os.path.isfile(logo_path):
                    try:
                        logo_max_w=W-BORDER-sx2-4
                        logo_max_h=88
                        logo_rect=fitz.Rect(sx2, H-FOOTER_H-logo_max_h-6, W-BORDER, H-FOOTER_H-6)
                        pg.insert_image(logo_rect, filename=logo_path, keep_proportion=True)
                    except Exception:
                        pass

            # Scale bar
            if show_scale:
                scene_w_in=r.width()/PX
                if scene_w_in>0:
                    bar_len=DRAW_W/scene_w_in*12
                    bx=DX1+8; by=DY2-14
                    if bar_len<DRAW_W-20:
                        pg.draw_line((bx,by),(bx+bar_len,by),color=dark,width=1.5)
                        pg.draw_line((bx,by-4),(bx,by+4),color=dark,width=1.0)
                        pg.draw_line((bx+bar_len,by-4),(bx+bar_len,by+4),color=dark,width=1.0)
                        pg.insert_text((bx,by+10),"1 ft",fontsize=6,color=dark,fontname="helv")

            # Revision stamp
            pg.draw_rect(fitz.Rect(W-SIDEBAR_W-80,4,W-SIDEBAR_W-4,HEADER_H-4),
                         color=(1,1,1),fill=(1,1,1),width=0.8)
            pg.insert_text((W-SIDEBAR_W-76,18),f"REV  {rev}",fontsize=11,color=red,fontname="helv")
            if rev_d:
                pg.insert_text((W-SIDEBAR_W-76,32),rev_d,fontsize=7,color=(0.3,0.3,0.3),fontname="helv")

            # Footer
            tb_y=H-FOOTER_H
            pg.draw_rect(fitz.Rect(0,tb_y,W,H),color=dark,fill=dark)
            pg.insert_text((BORDER,tb_y+13),f"{customer}",fontsize=8,color=(1,1,1),fontname="helv")
            pg.insert_text((BORDER,tb_y+25),f"{location}",fontsize=7,color=(0.85,0.85,0.85),fontname="helv")
            pg.insert_text((W-200,tb_y+13),"Defense Fire Protection",fontsize=7,color=(1,1,1),fontname="helv")
            pg.insert_text((W-200,tb_y+23),_dt.date.today().strftime("Date: %Y-%m-%d"),fontsize=6,color=(0.9,0.9,0.9),fontname="helv")
            pg.insert_text((W-100,tb_y+13),f"Page {pg_idx+1} of {total_pages}",fontsize=7,color=(1,1,1),fontname="helv")
            pg.insert_text((W-60,tb_y+25),f"REV {rev}",fontsize=7,color=(1,1,1),fontname="helv")

        doc.save(path); doc.close()
        for tmp in tmp_files:
            try: os.remove(tmp)
            except: pass
        return True, path
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════════════════════════
#  Project info dialog
# ═══════════════════════════════════════════════════════════════════════════════

class ProjectInfoDialog(QDialog):
    """Create / edit project metadata: customer, location, job #, notes."""
    def __init__(self, meta=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Project Information")
        self.setMinimumWidth(420)
        m = meta or {}
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        def _row(label, widget):
            row = QHBoxLayout()
            lbl = QLabel(label); lbl.setFixedWidth(110)
            lbl.setStyleSheet("font-weight:bold;font-size:11px;")
            row.addWidget(lbl); row.addWidget(widget); layout.addLayout(row)

        self._customer = QLineEdit(m.get("customer",""))
        self._customer.setPlaceholderText("e.g. McDonald's – Main St")
        _row("Customer:", self._customer)

        self._location = QLineEdit(m.get("location",""))
        self._location.setPlaceholderText("e.g. 123 Main St, Anytown AB")
        _row("Location:", self._location)

        self._job = QLineEdit(m.get("job_number",""))
        self._job.setPlaceholderText("e.g. DFP-2026-001")
        _row("Job Number:", self._job)

        self._designer = QLineEdit(m.get("designer",""))
        self._designer.setPlaceholderText("Your name")
        _row("Designer:", self._designer)

        # Revision — inline: Rev letter + date
        rev_widget = QWidget()
        rev_row = QHBoxLayout(rev_widget); rev_row.setContentsMargins(0,0,0,0); rev_row.setSpacing(6)
        self._revision = QLineEdit(m.get("revision","A"))
        self._revision.setFixedWidth(50); self._revision.setPlaceholderText("A")
        rev_date_lbl = QLabel("Date:"); rev_date_lbl.setStyleSheet("font-size:11px;")
        self._rev_date = QLineEdit(m.get("rev_date", datetime.date.today().strftime("%Y-%m-%d")))
        self._rev_date.setPlaceholderText("YYYY-MM-DD")
        rev_row.addWidget(self._revision); rev_row.addWidget(rev_date_lbl)
        rev_row.addWidget(self._rev_date); rev_row.addStretch()
        _row("Revision:", rev_widget)

        self._tank = QLineEdit(m.get("tank",""))
        self._tank.setPlaceholderText("e.g. 2× Ansul R-102 1.5 gal")
        _row("Tank / Cylinder:", self._tank)

        self._notes = QTextEdit(m.get("notes",""))
        self._notes.setPlaceholderText("Any additional notes…")
        self._notes.setFixedHeight(72)
        layout.addWidget(QLabel("Notes:")); layout.addWidget(self._notes)

        btns = QHBoxLayout()
        ok = QPushButton("OK"); ok.setDefault(True)
        ok.setStyleSheet("background:#1a5276;color:white;font-weight:bold;"
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
            "tank":       self._tank.text().strip(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  Main dialog
# ═══════════════════════════════════════════════════════════════════════════════

class SuppressionDesigner(QDialog):
    def __init__(self, parent=None, project_name=""):
        super().__init__(parent)
        self.setMinimumSize(1100,680)
        self.setWindowState(Qt.WindowMaximized)
        self.project_name = project_name
        self._project_meta = {}
        self._current_file = None
        self._dirty = False
        self._undo_stack = []
        self._redo_stack = []
        self._restoring  = False
        self._show_scale = False
        self._systems = []  # list of {"name":str, "scene":SuppressionScene, "canvas":SuppressionCanvas}
        self._build_ui()
        self._add_system("System 1")
        self._update_title()

    def _build_ui(self):
        main=QVBoxLayout(self); main.setContentsMargins(0,0,0,0); main.setSpacing(0)
        tb=QWidget(); tb.setStyleSheet("background:#232728;")
        tbl=QHBoxLayout(tb); tbl.setContentsMargins(8,5,8,5); tbl.setSpacing(5)
        def _btn(txt,slot,color="#333738",checkable=False):
            b=QPushButton(txt); b.setCheckable(checkable)
            b.setStyleSheet(f"QPushButton{{background:{color};color:#efe6e1;border-radius:3px;"
                            f"padding:5px 10px;border:none;font-weight:bold;font-size:11px;}}"
                            f"QPushButton:hover{{background:#ff7002;color:white;}}"
                            f"QPushButton:checked{{background:#ff7002;color:white;}}")
            b.clicked.connect(slot); return b
        def _sep():
            s=QFrame(); s.setFrameShape(QFrame.VLine); s.setStyleSheet("color:#555;"); return s
        self._undo_btn=_btn("↩ Undo",self._undo); self._undo_btn.setEnabled(False)
        self._redo_btn=_btn("↪ Redo",self._redo); self._redo_btn.setEnabled(False)
        tbl.addWidget(self._undo_btn); tbl.addWidget(self._redo_btn)
        tbl.addWidget(_sep())
        tbl.addWidget(_btn("+ Hood",self._add_hood))
        tbl.addWidget(_btn("+ Duct",self._add_duct))
        tbl.addWidget(_sep())
        self._pipe_btn=_btn("✏ Draw Pipe",self._toggle_pipe_draw,color="#1a5276",checkable=True)
        tbl.addWidget(self._pipe_btn)
        # Pipe colour + thickness pickers — styled for dark toolbar
        _cb_style = ("QComboBox{background:#3a3d3e;color:#efe6e1;border:1px solid #666;"
                     "border-radius:3px;padding:4px 6px;font-size:11px;font-weight:bold;}"
                     "QComboBox:hover{border:1px solid #ff7002;}"
                     "QComboBox::drop-down{border:none;width:16px;}"
                     "QComboBox::down-arrow{width:8px;height:8px;}"
                     "QComboBox QAbstractItemView{background:#2d3030;color:#efe6e1;"
                     "selection-background-color:#ff7002;selection-color:white;border:1px solid #555;}")
        self._pipe_col_cb = QComboBox(); self._pipe_col_cb.setFixedWidth(90)
        self._pipe_col_cb.setStyleSheet(_cb_style)
        for name, hexcol in PIPE_COLORS:
            self._pipe_col_cb.addItem(name, hexcol)
            idx = self._pipe_col_cb.count()-1
            self._pipe_col_cb.setItemData(idx, QColor(hexcol), Qt.DecorationRole)
        self._pipe_col_cb.currentIndexChanged.connect(self._on_pipe_col_changed)
        tbl.addWidget(self._pipe_col_cb)
        self._pipe_w_cb = QComboBox(); self._pipe_w_cb.setFixedWidth(64)
        self._pipe_w_cb.setStyleSheet(_cb_style)
        for w in range(1, 8):
            self._pipe_w_cb.addItem(f"{w} px", w)
        self._pipe_w_cb.setCurrentIndex(PIPE_W - 1)
        self._pipe_w_cb.currentIndexChanged.connect(self._on_pipe_w_changed)
        tbl.addWidget(self._pipe_w_cb)
        tbl.addWidget(_sep())
        self._lbl_btn=_btn("Labels ON",self._toggle_labels,checkable=True)
        self._lbl_btn.setChecked(True); tbl.addWidget(self._lbl_btn)
        self._dim_btn=_btn("Dims OFF",self._toggle_dims,checkable=True)
        self._dim_btn.setChecked(False); tbl.addWidget(self._dim_btn)
        self._snap_btn=_btn("Snap OFF",self._toggle_snap,checkable=True)
        self._snap_btn.setChecked(False); tbl.addWidget(self._snap_btn)
        self._scale_btn=_btn("Scale OFF",self._toggle_scale_bar,checkable=True)
        self._scale_btn.setChecked(False); tbl.addWidget(self._scale_btn)
        tbl.addWidget(_sep())
        tbl.addWidget(_btn("Fit View",self._fit))
        tbl.addWidget(_btn("Clear All",self._clear))
        tbl.addWidget(_sep())
        tbl.addWidget(_btn("Project Info",  self._edit_project_info))
        tbl.addWidget(_btn("New",           self._new_project))
        tbl.addWidget(_btn("Open",          self._open_project, color="#1a5276"))
        tbl.addWidget(_btn("Save",          self._save_project,  color="#1a5276"))
        tbl.addWidget(_btn("Save As",       self._save_project_as))
        tbl.addWidget(_sep())
        tbl.addWidget(_btn("Export PDF",    self._export, color="#c0392b"))
        if _PRINT_AVAILABLE:
            tbl.addWidget(_btn("Print",     self._print_pdf, color="#7d3c98"))
        tbl.addWidget(_sep())
        tbl.addWidget(_btn("Settings",      self._open_settings))
        tbl.addStretch()
        self._mode_lbl=QLabel("  Select  ·  Scroll=zoom  ·  Middle-drag or Ctrl+drag=pan  ·  Del=delete  ·  Right-click=options  ·  Esc=cancel")
        self._mode_lbl.setStyleSheet("color:#888;font-size:10px;"); tbl.addWidget(self._mode_lbl)
        main.addWidget(tb)
        body=QSplitter(Qt.Horizontal)
        body.setStyleSheet("QSplitter::handle{background:#d0c8c0;width:4px;}")
        self._palette=AppliancePalette()
        self._palette.appliance_clicked.connect(self._on_appliance)
        self._palette.equip_clicked.connect(self._on_equip)
        body.addWidget(self._palette)
        # Tab widget — one tab per suppression system, each containing its own canvas
        self._tab_widget=QTabWidget()
        self._tab_widget.setStyleSheet(
            "QTabWidget::pane{border:none;margin:0;}"
            "QTabBar::tab{background:#3a3d3e;color:#efe6e1;padding:5px 14px;"
            "border:1px solid #555;border-bottom:none;"
            "border-top-left-radius:3px;border-top-right-radius:3px;"
            "font-size:11px;font-weight:bold;}"
            "QTabBar::tab:selected{background:#ff7002;color:white;}"
            "QTabBar::tab:hover:!selected{background:#555;}")
        _add_sys_btn=QPushButton("+ System")
        _add_sys_btn.setFixedHeight(26)
        _add_sys_btn.setStyleSheet(
            "QPushButton{background:#1a5276;color:#efe6e1;border:none;"
            "padding:4px 10px;border-radius:3px;font-size:11px;font-weight:bold;}"
            "QPushButton:hover{background:#ff7002;color:white;}")
        _add_sys_btn.clicked.connect(self._add_system_prompt)
        self._tab_widget.setCornerWidget(_add_sys_btn,Qt.TopRightCorner)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)
        self._tab_widget.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self._tab_widget.tabBar().customContextMenuRequested.connect(self._tab_context_menu)
        body.addWidget(self._tab_widget)
        self._sys_panel=SystemPanel(); body.addWidget(self._sys_panel)
        self._sys_panel.mfr_changed.connect(self._on_mfr_changed)
        body.setStretchFactor(0,0); body.setStretchFactor(1,1); body.setStretchFactor(2,0)
        body.setSizes([128,760,240]); main.addWidget(body)
        self._status=QLabel("  Add a hood, then select an appliance from the left and click the canvas.  Right-click any item for options.")
        self._status.setStyleSheet("background:#232728;color:#efe6e1;padding:3px 8px;font-size:10px;")
        main.addWidget(self._status)

    # ── Multi-system helpers ─────────────────────────────────────────────────

    @property
    def _scene(self):
        idx=self._tab_widget.currentIndex()
        if 0<=idx<len(self._systems):
            return self._systems[idx]["scene"]
        return None

    @property
    def _canvas(self):
        idx=self._tab_widget.currentIndex()
        if 0<=idx<len(self._systems):
            return self._systems[idx]["canvas"]
        return None

    def _add_system(self, name="System 1"):
        scene=SuppressionScene()
        scene.layout_changed.connect(self._on_changed)
        if hasattr(self,"_lbl_btn"):
            scene.show_labels=self._lbl_btn.isChecked()
            scene.show_dimensions=self._dim_btn.isChecked()
            scene.snap_to_grid=self._snap_btn.isChecked()
        canvas=SuppressionCanvas(scene)
        sys_info={"name":name,"scene":scene,"canvas":canvas}
        self._systems.append(sys_info)
        self._tab_widget.addTab(canvas,name)
        self._tab_widget.setCurrentIndex(len(self._systems)-1)
        return sys_info

    def _add_system_prompt(self):
        name,ok=QInputDialog.getText(self,"Add System","System name:",
                                     text=f"System {len(self._systems)+1}")
        if ok and name.strip():
            self._add_system(name.strip())
            self._dirty=True; self._update_title()

    def _on_tab_changed(self, idx):
        if not (0<=idx<len(self._systems)):
            return
        sc=self._systems[idx]["scene"]
        self._sys_panel.refresh(sc)
        if hasattr(self,"_pipe_btn") and self._pipe_btn.isChecked():
            self._pipe_btn.setChecked(False)
            sc._pipe_draw=False; sc._pipe_start=None
            self._mode_lbl.setText(
                "  Select  ·  Scroll=zoom  ·  Middle-drag or Ctrl+drag=pan  ·  Del=delete  ·  Right-click=options  ·  Esc=cancel")
        if hasattr(self,"_lbl_btn"):
            sc.show_labels=self._lbl_btn.isChecked()
            sc.show_dimensions=self._dim_btn.isChecked()
            sc.snap_to_grid=self._snap_btn.isChecked()

    def _tab_context_menu(self, pos):
        idx=self._tab_widget.tabBar().tabAt(pos)
        if idx<0: return
        menu=QMenu(self)
        rename_act=menu.addAction("Rename System")
        menu.addSeparator()
        delete_act=menu.addAction("Delete System")
        if len(self._systems)<=1:
            delete_act.setEnabled(False)
        act=menu.exec_(self._tab_widget.tabBar().mapToGlobal(pos))
        if act==rename_act:
            old=self._systems[idx]["name"]
            name,ok=QInputDialog.getText(self,"Rename System","System name:",text=old)
            if ok and name.strip():
                self._systems[idx]["name"]=name.strip()
                self._tab_widget.setTabText(idx,name.strip())
                self._dirty=True; self._update_title()
        elif act==delete_act:
            ans=QMessageBox.question(self,"Delete System",
                f"Delete '{self._systems[idx]['name']}' and all its content?",
                QMessageBox.Yes|QMessageBox.No)
            if ans==QMessageBox.Yes:
                self._tab_widget.removeTab(idx)
                self._systems.pop(idx)
                self._dirty=True; self._update_title()
                sc=self._scene
                if sc: self._sys_panel.refresh(sc)

    def _on_mfr_changed(self, mfr):
        sc=self._scene
        if sc: sc.set_active_mfr(mfr)

    def _add_hood(self):
        try:
            dlg=HoodDialog(self)
            if dlg.exec_()!=QDialog.Accepted: return
            v=dlg.values()
            self._scene.add_hood(v["w_in"],v["d_in"],v["label"],v["has_duct"],v["duct_w_in"],v["duct_h_in"],v.get("zone","Zone 1"))
            self._canvas.fit_all()
        except Exception:
            _log_error("_add_hood", None)

    def _add_duct(self): self._scene.add_duct(); self._status.setText("  Duct added — drag to reposition.")

    def _toggle_pipe_draw(self, checked):
        self._scene._pipe_draw  = checked
        self._scene._pipe_start = None
        self._scene._pipe_preview = None
        if checked:
            self._scene.set_mode_select()   # exit placement mode
            self._palette.clear_all()
            self._mode_lbl.setText(
                "  ✏ Draw Pipe — Left-click to place points, chains automatically  |  "
                "Right-click to end segment  |  Hold Ctrl for diagonal  |  Esc = cancel current  |  Del = delete selected pipe")
        else:
            self._mode_lbl.setText(
                "  Select  ·  Scroll=zoom  ·  Middle-drag or Ctrl+drag=pan  ·  Del=delete  ·  Right-click=options  ·  Esc=cancel")
        self._canvas.viewport().update()

    def _on_pipe_col_changed(self, idx):
        hexcol = self._pipe_col_cb.itemData(idx)
        self._scene._pipe_color = QColor(hexcol) if hexcol else QColor(PIPE_COL)

    def _on_pipe_w_changed(self, idx):
        self._scene._pipe_width = self._pipe_w_cb.itemData(idx) or PIPE_W

    def _toggle_labels(self,checked):
        for s in self._systems: s["scene"].show_labels=checked
        self._lbl_btn.setText("Labels ON" if checked else "Labels OFF")
        sc=self._scene
        if sc: sc.update()

    def _toggle_dims(self,checked):
        for s in self._systems: s["scene"].show_dimensions=checked
        self._dim_btn.setText("Dims ON" if checked else "Dims OFF")
        sc=self._scene
        if sc: sc.update()

    def _on_appliance(self,key):
        if not key: self._scene.set_mode_select(); self._mode_lbl.setText("  Select  ·  Scroll=zoom  ·  Middle-drag or Ctrl+drag=pan  ·  Del=delete  ·  Right-click=options  ·  Esc=cancel"); return
        # Exit pipe-draw mode when placing appliances
        if self._scene._pipe_draw:
            self._scene._pipe_draw=False; self._scene._pipe_start=None
            self._pipe_btn.setChecked(False)
        dlg=ApplianceSizeDialog(key,self)
        if dlg.exec_()!=QDialog.Accepted: self._palette.clear_all(); return
        v=dlg.values()
        self._scene.set_mode_place("appliance",{"key":key,"w_in":v["w_in"],"d_in":v["d_in"],"h_in":v["h_in"],"name":v["custom_name"]})
        self._mode_lbl.setText(f"  Placing {APPLIANCE_DEFS[key]['name']} — click canvas  |  Esc=cancel")

    def _on_equip(self,key):
        if not key: self._scene.set_mode_select(); return
        if key=="nozzle":
            dlg=NozzleDialog(self)
            if dlg.exec_()!=QDialog.Accepted: self._palette.clear_all(); return
            self._scene.set_mode_place("free_nozzle",{"nozzle_type":dlg.nozzle_type(),"direction":dlg.direction()})
            self._mode_lbl.setText(f"  Placing nozzle ({dlg.nozzle_type()} {dlg.direction()}) — click canvas  |  Esc=cancel")
        elif key=="bottle":
            dlg=BottleSizeDialog(self, locked_mfr=self._scene.active_mfr)
            if dlg.exec_()!=QDialog.Accepted: self._palette.clear_all(); return
            tank=dlg.selected_tank(); mk=dlg.mfr_key()
            self._scene.set_mode_place("bottle",{
                "gal":tank.get("gal"), "max_flow":tank["max_flow"],
                "mfr_key":mk, "label":tank["model"]})
            self._mode_lbl.setText(f"  Placing {MANUFACTURERS[mk]['name']} {tank['model']} — click canvas  |  Esc=cancel")
        elif key=="control_head":
            dlg = ControlHeadOptionsDialog(parent=self)
            if dlg.exec_() != QDialog.Accepted:
                self._palette.clear_all(); return
            self._scene.set_mode_place("control_head", {"options": dlg.values()})
            self._mode_lbl.setText("  Placing control head — click canvas  |  Esc=cancel")
        elif key=="pull_station":
            self._scene.set_mode_place("pull_station")
            self._mode_lbl.setText("  Placing pull station — click canvas  |  Esc=cancel")
        elif key=="alarm_bell":
            self._scene.set_mode_place("alarm_bell")
            self._mode_lbl.setText("  Placing alarm bell — click canvas  |  Esc=cancel")
        elif key=="gas_valve":
            self._scene.set_mode_place("gas_valve")
            self._mode_lbl.setText("  Placing gas valve — click canvas  |  Esc=cancel")
        elif key=="detector":
            dlg=LinkTypeDialog(self)
            if dlg.exec_()!=QDialog.Accepted: self._palette.clear_all(); return
            lt=dlg.link_type()
            self._scene.set_mode_place("detector",{"link_type":lt})
            self._mode_lbl.setText(f"  Placing link ({lt}) — click canvas  |  Esc=cancel")

    def _on_changed(self):
        try:
            sc=self._scene
            if sc:
                try:
                    self._sys_panel.refresh(sc)
                except Exception:
                    _log_error("_sys_panel.refresh", None)
            if sc and sc._mode=="select":
                self._palette.clear_all()
                self._mode_lbl.setText("  Select  ·  Scroll=zoom  ·  Middle-drag or Ctrl+drag=pan  ·  Del=delete  ·  Right-click=options  ·  Esc=cancel")
            if not self._restoring:
                try:
                    state = json.dumps(self._project_to_dict())
                except Exception:
                    _log_error("_project_to_dict", None)
                    state = None
                if state and (not self._undo_stack or self._undo_stack[-1] != state):
                    self._undo_stack.append(state)
                    if len(self._undo_stack) > 40:
                        self._undo_stack.pop(0)
                    self._redo_stack.clear()
            self._update_undo_btns()
            self._dirty = True
            self._update_title()
        except Exception:
            _log_error("_on_changed", None)

    def _update_undo_btns(self):
        if hasattr(self, '_undo_btn'):
            self._undo_btn.setEnabled(len(self._undo_stack) > 1)
            self._redo_btn.setEnabled(bool(self._redo_stack))

    def _undo(self):
        if len(self._undo_stack) <= 1: return
        self._restoring = True
        self._redo_stack.append(self._undo_stack.pop())
        self._project_from_dict(json.loads(self._undo_stack[-1]))
        self._restoring = False
        self._update_undo_btns()

    def _redo(self):
        if not self._redo_stack: return
        self._restoring = True
        state = self._redo_stack.pop()
        self._undo_stack.append(state)
        self._project_from_dict(json.loads(state))
        self._restoring = False
        self._update_undo_btns()

    def _toggle_snap(self, checked):
        for s in self._systems: s["scene"].snap_to_grid=checked
        self._snap_btn.setText("Snap ON" if checked else "Snap OFF")
        cv=self._canvas
        if cv: cv.viewport().update()

    def _toggle_scale_bar(self, checked):
        self._show_scale = checked
        self._scale_btn.setText("Scale ON" if checked else "Scale OFF")

    def _print_pdf(self):
        if not _PRINT_AVAILABLE:
            QMessageBox.warning(self,"Print","Print support not available."); return
        import tempfile
        tmp = tempfile.mktemp(suffix=".pdf")
        systems=[(s["name"],s["scene"]) for s in self._systems]
        ok, res = export_submittal_pdf(systems, tmp, self.project_name,
                                       self._project_meta, show_scale=self._show_scale)
        if not ok:
            QMessageBox.critical(self,"Print Failed", res); return
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOrientation(QPrinter.Landscape)
        dlg = QPrintDialog(printer, self)
        if dlg.exec_() == QDialog.Accepted:
            painter = QPainter(printer)
            img = QImage(res) if False else None  # render PDF page via fitz
            doc = fitz.open(tmp)
            pg = doc[0]
            pix = pg.get_pixmap(matrix=fitz.Matrix(3,3))
            doc.close()
            qimg = QImage(pix.samples, pix.width, pix.height,
                          pix.stride, QImage.Format_RGB888)
            r = printer.pageRect()
            painter.drawImage(r, qimg)
            painter.end()
        try: os.remove(tmp)
        except: pass

    # ── Project management ───────────────────────────────────────────────────

    def _update_title(self):
        meta = self._project_meta
        cust = meta.get("customer","") or "Untitled Project"
        job  = meta.get("job_number","")
        fn   = os.path.basename(self._current_file) if self._current_file else "unsaved"
        dirty = " •" if self._dirty else ""
        parts = [cust]
        if job: parts.append(job)
        parts.append(f"[{fn}]")
        self.setWindowTitle(f"DFP TakeoffPro v{APP_VERSION}  —  Kitchen Suppression Designer   |   {' · '.join(parts)}{dirty}")

    def _project_to_dict(self):
        return {
            "version": 2,
            "meta": self._project_meta,
            "created": self._project_meta.get("_created", datetime.datetime.now().isoformat()),
            "saved":   datetime.datetime.now().isoformat(),
            "systems": [{"name":s["name"],"scene":s["scene"].to_dict()} for s in self._systems],
        }

    def _project_from_dict(self, d):
        self._project_meta = d.get("meta", {})
        self._project_meta["_created"] = d.get("created","")
        # Clear existing tabs
        while self._tab_widget.count():
            self._tab_widget.removeTab(0)
        self._systems.clear()
        # Load systems — support v1 (single scene) and v2 (systems list)
        if d.get("version",1) >= 2:
            sys_list = d.get("systems", [])
        else:
            sys_list = [{"name":"System 1","scene":d.get("scene",[])}]
        for s in sys_list:
            sys_info = self._add_system(s.get("name","System 1"))
            sys_info["scene"].load_dict(s.get("scene",[]))
        if not self._systems:
            self._add_system("System 1")
        self._tab_widget.setCurrentIndex(0)
        self._dirty = False
        self._update_title()
        cv=self._canvas
        if cv: cv.fit_all()

    def _check_unsaved(self):
        """Return True if safe to proceed (saved or user chose to discard)."""
        if not self._dirty:
            return True
        ans = QMessageBox.question(
            self, "Unsaved Changes",
            "You have unsaved changes. Save before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if ans == QMessageBox.Save:
            return self._save_project()
        return ans == QMessageBox.Discard

    def reject(self):
        if self._check_unsaved():
            super().reject()

    def closeEvent(self, event):
        if self._check_unsaved():
            event.accept()
        else:
            event.ignore()

    def _edit_project_info(self):
        dlg = ProjectInfoDialog(self._project_meta, self)
        if dlg.exec_() == QDialog.Accepted:
            self._project_meta.update(dlg.values())
            self._dirty = True
            self._update_title()

    def _new_project(self):
        if not self._check_unsaved():
            return
        dlg = ProjectInfoDialog(parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        self._project_meta = dlg.values()
        self._project_meta["_created"] = datetime.datetime.now().isoformat()
        self._current_file = None
        while self._tab_widget.count():
            self._tab_widget.removeTab(0)
        self._systems.clear()
        self._add_system("System 1")
        self._dirty = False
        self._update_title()

    def _save_project(self):
        """Save to current file; prompt for path if not yet saved. Returns True on success."""
        if not self._current_file:
            return self._save_project_as()
        try:
            with open(self._current_file, "w", encoding="utf-8") as f:
                json.dump(self._project_to_dict(), f, indent=2)
            self._dirty = False
            self._update_title()
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))
            return False

    def _save_project_as(self):
        meta  = self._project_meta
        cust  = meta.get("customer","Project").replace(" ","_")
        job   = meta.get("job_number","")
        default = f"{cust}{'_'+job if job else ''}.dfp"
        proj_dir = _projects_dir()
        name, ok = QInputDialog.getText(self, "Save Project As", "Filename:", text=default)
        if not ok or not name.strip():
            return False
        name = name.strip()
        if not name.endswith(".dfp"):
            name += ".dfp"
        path = os.path.join(proj_dir, name)
        self._current_file = path
        return self._save_project()

    def _open_project(self):
        if not self._check_unsaved():
            return
        proj_dir = _projects_dir()
        files = sorted(f for f in os.listdir(proj_dir) if f.endswith(".dfp")) if os.path.isdir(proj_dir) else []
        if not files:
            QMessageBox.information(self, "No Projects", f"No saved projects found in:\n{proj_dir}")
            return
        name, ok = QInputDialog.getItem(self, "Open Project", "Select project:", files, 0, False)
        if not ok or not name:
            return
        path = os.path.join(proj_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._current_file = path
            self._project_from_dict(data)
        except Exception as e:
            QMessageBox.critical(self, "Open Failed", str(e))

    def _fit(self): self._canvas.fit_all()

    def _clear(self):
        if QMessageBox.question(self,"Clear","Remove all items from this system?",
                                QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
            sc=self._scene
            if sc:
                for i in list(sc.items()):
                    if getattr(i,"ITEM_TYPE","") not in ("","pipe_overlay"):
                        sc.removeItem(i)
                sc.layout_changed.emit()

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_Z:
                self._undo(); return
            if event.key() in (Qt.Key_Y, Qt.Key_R):
                self._redo(); return
            if event.key() == Qt.Key_S:
                self._save_project(); return
        super().keyPressEvent(event)

    def _open_settings(self):
        try:
            dlg = AppSettingsDialog(self)
            dlg.exec_()
        except Exception:
            _log_error("_open_settings", None)

    def _export(self):
        has_content=any(s["scene"].hoods() or s["scene"].appliances() for s in self._systems)
        if not has_content:
            QMessageBox.warning(self,"Nothing to export","Add a hood and appliances first."); return
        customer = (self._project_meta.get("customer","") or "").strip()
        location = (self._project_meta.get("location","") or "").strip()
        if not customer or not location:
            missing = []
            if not customer: missing.append("Customer Name")
            if not location: missing.append("Location")
            msg = QMessageBox(self)
            msg.setWindowTitle("Missing Project Info")
            msg.setIcon(QMessageBox.Warning)
            msg.setText(f"The following fields are empty:\n• " + "\n• ".join(missing) +
                        "\n\nThe export will be missing this information.")
            enter_btn = msg.addButton("Enter Info", QMessageBox.AcceptRole)
            msg.addButton("Continue Without", QMessageBox.RejectRole)
            msg.exec_()
            if msg.clickedButton() == enter_btn:
                self._edit_project_info()
                customer = (self._project_meta.get("customer","") or "").strip()
                location = (self._project_meta.get("location","") or "").strip()
                if not customer or not location:
                    return
        pdf_dir = _submittals_dir()
        default_pdf = f"{self.project_name or 'Suppression'}_Submittal.pdf"
        name, ok = QInputDialog.getText(self, "Save Submittal PDF", "Filename:", text=default_pdf)
        if not ok or not name.strip():
            return
        name = name.strip()
        if not name.endswith(".pdf"):
            name += ".pdf"
        path = os.path.join(pdf_dir, name)
        systems=[(s["name"],s["scene"]) for s in self._systems]
        ok,res=export_submittal_pdf(systems,path,self.project_name,
                                    self._project_meta, show_scale=self._show_scale)
        if ok:
            QMessageBox.information(self,"Exported",f"Saved:\n{res}"); os.startfile(res)
        else:
            QMessageBox.critical(self,"Error",f"Export failed:\n{res}")
