"""
DFP TakeoffPro – Estimator Module
Provides:
  - PMA Inspection Quote dialog (all 4 fire protection disciplines)
  - Installation Estimate dialog (FA, Sprinkler, Ext/Suppression)
  - Programming & V.I. calculator
Data is stored in the project SQLite database (db.py).
"""

import db, estimator_export
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget,
    QWidget, QTableWidget, QTableWidgetItem, QHeaderView, QDoubleSpinBox,
    QSpinBox, QComboBox, QLineEdit, QFormLayout, QGroupBox, QSplitter,
    QScrollArea, QAbstractItemView, QMessageBox, QFrame, QSizePolicy,
    QAction, QToolBar, QMenu, QStyledItemDelegate, QStyleOptionViewItem,
    QCheckBox,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QBrush

# ── Colours (matching main app palette) ──────────────────────────────────────
C_DARK   = "#232728"
C_ORANGE = "#ff7002"
C_BLUE   = "#2980b9"
C_GREEN  = "#27ae60"
C_GREY   = "#f0f0f0"
C_DGREY  = "#d0d0d0"
C_INPUT  = "#e8f4fb"
C_TOTAL  = "#e8f8e8"

STYLE_HDR = f"background:{C_DARK};color:white;font-weight:bold;padding:6px;font-size:12px;"
STYLE_TOT = f"background:{C_TOTAL};font-weight:bold;padding:4px;"
STYLE_BTN_PRIMARY = (
    f"background:{C_ORANGE};color:white;padding:8px 16px;"
    "font-size:13px;font-weight:bold;border-radius:4px;"
)
STYLE_BTN_SECONDARY = (
    f"background:{C_DARK};color:white;padding:6px 12px;"
    "font-size:12px;font-weight:bold;border-radius:4px;"
)


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_or_create_project(project_id, job_name):
    """Return a valid project_id. Creates a new project if project_id is None."""
    if project_id:
        return project_id
    name = (job_name or "").strip() or "New Job"
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO projects(name) VALUES(?)", (name,)
        )
        conn.commit()
        return cur.lastrowid


def _init_tables():
    """Create estimator tables if they don't exist yet."""
    with db.get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pma_quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT DEFAULT 'PMA Quote',
                customer TEXT DEFAULT '',
                address  TEXT DEFAULT '',
                term_years INTEGER DEFAULT 5,
                escalation REAL DEFAULT 0.0,
                site_multiplier REAL DEFAULT 1.0,
                rate_fa_lead REAL DEFAULT 90.0,
                rate_fa_help REAL DEFAULT 65.0,
                rate_sp      REAL DEFAULT 110.0,
                rate_sg      REAL DEFAULT 65.0,
                margin_fa REAL DEFAULT 0.40,
                margin_sp REAL DEFAULT 0.40,
                margin_sg REAL DEFAULT 0.40,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pma_line_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quote_id INTEGER NOT NULL,
                discipline TEXT NOT NULL,
                item_name TEXT NOT NULL,
                techs INTEGER DEFAULT 1,
                qty REAL DEFAULT 0,
                unit_hrs REAL DEFAULT 0.0,
                frequency REAL DEFAULT 1.0,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (quote_id) REFERENCES pma_quotes(id)
            )
        """)
        # Migrations
        for sql in [
            "ALTER TABLE pma_quotes ADD COLUMN kh_data TEXT DEFAULT NULL",
            "ALTER TABLE pma_line_items ADD COLUMN fixed_sell REAL DEFAULT 0",
        ]:
            try:
                conn.execute(sql); conn.commit()
            except Exception:
                pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS install_estimates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT DEFAULT 'Install Estimate',
                discipline TEXT DEFAULT 'Fire Alarm',
                difficulty TEXT DEFAULT 'Regular',
                labour_rate REAL DEFAULT 100.0,
                material_markup REAL DEFAULT 0.25,
                labour_margin REAL DEFAULT 0.40,
                labour_factor REAL DEFAULT 1.0,
                prog_sell REAL DEFAULT 0.0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS install_line_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                estimate_id INTEGER NOT NULL,
                category TEXT DEFAULT '',
                description TEXT NOT NULL,
                qty REAL DEFAULT 0,
                unit TEXT DEFAULT 'E',
                unit_cost REAL DEFAULT 0.0,
                lu_reg  REAL DEFAULT 0.0,
                lu_diff REAL DEFAULT 0.0,
                lu_hard REAL DEFAULT 0.0,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (estimate_id) REFERENCES install_estimates(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS programming_calcs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                panel_type TEXT DEFAULT '4007es',
                num_panels INTEGER DEFAULT 0,
                job_type TEXT DEFAULT 'Stand-Alone Small',
                devices_prog_vi INTEGER DEFAULT 0,
                devices_prog    INTEGER DEFAULT 0,
                devices_vi      INTEGER DEFAULT 0,
                min_prog_vi_4007 REAL DEFAULT 4,
                min_prog_vi_4010 REAL DEFAULT 5,
                min_prog_vi_4100 REAL DEFAULT 8,
                min_prog_4007 REAL DEFAULT 4,
                min_prog_4010 REAL DEFAULT 5,
                min_prog_4100 REAL DEFAULT 8,
                min_vi_4007 REAL DEFAULT 6,
                min_vi_4010 REAL DEFAULT 6,
                min_vi_4100 REAL DEFAULT 6,
                hrs_panel_4007 REAL DEFAULT 3,
                hrs_panel_4010 REAL DEFAULT 4,
                hrs_panel_4100 REAL DEFAULT 6,
                rate_prog REAL DEFAULT 140.0,
                rate_vi   REAL DEFAULT 110.0,
                expenses  REAL DEFAULT 0.0,
                margin    REAL DEFAULT 0.40,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        conn.commit()


# ── Default PMA line items ─────────────────────────────────────────────────

PMA_DEFAULTS = {
    "Fire Alarm": [
        ("Panel (include all nodes)",           2, 1,    0.60, 1.0),
        ("Annunciator",                         2, 0,    0.15, 1.0),
        ("Transponder",                         2, 0,    0.40, 1.0),
        ("Phones",                              2, 0,    0.0334,1.0),
        ("Audio / Visual Devices",              1, 0,    0.0166,1.0),
        ("Heat Detector Conv. / Addressable",   2, 0,    0.05, 1.0),
        ("Smoke Detector Conventional",         2, 0,    0.10, 1.0),
        ("Smoke Detector Addressable",          2, 0,    0.05, 1.0),
        ("Smoke Detector – Sensitivity Test",   2, 0,    0.13, 1.0),
        ("Smoke Detector – Ducts",              2, 0,    0.20, 1.0),
        ("Pull Stations",                       2, 0,    0.0334,1.0),
        ("BEAM / Flame Detector",               2, 0,    0.50, 1.0),
        ("NAC Extender",                        2, 0,    0.20, 1.0),
        ("Smoke Alarms In-Suite",               2, 0,    0.05, 1.0),
        ("Door Holders",                        2, 0,    0.035,1.0),
        ("Relays / Fans / Monitors",            2, 0,    0.035,1.0),
        ("Dampers",                             2, 0,    0.30, 1.0),
        ("Sprinkler Zone Monitor",              1, 0,    0.035,1.0),
        ("Sprinkler Pressure Switch",           1, 0,    0.035,1.0),
        ("EOL",                                 2, 0,    0.035,1.0),
        ("Isolators",                           2, 0,    0.085,1.0),
        ("Residential Suite Entries",           1, 0,    0.05, 1.0),
        ("VESDA Inspection",                    2, 0,    0.20, 1.0),
        ("VESDA Filter Replacement",            1, 0,    0.50, 1.0),
        ("Truck Charge",                        1, 0,    0.0,  1.0, 75.0),
    ],
    "Sprinkler": [
        ("Antifreeze Glycol Loop",              1, 0,    0.50,  1.0),
        ("Backflow",                            1, 0,    0.50,  1.0),
        ("Dry Valve",                           1, 0,    1.50,  1.0),
        ("Accelerator",                         1, 0,    0.25,  1.0),
        ("Compressor",                          1, 0,    0.25,  1.0),
        ("Winterize (check low points)",        1, 0,    1.00,  1.0),
        ("Fire Pump Annual",                    2, 0,    3.00,  1.0),
        ("Fire Hydrant Inspection",             1, 0,    0.50,  1.0),
        ("Fire Hydrant Winterize",              1, 0,    0.50,  1.0),
        ("Fire Hose Valve",                     1, 0,    0.0833,1.0),
        ("Pressure Reducing / Hose Valve",      1, 0,    0.25,  1.0),
        ("Standpipe",                           1, 0,    1.00,  1.0),
        ("Sprinkler Tree Supply",               1, 0,    0.50,  1.0),
        ("Zone Control (Tamper & Flow)",        1, 0,    0.40,  1.0),
        ("Zone Control PIV",                    1, 0,    0.25,  1.0),
        ("Residential Suite Entries",           1, 0,    0.0333,1.0),
        ("Foam System",                         1, 0,    4.00,  1.0),
        ("Pre-action / Deluge",                 1, 0,    2.00,  1.0),
        ("3-yr: Dry Full Flow",                 2, 0,    3.00,  0.3333),
        ("3-yr: Dry Air Leakage",               1, 0,    1.50,  0.3333),
        ("5-yr: Internal Valve",                1, 0,    6.40,  0.20),
        ("5-yr: Obstruction",                   1, 0,    8.00,  0.20),
        ("5-yr: Gauge Replacement",             1, 0,    0.10,  0.20),
        ("Truck Charge",                        1, 0,    0.0,   1.0, 75.0),
    ],
    "Emergency Lighting": [
        # (name, techs, qty, unit_hrs, freq, fixed_sell)
        ("Packs",                               1, 0,    0.0834,1.0, 15.0),
        ("Remotes",                             1, 0,    0.05,  1.0, 15.0),
        ("Exit Signs",                          1, 0,    0.05,  1.0, 15.0),
        ("Truck Charge",                        1, 0,    0.0,   1.0, 75.0),
    ],
    "Extinguisher / Hose": [
        # (name, techs, qty, unit_hrs, freq, fixed_sell)
        ("ABC",                                 1, 0,    0.050, 1.0, 11.25),
        ("Cartridge Operated",                  1, 0,    0.250, 1.0, 11.25),
        ("FE-36 / Halotron / CO2 / K-Class",    1, 0,    0.050, 1.0, 11.25),
        ("Hose",                                1, 0,    0.125, 1.0, 12.0),
        ("Truck Charge",                        1, 0,    0.0,   1.0, 75.0),
    ],
    "Kitchen Suppression": [
        ("Kitchen Hood",                        1, 0,    1.34,  2.0),
        ("Additional Cylinders",                1, 0,    0.1667,2.0),
        ("Nozzles / Caps (per nozzle)",         1, 0,    0.050, 2.0),
        ("Fusible Link Replacement",            1, 0,    0.030, 2.0),
        ("CO2 – Pre-Bid",                       1, 0,    3.00,  2.0),
        ("CO2 Additional Cylinders",            1, 0,    0.50,  2.0),
        ("Dry Chem – Pre-Bid",                  1, 0,    2.00,  2.0),
        ("Dry Chem Additional Cylinders",       1, 0,    0.50,  2.0),
    ],
}

DISC_RATE_KEY = {
    "Fire Alarm":         "fa",
    "Emergency Lighting": "fa",
    "Sprinkler":          "sp",
    "Extinguisher / Hose":"sg",
    "Kitchen Suppression":"sg",
}
DISC_MARGIN_KEY = {
    "Fire Alarm":         "margin_fa",
    "Emergency Lighting": "margin_fa",
    "Sprinkler":          "margin_sp",
    "Extinguisher / Hose":"margin_sg",
    "Kitchen Suppression":"margin_sg",
}

# ── Default install line items ─────────────────────────────────────────────

INSTALL_DEFAULTS = {
    "Fire Alarm": [
        ("Control Panels","FACP Conventional 4-Zone",       0,"E",0, 3.00,3.75,4.50),
        ("Control Panels","FACP Conventional 8-Zone",       0,"E",0, 7.00,8.75,10.50),
        ("Control Panels","FACP Addressable (small)",       0,"E",0,12.00,15.00,18.75),
        ("Control Panels","FACP Addressable (large)",       0,"E",0,20.00,25.00,31.25),
        ("Control Panels","Remote LCD Annunciator",         0,"E",0, 2.00,2.50,3.13),
        ("Control Panels","Integrated Digital Communicator",0,"E",0, 1.00,1.25,1.60),
        ("Panel Modules", "Relay Module",                   0,"E",0, 0.90,1.13,1.41),
        ("Panel Modules", "Power Supply 6A",                0,"E",0, 2.00,2.50,3.13),
        ("Panel Modules", "Amplifier",                      0,"E",0, 2.00,2.50,3.13),
        ("Panel Modules", "Add. Addressable Loop Module",   0,"E",0, 1.00,1.25,1.56),
        ("Initiating",   "Manual Station Conventional",     0,"E",0, 0.50,0.63,0.78),
        ("Initiating",   "Manual Station Addressable",      0,"E",0, 0.50,0.63,0.78),
        ("Initiating",   "Detector Base",                   0,"E",0, 0.65,0.81,1.02),
        ("Initiating",   "Detector Head",                   0,"E",0, 0.20,0.25,0.31),
        ("Initiating",   "Duct Detector",                   0,"E",0, 2.00,2.50,3.00),
        ("Initiating",   "Beam Detector TX/RX",             0,"E",0, 4.00,5.00,6.25),
        ("Initiating",   "Flow Switch (no plumbing)",       0,"E",0, 1.20,1.50,1.88),
        ("Initiating",   "Tamper Switch (no plumbing)",     0,"E",0, 1.20,1.50,1.88),
        ("Notification", "Bell",                            0,"E",0, 0.75,0.94,1.17),
        ("Notification", "Strobe Light",                    0,"E",0, 0.75,0.94,1.17),
        ("Notification", "Horn / Strobe Combo",             0,"E",0, 0.75,0.94,1.17),
        ("Notification", "Chime / Strobe",                  0,"E",0, 0.75,0.94,1.17),
        ("Notification", "Speaker 8\" Ceiling",             0,"E",0, 1.00,1.25,1.56),
        ("Notification", "Firefighter Phone Handset",       0,"E",0, 1.20,1.50,1.88),
        ("Notification", "Firefighter Phone Jack",          0,"E",0, 0.50,0.63,0.78),
        ("Misc",         "Magnetic Door Holder",            0,"E",0, 1.00,1.25,1.56),
        ("Misc",         "Addressable Control Relay",       0,"E",0, 0.75,0.94,1.17),
        ("Misc",         "End of Line Resistor",            0,"E",0, 0.10,0.13,0.16),
        ("Wiring",       "18/2 Shielded (per 1000 LF)",     0,"M",0, 2.20,2.80,3.30),
        ("Wiring",       "18/4 Shielded (per 1000 LF)",     0,"M",0, 2.50,3.10,3.80),
        ("Conduit",      "EMT 1/2\" (per 100 LF)",          0,"C",0, 3.00,3.80,4.50),
        ("Conduit",      "EMT 3/4\" (per 100 LF)",          0,"C",0, 3.50,4.40,5.30),
        ("Conduit",      "Rigid Steel 1/2\" (per 100 LF)",  0,"C",0, 5.50,6.80,8.20),
    ],
    "Sprinkler": [
        ("Sprinkler Heads","Upright / Pendant Std Response", 0,"E",0, 0.50,0.65,0.80),
        ("Sprinkler Heads","Quick Response Upright/Pendant", 0,"E",0, 0.50,0.65,0.80),
        ("Sprinkler Heads","Concealed Pendant",              0,"E",0, 0.70,0.90,1.10),
        ("Sprinkler Heads","Extended Coverage Sidewall",     0,"E",0, 0.60,0.75,0.95),
        ("Sprinkler Heads","Dry Pendant",                    0,"E",0, 0.75,0.95,1.20),
        ("Sprinkler Heads","ESFR Upright",                   0,"E",0, 0.60,0.75,0.95),
        ("Sprinkler Heads","Residential Head",               0,"E",0, 0.45,0.58,0.72),
        ("Pipe - CPVC",   "CPVC 3/4\" (per LF)",            0,"LF",0,0.03,0.04,0.05),
        ("Pipe - CPVC",   "CPVC 1\" (per LF)",              0,"LF",0,0.03,0.04,0.05),
        ("Pipe - CPVC",   "CPVC 1-1/4\" (per LF)",          0,"LF",0,0.04,0.05,0.06),
        ("Pipe - Steel",  "Black Steel 1\" (per LF)",        0,"LF",0,0.05,0.06,0.08),
        ("Pipe - Steel",  "Black Steel 1-1/4\" (per LF)",    0,"LF",0,0.06,0.08,0.10),
        ("Pipe - Steel",  "Black Steel 1-1/2\" (per LF)",    0,"LF",0,0.07,0.09,0.11),
        ("Pipe - Steel",  "Black Steel 2\" (per LF)",        0,"LF",0,0.09,0.11,0.14),
        ("Pipe - Steel",  "Black Steel 2-1/2\" (per LF)",    0,"LF",0,0.11,0.14,0.17),
        ("Pipe - Steel",  "Black Steel 3\" (per LF)",        0,"LF",0,0.14,0.17,0.21),
        ("Pipe - Steel",  "Black Steel 4\" (per LF)",        0,"LF",0,0.18,0.22,0.28),
        ("Fittings",      "Grooved Coupling 2\"",            0,"E",0, 0.20,0.25,0.31),
        ("Fittings",      "Grooved Coupling 3\"",            0,"E",0, 0.30,0.38,0.47),
        ("Fittings",      "Grooved Coupling 4\"",            0,"E",0, 0.40,0.50,0.63),
        ("Fittings",      "Grooved Elbow 2\"",               0,"E",0, 0.25,0.31,0.39),
        ("Fittings",      "Grooved Tee 2\"",                 0,"E",0, 0.30,0.38,0.47),
        ("Hangers",       "Hanger 3/4\" – 1\"",              0,"E",0, 0.15,0.19,0.23),
        ("Hangers",       "Hanger 1-1/4\" – 2\"",            0,"E",0, 0.20,0.25,0.31),
        ("Hangers",       "Hanger 2-1/2\" – 4\"",            0,"E",0, 0.30,0.38,0.47),
        ("Hangers",       "Seismic Brace",                   0,"E",0, 0.50,0.63,0.78),
        ("Valves",        "OS&Y Gate Valve 2-1/2\"",         0,"E",0, 2.00,2.50,3.13),
        ("Valves",        "Butterfly Valve 2-1/2\"",         0,"E",0, 1.50,1.88,2.34),
        ("Valves",        "Zone Control Valve Assembly",      0,"E",0, 4.00,5.00,6.25),
        ("Valves",        "PIV Post Indicator Valve",         0,"E",0, 4.00,5.00,6.25),
        ("System",        "Alarm Check Valve 4\"",            0,"E",0, 8.00,10.00,12.50),
        ("System",        "Dry Valve Assembly 4\"",           0,"E",0,12.00,15.00,18.75),
        ("System",        "Backflow Preventer 2-1/2\"",       0,"E",0, 4.00,5.00,6.25),
        ("System",        "Inspector Test & Drain",           0,"E",0, 2.00,2.50,3.13),
        ("System",        "FDC Siamese Connection",           0,"E",0, 3.00,3.75,4.69),
        ("System",        "Flow Switch",                      0,"E",0, 1.20,1.50,1.88),
        ("System",        "Tamper Switch",                    0,"E",0, 1.20,1.50,1.88),
    ],
    "Extinguisher / Kitchen Suppression": [
        ("Portable Ext.", "ABC 2.5 lb",                      0,"E",0, 0.30,0.38,0.47),
        ("Portable Ext.", "ABC 5 lb",                        0,"E",0, 0.35,0.44,0.55),
        ("Portable Ext.", "ABC 10 lb",                       0,"E",0, 0.40,0.50,0.63),
        ("Portable Ext.", "ABC 20 lb",                       0,"E",0, 0.50,0.63,0.78),
        ("Portable Ext.", "CO2 5 lb",                        0,"E",0, 0.40,0.50,0.63),
        ("Portable Ext.", "CO2 15 lb",                       0,"E",0, 0.50,0.63,0.78),
        ("Portable Ext.", "Halotron / FE-36 5 lb",           0,"E",0, 0.40,0.50,0.63),
        ("Portable Ext.", "Class K Kitchen",                  0,"E",0, 0.50,0.63,0.78),
        ("Portable Ext.", "Cabinet (surface)",                0,"E",0, 0.75,0.94,1.17),
        ("Kitchen Supp.", "Ansul R-102 / Amerex KP System",  0,"E",0, 8.00,10.00,12.50),
        ("Kitchen Supp.", "Additional Nozzle",                0,"E",0, 0.50,0.63,0.78),
        ("Kitchen Supp.", "Additional Agent Cylinder",        0,"E",0, 0.75,0.94,1.17),
        ("Kitchen Supp.", "Gas / Electrical Shunt Trip",      0,"E",0, 1.00,1.25,1.56),
        ("Kitchen Supp.", "Mechanical Gas Valve",             0,"E",0, 1.50,1.88,2.34),
        ("Kitchen Supp.", "Fusible Link (per link)",          0,"E",0, 0.10,0.13,0.16),
        ("Kitchen Supp.", "Pull Station / Manual Release",    0,"E",0, 0.50,0.63,0.78),
        ("Kitchen Supp.", "Pipe 1/2\" SS (per LF)",           0,"LF",0,0.06,0.08,0.10),
        ("Clean Agent",   "FM-200 / Novec System (base)",    0,"E",0,16.00,20.00,25.00),
        ("Clean Agent",   "CO2 Total Flood (base)",          0,"E",0,16.00,20.00,25.00),
        ("Clean Agent",   "Additional Cylinder",              0,"E",0, 1.50,1.88,2.34),
        ("Clean Agent",   "Nozzle",                          0,"E",0, 0.75,0.94,1.17),
        ("Clean Agent",   "Solenoid Valve",                   0,"E",0, 1.00,1.25,1.56),
    ],
}


# Maps install default row descriptions → labour_units.name
# Multiple descriptions can share one LU name (e.g. both manual station types → "Manual Station")
INSTALL_LU_MAP = {
    # FA – Panels
    "FACP Conventional 4-Zone":        "FACP Conventional 4-Zone",
    "FACP Conventional 8-Zone":        "FACP Conventional 8-Zone",
    "FACP Addressable (small)":        "FACP Addressable Small",
    "FACP Addressable (large)":        "FACP Addressable Large",
    "Remote LCD Annunciator":          "Annunciator",
    "Integrated Digital Communicator": "Relay Module",
    "Relay Module":                    "Relay Module",
    "Power Supply 6A":                 "Power Supply 6A",
    "Amplifier":                       "Power Supply 6A",
    "Add. Addressable Loop Module":    "Relay Module",
    # FA – Devices
    "Manual Station Conventional":     "Manual Station",
    "Manual Station Addressable":      "Manual Station",
    "Detector Base":                   "Detector Base",
    "Detector Head":                   "Detector Head",
    "Duct Detector":                   "Duct Detector",
    "Beam Detector TX/RX":             "Beam Detector TX/RX",
    "Flow Switch (no plumbing)":       "Flow / Tamper Switch",
    "Tamper Switch (no plumbing)":     "Flow / Tamper Switch",
    "Bell":                            "Bell",
    "Strobe Light":                    "Horn / Strobe",
    "Horn / Strobe Combo":             "Horn / Strobe",
    "Chime / Strobe":                  "Horn / Strobe",
    'Speaker 8" Ceiling':              "Speaker",
    "Firefighter Phone Handset":       "Phone Handset",
    "Firefighter Phone Jack":          "Phone Jack",
    "Magnetic Door Holder":            "Door Holder / Relay",
    "Addressable Control Relay":       "Door Holder / Relay",
    "End of Line Resistor":            "Relay Module",
    # Wiring & Conduit
    "18/2 Shielded (per 1000 LF)":     "Wire 18/2 per 1000 LF",
    "18/4 Shielded (per 1000 LF)":     "Wire 18/4 per 1000 LF",
    'EMT 1/2" (per 100 LF)':           'EMT 1/2" per 100 LF',
    'EMT 3/4" (per 100 LF)':           'EMT 3/4" per 100 LF',
    'Rigid Steel 1/2" (per 100 LF)':   'Rigid Steel 1/2" per 100 LF',
    # Sprinkler
    "Upright / Pendant Std Response":  "Sprinkler Head",
    "Quick Response Upright/Pendant":  "Sprinkler Head",
    "Concealed Pendant":               "Concealed Pendant",
    "Extended Coverage Sidewall":      "Sprinkler Head",
    "Dry Pendant":                     "Dry Pendant",
    "ESFR Upright":                    "Sprinkler Head",
    "Residential Head":                "Sprinkler Head",
    'Grooved Coupling 2"':             'Grooved Coupling 2"',
    'Grooved Coupling 3"':             'Grooved Coupling 3"',
    'Grooved Coupling 4"':             'Grooved Coupling 3"',
    'Grooved Elbow 2"':                'Grooved Coupling 2"',
    'Grooved Tee 2"':                  'Grooved Coupling 2"',
    'Hanger 3/4" – 1"':           "Hanger Small",
    'Hanger 1-1/4" – 2"':         "Hanger Small",
    'Hanger 2-1/2" – 4"':         "Hanger Large",
    "Seismic Brace":                   "Hanger Large",
    "Zone Control Valve Assembly":     "Zone Control Valve Assembly",
    'Alarm Check Valve 4"':            'Alarm Check Valve 4"',
    # Ext / Suppression
    "ABC 2.5 lb":                      "Portable Extinguisher",
    "ABC 5 lb":                        "Portable Extinguisher",
    "ABC 10 lb":                       "Portable Extinguisher",
    "ABC 20 lb":                       "Portable Extinguisher",
    "CO2 5 lb":                        "Portable Extinguisher",
    "CO2 15 lb":                       "Portable Extinguisher",
    "Halotron / FE-36 5 lb":           "Portable Extinguisher",
    "Class K Kitchen":                 "Portable Extinguisher",
    "Cabinet (surface)":               "Portable Extinguisher",
    "Ansul R-102 / Amerex KP System":  "Kitchen Suppression System",
    "Additional Nozzle":               "Suppression Nozzle",
    "Additional Agent Cylinder":       "Suppression Nozzle",
    "Gas / Electrical Shunt Trip":     "Relay Module",
    "Mechanical Gas Valve":            "Zone Control Valve Assembly",
    "Fusible Link (per link)":         "Suppression Nozzle",
    "Pull Station / Manual Release":   "Manual Station",
}


def _lu_id_for_name(name, lu_name_cache={}):
    """Return lu_id for a labour_units.name, cached per session."""
    if name in lu_name_cache:
        return lu_name_cache[name]
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM labour_units WHERE name=? COLLATE NOCASE", (name,)
        ).fetchone()
    result = row["id"] if row else None
    lu_name_cache[name] = result
    return result


def _lu_id_for_desc(desc):
    """Return lu_id for an INSTALL_DEFAULTS description via INSTALL_LU_MAP."""
    lu_name = INSTALL_LU_MAP.get(desc)
    return _lu_id_for_name(lu_name) if lu_name else None


# ─────────────────────────────────────────────────────────────────────────────
# Library Picker Dialog
# ─────────────────────────────────────────────────────────────────────────────

class LibraryPickerDialog(QDialog):
    """Pick a product or assembly from the shared library to add to an estimate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add from Library")
        self.resize(700, 550)
        self.selected = None   # set on accept: dict with keys type/id/name/unit_cost/lu_reg/lu_diff/lu_hard/category
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.textChanged.connect(self._filter)
        search_row.addWidget(QLabel("Search:")); search_row.addWidget(self._search)
        layout.addLayout(search_row)

        self._tabs = QTabWidget()
        self._prod_tbl  = self._make_table(["Category","Name","Code","Unit Cost","Labour Unit","LU Reg","LU Diff","LU Hard"])
        self._asm_tbl   = self._make_table(["Category","Name","Description","Mat Cost","LU Reg","LU Diff","LU Hard"])
        self._tabs.addTab(self._prod_tbl, "Products")
        self._tabs.addTab(self._asm_tbl,  "Assemblies")
        layout.addWidget(self._tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        add    = QPushButton("Add to Estimate")
        add.setStyleSheet(STYLE_BTN_PRIMARY)
        add.clicked.connect(self._accept)
        btn_row.addWidget(cancel); btn_row.addWidget(add)
        layout.addLayout(btn_row)

        self._load_products()
        self._load_assemblies()

    def _make_table(self, headers):
        t = QTableWidget()
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        t.setAlternatingRowColors(True)
        t.doubleClicked.connect(self._accept)
        return t

    def _load_products(self):
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT id,category,name,code,unit_cost,lu_reg,lu_diff,lu_hard,lu_id "
                "FROM products ORDER BY category,name"
            ).fetchall()
        self._products = []
        for r in rows:
            lu_reg, lu_diff, lu_hard, lu_name = db.resolve_lu(r)
            p = dict(r); p["lu_reg"] = lu_reg; p["lu_diff"] = lu_diff
            p["lu_hard"] = lu_hard; p["lu_name"] = lu_name
            self._products.append(p)
        self._fill_prod_table(self._products)

    def _fill_prod_table(self, rows):
        t = self._prod_tbl
        t.setRowCount(0)
        for r in rows:
            i = t.rowCount(); t.insertRow(i)
            t.setItem(i,0, QTableWidgetItem(r["category"]))
            t.setItem(i,1, QTableWidgetItem(r["name"]))
            t.setItem(i,2, QTableWidgetItem(r.get("code","")))
            t.setItem(i,3, QTableWidgetItem(f"${r['unit_cost']:,.2f}"))
            t.setItem(i,4, QTableWidgetItem(r.get("lu_name","—")))
            t.setItem(i,5, QTableWidgetItem(f"{r.get('lu_reg',0):.3f}"))
            t.setItem(i,6, QTableWidgetItem(f"{r.get('lu_diff',0):.3f}"))
            t.setItem(i,7, QTableWidgetItem(f"{r.get('lu_hard',0):.3f}"))
            t.item(i,0).setData(Qt.UserRole, r["id"])

    def _load_assemblies(self):
        with db.get_conn() as conn:
            asms = conn.execute("SELECT id,category,name,description FROM assemblies ORDER BY category,name").fetchall()
        self._assemblies = []
        for a in asms:
            aid = a["id"]
            with db.get_conn() as conn:
                items = conn.execute(
                    "SELECT ai.quantity, p.unit_cost, p.lu_reg, p.lu_diff, p.lu_hard "
                    "FROM assembly_items ai JOIN products p ON ai.product_id=p.id WHERE ai.assembly_id=?",
                    (aid,)
                ).fetchall()
            mat  = sum(it["quantity"]*it["unit_cost"] for it in items)
            lu_r = sum(it["quantity"]*it["lu_reg"]    for it in items)
            lu_d = sum(it["quantity"]*it["lu_diff"]   for it in items)
            lu_h = sum(it["quantity"]*it["lu_hard"]   for it in items)
            self._assemblies.append({
                "id": aid, "category": a["category"], "name": a["name"],
                "description": a["description"],
                "unit_cost": mat, "lu_reg": lu_r, "lu_diff": lu_d, "lu_hard": lu_h,
            })
        self._fill_asm_table(self._assemblies)

    def _fill_asm_table(self, rows):
        t = self._asm_tbl
        t.setRowCount(0)
        for r in rows:
            i = t.rowCount(); t.insertRow(i)
            t.setItem(i,0, QTableWidgetItem(r["category"]))
            t.setItem(i,1, QTableWidgetItem(r["name"]))
            t.setItem(i,2, QTableWidgetItem(r.get("description","")))
            t.setItem(i,3, QTableWidgetItem(f"${r['unit_cost']:,.2f}"))
            t.setItem(i,4, QTableWidgetItem(f"{r['lu_reg']:.3f}"))
            t.setItem(i,5, QTableWidgetItem(f"{r['lu_diff']:.3f}"))
            t.setItem(i,6, QTableWidgetItem(f"{r['lu_hard']:.3f}"))
            t.item(i,0).setData(Qt.UserRole, r["id"])

    def _filter(self, text):
        q = text.lower()
        self._fill_prod_table([r for r in self._products
                                if q in r["name"].lower() or q in r["category"].lower()])
        self._fill_asm_table([r for r in self._assemblies
                               if q in r["name"].lower() or q in r["category"].lower()])

    def _accept(self):
        tab = self._tabs.currentIndex()
        tbl = self._prod_tbl if tab == 0 else self._asm_tbl
        row = tbl.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select Item", "Please select an item first.")
            return
        src_id = tbl.item(row, 0).data(Qt.UserRole)
        if tab == 0:
            rec = next((p for p in self._products if p["id"] == src_id), None)
            if rec:
                self.selected = {"type": "product", "id": src_id,
                                 "name": rec["name"], "category": rec["category"],
                                 "unit_cost": rec["unit_cost"],
                                 "lu_reg": rec.get("lu_reg",0),
                                 "lu_diff": rec.get("lu_diff",0),
                                 "lu_hard": rec.get("lu_hard",0)}
        else:
            rec = next((a for a in self._assemblies if a["id"] == src_id), None)
            if rec:
                self.selected = {"type": "assembly", "id": src_id,
                                 "name": rec["name"], "category": rec["category"],
                                 "unit_cost": rec["unit_cost"],
                                 "lu_reg": rec["lu_reg"],
                                 "lu_diff": rec["lu_diff"],
                                 "lu_hard": rec["lu_hard"]}
        if self.selected:
            self.accept()


# ─────────────────────────────────────────────────────────────────────────────
# Small helper widgets
# ─────────────────────────────────────────────────────────────────────────────

def _hline():
    f = QFrame(); f.setFrameShape(QFrame.HLine); f.setFrameShadow(QFrame.Sunken)
    return f

def _bold_label(text, size=11):
    lbl = QLabel(text)
    lbl.setFont(QFont("Arial", size, QFont.Bold))
    return lbl

def _money(v):
    if v == 0:
        return "-"
    return f"${v:,.2f}"

class _Spin(QSpinBox):
    def wheelEvent(self, e): e.ignore()

class _DSpin(QDoubleSpinBox):
    def wheelEvent(self, e): e.ignore()


def _make_spin(decimals=2, min_val=0.0, max_val=99999.0, val=0.0, step=1.0, suffix=""):
    s = _DSpin()
    s.setDecimals(decimals); s.setMinimum(min_val); s.setMaximum(max_val)
    s.setValue(val); s.setSingleStep(step)
    if suffix:
        s.setSuffix(suffix)
    s.setAlignment(Qt.AlignRight)
    s.setStyleSheet("background:#e8f4fb;")
    return s


# ─────────────────────────────────────────────────────────────────────────────
# PMA QUOTE DIALOG
# ─────────────────────────────────────────────────────────────────────────────

DISCIPLINES = [
    "Fire Alarm",
    "Sprinkler",
    "Emergency Lighting",
    "Extinguisher / Hose",
    "Kitchen Suppression",
]


class PmaQuoteDialog(QDialog):
    def __init__(self, project_id=None, parent=None):
        super().__init__(parent)
        self._initial_project_id = project_id  # may be None
        self.project_id = project_id
        self.quote_id   = None
        self._recalc_timer = QTimer(self)
        self._recalc_timer.setSingleShot(True)
        self._recalc_timer.timeout.connect(self._recalc)
        self.setWindowTitle("PMA Inspection Quote")
        self.setWindowState(Qt.WindowMaximized)
        _init_tables()
        self._quote = {"customer":"","address":"","term_years":5,"escalation":0.0,
                       "site_multiplier":1.0,"rate_fa_lead":90,"rate_fa_help":65,
                       "rate_sp":110,"rate_sg":65,
                       "margin_fa":0.40,"margin_sp":0.40,"margin_sg":0.40}
        self._build_ui()
        # Load after UI so job_name field exists; project created on first save
        if self.project_id:
            self._load_or_create_quote()
            self._populate_tabs()
        self._recalc()

    # ── Data layer ─────────────────────────────────────────────────────────

    def _ensure_project(self, job_name=""):
        """Create project on first save if we started without one."""
        if not self.project_id:
            self.project_id = _get_or_create_project(None, job_name or "PMA Quote")
        else:
            # Update project name if user changed the job name field
            if job_name:
                with db.get_conn() as conn:
                    conn.execute("UPDATE projects SET name=? WHERE id=?",
                                 (job_name, self.project_id))
                    conn.commit()

    def _load_or_create_quote(self, job_name=""):
        self._ensure_project(job_name)
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM pma_quotes WHERE project_id=? ORDER BY id DESC LIMIT 1",
                (self.project_id,)
            ).fetchone()
            if row:
                self.quote_id = row["id"]
                self._quote = dict(row)
                kh_raw = row["kh_data"] if "kh_data" in row.keys() else None
                if kh_raw and hasattr(self, "_kh_location"):
                    self._apply_kh_data(kh_raw)
                elif kh_raw:
                    self._kh_pending_data = kh_raw
            else:
                cur = conn.execute(
                    "INSERT INTO pma_quotes(project_id) VALUES(?)",
                    (self.project_id,)
                )
                conn.commit()
                self.quote_id = cur.lastrowid
                self._quote = {"id": self.quote_id, "project_id": self.project_id,
                               "customer":"","address":"","term_years":5,"escalation":0.0,
                               "site_multiplier":1.0,"rate_fa_lead":90,"rate_fa_help":65,
                               "rate_sp":110,"rate_sg":65,
                               "margin_fa":0.40,"margin_sp":0.40,"margin_sg":0.40}
                # Seed default line items
                for disc, items in PMA_DEFAULTS.items():
                    for sort_i, row in enumerate(items):
                        name,techs,qty,unit_hrs,freq = row[:5]
                        fixed_sell = row[5] if len(row) > 5 else 0.0
                        conn.execute(
                            "INSERT INTO pma_line_items"
                            "(quote_id,discipline,item_name,techs,qty,unit_hrs,frequency,sort_order,fixed_sell)"
                            " VALUES(?,?,?,?,?,?,?,?,?)",
                            (self.quote_id, disc, name, techs, qty, unit_hrs, freq, sort_i, fixed_sell)
                        )
                conn.commit()

    def _load_items(self, discipline):
        with db.get_conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM pma_line_items WHERE quote_id=? AND discipline=? ORDER BY sort_order",
                (self.quote_id, discipline)
            ).fetchall()]

    def _save_header(self):
        q = self._quote
        kh_json = self._collect_kh_data() if hasattr(self, "_kh_location") else None
        with db.get_conn() as conn:
            conn.execute("""
                UPDATE pma_quotes SET customer=?,address=?,term_years=?,escalation=?,
                site_multiplier=?,rate_fa_lead=?,rate_fa_help=?,rate_sp=?,rate_sg=?,
                margin_fa=?,margin_sp=?,margin_sg=?,kh_data=? WHERE id=?
            """, (q.get("customer",""),q.get("address",""),
                  q.get("term_years",5),q.get("escalation",0.0),
                  q.get("site_multiplier",1.0),
                  q.get("rate_fa_lead",100),q.get("rate_fa_help",75),
                  q.get("rate_sp",110),q.get("rate_sg",90),
                  q.get("margin_fa",0.35),q.get("margin_sp",0.32),q.get("margin_sg",0.32),
                  kh_json, self.quote_id))
            conn.commit()

    def _save_item_row(self, item_id, techs, qty, unit_hrs, frequency):
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE pma_line_items SET techs=?,qty=?,unit_hrs=?,frequency=? WHERE id=?",
                (techs, qty, unit_hrs, frequency, item_id)
            )
            conn.commit()

    # ── UI build ───────────────────────────────────────────────────────────

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(6); main_layout.setContentsMargins(8,8,8,8)

        # Title
        title = QLabel("PMA INSPECTION QUOTE")
        title.setStyleSheet(STYLE_HDR + "font-size:15px;border-radius:4px;")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # Header form
        hdr_box = QGroupBox("Quote Details")
        hdr_form = QHBoxLayout(hdr_box)

        left_form = QFormLayout()
        # Job name field — creates/names the project
        existing_name = ""
        if self.project_id:
            with db.get_conn() as conn:
                prow = conn.execute("SELECT name FROM projects WHERE id=?",
                                    (self.project_id,)).fetchone()
                if prow: existing_name = prow["name"]
        self.e_job_name = QLineEdit(existing_name)
        self.e_job_name.setPlaceholderText("Enter job / project name…")
        self.e_job_name.setStyleSheet("background:#fff3cd;font-weight:bold;")
        left_form.addRow("Job Name:", self.e_job_name)
        self.e_customer = QLineEdit(self._quote.get("customer",""))
        self.e_address  = QLineEdit(self._quote.get("address",""))
        left_form.addRow("Customer:", self.e_customer)
        left_form.addRow("Address:",  self.e_address)

        mid_form = QFormLayout()
        self.sp_term = _Spin(); self.sp_term.setRange(1,10)
        self.sp_term.setValue(int(self._quote.get("term_years",5)))
        self.sp_escal = _make_spin(1,0,20,self._quote.get("escalation",0.03)*100, suffix="%")
        self.sp_site  = _make_spin(2,0.5,2.0,self._quote.get("site_multiplier",1.0),0.1)
        mid_form.addRow("Term (years):", self.sp_term)
        mid_form.addRow("Escalation/yr:", self.sp_escal)
        mid_form.addRow("Site Multiplier:", self.sp_site)

        rate_form = QFormLayout()
        rate_form.addRow(QLabel("<b>Burdened Cost Rates</b>"))
        self.sp_rate_fa_lead = _make_spin(0,0,500,self._quote.get("rate_fa_lead",90),5,suffix=" $/hr")
        self.sp_rate_fa_help = _make_spin(0,0,500,self._quote.get("rate_fa_help",65), 5,suffix=" $/hr")
        self.sp_rate_sp      = _make_spin(0,0,500,self._quote.get("rate_sp",110),     5,suffix=" $/hr")
        self.sp_rate_sg      = _make_spin(0,0,500,self._quote.get("rate_sg",65),      5,suffix=" $/hr")
        rate_form.addRow("FA Lead (burdened):",   self.sp_rate_fa_lead)
        rate_form.addRow("FA Helper (burdened):", self.sp_rate_fa_help)
        rate_form.addRow("SP (burdened):",        self.sp_rate_sp)
        rate_form.addRow("SG/EXT (burdened):",    self.sp_rate_sg)

        margin_form = QFormLayout()
        self.sp_margin_fa = _make_spin(0,0,99,self._quote.get("margin_fa",0.35)*100,1,suffix="%")
        self.sp_margin_sp = _make_spin(0,0,99,self._quote.get("margin_sp",0.32)*100,1,suffix="%")
        self.sp_margin_sg = _make_spin(0,0,99,self._quote.get("margin_sg",0.32)*100,1,suffix="%")
        margin_form.addRow("FA Margin:", self.sp_margin_fa)
        margin_form.addRow("SP Margin:", self.sp_margin_sp)
        margin_form.addRow("SG Margin:", self.sp_margin_sg)

        for f in (left_form, mid_form, rate_form, margin_form):
            w = QWidget(); w.setLayout(f)
            hdr_form.addWidget(w)

        main_layout.addWidget(hdr_box)

        # Discipline tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { min-width: 160px; padding: 6px 12px; }")
        self._disc_tables = {}
        for disc in DISCIPLINES:
            if disc == "Kitchen Suppression":
                tab = self._build_kitchen_tab()
            else:
                tab = self._build_disc_tab(disc)
            self.tabs.addTab(tab, disc)
        main_layout.addWidget(self.tabs, stretch=1)

        # Pricing summary bar
        summary_box = QGroupBox("Pricing Summary")
        sum_layout = QHBoxLayout(summary_box)
        self._sum_labels = {}
        for disc in DISCIPLINES + ["TOTAL ANNUAL", "CONTRACT VALUE"]:
            col = QVBoxLayout()
            name_lbl = QLabel(disc)
            name_lbl.setAlignment(Qt.AlignCenter)
            name_lbl.setFont(QFont("Arial", 8, QFont.Bold))
            val_lbl = QLabel("-")
            val_lbl.setAlignment(Qt.AlignCenter)
            val_lbl.setFont(QFont("Arial", 11, QFont.Bold))
            if disc in ("TOTAL ANNUAL", "CONTRACT VALUE"):
                val_lbl.setStyleSheet(f"color:{C_ORANGE};")
            col.addWidget(name_lbl); col.addWidget(val_lbl)
            sum_layout.addLayout(col)
            self._sum_labels[disc] = val_lbl
            if disc not in ("TOTAL ANNUAL", "CONTRACT VALUE"):
                sum_layout.addWidget(_hline())

        main_layout.addWidget(summary_box)

        # Buttons
        btn_row = QHBoxLayout()
        export_tab_btn = QPushButton("Export Current Tab")
        export_tab_btn.setStyleSheet(STYLE_BTN_SECONDARY)
        export_tab_btn.clicked.connect(self._export_current_tab)
        btn_row.addWidget(export_tab_btn)
        export_all_btn = QPushButton("Export All to Excel")
        export_all_btn.setStyleSheet(STYLE_BTN_SECONDARY)
        export_all_btn.clicked.connect(self._export_excel)
        btn_row.addWidget(export_all_btn)
        btn_row.addStretch()
        save_btn = QPushButton("Save & Close")
        save_btn.setStyleSheet(STYLE_BTN_PRIMARY)
        save_btn.clicked.connect(self._save_and_close)
        btn_row.addWidget(save_btn)
        main_layout.addLayout(btn_row)

        # Connect signals
        for w in (self.e_job_name, self.e_customer, self.e_address):
            w.textChanged.connect(self._on_header_change)
        for w in (self.sp_term, self.sp_escal, self.sp_site,
                  self.sp_rate_fa_lead, self.sp_rate_fa_help,
                  self.sp_rate_sp, self.sp_rate_sg,
                  self.sp_margin_fa, self.sp_margin_sp, self.sp_margin_sg):
            w.valueChanged.connect(self._on_header_change)
        # SG margin drives KS per-system margin spinboxes
        self.sp_margin_sg.valueChanged.connect(self._push_sg_margin_to_kh)
        # Sync initial value
        self._push_sg_margin_to_kh(self.sp_margin_sg.value())

        # Disable scroll-wheel on all spinboxes unless they have keyboard focus
    def _build_disc_tab(self, discipline):
        widget = QWidget()
        layout = QVBoxLayout(widget); layout.setContentsMargins(4,4,4,4); layout.setSpacing(4)

        # Add item button
        add_row = QHBoxLayout()
        add_btn = QPushButton("+ Add Item")
        add_btn.setStyleSheet(STYLE_BTN_SECONDARY)
        add_btn.clicked.connect(lambda _, d=discipline: self._add_item(d))
        add_row.addWidget(add_btn); add_row.addStretch()
        layout.addLayout(add_row)

        # Table
        tbl = QTableWidget()
        tbl.setColumnCount(10)
        tbl.setHorizontalHeaderLabels([
            "Item Description", "Techs Req'd", "Quantity",
            "Unit Hours", "Adj. Hours", "Minutes",
            "Frequency", "Ext. Hours", "$/unit", "Del"
        ])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col, w in enumerate([None,70,80,80,80,70,80,90,80,40]):
            if w:
                tbl.setColumnWidth(col, w)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        layout.addWidget(tbl, stretch=1)

        # Totals row
        tot_row = QHBoxLayout()
        tot_lbl = QLabel("Total Man-Hours: –   |   Hours to Complete: –   |   Labour Cost: –   |   Sell Price: –")
        tot_lbl.setStyleSheet(STYLE_TOT)
        tot_row.addWidget(tot_lbl)
        layout.addLayout(tot_row)

        self._disc_tables[discipline] = {"table": tbl, "total_lbl": tot_lbl}
        return widget

    # ── Kitchen Suppression (KH Inspections Calculator) ───────────────────

    _KH_CARTRIDGES = [
        ("cart_rg",   "RG Test Cartridge",          14.0),
        ("cart_a12",  "A+ 12g CO2 Cartridge",       12.0),
        ("cart_pyro", "Pyrochem 16g CO2 Cartridge", 28.0),
        ("cart_buck", "Buckeye AC-s Cartridge",      30.0),
    ]
    _KH_LOCATIONS = [
        ("Calgary",  0.500),
        ("Cochrane", 0.833),
        ("Airdrie",  0.667),
        ("Okotoks",  0.833),
        ("Other",    None),
    ]

    def _build_kitchen_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        hdr = QLabel("Kitchen Suppression — KH Inspections Pricing Calculator")
        hdr.setStyleSheet("font-weight:bold; font-size:13px;")
        layout.addWidget(hdr)

        info = QLabel("Uses SG/EXT burden rate and site multiplier from header.  Per-system margin set below.")
        info.setStyleSheet("color:#555; font-size:10px; font-style:italic;")
        layout.addWidget(info)

        # Location / travel
        loc_box = QGroupBox("Location / Travel")
        loc_form = QFormLayout(loc_box)
        self._kh_location = QComboBox()
        for name, hrs in self._KH_LOCATIONS:
            self._kh_location.addItem(name, hrs)
        self._kh_travel_spin = _DSpin()
        self._kh_travel_spin.setRange(0, 24); self._kh_travel_spin.setDecimals(3)
        self._kh_travel_spin.setSuffix(" hr"); self._kh_travel_spin.setValue(0.5)
        self._kh_travel_spin.setEnabled(False)

        def _on_loc_changed(idx):
            hrs = self._kh_location.currentData()
            if hrs is not None:
                self._kh_travel_spin.setValue(hrs)
                self._kh_travel_spin.setEnabled(False)
            else:
                self._kh_travel_spin.setEnabled(True)
            self._on_kh_change()

        self._kh_location.currentIndexChanged.connect(_on_loc_changed)
        self._kh_travel_spin.valueChanged.connect(self._on_kh_change)
        loc_row = QHBoxLayout()
        loc_row.addWidget(self._kh_location)
        loc_row.addWidget(QLabel("  Travel one-way:"))
        loc_row.addWidget(self._kh_travel_spin)
        loc_row.addStretch()
        loc_form.addRow("Location:", loc_row)
        layout.addWidget(loc_box)

        # Number of systems
        nsys_row = QHBoxLayout()
        nsys_row.addWidget(QLabel("Number of systems on site:"))
        self._kh_num_systems = _Spin()
        self._kh_num_systems.setRange(0, 3); self._kh_num_systems.setValue(0)
        self._kh_num_systems.valueChanged.connect(self._on_kh_num_systems_changed)
        nsys_row.addWidget(self._kh_num_systems)
        nsys_row.addStretch()
        layout.addLayout(nsys_row)

        # Per-system group boxes
        self._kh_sys_widgets = []
        for i in range(3):
            title = f"System {i+1}" + ("  ·  includes call-out / travel fee" if i == 0 else "")
            box = QGroupBox(title)
            form = QFormLayout(box)

            on_site = _DSpin()
            on_site.setRange(0, 24); on_site.setDecimals(2); on_site.setSingleStep(0.25)
            on_site.setSuffix(" hr"); on_site.setValue(1.5)
            on_site.valueChanged.connect(self._on_kh_change)
            form.addRow("On-site hours:", on_site)

            links = _Spin()
            links.setRange(0, 100); links.setValue(0)
            links.valueChanged.connect(self._on_kh_change)
            form.addRow("Fusible links:", links)

            cart_checks = {}
            for key, label, cost in self._KH_CARTRIDGES:
                chk = QCheckBox(f"{label}  (${cost:.0f})")
                chk.stateChanged.connect(self._on_kh_change)
                form.addRow("", chk)
                cart_checks[key] = chk

            margin_spin = _DSpin()
            margin_spin.setRange(0, 99); margin_spin.setDecimals(1)
            margin_spin.setSuffix("%"); margin_spin.setValue(35.0)
            margin_spin.valueChanged.connect(self._on_kh_change)
            form.addRow("Gross margin:", margin_spin)

            cogs_lbl = QLabel("COGS: —")
            sell_lbl = QLabel("Sell: —")
            sell_lbl.setStyleSheet(f"font-weight:bold; color:{C_ORANGE};")
            res_row = QHBoxLayout()
            res_row.addWidget(cogs_lbl); res_row.addWidget(sell_lbl); res_row.addStretch()
            res_w = QWidget(); res_w.setLayout(res_row)
            form.addRow(res_w)

            layout.addWidget(box)
            self._kh_sys_widgets.append({
                "box": box, "on_site": on_site, "links": links,
                "carts": cart_checks, "margin": margin_spin,
                "cogs_lbl": cogs_lbl, "sell_lbl": sell_lbl,
            })
            if i > 0:
                box.setVisible(False)

        self._kh_total_lbl = QLabel("Total Kitchen Suppression: —")
        self._kh_total_lbl.setStyleSheet(STYLE_TOT)
        layout.addWidget(self._kh_total_lbl)
        layout.addStretch()

        # Wrap in scroll area so adding systems never squeezes the summary bar
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        return scroll

    def _on_kh_num_systems_changed(self, n):
        for i, w in enumerate(self._kh_sys_widgets):
            w["box"].setVisible(i < n)
        self._on_kh_change()

    def _on_kh_change(self):
        self._recalc_timer.start(200)

    def _push_sg_margin_to_kh(self, val):
        for sw in self._kh_sys_widgets:
            sw["margin"].blockSignals(True)
            sw["margin"].setValue(val)
            sw["margin"].blockSignals(False)
        self._recalc_timer.start(200)

    def _recalc_kitchen(self):
        labour_rate = self.sp_rate_sg.value()
        site_mult   = self.sp_site.value()
        LINK_COST   = 9.0
        CART_COSTS  = {"cart_rg": 14.0, "cart_a12": 12.0, "cart_pyro": 28.0, "cart_buck": 30.0}
        travel_hrs  = self._kh_travel_spin.value()
        num_sys     = self._kh_num_systems.value()
        total_sell  = 0.0
        if num_sys == 0:
            for sw in self._kh_sys_widgets:
                sw["cogs_lbl"].setText("COGS: —")
                sw["sell_lbl"].setText("Sell: —")
            self._kh_total_lbl.setText("Total Kitchen Suppression: —")
            return 0.0
        for i, sw in enumerate(self._kh_sys_widgets):
            if i >= num_sys:
                continue
            on_site  = sw["on_site"].value() * site_mult   # site multiplier applied
            links    = sw["links"].value()
            margin   = sw["margin"].value() / 100.0
            labour   = on_site * labour_rate
            if i == 0:
                labour += travel_hrs * labour_rate  # call-out / travel fee on first system
            link_cost = links * LINK_COST
            cart_cost = sum(CART_COSTS[k] for k, chk in sw["carts"].items() if chk.isChecked())
            cogs = labour + link_cost + cart_cost
            sell = cogs / (1 - margin) if margin < 1 else cogs
            sw["cogs_lbl"].setText(f"COGS: {_money(cogs)}")
            sw["sell_lbl"].setText(f"Sell: {_money(sell)}")
            total_sell += sell
        self._kh_total_lbl.setText(f"Total Kitchen Suppression: {_money(total_sell)}")
        return total_sell

    def _collect_kh_data(self):
        import json as _json
        loc_idx = self._kh_location.currentIndex()
        systems = []
        for sw in self._kh_sys_widgets:
            systems.append({
                "on_site_hrs":   sw["on_site"].value(),
                "fusible_links": sw["links"].value(),
                "carts":         {k: chk.isChecked() for k, chk in sw["carts"].items()},
                "margin":        sw["margin"].value(),
            })
        return _json.dumps({
            "location_idx": loc_idx,
            "travel_hrs":   self._kh_travel_spin.value(),
            "num_systems":  self._kh_num_systems.value(),
            "systems":      systems,
        })

    def _apply_kh_data(self, raw_json):
        import json as _json
        try:
            d = _json.loads(raw_json)
        except Exception:
            return
        loc_idx = d.get("location_idx", 0)
        if 0 <= loc_idx < self._kh_location.count():
            self._kh_location.setCurrentIndex(loc_idx)
        hrs = d.get("travel_hrs", 0.5)
        if self._kh_location.currentData() is None:
            self._kh_travel_spin.setValue(hrs)
        num = d.get("num_systems", 1)
        self._kh_num_systems.setValue(num)
        for i, sw in enumerate(self._kh_sys_widgets):
            sd = d.get("systems", [{}] * 3)[i] if i < len(d.get("systems", [])) else {}
            sw["on_site"].setValue(sd.get("on_site_hrs", 1.5))
            sw["links"].setValue(sd.get("fusible_links", 6))
            for k, chk in sw["carts"].items():
                chk.setChecked(sd.get("carts", {}).get(k, False))
            sw["margin"].setValue(sd.get("margin", 35.0))

    def _populate_tabs(self):
        for disc in DISCIPLINES:
            if disc == "Kitchen Suppression":
                continue
            items = self._load_items(disc)
            self._populate_disc_table(disc, items)
        # Apply any KH data loaded before the UI was ready
        if hasattr(self, "_kh_pending_data") and self._kh_pending_data:
            self._apply_kh_data(self._kh_pending_data)
            self._kh_pending_data = None

    def _populate_disc_table(self, discipline, items):
        entry = self._disc_tables[discipline]
        tbl = entry["table"]
        tbl.setRowCount(0)
        tbl.blockSignals(True)
        for item in items:
            r = tbl.rowCount(); tbl.insertRow(r)
            # Description
            name_item = QTableWidgetItem(item["item_name"])
            name_item.setData(Qt.UserRole, item["id"])
            tbl.setItem(r, 0, name_item)
            # Techs
            techs_spin = _Spin(); techs_spin.setRange(1,4); techs_spin.setValue(int(item["techs"]))
            techs_spin.valueChanged.connect(lambda v, row=r, d=discipline: self._on_cell_change(d, row))
            tbl.setCellWidget(r, 1, techs_spin)
            # Qty
            qty_spin = _DSpin(); qty_spin.setDecimals(0); qty_spin.setRange(0,9999); qty_spin.setValue(float(item["qty"]))
            qty_spin.valueChanged.connect(lambda v, row=r, d=discipline: self._on_cell_change(d, row))
            tbl.setCellWidget(r, 2, qty_spin)
            # Unit hrs
            uh_spin = _DSpin(); uh_spin.setDecimals(4); uh_spin.setRange(0,100); uh_spin.setValue(float(item["unit_hrs"])); uh_spin.setSingleStep(0.01)
            uh_spin.valueChanged.connect(lambda v, row=r, d=discipline: self._on_cell_change(d, row))
            tbl.setCellWidget(r, 3, uh_spin)
            # Adj hrs (calculated)
            adj = QTableWidgetItem(); adj.setFlags(Qt.ItemIsEnabled); adj.setBackground(QBrush(QColor(C_GREY)))
            tbl.setItem(r, 4, adj)
            # Minutes (calculated)
            mins = QTableWidgetItem(); mins.setFlags(Qt.ItemIsEnabled); mins.setBackground(QBrush(QColor(C_GREY)))
            tbl.setItem(r, 5, mins)
            # Frequency
            freq_spin = _DSpin(); freq_spin.setDecimals(4); freq_spin.setRange(0,52); freq_spin.setValue(float(item["frequency"])); freq_spin.setSingleStep(1)
            freq_spin.valueChanged.connect(lambda v, row=r, d=discipline: self._on_cell_change(d, row))
            tbl.setCellWidget(r, 6, freq_spin)
            # Ext hours (calculated)
            ext = QTableWidgetItem(); ext.setFlags(Qt.ItemIsEnabled); ext.setBackground(QBrush(QColor(C_GREY)))
            tbl.setItem(r, 7, ext)
            # Fixed sell $/unit (0 = use hours calc)
            fs_spin = _DSpin(); fs_spin.setDecimals(2); fs_spin.setRange(0, 99999)
            fs_spin.setValue(float(item.get("fixed_sell") or 0)); fs_spin.setPrefix("$")
            fs_spin.valueChanged.connect(lambda v, row=r, d=discipline: self._on_cell_change(d, row))
            tbl.setCellWidget(r, 8, fs_spin)
            # Delete button
            del_btn = QPushButton("✕"); del_btn.setFixedWidth(32)
            del_btn.setStyleSheet("color:red;font-weight:bold;")
            del_btn.clicked.connect(lambda _, iid=item["id"], d=discipline: self._delete_item(iid, d))
            tbl.setCellWidget(r, 9, del_btn)
        tbl.blockSignals(False)

    def _add_item(self, discipline):
        if not self.quote_id:
            job_name = self.e_job_name.text().strip() or "PMA Quote"
            self._ensure_project(job_name)
            self._load_or_create_quote(job_name)
        with db.get_conn() as conn:
            sort_max = conn.execute(
                "SELECT MAX(sort_order) FROM pma_line_items WHERE quote_id=? AND discipline=?",
                (self.quote_id, discipline)
            ).fetchone()[0] or 0
            cur = conn.execute(
                "INSERT INTO pma_line_items(quote_id,discipline,item_name,techs,qty,unit_hrs,frequency,sort_order,fixed_sell)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (self.quote_id, discipline, "New Item", 1, 0, 0.1, 1.0, sort_max+1, 0.0)
            )
            conn.commit()
            new_id = cur.lastrowid
        items = self._load_items(discipline)
        self._populate_disc_table(discipline, items)
        self._recalc()

    def _delete_item(self, item_id, discipline):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM pma_line_items WHERE id=?", (item_id,))
            conn.commit()
        items = self._load_items(discipline)
        self._populate_disc_table(discipline, items)
        self._recalc()

    def _on_header_change(self, *args):
        self._recalc_timer.start(200)

    def _on_cell_change(self, discipline, row):
        self._recalc_timer.start(200)

    # ── Recalc ─────────────────────────────────────────────────────────────

    def _get_rate(self, discipline):
        key = DISC_RATE_KEY.get(discipline, "fa")
        if key == "fa":
            lead = self.sp_rate_fa_lead.value()
            helper = self.sp_rate_fa_help.value()
            return (lead + helper) / 2  # blended
        elif key == "sp":
            return self.sp_rate_sp.value()
        else:
            return self.sp_rate_sg.value()

    def _get_margin(self, discipline):
        key = DISC_MARGIN_KEY.get(discipline, "margin_fa")
        return getattr(self, f"sp_{key}").value() / 100.0

    def _recalc(self):
        site_mult = self.sp_site.value()
        disc_sells = {}

        for disc in DISCIPLINES:
            if disc == "Kitchen Suppression":
                disc_sells[disc] = self._recalc_kitchen()
                continue

            entry = self._disc_tables[disc]
            tbl = entry["table"]
            total_man_hrs = 0.0
            hrs_to_complete = 0.0

            fixed_sell_total = 0.0
            for r in range(tbl.rowCount()):
                techs      = tbl.cellWidget(r, 1).value() if tbl.cellWidget(r,1) else 1
                qty        = tbl.cellWidget(r, 2).value() if tbl.cellWidget(r,2) else 0
                uh         = tbl.cellWidget(r, 3).value() if tbl.cellWidget(r,3) else 0
                freq       = tbl.cellWidget(r, 6).value() if tbl.cellWidget(r,6) else 1
                fixed_unit = tbl.cellWidget(r, 8).value() if tbl.cellWidget(r,8) else 0
                adj_h  = site_mult * uh
                mins   = adj_h * 60
                ext_h  = adj_h * freq * qty * techs

                item4 = tbl.item(r,4); item5 = tbl.item(r,5); item7 = tbl.item(r,7)
                if item4: item4.setText(f"{adj_h:.4f}")
                if item5: item5.setText(f"{mins:.1f}")
                if item7: item7.setText(f"{ext_h:.2f}")

                if fixed_unit > 0:
                    fixed_sell_total += qty * freq * fixed_unit
                else:
                    total_man_hrs += ext_h
                    if techs > 0:
                        hrs_to_complete += ext_h / techs

            rate   = self._get_rate(disc)
            margin = self._get_margin(disc)
            cost   = total_man_hrs * rate
            sell   = (cost / (1 - margin) if margin < 1 else cost) + fixed_sell_total

            disc_sells[disc] = sell
            entry["total_lbl"].setText(
                f"Total Man-Hours: {total_man_hrs:.2f}  |  "
                f"Hrs to Complete: {hrs_to_complete:.2f}  |  "
                f"Labour Cost: {_money(cost)}  |  "
                f"Sell Price: {_money(sell)}"
            )

        total = sum(disc_sells.values())
        term  = self.sp_term.value()
        escal = self.sp_escal.value() / 100.0

        # Contract value = sum of escalating annual payments
        # Year i costs: total × (1+e)^(i-1) for i=1..term
        if escal > 0:
            contract_val = total * ((1 + escal) ** term - 1) / escal
        else:
            contract_val = total * term

        for disc in DISCIPLINES:
            self._sum_labels[disc].setText(_money(disc_sells.get(disc,0)))
        self._sum_labels["TOTAL ANNUAL"].setText(_money(total))
        self._sum_labels["CONTRACT VALUE"].setText(_money(contract_val))

    # ── Save ───────────────────────────────────────────────────────────────

    def _collect_header(self):
        self._quote["customer"]       = self.e_customer.text()
        self._quote["address"]        = self.e_address.text()
        self._quote["term_years"]     = self.sp_term.value()
        self._quote["escalation"]     = self.sp_escal.value() / 100.0
        self._quote["site_multiplier"]= self.sp_site.value()
        self._quote["rate_fa_lead"]   = self.sp_rate_fa_lead.value()
        self._quote["rate_fa_help"]   = self.sp_rate_fa_help.value()
        self._quote["rate_sp"]        = self.sp_rate_sp.value()
        self._quote["rate_sg"]        = self.sp_rate_sg.value()
        self._quote["margin_fa"]      = self.sp_margin_fa.value() / 100.0
        self._quote["margin_sp"]      = self.sp_margin_sp.value() / 100.0
        self._quote["margin_sg"]      = self.sp_margin_sg.value() / 100.0

    def _collect_table_rows(self):
        for disc in DISCIPLINES:
            if disc == "Kitchen Suppression":
                continue
            tbl = self._disc_tables[disc]["table"]
            for r in range(tbl.rowCount()):
                item_id = tbl.item(r,0).data(Qt.UserRole) if tbl.item(r,0) else None
                if not item_id:
                    continue
                techs = tbl.cellWidget(r,1).value() if tbl.cellWidget(r,1) else 1
                qty   = tbl.cellWidget(r,2).value() if tbl.cellWidget(r,2) else 0
                uh    = tbl.cellWidget(r,3).value() if tbl.cellWidget(r,3) else 0
                freq  = tbl.cellWidget(r,6).value() if tbl.cellWidget(r,6) else 1
                fs    = tbl.cellWidget(r,8).value() if tbl.cellWidget(r,8) else 0
                name  = tbl.item(r,0).text() if tbl.item(r,0) else ""
                with db.get_conn() as conn:
                    conn.execute(
                        "UPDATE pma_line_items SET item_name=?,techs=?,qty=?,unit_hrs=?,frequency=?,fixed_sell=? WHERE id=?",
                        (name, techs, qty, uh, freq, fs, item_id)
                    )
                    conn.commit()

    def _export_current_tab(self):
        disc = DISCIPLINES[self.tabs.currentIndex()]
        self._run_export(discipline=disc)

    def _export_excel(self):
        self._run_export(discipline=None)

    def _run_export(self, discipline=None):
        from PyQt5.QtWidgets import QFileDialog
        self._collect_header(); self._save_header(); self._collect_table_rows()
        if not self.project_id or not self.quote_id:
            job_name = self.e_job_name.text().strip() or "PMA Quote"
            self._load_or_create_quote(job_name)
        suffix = discipline.replace(" / ", "_").replace(" ", "_") if discipline else "All"
        default_name = f"DFP_PMA_{suffix}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PMA Quote to Excel", default_name,
            "Excel Files (*.xlsx)"
        )
        if not path:
            return
        ok, result = estimator_export.export_estimates(
            self.project_id, path, discipline=discipline
        )
        if ok:
            QMessageBox.information(self, "Export Complete",
                f"Exported to:\n{result}\n\nBlue cells = enter into Uptick.")
        else:
            QMessageBox.critical(self, "Export Failed", result)

    def _save_and_close(self):
        self._collect_header()
        job_name = self.e_job_name.text().strip() or "PMA Quote"
        if not self.project_id or not self.quote_id:
            self._load_or_create_quote(job_name)
            self._populate_tabs()
        else:
            self._ensure_project(job_name)
        self._save_header()
        self._collect_table_rows()
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
# INSTALLATION ESTIMATE DIALOG
# ─────────────────────────────────────────────────────────────────────────────

INSTALL_DISCIPLINES = list(INSTALL_DEFAULTS.keys())

class InstallEstimateDialog(QDialog):
    def __init__(self, project_id=None, parent=None):
        super().__init__(parent)
        self.project_id  = project_id
        self.estimate_id = None
        self._recalc_timer = QTimer(self)
        self._recalc_timer.setSingleShot(True)
        self._recalc_timer.timeout.connect(self._recalc)
        self.setWindowTitle("Installation Estimate")
        self.setWindowState(Qt.WindowMaximized)
        _init_tables()
        self._est = {"discipline": INSTALL_DISCIPLINES[0], "difficulty": "Regular",
                     "labour_rate": 90.0, "material_margin": 0.40,
                     "labour_margin": 0.40, "labour_factor": 1.0, "prog_sell": 0.0}
        self._excluded_lu  = set()  # in-memory exclusions before first DB save
        self._excluded_pid = set()
        self._build_ui()
        if self.project_id:
            self._load_or_create_estimate()
            self._populate_table()
        else:
            self._populate_defaults(INSTALL_DISCIPLINES[0])
        self._recalc()

    # ── Data ───────────────────────────────────────────────────────────────

    def _load_or_create_estimate(self, job_name=""):
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM install_estimates WHERE project_id=? ORDER BY id DESC LIMIT 1",
                (self.project_id,)
            ).fetchone()
            if row:
                self.estimate_id = row["id"]
                self._est = dict(row)
            else:
                cur = conn.execute(
                    "INSERT INTO install_estimates(project_id) VALUES(?)",
                    (self.project_id,)
                )
                conn.commit()
                self.estimate_id = cur.lastrowid
                self._est = {"id": self.estimate_id, "project_id": self.project_id,
                             "discipline": INSTALL_DISCIPLINES[0],
                             "difficulty": "Regular",
                             "labour_rate": 90.0, "material_margin": 0.40,
                             "labour_margin": 0.40, "labour_factor": 1.0,
                             "prog_sell": 0.0}
                self._seed_items(INSTALL_DISCIPLINES[0])

    @staticmethod
    def _product_lookup():
        """Return dict of lowercase product name -> product dict with resolved LU values."""
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT id, name, unit_cost, lu_reg, lu_diff, lu_hard, lu_id FROM products"
            ).fetchall()
        result = {}
        for r in rows:
            lu_reg, lu_diff, lu_hard, _ = db.resolve_lu(r)
            result[r["name"].lower()] = {
                "id": r["id"], "name": r["name"], "unit_cost": r["unit_cost"],
                "lu_reg": lu_reg, "lu_diff": lu_diff, "lu_hard": lu_hard,
            }
        return result

    def _seed_items(self, discipline):
        defaults = INSTALL_DEFAULTS.get(discipline, [])
        _lu_id_for_name.cache_clear() if hasattr(_lu_id_for_name, 'cache_clear') else None
        with db.get_conn() as conn:
            conn.execute("DELETE FROM install_line_items WHERE estimate_id=?", (self.estimate_id,))
            for i, (cat, desc, qty, unit, ucost, lu_r, lu_d, lu_h) in enumerate(defaults):
                lu_id = _lu_id_for_desc(desc)
                # If LU found, pull its values; else use hardcoded defaults
                if lu_id:
                    lu_row = conn.execute(
                        "SELECT lu_reg,lu_diff,lu_hard FROM labour_units WHERE id=?", (lu_id,)
                    ).fetchone()
                    if lu_row:
                        lu_r, lu_d, lu_h = lu_row["lu_reg"], lu_row["lu_diff"], lu_row["lu_hard"]
                conn.execute(
                    "INSERT INTO install_line_items"
                    "(estimate_id,category,description,qty,unit,unit_cost,"
                    " lu_reg,lu_diff,lu_hard,sort_order,lu_id)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (self.estimate_id, cat, desc, qty, unit, ucost, lu_r, lu_d, lu_h, i, lu_id)
                )
            conn.commit()

    def _load_items(self):
        with db.get_conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM install_line_items WHERE estimate_id=? ORDER BY sort_order",
                (self.estimate_id,)
            ).fetchall()]

    def _auto_link_rows(self):
        """Set lu_id on any row that has none, via INSTALL_LU_MAP name lookup."""
        for r in range(self.tbl.rowCount()):
            cell = self.tbl.item(r, 0)
            if not cell or cell.data(Qt.UserRole + 2):
                continue  # already has lu_id
            desc = self.tbl.item(r, 1).text().strip() if self.tbl.item(r, 1) else ""
            lu_id = _lu_id_for_desc(desc)
            if not lu_id:
                continue
            cell.setData(Qt.UserRole + 2, lu_id)
            cat = cell.text().replace("⬡ ", "")
            cell.setText(f"⬡ {cat}")
            item_id = cell.data(Qt.UserRole)
            if item_id:
                with db.get_conn() as conn:
                    conn.execute(
                        "UPDATE install_line_items SET lu_id=? WHERE id=?", (lu_id, item_id)
                    )
                    conn.commit()

    def _populate_defaults(self, discipline):
        """Populate table from INSTALL_DEFAULTS without touching DB (no project yet)."""
        lookup = self._product_lookup()
        self.tbl.setRowCount(0)
        self.tbl.blockSignals(True)
        for cat, desc, qty, unit, ucost, lu_r, lu_d, lu_h in INSTALL_DEFAULTS.get(discipline, []):
            lu_id = _lu_id_for_desc(desc)
            fake = {"id": None, "category": cat, "description": desc,
                    "qty": qty, "unit": unit, "unit_cost": ucost,
                    "lu_reg": lu_r, "lu_diff": lu_d, "lu_hard": lu_h,
                    "lu_id": lu_id, "source_type": "manual", "source_id": None}
            self._insert_table_row(fake)
        self.tbl.blockSignals(False)
        self._auto_link_rows()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(6); main.setContentsMargins(8,8,8,8)

        title = QLabel("INSTALLATION ESTIMATE")
        title.setStyleSheet(STYLE_HDR + "font-size:15px;border-radius:4px;")
        title.setAlignment(Qt.AlignCenter)
        main.addWidget(title)

        # Header settings
        hdr_box = QGroupBox("Estimate Settings")
        hdr_layout = QHBoxLayout(hdr_box)

        # Job name
        f0 = QFormLayout()
        existing_name = ""
        if self.project_id:
            with db.get_conn() as conn:
                prow = conn.execute("SELECT name FROM projects WHERE id=?",
                                    (self.project_id,)).fetchone()
                if prow: existing_name = prow["name"]
        self.e_job_name = QLineEdit(existing_name)
        self.e_job_name.setPlaceholderText("Enter job / project name…")
        self.e_job_name.setStyleSheet("background:#fff3cd;font-weight:bold;")
        f0.addRow("Job Name:", self.e_job_name)
        w0 = QWidget(); w0.setLayout(f0)
        hdr_layout.addWidget(w0)

        f1 = QFormLayout()
        self.cb_disc = QComboBox()
        self.cb_disc.addItems(INSTALL_DISCIPLINES)
        idx = INSTALL_DISCIPLINES.index(self._est.get("discipline", INSTALL_DISCIPLINES[0]))
        self.cb_disc.setCurrentIndex(idx)
        self.cb_disc.currentTextChanged.connect(self._on_discipline_change)
        f1.addRow("Discipline:", self.cb_disc)

        self.cb_diff = QComboBox()
        self.cb_diff.addItems(["Regular", "Difficult", "Hard"])
        self.cb_diff.setCurrentText(self._est.get("difficulty","Regular"))
        self.cb_diff.currentTextChanged.connect(lambda _: self._recalc_timer.start(100))
        f1.addRow("Difficulty:", self.cb_diff)

        f2 = QFormLayout()
        self.sp_rate  = _make_spin(0,0,500,self._est.get("labour_rate",90),5,suffix=" $/hr")
        self.sp_mat_mu = _make_spin(0,0,99,self._est.get("material_margin",0.40)*100,1,suffix="%")
        f2.addRow("Burdened Labour Rate:", self.sp_rate)
        f2.addRow("Material Margin:", self.sp_mat_mu)

        f3 = QFormLayout()
        self.sp_lab_margin = _make_spin(0,0,99,self._est.get("labour_margin",0.40)*100,1,suffix="%")
        self.sp_factor = _make_spin(2,0.5,3.0,self._est.get("labour_factor",1.0),0.05)
        f3.addRow("Labour Margin:", self.sp_lab_margin)
        f3.addRow("Labour Factor:", self.sp_factor)

        f4 = QFormLayout()
        self.sp_prog_sell = _make_spin(2,0,999999,self._est.get("prog_sell",0.0),100)
        f4.addRow("Prog / V.I. Sell $:", self.sp_prog_sell)

        f5 = QFormLayout()
        self.chk_labour = QCheckBox("Include Labour")
        self.chk_labour.setChecked(bool(self._est.get("labour_included", 1)))
        self.chk_labour.setStyleSheet("font-weight:bold;font-size:13px;")
        self.chk_labour.stateChanged.connect(self._on_labour_toggle)
        f5.addRow("", self.chk_labour)

        for f in (f1,f2,f3,f4,f5):
            w = QWidget(); w.setLayout(f)
            hdr_layout.addWidget(w)
        main.addWidget(hdr_box)

        # Table header label
        diff_label = QLabel("Enter quantities in the Qty column. Unit costs and labour units are editable. Calculated columns update automatically.")
        diff_label.setStyleSheet("color:#555;font-size:10px;padding:2px;")
        main.addWidget(diff_label)

        # Main table
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(11)
        self.tbl.setHorizontalHeaderLabels([
            "Category", "Description", "Qty", "Unit",
            "Unit Cost", "Ext. Material",
            "LU (Reg)", "LU (Diff)", "LU (Hard)",
            "LU Used", "Ext. Labour Hrs"
        ])
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for col, w in [(0,110),(2,65),(3,45),(4,85),(5,95),(6,75),(7,75),(8,75),(9,75),(10,90)]:
            self.tbl.setColumnWidth(col, w)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._row_context_menu)
        main.addWidget(self.tbl, stretch=1)

        # Add / remove row buttons
        row_btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add Row")
        add_btn.setStyleSheet(STYLE_BTN_SECONDARY)
        add_btn.clicked.connect(self._add_row)
        lib_btn = QPushButton("Add from Library")
        lib_btn.setStyleSheet(f"background:{C_BLUE};color:white;padding:6px 12px;font-size:12px;font-weight:bold;border-radius:4px;")
        lib_btn.clicked.connect(self._add_from_library)
        imp_btn = QPushButton("Update from Takeoff")
        imp_btn.setStyleSheet(f"background:#27ae60;color:white;padding:6px 12px;font-size:12px;font-weight:bold;border-radius:4px;")
        imp_btn.clicked.connect(self._import_from_takeoff)
        del_btn = QPushButton("Remove Selected")
        del_btn.setStyleSheet("background:#c02b0a;color:white;padding:6px 12px;font-size:12px;border-radius:4px;")
        del_btn.clicked.connect(self._remove_selected_rows)
        row_btn_row.addWidget(add_btn); row_btn_row.addWidget(lib_btn)
        row_btn_row.addWidget(imp_btn); row_btn_row.addWidget(del_btn)
        row_btn_row.addStretch()
        main.addLayout(row_btn_row)

        # Summary panel
        sum_box = QGroupBox("Cost Summary")
        sum_layout = QHBoxLayout(sum_box)

        self._sum = {}
        for key, label in [
            ("mat_cost",   "Material Cost"),
            ("mat_sell",   "Material Sell"),
            ("lab_hrs",    "Labour Hours"),
            ("lab_cost",   "Labour Cost"),
            ("lab_sell",   "Labour Sell"),
            ("prog",       "Prog / V.I."),
            ("total_sell", "TOTAL SELL"),
            ("margin",     "Est. Margin"),
        ]:
            col = QVBoxLayout()
            nl = QLabel(label); nl.setAlignment(Qt.AlignCenter)
            nl.setFont(QFont("Arial",8,QFont.Bold))
            vl = QLabel("-"); vl.setAlignment(Qt.AlignCenter)
            vl.setFont(QFont("Arial", 12 if key in ("total_sell","margin") else 10, QFont.Bold))
            if key in ("total_sell","margin"):
                vl.setStyleSheet(f"color:{C_ORANGE};")
            col.addWidget(nl); col.addWidget(vl)
            sum_layout.addLayout(col)
            self._sum[key] = vl
            if key != "margin":
                sum_layout.addWidget(_hline())

        main.addWidget(sum_box)

        # Buttons
        btn_row = QHBoxLayout()
        exp_btn = QPushButton("Export to Excel")
        exp_btn.setStyleSheet(STYLE_BTN_SECONDARY)
        exp_btn.clicked.connect(self._export_excel)
        btn_row.addWidget(exp_btn)
        btn_row.addStretch()
        save_btn = QPushButton("Save & Close")
        save_btn.setStyleSheet(STYLE_BTN_PRIMARY)
        save_btn.clicked.connect(self._save_and_close)
        btn_row.addWidget(save_btn)
        main.addLayout(btn_row)

        # Connect signals
        for w in (self.sp_rate, self.sp_mat_mu, self.sp_lab_margin, self.sp_factor, self.sp_prog_sell):
            w.valueChanged.connect(lambda _: self._recalc_timer.start(100))

    def _populate_table(self):
        items = self._load_items()
        self.tbl.setRowCount(0)
        self.tbl.blockSignals(True)
        for item in items:
            self._insert_table_row(item)
        self.tbl.blockSignals(False)
        self._auto_link_rows()

    def _insert_table_row(self, item=None):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)

        row_lu_id = item.get("lu_id") if item else None
        cat_text = (item["category"] if item else "")
        if row_lu_id:
            cat_text = f"⬡ {cat_text}"
        cat = QTableWidgetItem(cat_text)
        cat.setData(Qt.UserRole,     item["id"] if item else None)
        cat.setData(Qt.UserRole + 1, item.get("source_id"))
        cat.setData(Qt.UserRole + 2, row_lu_id)
        cat.setData(Qt.UserRole + 3, item.get("source_type", "manual") if item else "manual")
        self.tbl.setItem(r, 0, cat)

        desc = QTableWidgetItem(item["description"] if item else "New Item")
        self.tbl.setItem(r, 1, desc)

        qty_spin = _DSpin(); qty_spin.setDecimals(1); qty_spin.setRange(0,99999)
        qty_spin.setValue(float(item["qty"]) if item else 0)
        qty_spin.valueChanged.connect(lambda _: self._recalc_timer.start(100))
        self.tbl.setCellWidget(r, 2, qty_spin)

        unit_item = QTableWidgetItem(item["unit"] if item else "E")
        unit_item.setTextAlignment(Qt.AlignCenter)
        self.tbl.setItem(r, 3, unit_item)

        uc_spin = _DSpin(); uc_spin.setDecimals(2); uc_spin.setRange(0,999999)
        uc_spin.setValue(float(item["unit_cost"]) if item else 0)
        uc_spin.setPrefix("$")
        uc_spin.valueChanged.connect(lambda _: self._recalc_timer.start(100))
        self.tbl.setCellWidget(r, 4, uc_spin)

        # Ext material (calc)
        ext_mat = QTableWidgetItem(); ext_mat.setFlags(Qt.ItemIsEnabled)
        ext_mat.setBackground(QBrush(QColor(C_GREY))); self.tbl.setItem(r, 5, ext_mat)

        # LU inputs
        for col, attr in [(6,"lu_reg"),(7,"lu_diff"),(8,"lu_hard")]:
            sp = _DSpin(); sp.setDecimals(3); sp.setRange(0,100)
            sp.setValue(float(item[attr]) if item else 0)
            sp.setSingleStep(0.05)
            sp.valueChanged.connect(lambda _: self._recalc_timer.start(100))
            self.tbl.setCellWidget(r, col, sp)

        # LU used (calc)
        lu_used = QTableWidgetItem(); lu_used.setFlags(Qt.ItemIsEnabled)
        lu_used.setBackground(QBrush(QColor(C_GREY))); self.tbl.setItem(r, 9, lu_used)

        # Ext hours (calc)
        ext_hrs = QTableWidgetItem(); ext_hrs.setFlags(Qt.ItemIsEnabled)
        ext_hrs.setBackground(QBrush(QColor(C_GREEN if item else C_GREY)))
        self.tbl.setItem(r, 10, ext_hrs)

    def _add_row(self):
        if not self.estimate_id:
            job_name = self.e_job_name.text().strip() or "Install Estimate"
            if not self.project_id:
                self.project_id = _get_or_create_project(None, job_name)
            self._load_or_create_estimate(job_name)
            self._populate_table()  # sync table with seeded DB rows
        with db.get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO install_line_items(estimate_id,description,qty,unit,sort_order)"
                " VALUES(?,?,?,?,?)",
                (self.estimate_id, "New Item", 0, "E",
                 self.tbl.rowCount())
            )
            conn.commit()
            new_id = cur.lastrowid
        fake = {"id":new_id,"category":"","description":"New Item","qty":0,"unit":"E",
                "unit_cost":0,"lu_reg":0,"lu_diff":0,"lu_hard":0}
        self.tbl.blockSignals(True)
        self._insert_table_row(fake)
        self.tbl.blockSignals(False)
        self._recalc()

    def _on_labour_toggle(self):
        include = self.chk_labour.isChecked()
        # Grey out labour columns visually
        for col in (6, 7, 8, 9, 10):
            for r in range(self.tbl.rowCount()):
                item = self.tbl.item(r, col)
                if item:
                    item.setForeground(QBrush(QColor("#999999" if not include else "#000000")))
        self._recalc()

    def _add_from_library(self):
        dlg = LibraryPickerDialog(self)
        if dlg.exec_() != QDialog.Accepted or not dlg.selected:
            return
        sel = dlg.selected
        # Check if this product is already in the table
        for r in range(self.tbl.rowCount()):
            cell = self.tbl.item(r, 0)
            if cell and cell.data(Qt.UserRole + 1) == sel["id"]:
                self.tbl.selectRow(r)
                QMessageBox.information(self, "Already Present",
                    f"'{sel['name']}' is already in the estimate (row {r+1}).\n"
                    "Adjust the quantity there instead.")
                return

        # Ensure estimate exists in DB before inserting
        if not self.estimate_id:
            job_name = self.e_job_name.text().strip() or "Install Estimate"
            if not self.project_id:
                self.project_id = _get_or_create_project(None, job_name)
            self._load_or_create_estimate(job_name)
            self._populate_table()
        with db.get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO install_line_items"
                "(estimate_id,category,description,qty,unit,unit_cost,lu_reg,lu_diff,lu_hard,sort_order,source_type,source_id)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.estimate_id, sel["category"], sel["name"], 0, "E",
                 sel["unit_cost"], sel["lu_reg"], sel["lu_diff"], sel["lu_hard"],
                 self.tbl.rowCount(), sel["type"], sel["id"])
            )
            # Clear any exclusion for this product so import can update it
            conn.execute(
                "DELETE FROM install_estimate_excluded WHERE estimate_id=? AND product_id=?",
                (self.estimate_id, sel["id"])
            )
            conn.commit()
            new_id = cur.lastrowid
        row = {"id": new_id, "category": sel["category"], "description": sel["name"],
               "qty": 0, "unit": "E", "unit_cost": sel["unit_cost"],
               "lu_reg": sel["lu_reg"], "lu_diff": sel["lu_diff"], "lu_hard": sel["lu_hard"]}
        self.tbl.blockSignals(True)
        self._insert_table_row(row)
        self.tbl.blockSignals(False)
        self._recalc()

    def _row_context_menu(self, pos):
        row = self.tbl.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu(self)
        link_action = menu.addAction("Link to Product…")
        unlink_action = menu.addAction("Unlink Product")
        action = menu.exec_(self.tbl.viewport().mapToGlobal(pos))
        if action == link_action:
            self._link_row_to_product(row)
        elif action == unlink_action:
            self._unlink_row(row)

    def _link_row_to_product(self, row):
        dlg = LibraryPickerDialog(self)
        dlg._tabs.setCurrentIndex(0)  # products only makes sense for linking
        if dlg.exec_() != QDialog.Accepted or not dlg.selected:
            return
        sel = dlg.selected
        item_id = self.tbl.item(row, 0).data(Qt.UserRole) if self.tbl.item(row, 0) else None
        # Update DB if row is saved
        if item_id:
            with db.get_conn() as conn:
                conn.execute(
                    "UPDATE install_line_items SET source_type='product', source_id=? WHERE id=?",
                    (sel["id"], item_id)
                )
                conn.commit()
        # Store link in the cell's extra role so import can find it in memory too
        if self.tbl.item(row, 0):
            self.tbl.item(row, 0).setData(Qt.UserRole + 1, sel["id"])
            cat_text = self.tbl.item(row, 0).text().replace("⬡ ", "")
            self.tbl.item(row, 0).setText(f"⬡ {cat_text}")
        QMessageBox.information(self, "Linked",
            f"Row linked to product: {sel['name']}.\n"
            "Takeoff imports will now update this row's qty.")

    def _unlink_row(self, row):
        item_id = self.tbl.item(row, 0).data(Qt.UserRole) if self.tbl.item(row, 0) else None
        if item_id:
            with db.get_conn() as conn:
                conn.execute(
                    "UPDATE install_line_items SET source_type='manual', source_id=NULL, lu_id=NULL WHERE id=?",
                    (item_id,)
                )
                conn.commit()
        if self.tbl.item(row, 0):
            self.tbl.item(row, 0).setData(Qt.UserRole + 1, None)
            self.tbl.item(row, 0).setData(Qt.UserRole + 2, None)
            cat_text = self.tbl.item(row, 0).text().replace("⬡ ", "")
            self.tbl.item(row, 0).setText(cat_text)

    def _import_from_takeoff(self):
        if not self.project_id:
            job_name = self.e_job_name.text().strip()
            if not job_name:
                QMessageBox.information(self, "Job Required",
                    "Enter a job name first so we know which takeoff to import from.")
                return
            self.project_id = _get_or_create_project(None, job_name)

        # Pull all takeoff counts including product lu_id
        with db.get_conn() as conn:
            rows = conn.execute("""
                SELECT p.id, p.name, p.category, p.unit_cost,
                       p.lu_reg, p.lu_diff, p.lu_hard, p.lu_id,
                       SUM(ti.count) as total_count
                FROM takeoff_items ti
                JOIN products p ON ti.product_id = p.id
                WHERE ti.project_id = ? AND ti.count > 0
                GROUP BY p.id
                ORDER BY p.category, p.name
            """, (self.project_id,)).fetchall()

        # Build lu_groups / no_lu from whatever is in the takeoff (may be empty)
        lu_groups_pre = {}
        no_lu_pre = {}
        for r in rows:
            qty  = float(r["total_count"])
            lu_id = r["lu_id"]
            if lu_id:
                if lu_id not in lu_groups_pre:
                    lu_groups_pre[lu_id] = {"qty": 0.0, "mat_cost": 0.0}
                lu_groups_pre[lu_id]["qty"]      += qty
                lu_groups_pre[lu_id]["mat_cost"] += qty * (r["unit_cost"] or 0)
            else:
                no_lu_pre[r["id"]] = r

        if not rows and not self.estimate_id:
            QMessageBox.information(self, "No Takeoff",
                "No items counted on the print for this job yet.")
            return

        # Confirm with user
        if rows:
            msg_body = (f"Found {len(rows)} product(s) with counts.\n\n"
                        "Products sharing a Labour Unit will be combined into one row.\n"
                        "Rows removed from the print will be removed from the estimate.")
        else:
            msg_body = "No items in the takeoff — all previously imported rows will be removed."

        reply = QMessageBox.question(self, "Sync from Takeoff", msg_body,
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        if not self.estimate_id:
            self._load_or_create_estimate(self.e_job_name.text().strip() or "Install Estimate")
            self._populate_table()

        self._auto_link_rows()

        # Load exclusions for this estimate
        excluded_lu = set()
        excluded_pid = set()
        if self.estimate_id:
            with db.get_conn() as conn:
                for ex in conn.execute(
                    "SELECT lu_id, product_id FROM install_estimate_excluded WHERE estimate_id=?",
                    (self.estimate_id,)
                ).fetchall():
                    if ex["lu_id"]:  excluded_lu.add(ex["lu_id"])
                    if ex["product_id"]: excluded_pid.add(ex["product_id"])
        excluded_lu  |= self._excluded_lu
        excluded_pid |= self._excluded_pid

        # ── Takeoff groups (already built above as lu_groups_pre / no_lu_pre) ──
        lu_groups = lu_groups_pre
        no_lu = {pid: {
            "name": d["name"], "category": d["category"],
            "qty": float(d["total_count"]), "unit_cost": d["unit_cost"] or 0,
            "lu_reg": d["lu_reg"] or 0, "lu_diff": d["lu_diff"] or 0,
            "lu_hard": d["lu_hard"] or 0,
        } for pid, d in no_lu_pre.items()}

        # ── Build maps from existing table rows ───────────────────────────────
        lu_row_map  = {}   # lu_id       → table row index
        pid_row_map = {}   # product_id  → table row index (source_id fallback)
        for r in range(self.tbl.rowCount()):
            cell = self.tbl.item(r, 0)
            if not cell:
                continue
            row_lu_id = cell.data(Qt.UserRole + 2)
            if row_lu_id:
                lu_row_map[row_lu_id] = r
            src_id = cell.data(Qt.UserRole + 1)
            if src_id:
                pid_row_map[src_id] = r

        added = updated = 0

        def _update_row(tbl_row, qty, uc, item_id, lu_id_val=None):
            w = self.tbl.cellWidget(tbl_row, 2)
            if w:
                w.blockSignals(True); w.setValue(qty); w.blockSignals(False)
            uc_w = self.tbl.cellWidget(tbl_row, 4)
            if uc_w:
                uc_w.blockSignals(True); uc_w.setValue(uc); uc_w.blockSignals(False)
            if item_id:
                with db.get_conn() as conn:
                    conn.execute(
                        "UPDATE install_line_items SET qty=?,unit_cost=? WHERE id=?",
                        (qty, uc, item_id)
                    )
                    conn.commit()

        # ── Process LU-grouped products ───────────────────────────────────────
        sort_start = self.tbl.rowCount()
        for lu_id, data in lu_groups.items():
            qty = data["qty"]
            uc  = data["mat_cost"] / qty if qty else 0
            if lu_id in excluded_lu and lu_id not in lu_row_map:
                continue  # user deleted this row — don't re-add
            if lu_id in lu_row_map:
                tbl_row = lu_row_map[lu_id]
                item_id = self.tbl.item(tbl_row, 0).data(Qt.UserRole)
                _update_row(tbl_row, qty, uc, item_id)
                updated += 1
            else:
                # Get LU name and values for the new row
                with db.get_conn() as conn:
                    lu_rec = conn.execute(
                        "SELECT name,category,lu_reg,lu_diff,lu_hard FROM labour_units WHERE id=?",
                        (lu_id,)
                    ).fetchone()
                if not lu_rec:
                    continue
                with db.get_conn() as conn:
                    cur = conn.execute(
                        "INSERT INTO install_line_items"
                        "(estimate_id,category,description,qty,unit,unit_cost,"
                        " lu_reg,lu_diff,lu_hard,sort_order,lu_id,source_type)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (self.estimate_id, lu_rec["category"], lu_rec["name"],
                         qty, "E", uc, lu_rec["lu_reg"], lu_rec["lu_diff"],
                         lu_rec["lu_hard"], sort_start, lu_id, "import_lu")
                    )
                    conn.commit()
                row_dict = {
                    "id": cur.lastrowid, "category": lu_rec["category"],
                    "description": lu_rec["name"], "qty": qty,
                    "unit": "E", "unit_cost": uc,
                    "lu_reg": lu_rec["lu_reg"], "lu_diff": lu_rec["lu_diff"],
                    "lu_hard": lu_rec["lu_hard"], "lu_id": lu_id,
                    "source_type": "import_lu", "source_id": None,
                }
                self.tbl.blockSignals(True)
                self._insert_table_row(row_dict)
                self.tbl.blockSignals(False)
                sort_start += 1
                added += 1

        # ── Process no-LU products (name match or new row) ────────────────────
        for pid, data in no_lu.items():
            if pid in excluded_pid and pid not in pid_row_map:
                continue  # user deleted this row — don't re-add
            if pid in pid_row_map:
                tbl_row = pid_row_map[pid]
                item_id = self.tbl.item(tbl_row, 0).data(Qt.UserRole)
                _update_row(tbl_row, data["qty"], data["unit_cost"], item_id)
                updated += 1
            else:
                with db.get_conn() as conn:
                    cur = conn.execute(
                        "INSERT INTO install_line_items"
                        "(estimate_id,category,description,qty,unit,unit_cost,"
                        " lu_reg,lu_diff,lu_hard,sort_order,source_type,source_id)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (self.estimate_id, data["category"], data["name"],
                         data["qty"], "E", data["unit_cost"],
                         data["lu_reg"], data["lu_diff"], data["lu_hard"],
                         sort_start, "product", pid)
                    )
                    conn.commit()
                row_dict = {
                    "id": cur.lastrowid, "category": data["category"],
                    "description": data["name"], "qty": data["qty"],
                    "unit": "E", "unit_cost": data["unit_cost"],
                    "lu_reg": data["lu_reg"], "lu_diff": data["lu_diff"],
                    "lu_hard": data["lu_hard"], "lu_id": None,
                    "source_type": "product", "source_id": pid,
                }
                self.tbl.blockSignals(True)
                self._insert_table_row(row_dict)
                self.tbl.blockSignals(False)
                sort_start += 1
                added += 1

        # ── Remove rows whose takeoff count has gone to zero ──────────────────
        # Only removes rows that:
        #   1. Are explicitly tracked in lu_row_map or pid_row_map (they were
        #      already in the table with a lu_id or source_id link)
        #   2. Have source_type 'import_lu' or 'product' (were created by a
        #      previous import, not manually added or seeded as defaults)
        #   3. Whose lu_id / source_id is no longer in the current takeoff
        rows_to_remove = set()
        for lu_id_key, tbl_row in lu_row_map.items():
            if lu_id_key in lu_groups:
                continue  # still in takeoff — keep
            cell = self.tbl.item(tbl_row, 0)
            if cell and cell.data(Qt.UserRole + 3) in ("import_lu", "product"):
                rows_to_remove.add(tbl_row)
        for pid_key, tbl_row in pid_row_map.items():
            if pid_key in no_lu:
                continue  # still in takeoff — keep
            cell = self.tbl.item(tbl_row, 0)
            if cell and cell.data(Qt.UserRole + 3) in ("import_lu", "product"):
                rows_to_remove.add(tbl_row)

        removed = 0
        for r in sorted(rows_to_remove, reverse=True):
            cell = self.tbl.item(r, 0)
            if not cell:
                continue
            item_id = cell.data(Qt.UserRole)
            if item_id:
                with db.get_conn() as conn:
                    conn.execute("DELETE FROM install_line_items WHERE id=?", (item_id,))
                    conn.commit()
            self.tbl.removeRow(r)
            removed += 1

        # ── Linear assembly runs ──────────────────────────────────────────────
        import math as _math
        with db.get_conn() as conn:
            lin_rows = conn.execute("""
                SELECT lr.assembly_id,
                       a.name, a.category,
                       a.wire_count, a.bundle_factor, a.prep_lu_per_wire,
                       a.lu_reg, a.lu_diff, a.lu_hard,
                       a.wire_lu_reg, a.wire_lu_diff, a.wire_lu_hard,
                       SUM(lr.footage) as total_footage
                FROM linear_runs lr
                JOIN assemblies a ON lr.assembly_id = a.id
                WHERE lr.project_id = ?
                GROUP BY lr.assembly_id
            """, (self.project_id,)).fetchall()

        for lr in lin_rows:
            aid     = lr["assembly_id"]
            footage = float(lr["total_footage"] or 0)
            n       = lr["wire_count"] or 1
            bf      = lr["bundle_factor"] or 0.35
            prep    = lr["prep_lu_per_wire"] or 0.0
            c_reg, c_diff, c_hard = lr["lu_reg"] or 0, lr["lu_diff"] or 0, lr["lu_hard"] or 0
            w_reg  = (lr["wire_lu_reg"]  or 0) * (1 + (n - 1) * bf)
            w_diff = (lr["wire_lu_diff"] or 0) * (1 + (n - 1) * bf)
            w_hard = (lr["wire_lu_hard"] or 0) * (1 + (n - 1) * bf)
            # LU values are hrs/100ft; prep is fixed hrs/wire — convert to same per-100ft basis
            prep_per_100ft = (prep * n * 100.0 / footage) if footage else 0
            eff_reg  = c_reg  + w_reg  + prep_per_100ft
            eff_diff = c_diff + w_diff + prep_per_100ft
            eff_hard = c_hard + w_hard + prep_per_100ft

            with db.get_conn() as conn:
                comp_rows = conn.execute(
                    "SELECT ai.quantity, p.id as product_id, p.name as prod_name,"
                    " p.category as prod_cat, p.unit_cost FROM assembly_items ai"
                    " JOIN products p ON ai.product_id = p.id WHERE ai.assembly_id=?",
                    (aid,)
                ).fetchall()

            # Remove all existing linear rows for this assembly (full replace on each import)
            stale = [r for r in range(self.tbl.rowCount() - 1, -1, -1)
                     if self.tbl.item(r, 0) and
                        self.tbl.item(r, 0).data(Qt.UserRole + 3) == "linear" and
                        self.tbl.item(r, 0).data(Qt.UserRole + 1) == aid]
            for r in stale:
                self.tbl.removeRow(r)
                removed += 1
            if self.estimate_id:
                with db.get_conn() as conn:
                    conn.execute(
                        "DELETE FROM install_line_items"
                        " WHERE estimate_id=? AND source_type='linear' AND source_id=?",
                        (self.estimate_id, aid)
                    )
                    conn.commit()

            self.tbl.blockSignals(True)

            # One row per component (material only, no labour)
            for comp in comp_rows:
                comp_qty = footage * float(comp["quantity"] or 0)
                uc = float(comp["unit_cost"] or 0)
                cat = comp["prod_cat"] or lr["category"]
                desc = comp["prod_name"]
                iid = None
                if self.estimate_id:
                    with db.get_conn() as conn:
                        cur = conn.execute(
                            "INSERT INTO install_line_items"
                            "(estimate_id,category,description,qty,unit,unit_cost,"
                            " lu_reg,lu_diff,lu_hard,sort_order,source_type,source_id)"
                            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (self.estimate_id, cat, desc, comp_qty, "ft", uc,
                             0, 0, 0, self.tbl.rowCount(), "linear", aid)
                        )
                        conn.commit()
                    iid = cur.lastrowid
                self._insert_table_row({
                    "id": iid, "category": cat, "description": desc,
                    "qty": comp_qty, "unit": "ft", "unit_cost": uc,
                    "lu_reg": 0, "lu_diff": 0, "lu_hard": 0,
                    "lu_id": None, "source_type": "linear", "source_id": aid,
                })
                added += 1

            # Labour row — qty in 100ft units so LU (hrs/100ft) × qty gives correct hours
            if eff_reg or eff_diff or eff_hard:
                lab_desc = f"{lr['name']} — Labour"
                qty_100ft = footage / 100.0
                iid = None
                if self.estimate_id:
                    with db.get_conn() as conn:
                        cur = conn.execute(
                            "INSERT INTO install_line_items"
                            "(estimate_id,category,description,qty,unit,unit_cost,"
                            " lu_reg,lu_diff,lu_hard,sort_order,source_type,source_id)"
                            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (self.estimate_id, lr["category"], lab_desc, qty_100ft, "100ft", 0,
                             eff_reg, eff_diff, eff_hard, self.tbl.rowCount(), "linear", aid)
                        )
                        conn.commit()
                    iid = cur.lastrowid
                self._insert_table_row({
                    "id": iid, "category": lr["category"], "description": lab_desc,
                    "qty": qty_100ft, "unit": "100ft", "unit_cost": 0,
                    "lu_reg": eff_reg, "lu_diff": eff_diff, "lu_hard": eff_hard,
                    "lu_id": None, "source_type": "linear", "source_id": aid,
                })
                added += 1

            self.tbl.blockSignals(False)

        # Remove any linear rows whose assembly no longer has runs in this project
        active_aids = {lr["assembly_id"] for lr in lin_rows}
        orphans = [r for r in range(self.tbl.rowCount() - 1, -1, -1)
                   if self.tbl.item(r, 0) and
                      self.tbl.item(r, 0).data(Qt.UserRole + 3) == "linear" and
                      self.tbl.item(r, 0).data(Qt.UserRole + 1) not in active_aids]
        for r in orphans:
            iid = self.tbl.item(r, 0).data(Qt.UserRole)
            if iid and self.estimate_id:
                with db.get_conn() as conn:
                    conn.execute("DELETE FROM install_line_items WHERE id=?", (iid,))
                    conn.commit()
            self.tbl.removeRow(r)
            removed += 1

        self._recalc()
        msg = []
        if updated: msg.append(f"{updated} row(s) updated")
        if added:   msg.append(f"{added} new row(s) added")
        if removed: msg.append(f"{removed} row(s) removed (count zeroed)")
        QMessageBox.information(self, "Import Complete", "\n".join(msg) + ".")

    def _remove_selected_rows(self):
        rows = sorted(set(i.row() for i in self.tbl.selectedItems()), reverse=True)
        for r in rows:
            cell = self.tbl.item(r, 0)
            item_id = cell.data(Qt.UserRole)    if cell else None
            row_lu_id = cell.data(Qt.UserRole + 2) if cell else None
            row_pid   = cell.data(Qt.UserRole + 1) if cell else None
            if item_id or (self.estimate_id and (row_lu_id or row_pid)):
                with db.get_conn() as conn:
                    if item_id:
                        conn.execute("DELETE FROM install_line_items WHERE id=?", (item_id,))
                    # Record exclusion so import won't re-add this row
                    if self.estimate_id and (row_lu_id or row_pid):
                        try:
                            conn.execute(
                                "INSERT OR IGNORE INTO install_estimate_excluded"
                                "(estimate_id, lu_id, product_id) VALUES(?,?,?)",
                                (self.estimate_id, row_lu_id, row_pid)
                            )
                        except Exception:
                            pass
                    conn.commit()
            if not self.estimate_id:
                if row_lu_id:  self._excluded_lu.add(row_lu_id)
                if row_pid:    self._excluded_pid.add(row_pid)
            self.tbl.removeRow(r)
        self._recalc()

    def _on_discipline_change(self, new_disc):
        reply = QMessageBox.question(
            self, "Change Discipline",
            f"Switch to {new_disc}?\nThis will replace all line items with defaults for that discipline.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if self.estimate_id:
                self._seed_items(new_disc)
                self._populate_table()
            else:
                self._populate_defaults(new_disc)
            self._recalc()
        else:
            idx = INSTALL_DISCIPLINES.index(self._est.get("discipline", INSTALL_DISCIPLINES[0]))
            self.cb_disc.blockSignals(True)
            self.cb_disc.setCurrentIndex(idx)
            self.cb_disc.blockSignals(False)

    def _recalc(self):
        diff = self.cb_diff.currentText()
        rate = self.sp_rate.value()
        mat_margin = self.sp_mat_mu.value() / 100.0
        lab_margin = self.sp_lab_margin.value() / 100.0
        factor = self.sp_factor.value()
        prog_sell = self.sp_prog_sell.value()
        diff_col = {6:"Regular", 7:"Difficult", 8:"Hard"}
        lu_col = {v:k for k,v in diff_col.items()}[diff]

        total_mat = 0.0
        total_hrs = 0.0

        for r in range(self.tbl.rowCount()):
            qty = self.tbl.cellWidget(r,2).value() if self.tbl.cellWidget(r,2) else 0
            uc  = self.tbl.cellWidget(r,4).value() if self.tbl.cellWidget(r,4) else 0
            lu_reg  = self.tbl.cellWidget(r,6).value() if self.tbl.cellWidget(r,6) else 0
            lu_diff = self.tbl.cellWidget(r,7).value() if self.tbl.cellWidget(r,7) else 0
            lu_hard = self.tbl.cellWidget(r,8).value() if self.tbl.cellWidget(r,8) else 0

            lu_map = {"Regular": lu_reg, "Difficult": lu_diff, "Hard": lu_hard}
            lu_used = lu_map.get(diff, lu_reg) * factor

            ext_mat = qty * uc
            ext_hrs = qty * lu_used
            total_mat += ext_mat
            total_hrs += ext_hrs

            if self.tbl.item(r,5):  self.tbl.item(r,5).setText(f"${ext_mat:,.2f}" if ext_mat else "-")
            if self.tbl.item(r,9):  self.tbl.item(r,9).setText(f"{lu_used:.3f}")
            if self.tbl.item(r,10): self.tbl.item(r,10).setText(f"{ext_hrs:.2f}" if ext_hrs else "-")
            # Colour rows with qty > 0
            if self.tbl.item(r,10):
                self.tbl.item(r,10).setBackground(
                    QBrush(QColor(C_TOTAL)) if ext_hrs > 0 else QBrush(QColor(C_GREY))
                )

        include_labour = self.chk_labour.isChecked()
        mat_sell  = total_mat / (1 - mat_margin) if mat_margin < 1 else total_mat
        lab_cost  = (total_hrs * rate) if include_labour else 0.0
        lab_sell  = (lab_cost / (1 - lab_margin) if lab_margin < 1 else lab_cost) if include_labour else 0.0
        total_sell = mat_sell + lab_sell + prog_sell
        direct_cost = total_mat + lab_cost
        margin = (total_sell - direct_cost) / total_sell if total_sell > 0 else 0

        self._sum["mat_cost"].setText(_money(total_mat))
        self._sum["mat_sell"].setText(_money(mat_sell))
        self._sum["lab_hrs"].setText(f"{total_hrs:.1f} hrs")
        self._sum["lab_cost"].setText(_money(lab_cost))
        self._sum["lab_sell"].setText(_money(lab_sell))
        self._sum["prog"].setText(_money(prog_sell))
        self._sum["total_sell"].setText(_money(total_sell))
        self._sum["margin"].setText(f"{margin*100:.1f}%")

    def _export_excel(self):
        from PyQt5.QtWidgets import QFileDialog
        self._save_and_close()
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Estimates to Excel", "DFP_Estimate.xlsx",
            "Excel Files (*.xlsx)"
        )
        if not path:
            return
        ok, result = estimator_export.export_estimates(self.project_id, path)
        if ok:
            QMessageBox.information(self, "Export Complete",
                f"Exported to:\n{result}\n\nBlue cells = enter into Uptick.")
        else:
            QMessageBox.critical(self, "Export Failed", result)
        return  # dialog already closed by _save_and_close

    def _save_and_close(self):
        job_name = self.e_job_name.text().strip() or "Install Estimate"
        if not self.project_id:
            self.project_id = _get_or_create_project(None, job_name)
        else:
            with db.get_conn() as conn:
                conn.execute("UPDATE projects SET name=? WHERE id=?",
                             (job_name, self.project_id)); conn.commit()
        if not self.estimate_id:
            self._load_or_create_estimate()
            self._populate_table()
        self._est["discipline"]      = self.cb_disc.currentText()
        self._est["difficulty"]      = self.cb_diff.currentText()
        self._est["labour_rate"]     = self.sp_rate.value()
        self._est["material_margin"] = self.sp_mat_mu.value() / 100.0
        self._est["labour_margin"]   = self.sp_lab_margin.value() / 100.0
        self._est["labour_factor"]   = self.sp_factor.value()
        self._est["prog_sell"]       = self.sp_prog_sell.value()
        self._est["labour_included"] = 1 if self.chk_labour.isChecked() else 0
        with db.get_conn() as conn:
            conn.execute("""
                UPDATE install_estimates SET discipline=?,difficulty=?,labour_rate=?,
                labour_margin=?,labour_factor=?,prog_sell=?,labour_included=?
                WHERE id=?
            """, (self._est["discipline"], self._est["difficulty"],
                  self._est["labour_rate"],
                  self._est["labour_margin"], self._est["labour_factor"],
                  self._est["prog_sell"], self._est["labour_included"], self.estimate_id))
            # Save all line items
            for r in range(self.tbl.rowCount()):
                item_id = self.tbl.item(r,0).data(Qt.UserRole) if self.tbl.item(r,0) else None
                if not item_id:
                    continue
                cat  = self.tbl.item(r,0).text() if self.tbl.item(r,0) else ""
                desc = self.tbl.item(r,1).text() if self.tbl.item(r,1) else ""
                qty  = self.tbl.cellWidget(r,2).value() if self.tbl.cellWidget(r,2) else 0
                unit = self.tbl.item(r,3).text() if self.tbl.item(r,3) else "E"
                uc   = self.tbl.cellWidget(r,4).value() if self.tbl.cellWidget(r,4) else 0
                lu_r = self.tbl.cellWidget(r,6).value() if self.tbl.cellWidget(r,6) else 0
                lu_d = self.tbl.cellWidget(r,7).value() if self.tbl.cellWidget(r,7) else 0
                lu_h = self.tbl.cellWidget(r,8).value() if self.tbl.cellWidget(r,8) else 0
                conn.execute("""
                    UPDATE install_line_items SET category=?,description=?,qty=?,unit=?,
                    unit_cost=?,lu_reg=?,lu_diff=?,lu_hard=? WHERE id=?
                """, (cat, desc, qty, unit, uc, lu_r, lu_d, lu_h, item_id))
            conn.commit()
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
# PROGRAMMING DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class ProgrammingDialog(QDialog):
    def __init__(self, project_id=None, parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.calc_id = None
        self.setWindowTitle("Programming & V.I. Calculator")
        self.setWindowState(Qt.WindowMaximized)
        _init_tables()
        self._c = {"panel_type":"4007es","num_panels":0,"job_type":"Stand-Alone Small",
                   "devices_prog_vi":0,"devices_prog":0,"devices_vi":0,
                   "min_prog_vi_4007":4,"min_prog_vi_4010":5,"min_prog_vi_4100":8,
                   "min_prog_4007":4,"min_prog_4010":5,"min_prog_4100":8,
                   "min_vi_4007":6,"min_vi_4010":6,"min_vi_4100":6,
                   "hrs_panel_4007":3,"hrs_panel_4010":4,"hrs_panel_4100":6,
                   "rate_prog":140,"rate_vi":110,"expenses":0,"margin":0.40}
        self._build_ui()
        if self.project_id:
            self._load_or_create()
        self._recalc()

    def _load_or_create(self):
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM programming_calcs WHERE project_id=? LIMIT 1",
                (self.project_id,)
            ).fetchone()
            if row:
                self.calc_id = row["id"]
                self._c = dict(row)
            else:
                cur = conn.execute(
                    "INSERT INTO programming_calcs(project_id) VALUES(?)",
                    (self.project_id,)
                )
                conn.commit()
                self.calc_id = cur.lastrowid
                self._c = {"id": self.calc_id, "project_id": self.project_id,
                           "panel_type":"4007es","num_panels":1,"job_type":"Stand-Alone Small",
                           "devices_prog_vi":0,"devices_prog":0,"devices_vi":0,
                           "min_prog_vi_4007":4,"min_prog_vi_4010":5,"min_prog_vi_4100":8,
                           "min_prog_4007":4,"min_prog_4010":5,"min_prog_4100":8,
                           "min_vi_4007":6,"min_vi_4010":6,"min_vi_4100":6,
                           "hrs_panel_4007":3,"hrs_panel_4010":4,"hrs_panel_4100":6,
                           "rate_prog":140,"rate_vi":110,"expenses":0,"margin":0.40}

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8); layout.setContentsMargins(10,10,10,10)

        title = QLabel("PROGRAMMING & VERIFICATION / INSPECTION")
        title.setStyleSheet(STYLE_HDR + "font-size:14px;border-radius:4px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Job name
        job_box = QGroupBox("Job")
        jf = QFormLayout(job_box)
        existing_name = ""
        if self.project_id:
            with db.get_conn() as conn:
                prow = conn.execute("SELECT name FROM projects WHERE id=?",
                                    (self.project_id,)).fetchone()
                if prow: existing_name = prow["name"]
        self.e_job_name = QLineEdit(existing_name)
        self.e_job_name.setPlaceholderText("Enter job / project name…")
        self.e_job_name.setStyleSheet("background:#fff3cd;font-weight:bold;")
        jf.addRow("Job Name:", self.e_job_name)
        layout.addWidget(job_box)

        # Job setup
        setup_box = QGroupBox("Job Setup")
        sf = QFormLayout(setup_box)

        self.cb_panel = QComboBox(); self.cb_panel.addItems(["4007es","4010es","4100 Bay"])
        self.cb_panel.setCurrentText(self._c.get("panel_type","4007es"))
        sf.addRow("Panel Type:", self.cb_panel)

        self.sp_panels = _Spin(); self.sp_panels.setRange(0,99)
        self.sp_panels.setValue(int(self._c.get("num_panels",1)))
        sf.addRow("Number of Panels:", self.sp_panels)

        self.cb_job = QComboBox(); self.cb_job.addItems(["Stand-Alone Small","Stand-Alone Large","Network"])
        self.cb_job.setCurrentText(self._c.get("job_type","Stand-Alone Small"))
        sf.addRow("Job Type:", self.cb_job)

        self.sp_dev_pv = _Spin(); self.sp_dev_pv.setRange(0,99999)
        self.sp_dev_pv.setValue(int(self._c.get("devices_prog_vi",0)))
        sf.addRow("Devices – Prog & V.I.:", self.sp_dev_pv)

        self.sp_dev_p = _Spin(); self.sp_dev_p.setRange(0,99999)
        self.sp_dev_p.setValue(int(self._c.get("devices_prog",0)))
        sf.addRow("Devices – Prog Only:", self.sp_dev_p)

        self.sp_dev_v = _Spin(); self.sp_dev_v.setRange(0,99999)
        self.sp_dev_v.setValue(int(self._c.get("devices_vi",0)))
        sf.addRow("Devices – V.I. Only:", self.sp_dev_v)
        layout.addWidget(setup_box)

        # Minutes per device
        min_box = QGroupBox("Minutes per Device (editable)")
        mf = QFormLayout(min_box)
        self.sp_min_pv_4007 = _make_spin(1,0,60,self._c.get("min_prog_vi_4007",4),0.5)
        self.sp_min_pv_4010 = _make_spin(1,0,60,self._c.get("min_prog_vi_4010",5),0.5)
        self.sp_min_pv_4100 = _make_spin(1,0,60,self._c.get("min_prog_vi_4100",8),0.5)
        self.sp_hrs_panel_4007 = _make_spin(1,0,20,self._c.get("hrs_panel_4007",3),0.5)
        self.sp_hrs_panel_4010 = _make_spin(1,0,20,self._c.get("hrs_panel_4010",4),0.5)
        self.sp_hrs_panel_4100 = _make_spin(1,0,20,self._c.get("hrs_panel_4100",6),0.5)
        mf.addRow("Prog+VI min/dev (4007):", self.sp_min_pv_4007)
        mf.addRow("Prog+VI min/dev (4010):", self.sp_min_pv_4010)
        mf.addRow("Prog+VI min/dev (4100):", self.sp_min_pv_4100)
        mf.addRow("Hrs/panel (4007):", self.sp_hrs_panel_4007)
        mf.addRow("Hrs/panel (4010):", self.sp_hrs_panel_4010)
        mf.addRow("Hrs/panel (4100):", self.sp_hrs_panel_4100)
        layout.addWidget(min_box)

        # Pricing
        price_box = QGroupBox("Pricing")
        pf = QFormLayout(price_box)
        self.sp_rate_prog = _make_spin(0,0,500,self._c.get("rate_prog",140),5,suffix=" $/hr")
        self.sp_rate_vi   = _make_spin(0,0,500,self._c.get("rate_vi",110),  5,suffix=" $/hr")
        self.sp_expenses  = _make_spin(2,0,999999,self._c.get("expenses",0),100)
        self.sp_margin    = _make_spin(0,0,99,self._c.get("margin",0.40)*100,1,suffix="%")
        pf.addRow("Programming Rate (burdened):", self.sp_rate_prog)
        pf.addRow("V.I. Rate (burdened):", self.sp_rate_vi)
        pf.addRow("Expenses (LOA, travel, etc.):", self.sp_expenses)
        pf.addRow("Margin:", self.sp_margin)
        layout.addWidget(price_box)

        # Results
        res_box = QGroupBox("Results")
        res_layout = QFormLayout(res_box)
        self._lbl_panel_hrs  = QLabel("-"); self._lbl_device_hrs = QLabel("-")
        self._lbl_total_hrs  = QLabel("-"); self._lbl_prog_hrs   = QLabel("-")
        self._lbl_vi_hrs     = QLabel("-"); self._lbl_days       = QLabel("-")
        self._lbl_sell       = QLabel("-")
        self._lbl_sell.setStyleSheet(f"color:{C_ORANGE};font-size:14px;font-weight:bold;")
        for label, widget in [
            ("Panel Hours:", self._lbl_panel_hrs),
            ("Device Hours:", self._lbl_device_hrs),
            ("Total Hours:", self._lbl_total_hrs),
            ("  → Programming (1/3):", self._lbl_prog_hrs),
            ("  → V.I. (2/3):", self._lbl_vi_hrs),
            ("Calendar Days (8hr/day):", self._lbl_days),
            ("SELL PRICE:", self._lbl_sell),
        ]:
            res_layout.addRow(label, widget)
        layout.addWidget(res_box)

        # Buttons
        btn_row = QHBoxLayout()
        exp_btn = QPushButton("Export to Excel"); exp_btn.setStyleSheet(STYLE_BTN_SECONDARY)
        exp_btn.clicked.connect(self._export_excel)
        btn_row.addWidget(exp_btn); btn_row.addStretch()
        save_btn = QPushButton("Save & Close"); save_btn.setStyleSheet(STYLE_BTN_PRIMARY)
        save_btn.clicked.connect(self._save_and_close)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        # Connect all signals
        for w in (self.cb_panel, self.cb_job):
            w.currentTextChanged.connect(self._recalc)
        for w in (self.sp_panels, self.sp_dev_pv, self.sp_dev_p, self.sp_dev_v):
            w.valueChanged.connect(self._recalc)
        for w in (self.sp_min_pv_4007, self.sp_min_pv_4010, self.sp_min_pv_4100,
                  self.sp_hrs_panel_4007, self.sp_hrs_panel_4010, self.sp_hrs_panel_4100,
                  self.sp_rate_prog, self.sp_rate_vi, self.sp_expenses, self.sp_margin):
            w.valueChanged.connect(self._recalc)

    def _recalc(self, *_):
        pt = self.cb_panel.currentText()
        hrs_map = {"4007es": self.sp_hrs_panel_4007.value(),
                   "4010es": self.sp_hrs_panel_4010.value(),
                   "4100 Bay": self.sp_hrs_panel_4100.value()}
        min_map = {"4007es": self.sp_min_pv_4007.value(),
                   "4010es": self.sp_min_pv_4010.value(),
                   "4100 Bay": self.sp_min_pv_4100.value()}

        panel_hrs  = self.sp_panels.value() * hrs_map.get(pt, 3)
        device_hrs = (self.sp_dev_pv.value() * min_map.get(pt, 4) +
                      self.sp_dev_p.value()  * min_map.get(pt, 4) +
                      self.sp_dev_v.value()  * min_map.get(pt, 6)) / 60.0
        total_hrs  = panel_hrs + device_hrs
        prog_hrs   = total_hrs / 3.0
        vi_hrs     = total_hrs * 2.0 / 3.0
        days       = total_hrs / 8.0

        margin    = self.sp_margin.value() / 100.0
        cost      = prog_hrs * self.sp_rate_prog.value() + vi_hrs * self.sp_rate_vi.value() + self.sp_expenses.value()
        sell      = cost / (1 - margin) if margin < 1 else cost

        self._lbl_panel_hrs.setText(f"{panel_hrs:.1f} hrs")
        self._lbl_device_hrs.setText(f"{device_hrs:.1f} hrs")
        self._lbl_total_hrs.setText(f"{total_hrs:.1f} hrs")
        self._lbl_prog_hrs.setText(f"{prog_hrs:.1f} hrs")
        self._lbl_vi_hrs.setText(f"{vi_hrs:.1f} hrs")
        self._lbl_days.setText(f"{days:.1f} days")
        self._lbl_sell.setText(_money(sell))

    def _export_excel(self):
        from PyQt5.QtWidgets import QFileDialog
        self._save_and_close()
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Estimates to Excel", "DFP_Estimate.xlsx",
            "Excel Files (*.xlsx)"
        )
        if not path:
            return
        ok, result = estimator_export.export_estimates(self.project_id, path)
        if ok:
            QMessageBox.information(self, "Export Complete",
                f"Exported to:\n{result}\n\nBlue cells = enter into Uptick.")
        else:
            QMessageBox.critical(self, "Export Failed", result)

    def _save_and_close(self):
        job_name = self.e_job_name.text().strip() or "Programming"
        if not self.project_id:
            self.project_id = _get_or_create_project(None, job_name)
        else:
            with db.get_conn() as conn:
                conn.execute("UPDATE projects SET name=? WHERE id=?",
                             (job_name, self.project_id)); conn.commit()
        if not self.calc_id:
            self._load_or_create()
        pt = self.cb_panel.currentText()
        with db.get_conn() as conn:
            conn.execute("""
                UPDATE programming_calcs SET panel_type=?,num_panels=?,job_type=?,
                devices_prog_vi=?,devices_prog=?,devices_vi=?,
                min_prog_vi_4007=?,min_prog_vi_4010=?,min_prog_vi_4100=?,
                hrs_panel_4007=?,hrs_panel_4010=?,hrs_panel_4100=?,
                rate_prog=?,rate_vi=?,expenses=?,margin=? WHERE id=?
            """, (pt, self.sp_panels.value(), self.cb_job.currentText(),
                  self.sp_dev_pv.value(), self.sp_dev_p.value(), self.sp_dev_v.value(),
                  self.sp_min_pv_4007.value(), self.sp_min_pv_4010.value(), self.sp_min_pv_4100.value(),
                  self.sp_hrs_panel_4007.value(), self.sp_hrs_panel_4010.value(), self.sp_hrs_panel_4100.value(),
                  self.sp_rate_prog.value(), self.sp_rate_vi.value(),
                  self.sp_expenses.value(), self.sp_margin.value()/100.0,
                  self.calc_id))
            conn.commit()
        self.accept()
