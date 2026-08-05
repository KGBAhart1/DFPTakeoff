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


PAINT_BOOTH_MANUAL = [
    ("Getting Started", """
<b>Overview</b><br>
The Paint Booth Designer lays out a Badger Industry Guard dry-chemical
suppression system for a vehicle spray booth in an isometric 3-D view.
Add zones (work areas, pits, plenums, exhaust ducts), then place nozzles,
detectors, and cylinders. The tool calculates nozzle counts and flow
against the DIOM (P/N 60-900007-001) limits automatically.

<br><br><b>Creating a Project</b><br>
Click <b>New</b> to start a fresh booth, or <b>Open</b> to load a saved
<b>.pbp</b> file. Use <b>Project Info</b> to enter customer, location, job
number, designer, revision, and notes — <b>Save</b>/<b>Save As</b> stores
your work.
"""),

    ("Zones", """
<b>Adding a Zone</b><br>
Click <b>Add Zone</b> and choose a zone type, then click-drag on the canvas
to size it. Each zone type has its own DIOM module limits (max
length/width/height per nozzle) and the tool warns if a zone exceeds them.

<br><br><b>Zone Types</b><br>
• <b>Work Area</b> — general booth interior space<br>
• <b>Exhaust Duct</b><br>
• <b>Pit (Straight)</b> — D/P nozzles, max 40 ft/nozzle<br>
• <b>Cross Flow (Box)</b> — D/P, 16×4×18 ft/nozzle<br>
• <b>Cross Flow (Drive Thru)</b> — D/P, 15×4×12 ft/nozzle, U-shaped<br>
• <b>Raised Floor</b> — D/P, 30×15×1 ft/nozzle<br>
• <b>Side Exhaust</b> — D/P, 40×4×4 ft/nozzle<br>
• <b>Pit with Tunnel</b> — 3-Way nozzle, legs ≤18 ft, tunnel ≤18 ft<br>
• <b>Pit w/ Vertical Transition</b> — 3-Way, legs ≤18 ft, vertical ≤14 ft<br>

<br><b>Editing a Zone</b><br>
Drag a zone to move it, drag its corner handles to resize. Right-click for
more options. Nozzles placed inside a zone follow it when it's moved.
"""),

    ("Nozzles, Detectors & Cylinders", """
<b>Nozzles</b><br>
Nozzles are placed automatically to satisfy each zone's DIOM coverage —
the tool recalculates the count whenever a zone is resized. You can also
add or remove individual nozzles by right-clicking.

<br><br><b>Detection & Links</b><br>
Place detectors/fusible links from the equipment palette, same workflow as
the Suppression Designer — click to place, right-click to edit or delete.

<br><br><b>Cylinders</b><br>
Place cylinders from the equipment palette. The sidebar totals flow points
against the selected cylinder's rated capacity so you can confirm sizing
before exporting.
"""),

    ("Canvas Controls", """
<b>Navigation</b><br>
• <b>Scroll wheel</b> — Zoom in/out<br>
• <b>Middle-click drag</b> or <b>Ctrl+drag</b> — Pan<br>
• <b>Fit View</b> — Zoom to fit all content<br>

<br><b>Selection</b><br>
• <b>Click</b> — Select an item<br>
• <b>Del</b> — Delete selected items<br>
• <b>Esc</b> — Cancel current placement<br>
"""),

    ("Exporting & Printing", """
<b>Export PDF</b><br>
Produces a 2-page blueprint-style submittal — isometric system drawing,
nozzle/equipment schedule, DIOM compliance notes, and project info header —
matching the kitchen suppression system export format.

<br><br><b>Project Info</b><br>
Enter customer, location, job number, designer, revision, and notes; this
appears on the PDF header and sidebar.
"""),
]


DRAWING_DESIGNER_MANUAL = [
    ("Getting Started", """
<b>Overview</b><br>
The Drawing Designer builds a floor plan from scratch (or from an imported
background/kitchen report), then lets you produce a Wiring Diagram, a
One-Line Diagram, and a code-required Fire Safety Plan sheet — all from the
same building layout. The three views live in separate tabs; each tab's
own toolbar group is only enabled while that tab is active.

<br><br><b>Starting a Drawing</b><br>
Click <b>New</b> for a blank floor plan, or <b>Open</b> to load a saved
file. You can also start from a real building outline with <b>Import
Background…</b> (a PDF/image to trace over) or by importing an existing
kitchen report PDF to auto-generate a starting layout.
"""),

    ("Floor Plan Tools", """
<b>Walls</b><br>
• Click <b>Draw Wall</b>, click to start, click each corner.<br>
• Type a number then Enter to set the exact length of the segment you're
drawing (e.g. 12, 12.5, 12'6", 6"). Angles snap to 45°.<br>
• Click back near your start point to close the room automatically — you'll
be prompted for a name and ceiling height.<br>
• Double-click or Enter (no typed length) to finish an open wall run.<br>
• Drag a wall to move it — connected corners stretch with it automatically.<br>

<br><b>Rooms</b><br>
<b>Add Rectangle Room</b> drops a rectangular room you can resize by
dragging its corners. Rooms can be dragged, copied, and pasted like any
other item.

<br><br><b>Thickness / Snap / Grid</b><br>
Set wall thickness before drawing. Toggle <b>Snap</b> to lock new points to
the grid, and <b>Grid</b> to show/hide the grid overlay.

<br><br><b>Fire Zones</b><br>
Click <b>Zone</b> to draw a colored/hatched fire zone over an area of the
plan (matches the reference Fire Safety Plan hatch/color legend). Zone
labels can be dragged; a leader line follows automatically back to the zone.

<br><br><b>Symbols</b><br>
Pick a symbol from the right-hand palette (includes the full Calgary Fire
Department symbol set for Fire Safety Plan sheets), then click the canvas
to place it. Doors/Windows snap onto the nearest wall automatically. The
"You Are Here" marker is required before exporting a Fire Safety Plan.
"""),

    ("Background Trace", """
<b>Import Background</b><br>
Import a PDF or image (e.g. an architectural drawing) to trace walls and
rooms over top of it.

<br><br><b>Calibrate / Set Scale</b><br>
Use <b>Calibrate</b> to click two points a known real-world distance apart
so the background lines up at true scale, or use <b>Set Scale…</b> to enter
a ratio directly.

<br><br><b>Visibility / Remove</b><br>
Toggle the background's visibility on/off, or remove it entirely once
you've finished tracing.
"""),

    ("Wiring Diagram", """
<b>Connect Wires</b><br>
Switch to the <b>Wiring Diagram</b> tab, click <b>Connect Wires</b>, then
click two devices to wire them together. Right-click a wire to label it.
This view is not drawn to scale — it's a schematic device-to-device
connection diagram, separate from the physical Floor Plan layout.
"""),

    ("One-Line Diagram", """
<b>Overview</b><br>
The <b>One-Line Diagram</b> tab is a schematic riser-style layout of loops,
NAC circuits, and booster panels for the fire alarm system.

<br><br><b>Adding Devices</b><br>
Use <b>Add Loop</b>, <b>Add NAC</b>, <b>Add Booster</b>, and <b>Add
Standalone</b> to place each element, then connect them as needed.
<b>Loading</b> shows current draw/loading calculations for the system.

<br><br><b>Auto-Arrange</b><br>
Automatically lays out the current one-line diagram's elements in a clean
riser arrangement — a quick starting point you can still drag and adjust
manually afterward.

<br><br><b>Import FQQ (.xlsm)</b><br>
Imports device/loop data from an FQQ spreadsheet directly into the
One-Line Diagram, saving manual re-entry.
"""),

    ("Fire Safety Plan Export", """
<b>🚨 Export Fire Safety Plan</b><br>
Produces the dedicated, code-required Fire Safety Plan / "You Are Here"
sheet — a single-page export using the official Calgary Fire Department
symbol set, forced-uppercase labeling, and an on-page legend of only the
symbols actually used.

<br><br>Before exporting, make sure:<br>
• Walls/rooms are drawn and Fire Safety Plan symbols/zones are placed.<br>
• A <b>"You Are Here"</b> marker has been placed on the plan — the export
is blocked without one, since it's required on the posted sheet.
"""),

    ("Layers & General Export", """
<b>Layers</b><br>
Toggle visibility per trade/discipline on the left panel — this also
controls what's included in a normal <b>Export PDF</b>.

<br><br><b>Export PDF</b><br>
Pick a paper size and either auto-fit the scale to the page or force a
standard architectural/engineering scale. Select items first and choose
"Current selection only" to print just a section of the plan.

<br><br><b>Fit View / Clear Tab</b><br>
<b>Fit View</b> zooms the active tab to fit all its content. <b>Clear
Tab</b> clears only the currently active tab's contents.
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
