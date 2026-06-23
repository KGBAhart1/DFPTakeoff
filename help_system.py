"""
DFP TakeoffPro — Help & Manual System
--------------------------------------
Provides a searchable how-to manual and About dialog for both
the main Takeoff window and the Suppression Designer.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QTextBrowser, QPushButton, QScrollArea,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from version import APP_NAME, APP_VERSION, APP_COMPANY


# ═══════════════════════════════════════════════════════════════════════════════
#  Manual content — list of (title, body) tuples
# ═══════════════════════════════════════════════════════════════════════════════

TAKEOFF_MANUAL = [
    ("Getting Started", """
<b>Loading a PDF</b><br>
Click <b>Load PDF</b> on the toolbar to open a set of building plans. Use the page
selector on the left to navigate between sheets. Scroll to zoom in/out and
middle-click drag (or Ctrl+drag) to pan around the drawing.

<br><br><b>Projects</b><br>
Click <b>Projects</b> to open the project manager. From here you can create new
projects, open existing ones, or organize your work. All counts, marks, and
settings are saved per project.
"""),

    ("Counting & Marking", """
<b>Start Counting</b><br>
Click <b>Start Counting</b> on the toolbar — it toggles into counting mode.
Choose a device type from the count panel on the right, then click on the
drawing to place marks. Each click adds one count for that device type.

<br><br><b>Clear Marks</b><br>
<b>Clear Marks (page)</b> removes all marks on the current page only.

<br><br><b>Keyboard Shortcuts</b><br>
• <b>Scroll wheel</b> — Zoom in/out<br>
• <b>Middle-click drag</b> or <b>Ctrl+drag</b> — Pan<br>
• <b>Del</b> — Delete selected items<br>
"""),

    ("Design Mode & Scale", """
<b>Design Mode</b><br>
Toggle <b>Design Mode</b> to overlay coverage circles on placed devices.
Coverage radii follow NFPA spacing rules for each device type.

<br><br><b>Setting the Scale</b><br>
Two methods:<br>
1. <b>Measure on Drawing</b> — Click two points on the drawing whose real-world
   distance you know, then enter that distance. The scale is calculated
   automatically.<br>
2. <b>Set Scale…</b> — Enter a ratio directly (e.g. 1:100).

<br><br>Once the scale is set, coverage circles display at the correct real-world size.
"""),

    ("Estimating Tools", """
<b>PMA Quote</b><br>
Build a PMA (Preventive Maintenance Agreement) inspection quote covering all
fire protection disciplines. Fill in the equipment counts and the tool
calculates labour, materials, and pricing.

<br><br><b>Install Estimate</b><br>
Build an installation estimate with material takeoff and labour hours.
Add line items, quantities, and rates to produce a complete estimate.

<br><br><b>Programming</b><br>
Calculate programming and verification/inspection hours and sell price
for fire alarm system programming work.
"""),

    ("Exporting", """
<b>Export PDF</b><br>
Exports the current marked-up drawing as a PDF file. All marks, counts,
and coverage circles (if in Design Mode) are included in the export.
"""),
]


SUPPRESSION_MANUAL = [
    ("Getting Started", """
<b>Overview</b><br>
The Suppression Designer lets you lay out a kitchen fire suppression system.
Place hoods, appliances, nozzles, pipe runs, and detection to design a
complete system. The tool calculates flow points and recommends cylinder sizes.

<br><br><b>Creating a Project</b><br>
Click <b>New</b> to start a fresh project, or <b>Open</b> to load a saved one.
Use <b>Project Info</b> to enter customer name, location, job number, and notes.
<b>Save</b> stores your work — the app prompts to save if you close with unsaved changes.
"""),

    ("Hoods & Ducts", """
<b>Adding a Hood</b><br>
Click <b>Add Hood</b> in the left panel. Enter the hood dimensions (width and
depth in inches). Nozzles are automatically placed inside the hood.

<br><br><b>Adding a Duct</b><br>
Click <b>Add Duct</b> to add a grease duct to the system. Ducts get two nozzles
by default. You can move and edit nozzles by right-clicking them.

<br><br><b>Zones</b><br>
Each hood can be assigned to a zone. Zones appear in the PDF export sidebar.
"""),

    ("Appliances", """
<b>Adding Appliances</b><br>
Select an appliance from the left palette (organized by group: Fryers, Griddles,
Broilers, Woks, etc.). A size dialog appears — adjust dimensions or accept defaults.
Click on the canvas to place the appliance.

<br><br><b>Appliance Groups</b><br>
• <b>Fryers</b> — Small, Med, Large, Henny Penny<br>
• <b>Griddles</b> — Small, Med, Large, Round<br>
• <b>Broilers</b> — Char, Chain (open/closed), Chain Pizza Oven, Upright, Salamander<br>
• <b>Woks</b> — Standard and Range<br>
• <b>Other</b> — Range, Convection Oven, Tilt Skillet, Table, etc.<br>

<br><b>Editing Appliances</b><br>
Right-click an appliance for options:<br>
• <b>Edit Appliance…</b> — Change dimensions or label<br>
• <b>Edit Nozzles…</b> — Change nozzle type and direction<br>
• <b>Nudge Label</b> — Move the label up/down/left/right<br>
• <b>Bring to Front / Send to Back</b> — Layer ordering<br>

<br><b>Tables</b><br>
Tables are visual-only — they don't appear in the appliance/nozzle list on
the PDF export since they don't have nozzles.
"""),

    ("Nozzles & Flow", """
<b>Appliance Nozzles</b><br>
Nozzles are automatically placed when you add an appliance. The type and count
depend on the selected manufacturer. You can delete individual nozzles by
right-clicking them.

<br><br><b>Free Nozzles</b><br>
Click <b>Nozzle</b> in the equipment panel to place a free-standing nozzle
anywhere on the canvas. Choose the nozzle type and direction before placing.

<br><br><b>Flow Points</b><br>
Each nozzle contributes flow points to the system total. The sidebar shows
the running total and compares it against the selected cylinder's capacity.
Deleting a nozzle updates the count immediately.

<br><br><b>Nozzle Labels</b><br>
Right-click any nozzle to:<br>
• <b>Hide/Show Label</b><br>
• <b>Nudge Label</b> — Move the label in any direction to avoid overlaps<br>
• <b>Edit Nozzle…</b> — Change type or direction<br>
"""),

    ("Equipment", """
<b>Bottles / Cylinders</b><br>
Click <b>Bottle</b> to place a suppression cylinder. The size options depend on
the selected manufacturer. Flow capacity is shown in the sidebar.

<br><br><b>Control Head</b><br>
Click <b>Ctrl Head</b> to place a control head. A dialog appears with connection
options:<br>
• System connected to HVAC<br>
• System connected to building FACP<br>
• System utilizes a local bell<br>
• System utilizes a local visual indicator<br>
Selected options automatically appear in the Notes section of the PDF export.
Right-click to edit options after placement.

<br><br><b>Pull Station</b> — Manual pull station for system activation.<br>
<b>Alarm Bell</b> — Audible notification device.<br>
<b>Gas Valve</b> — Gas shut-off valve. Right-click to rotate (90°/180°/270°).
The label stays horizontal regardless of rotation. Supports label nudging.
"""),

    ("Detectors / Links", """
<b>Placing Detectors</b><br>
Click <b>Detector</b> and choose a fusible link type from the dropdown.
Click the canvas to place. Each link temperature gets a unique color.

<br><br><b>On the Canvas</b><br>
The detector shows just the temperature number (e.g. "450") to keep labels
compact. Right-click to edit the link type, nudge the label, or delete.

<br><br><b>In the Legend</b><br>
The PDF legend shows the full link name (e.g. "GLOBE 450 - ML Style") with
the matching color symbol. Only link types actually used appear in the legend.
"""),

    ("Labels & Pipe Runs", """
<b>Free Labels</b><br>
Click <b>Label</b> in the equipment panel to place a free text label anywhere.
Labels support multiple lines. A leader line with a dot automatically points
down — drag the orange dot to aim it at what you're labeling.
Right-click to edit text, add/remove the leader line, or delete.

<br><br><b>Pipe Runs</b><br>
Toggle <b>Draw Pipes</b> to enter pipe drawing mode. Click to set the start point,
then click again to complete a segment. Pipes snap to horizontal/vertical by
default — hold <b>Ctrl</b> while clicking to place at any angle.
Press <b>Esc</b> to cancel a pipe in progress.
"""),

    ("Manufacturers", """
<b>Switching Manufacturers</b><br>
Use the manufacturer dropdown in the toolbar. Options include:<br>
• <b>Kidde / Badger</b> (default)<br>
• <b>Buckeye BFR</b><br>
• <b>Amerex KP</b><br>

Switching manufacturers updates nozzle types, cylinder options, and flow
calculations across the entire design. Nozzle colors may change (Buckeye
uses color-coded nozzles).
"""),

    ("Canvas Controls", """
<b>Navigation</b><br>
• <b>Scroll wheel</b> — Zoom in/out<br>
• <b>Middle-click drag</b> or <b>Ctrl+drag</b> — Pan<br>
• <b>Fit View</b> — Zoom to fit all content<br>

<br><b>Selection</b><br>
• <b>Click</b> — Select an item<br>
• <b>Ctrl+A</b> — Select all items (then drag to move everything at once)<br>
• <b>Del</b> — Delete selected items<br>
• <b>Esc</b> — Cancel current placement or pipe draw<br>

<br><b>Toggles</b><br>
• <b>Labels</b> — Show/hide all labels<br>
• <b>Dims</b> — Show/hide appliance dimensions<br>
• <b>Snap</b> — Toggle grid snapping<br>
"""),

    ("Exporting & Printing", """
<b>Export PDF</b><br>
Creates a professional submittal PDF with:<br>
• Scaled system drawing<br>
• Appliance / nozzle list (tables excluded)<br>
• Cylinder and flow summary<br>
• Zone breakdown<br>
• Color-coded legend (nozzles and detectors)<br>
• Notes (including control head options)<br>

<br>If customer name or location is missing, you'll be prompted to enter it
before exporting.

<br><br><b>Print</b><br>
Sends the submittal directly to a printer (if available).

<br><br><b>Project Info</b><br>
Enter customer, location, job number, designer, revision, and notes.
This information appears on the PDF header and sidebar.
"""),
]


# ═══════════════════════════════════════════════════════════════════════════════
#  Help Dialog
# ═══════════════════════════════════════════════════════════════════════════════

class HelpDialog(QDialog):
    """Tabbed Help dialog with searchable manual and About page."""

    def __init__(self, manual_entries, context_name="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Help — {context_name}")
        self.setMinimumSize(680, 520)
        self._entries = manual_entries

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        tabs = QTabWidget()
        tabs.addTab(self._build_manual_tab(), "Manual")
        tabs.addTab(self._build_about_tab(), "About")
        layout.addWidget(tabs)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("padding:6px 20px;")
        close_btn.clicked.connect(self.accept)
        br = QHBoxLayout(); br.addStretch(); br.addWidget(close_btn)
        layout.addLayout(br)

    def _build_manual_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search manual…")
        self._search.setStyleSheet("padding:6px;font-size:12px;border:1px solid #ccc;border-radius:4px;")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setStyleSheet(
            "QTextBrowser{font-size:12px;border:1px solid #ddd;padding:8px;}"
        )
        layout.addWidget(self._browser)

        self._render_all()
        return w

    def _render_all(self, filter_text=""):
        html = ""
        ft = filter_text.lower().strip()
        for title, body in self._entries:
            if ft and ft not in title.lower() and ft not in body.lower():
                continue
            html += f'<h3 style="color:#1a5276;margin-top:16px;margin-bottom:4px;">{title}</h3>'
            if ft:
                import re
                pattern = re.compile(re.escape(ft), re.IGNORECASE)
                highlighted = pattern.sub(
                    lambda m: f'<span style="background:#ffe082;font-weight:bold;">{m.group()}</span>',
                    body
                )
                html += highlighted
            else:
                html += body
            html += '<hr style="border:none;border-top:1px solid #e0e0e0;">'
        if not html:
            html = '<p style="color:#888;text-align:center;margin-top:40px;">No results found.</p>'
        self._browser.setHtml(html)

    def _filter(self, text):
        self._render_all(text)

    def _build_about_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 30, 20, 20)

        title = QLabel(APP_NAME)
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setStyleSheet("color:#1a5276;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        ver = QLabel(f"Version {APP_VERSION}")
        ver.setFont(QFont("Arial", 12))
        ver.setStyleSheet("color:#555;")
        ver.setAlignment(Qt.AlignCenter)
        layout.addWidget(ver)

        layout.addSpacing(20)

        info_lines = [
            f"<b>Developer:</b> {APP_COMPANY}",
            "<b>Contact:</b> kevinh@defensefirepro.com",
            "",
            "Fire protection takeoff, estimating, and",
            "kitchen suppression system design tool.",
            "",
            "© 2026 Defense Fire Protection. All rights reserved.",
        ]
        info = QLabel("<br>".join(info_lines))
        info.setFont(QFont("Arial", 11))
        info.setAlignment(Qt.AlignCenter)
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()
        return w
