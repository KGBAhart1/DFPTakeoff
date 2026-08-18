"""
Fire Plan Builder — assembles an AHJ Fire Safety Plan submission package.

Starts with Calgary; more AHJs are added to AHJ_PROFILES as their
requirements are gathered. Wraps/assembles output already produced
elsewhere in the app (Drawing Designer's Fire Safety Plan export) rather
than duplicating drawing capability — see main.py MainWindow.
_open_fire_plan_builder.
"""

import os, sys, json
import fitz
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QScrollArea, QWidget, QGroupBox, QCheckBox,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QProgressDialog,
    QApplication, QTextEdit,
)
from PyQt5.QtCore import Qt

import db


# ═══════════════════════════════════════════════════════════════════════════════
#  AHJ registry — adding a new city later is a new entry here, not new logic
# ═══════════════════════════════════════════════════════════════════════════════

AHJ_PROFILES = {
    "calgary": {
        "display_name": "Calgary, AB",
        "documents": ["vbi", "base_building", "alarm_zone", "certificates"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Vital Building Information — Calgary Fire form FD 1019 (July 2021)
#  Sections and fields transcribed 1:1 from the official form so the
#  in-app sheet covers exactly what a Calgary Fire responder expects.
# ═══════════════════════════════════════════════════════════════════════════════

VBI_SECTIONS = [
    ("Building Info", [
        ("building_name", "Building Name", "text"),
        ("address", "Address", "text"),
        ("date", "Date (MM/DD/YYYY)", "text"),
    ]),
    ("Access", [
        ("weight_restricted", "Weight Restricted Parking/Access/Areas", "yesno"),
        ("weight_restricted_note", "  (if Yes) See site plan drawing showing restrictions", "text"),
    ]),
    ("Fire Alarm", [
        ("fa_panel_main_entrance", "Fire Alarm Panel at Main Entrance", "yesno"),
        ("fa_local_alarm", "Local Alarm", "yesno"),
        ("fa_911_signs", "911 Signs Posted", "yesno"),
        ("fa_annunciator_location", "Annunciator Location", "text"),
        ("fa_signal_silence_location", "Signal Silence Location", "text"),
        ("fa_reset_switch_location", "Reset Switch Location", "text"),
        ("fa_stage", "Fire Alarm", "choice", ["", "Single Stage", "2 Stage"]),
        ("fa_monitoring_company", "Monitoring Company", "text"),
        ("fa_voice_communication", "Voice Communication", "yesno"),
        ("fa_voice_in_stairways", "  In Stairways", "yesno"),
        ("fa_fire_phones", "Fire Phones", "yesno"),
        ("fa_fire_phones_location", "  Location", "text"),
    ]),
    ("Building Information", [
        ("below_grade_floors", "Below Grade Floors #", "text"),
        ("below_grade_use", "  Use", "text"),
        ("storeys", "# of Storeys", "text"),
        ("dimensions", "Dimensions", "text"),
        ("boiler_room_location", "Boiler Room Location", "text"),
        ("type_of_heat", "Type of Heat", "text"),
        ("has_13th_floor", "Is there a 13th Floor?", "yesno"),
        ("major_occupancy", "Major Occupancy", "text"),
        ("num_suites", "# of Suites", "text"),
        ("upper_floor_construction", "Upper Floor Construction", "choice", ["", "Wood", "Concrete", "Steel", "Other"]),
        ("roof_construction", "Roof Construction", "choice", ["", "Wood", "Concrete", "Steel", "Other"]),
        ("private_stairway", "Private Stairway", "yesno"),
        ("private_stairway_floors", "  Between which floors?", "text"),
    ]),
    ("Elevators", [
        ("elev_recall_key_location", "Recall Key Switch Location", "text"),
        ("elev_recall", "Elevator Recall", "choice", ["", "Automatic", "Manual"]),
        ("elev_keys_lockbox", "Elevator Keys in Lock Box or on Site with Security?", "yesno"),
        ("elev_designated_fire", "Is there a Designated Fire Elevator?", "yesno"),
        ("elev_designated_fire_location", "  If Yes, Location", "text"),
        ("elev_service_type", "FireFighter Service or Independent Service?", "choice", ["", "FF Service", "Independent"]),
        ("elev_emergency_power", "Which Elevator Runs on Emergency Power?", "text"),
        ("elev_phones", "Phones in Elevators", "yesno"),
        ("elev_service_company", "Elevator Service Company", "text"),
        ("elev_service_phone", "  Phone", "text"),
    ]),
    ("Dangerous Goods / Hazardous Processes", [
        ("dg_what", "What? (add additional sheets if necessary)", "multiline"),
        ("dg_hazmat_location", "Location of Hazardous Materials (attach drawing if applicable)", "text"),
        ("dg_msds_location", "Location of M.S.D.S. (attach drawing if applicable)", "text"),
        ("dg_pool", "Swimming Pool", "yesno"),
        ("dg_pool_location", "  Location", "text"),
        ("dg_hot_tub", "Hot Tub", "yesno"),
        ("dg_hot_tub_location", "  Location", "text"),
    ]),
    ("Fire Suppression Systems", [
        ("sprinklers", "Sprinklers", "choice", ["", "None", "Total", "Partial"]),
        ("sprinklers_partial_where", "  Partial where?", "text"),
        ("sprinkler_main_valve_location", "Sprinkler Main Valve Location", "text"),
        ("standpipes_2_5in", "Standpipes: 2 1/2\" Valves", "yesno"),
        ("standpipes_2_5in_location", "  Location", "text"),
        ("sprinkler_zone_isolation_valve_location", "Sprinkler Zone Isolation Valve Location", "text"),
        ("standpipes_1_5in", "Standpipes: 1 1/2\" Valves", "yesno"),
        ("standpipes_1_5in_location", "  Location", "text"),
        ("siamese_location", "Siamese Location", "text"),
        ("riser_isolation_valves", "Riser Isolation Valves", "yesno"),
        ("zone_indicated_at_fdc", "Each Zone Clearly Indicated at Fire Dept. Connection", "yesno"),
        ("fire_pump", "Fire Pump", "yesno"),
        ("fire_pump_location", "  Location", "text"),
        ("gpm_fp1", "GPM/LPM — FP#1", "text"),
        ("gpm_fp2", "GPM/LPM — FP#2", "text"),
        ("gpm_fp3", "GPM/LPM — FP#3", "text"),
        ("special_suppression", "Special Fire Suppression System", "yesno"),
        ("special_suppression_location", "  Location", "text"),
    ]),
    ("Smoke Removal & Ventilation", [
        ("smoke_openable_windows", "Openable Windows", "checkbox"),
        ("smoke_stairway_to_roof", "Stairway to Roof", "checkbox"),
        ("smoke_shaft", "Smoke Shaft", "checkbox"),
        ("smoke_building_exhaust", "Building Exhaust System", "checkbox"),
        ("smoke_damper_control_location", "Location of Smoke Damper Control", "text"),
        ("smoke_exhaust_fan", "Exhaust Fan", "yesno"),
        ("smoke_exhaust_fan_mode", "  If Yes", "choice", ["", "Automatic", "Manual"]),
        ("smoke_damper_control_type", "Type of Damper Control", "choice", ["", "Electrical Toggle", "Manual Pull"]),
        ("parkade_fans_shutdown", "Do Parkade Fans Shut Down on Fire Alarm Activation?", "yesno"),
        ("parkade_override_switch", "  If Yes, manual override switches at", "choice", ["", "Fire Alarm Panel", "Other Location"]),
        ("parkade_override_other_location", "  Other Location", "text"),
        ("smoke_instructions", "Specific Instructions (attach additional sheets if required)", "multiline"),
    ]),
    ("Stairway Information", [
        ("stair_pressurized", "Pressurized Stairways", "yesno"),
        ("stair_fan_activation", "Stairway Fan Activation", "choice", ["", "Automatic", "Manual"]),
        ("stair_numbered", "Numbered Stairways", "yesno"),
        ("stair_coloured", "Coloured Stairways", "yesno"),
        ("stair_number_colour_to_roof", "Stairway Number/Colour Direct to Roof", "text"),
        ("stair_pressurization_switch_location", "Location of Pressurization Control Switches", "text"),
        ("stair_crossover_floors", "Cross over Floors", "yesno"),
        ("stair_crossover_which_floors", "  Which Floors", "text"),
        ("stair_scissor", "Scissor Stairs", "yesno"),
        ("stair_scissor_range", "  From 1 to", "text"),
    ]),
    ("Garbage", [
        ("garbage_bin_location", "Bin Location", "text"),
        ("garbage_chute_location", "Chute Location", "text"),
        ("garbage_compactor", "Compactor", "yesno"),
        ("garbage_chute_sprinklers", "Chute Sprinklers", "yesno"),
        ("garbage_sprinkler_isolation_valve_location", "Sprinkler Isolation Valve Location", "text"),
    ]),
    ("Keys", [
        ("keys_lockbox", "Lock Box", "yesno"),
        ("keys_24hr_security", "24 Hour Security", "yesno"),
        ("keys_location", "Location", "text"),
        ("keys_list", "List Keys in Lock Box", "multiline"),
    ]),
    ("Roof", [
        ("roof_microwave_antennae", "Microwave Antennae", "yesno"),
        ("roof_antennae_quantity", "  Quantity", "text"),
        ("roof_strongest_wattage", "Strongest Wattage (Watts)", "text"),
        ("roof_locked", "Roof Locked", "yesno"),
        ("roof_guard_rail", "Guard Rail", "checkbox"),
        ("roof_parapet", "Parapet", "checkbox"),
        ("roof_unprotected", "Unprotected", "checkbox"),
        ("roof_hydrant", "Roof Hydrant", "yesno"),
        ("roof_access", "Roof Access", "choice", ["", "Door", "Hatch", "No Interior Access"]),
    ]),
    ("Shut Offs", [
        ("shutoff_sprinkler_location", "Sprinkler Location", "text"),
        ("shutoff_gas_location", "Gas Location", "text"),
        ("shutoff_water_location", "Water Location", "text"),
        ("shutoff_electric_location", "Electric Location", "text"),
    ]),
    ("Emergency Power / Lighting", [
        ("gen_location", "Generator Location", "text"),
        ("gen_na", "  N/A", "checkbox"),
        ("gen_fuel", "Fuel", "text"),
        ("gen_capacity_kw", "Capacity (K.W.)", "text"),
        ("battery_emergency_lights", "Battery Powered Emergency Lights", "yesno"),
        ("ups_power", "UPS Power", "yesno"),
        ("ups_power_location", "  Location", "text"),
        ("day_tank", "Day Tank", "yesno"),
        ("day_tank_location", "  Location", "text"),
        ("feeder_tank", "Feeder Tank", "yesno"),
        ("feeder_tank_location", "  Location", "text"),
        ("will_operate_fire_alarm", "Will Operate: Fire Alarm", "checkbox"),
        ("will_operate_voice_comm", "Will Operate: Voice Communications", "checkbox"),
        ("will_operate_elevators", "Will Operate: Elevators", "checkbox"),
        ("will_operate_fire_phones", "Will Operate: Fire Phones", "checkbox"),
        ("will_operate_fire_pump", "Will Operate: Fire Pump", "checkbox"),
        ("will_operate_lights", "Will Operate: Lights", "checkbox"),
        ("will_operate_smoke_vent", "Will Operate: Smoke Ventilation", "checkbox"),
        ("will_operate_other", "Will Operate: Other", "text"),
        ("private_generators", "Are there Privately Owned Generators in the Building?", "yesno"),
        ("private_generators_powering", "  If Yes, Powering What?", "text"),
        ("hours_on_building_gen", "Hours on Building Generator", "yesno"),
        ("hours_on_building_gen_hrs", "  Hrs", "text"),
    ]),
    ("General Information", [
        ("owner_address", "Building Owner & Address", "multiline"),
        ("owner_phone", "  Phone Number", "text"),
        ("manager_address", "Manager/Management Company & Address", "multiline"),
        ("manager_phone", "  Phone Number", "text"),
        ("caretaker", "Caretaker", "text"),
        ("caretaker_phone", "  Phone Number", "text"),
        ("contact_247", "24/7 Contact with knowledge of Building/Contents/Processes", "text"),
        ("contact_247_phone", "  Phone Number", "text"),
        ("contact_247_alt", "Alternate 24/7 Contact", "text"),
        ("contact_247_alt_phone", "  Phone Number", "text"),
    ]),
]


# ═══════════════════════════════════════════════════════════════════════════════
#  VBI Form data-entry dialog
# ═══════════════════════════════════════════════════════════════════════════════

class VBIFormDialog(QDialog):
    """Fills out the Vital Building Information sheet — one group box per
    FD 1019 section, built from VBI_SECTIONS rather than hand-laid-out."""

    def __init__(self, existing_values=None, project_meta=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vital Building Information (VBI) Form")
        self.resize(640, 700)
        self._values = existing_values or {}
        self._project_meta = project_meta or {}
        self._widgets = {}   # field_id -> widget
        self._build_ui()

    def closeEvent(self, event):
        # There's no real "discard" case for a fact-gathering form like
        # this — whatever's been typed so far is worth keeping even if the
        # user has to step away and finish later, so any close (X button,
        # Esc, either button) saves rather than losing partial progress.
        event.accept()
        self.accept()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)

        for section_title, fields in VBI_SECTIONS:
            box = QGroupBox(section_title)
            form = QFormLayout(box)
            for field_def in fields:
                field_id, label, ftype = field_def[0], field_def[1], field_def[2]
                widget = self._make_widget(ftype, field_def)
                self._widgets[field_id] = widget
                form.addRow(label, widget)
            inner_layout.addWidget(box)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        br = QHBoxLayout()
        questionnaire_btn = QPushButton("Export Questionnaire for Customer…")
        questionnaire_btn.setToolTip(
            "Export what's filled in so far as a fill-in-the-blanks PDF you can\n"
            "send the customer for whatever you don't have yet — doesn't require\n"
            "finishing or saving the form first.")
        questionnaire_btn.clicked.connect(self._export_questionnaire)
        ok = QPushButton("Save & Close")
        ok.setStyleSheet("background:#ff7002;color:white;padding:6px 18px;font-weight:bold;")
        ok.clicked.connect(self.accept)
        br.addWidget(questionnaire_btn)
        br.addStretch(); br.addWidget(ok)
        outer.addLayout(br)

    def _export_questionnaire(self):
        values = self.result_data()
        default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Submittals")
        os.makedirs(default_dir, exist_ok=True)
        building = self._project_meta.get("building_name") or self._project_meta.get("project_name", "VBI")
        default_name = os.path.join(default_dir, f"{building}_VBI_Questionnaire.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Export Questionnaire", default_name, "PDF (*.pdf)")
        if not path:
            return
        try:
            doc = build_vbi_pdf(values, self._project_meta, questionnaire=True)
            doc.save(path)
            doc.close()
            QMessageBox.information(self, "Exported", f"Questionnaire saved:\n{path}")
            os.startfile(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export questionnaire:\n{e}")

    def _make_widget(self, ftype, field_def):
        field_id = field_def[0]
        saved = self._values.get(field_id, "")
        if ftype == "yesno":
            w = QComboBox()
            w.addItems(["", "Yes", "No"])
            if saved: w.setCurrentText(saved)
            return w
        if ftype == "choice":
            choices = field_def[3]
            w = QComboBox()
            w.addItems(choices)
            if saved and saved in choices: w.setCurrentText(saved)
            return w
        if ftype == "checkbox":
            w = QCheckBox()
            w.setChecked(saved == "Yes")
            return w
        if ftype == "multiline":
            w = QTextEdit()
            w.setPlainText(saved)
            w.setFixedHeight(60)
            return w
        # "text"
        w = QLineEdit()
        w.setText(saved)
        return w

    def result_data(self):
        values = {}
        for section_title, fields in VBI_SECTIONS:
            for field_def in fields:
                field_id, ftype = field_def[0], field_def[2]
                w = self._widgets[field_id]
                if ftype in ("yesno", "choice"):
                    values[field_id] = w.currentText()
                elif ftype == "checkbox":
                    values[field_id] = "Yes" if w.isChecked() else ""
                elif ftype == "multiline":
                    values[field_id] = w.toPlainText().strip()
                else:
                    values[field_id] = w.text().strip()
        return values


# ═══════════════════════════════════════════════════════════════════════════════
#  VBI sheet PDF generation
# ═══════════════════════════════════════════════════════════════════════════════

_PAGE_W, _PAGE_H = 612, 792
_MARGIN = 30
_RED = (0.75, 0.17, 0.11)
_DARK = (0.14, 0.16, 0.16)
_SECTION_FILL = (0.85, 0.85, 0.85)


def build_vbi_pdf(values, project_meta, questionnaire=False):
    """Returns an open fitz.Document — a clean, DFP-styled sheet covering
    the same fields/sections/order as Calgary Fire's FD 1019 form (not a
    pixel copy of the city's letterhead).

    questionnaire=True: for sending to the customer to fill in whatever
    isn't known yet — already-filled fields still print their value (so
    the customer isn't re-answering what's already known), but empty
    fields render as a blank write-on line instead of an em dash."""
    doc = fitz.open()
    page = doc.new_page(width=_PAGE_W, height=_PAGE_H)
    y = _draw_header(page, project_meta, questionnaire)

    for section_title, fields in VBI_SECTIONS:
        if y > _PAGE_H - 70:
            page = doc.new_page(width=_PAGE_W, height=_PAGE_H)
            y = _draw_continuation_header(page, project_meta)
        y = _draw_section_bar(page, section_title, y)
        for field_def in fields:
            field_id, label, ftype = field_def[0], field_def[1], field_def[2]
            value = values.get(field_id, "") if values else ""
            if y > _PAGE_H - 40:
                page = doc.new_page(width=_PAGE_W, height=_PAGE_H)
                y = _draw_continuation_header(page, project_meta)
                y = _draw_section_bar(page, f"{section_title} (cont'd)", y)
            page.insert_text((_MARGIN + 6, y), f"{label}:", fontsize=9, fontname="hebo", color=_DARK)
            if value:
                page.insert_text((_MARGIN + 260, y), value, fontsize=9, fontname="helv", color=(0, 0, 0))
            elif questionnaire:
                hint = _choices_hint(ftype, field_def)
                if hint:
                    # Show the valid options so whoever's filling this in
                    # knows how to answer, instead of a bare blank line.
                    page.insert_text((_MARGIN + 260, y), f"({hint})", fontsize=8,
                                     fontname="heit", color=(0.45, 0.45, 0.45))
                else:
                    page.draw_line(fitz.Point(_MARGIN + 260, y + 2), fitz.Point(_PAGE_W - _MARGIN, y + 2),
                                   color=(0, 0, 0), width=0.6)
            else:
                page.insert_text((_MARGIN + 260, y), "-", fontsize=9, fontname="helv", color=(0, 0, 0))
            y += 14

    return doc


def _choices_hint(ftype, field_def):
    """Human-readable list of valid answers for a dropdown-style field, for
    the questionnaire export — None for free-text/multiline fields."""
    if ftype == "yesno":
        return "Yes / No"
    if ftype == "choice":
        return " / ".join(c for c in field_def[3] if c)
    if ftype == "checkbox":
        return "write Yes if applicable"
    return None


def _draw_header(page, project_meta, questionnaire=False):
    page.draw_rect(fitz.Rect(0, 0, _PAGE_W, 90), color=_RED, fill=_RED)
    page.insert_text((_MARGIN, 40), "DEFENSE FIRE PROTECTION", fontsize=20, color=(1, 1, 1), fontname="hebo")
    subtitle = ("Vital Building Information — Please Complete the Blank Fields Below"
               if questionnaire else "Vital Building Information")
    page.insert_text((_MARGIN, 62), subtitle, fontsize=13, color=(1, 1, 1), fontname="helv")
    y = 108
    building = project_meta.get("building_name") or project_meta.get("project_name", "")
    address = project_meta.get("address", "")
    page.insert_text((_MARGIN, y), f"Building:  {building}", fontsize=11, fontname="hebo"); y += 16
    if address:
        page.insert_text((_MARGIN, y), f"Address:  {address}", fontsize=10, fontname="helv"); y += 16
    return y + 10


def _draw_continuation_header(page, project_meta):
    building = project_meta.get("building_name") or project_meta.get("project_name", "")
    page.insert_text((_MARGIN, 30), "Vital Building Information (cont'd)", fontsize=11, fontname="hebo", color=_DARK)
    page.insert_text((_MARGIN, 46), building, fontsize=9, fontname="helv", color=_DARK)
    return 66


def _draw_section_bar(page, title, y):
    page.draw_rect(fitz.Rect(_MARGIN, y - 11, _PAGE_W - _MARGIN, y + 3), color=_SECTION_FILL, fill=_SECTION_FILL)
    page.insert_text((_MARGIN + 4, y), title, fontsize=10, fontname="hebo", color=_DARK)
    return y + 20


# ═══════════════════════════════════════════════════════════════════════════════
#  Main window — assembles the AHJ package
# ═══════════════════════════════════════════════════════════════════════════════

class FirePlanBuilderWindow(QDialog):
    """Launched non-modally (see main.py MainWindow._open_fire_plan_builder)
    so its own nested dialogs (VBI form, file pickers) and the "Open Drawing
    Designer" shortcut don't collide with an application-modal event loop —
    Drawing Designer's own launcher carries the same non-modal requirement
    for the same reason (main.py:4077-4078)."""

    def __init__(self, parent, project_id, project_name):
        super().__init__(parent)
        self.setWindowTitle(f"Fire Plan Builder — {project_name}" if project_name else "Fire Plan Builder")
        self.resize(560, 520)
        self._project_id = project_id
        self._project_name = project_name
        self._load_existing()
        self._build_ui()
        self._refresh_cert_list()

    def _load_existing(self):
        row = db.get_fire_plan(self._project_id)
        if row:
            self._ahj = row["ahj"]
            self._vbi_values = json.loads(row["vbi_data"] or "{}")
            self._has_zoned_alarm = bool(row["has_zoned_alarm"])
            self._base_building_path = row["base_building_path"] or ""
            self._alarm_zone_path = row["alarm_zone_path"] or ""
        else:
            self._ahj = "calgary"
            self._vbi_values = {}
            self._has_zoned_alarm = False
            self._base_building_path = ""
            self._alarm_zone_path = ""

    def _build_ui(self):
        layout = QVBoxLayout(self)

        top = QFormLayout()
        self._ahj_combo = QComboBox()
        for key, profile in AHJ_PROFILES.items():
            self._ahj_combo.addItem(profile["display_name"], key)
        idx = self._ahj_combo.findData(self._ahj)
        self._ahj_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._ahj_combo.currentIndexChanged.connect(self._save)
        top.addRow("AHJ:", self._ahj_combo)

        self._address_edit = QLineEdit(self._vbi_values.get("address", ""))
        self._address_edit.editingFinished.connect(self._save)
        top.addRow("Building Address:", self._address_edit)
        layout.addLayout(top)

        vbi_row = QHBoxLayout()
        self._vbi_status = QLabel()
        vbi_questionnaire_btn = QPushButton("Export Questionnaire…")
        vbi_questionnaire_btn.setToolTip(
            "Export whatever's filled in so far as a fill-in-the-blanks PDF\n"
            "to send the customer for the rest.")
        vbi_questionnaire_btn.clicked.connect(self._export_vbi_questionnaire)
        vbi_btn = QPushButton("Edit VBI Form…")
        vbi_btn.clicked.connect(self._edit_vbi)
        vbi_row.addWidget(QLabel("1. Vital Building Information Form"))
        vbi_row.addStretch(); vbi_row.addWidget(self._vbi_status)
        vbi_row.addWidget(vbi_questionnaire_btn); vbi_row.addWidget(vbi_btn)
        layout.addLayout(vbi_row)

        bb_row = QHBoxLayout()
        self._bb_status = QLabel()
        bb_open_dd = QPushButton("Open Drawing Designer")
        bb_open_dd.clicked.connect(self._open_drawing_designer)
        bb_attach = QPushButton("Attach PDF…")
        bb_attach.clicked.connect(self._attach_base_building)
        bb_row.addWidget(QLabel("2. Base Building Drawings"))
        bb_row.addStretch(); bb_row.addWidget(self._bb_status)
        bb_row.addWidget(bb_open_dd); bb_row.addWidget(bb_attach)
        layout.addLayout(bb_row)

        self._zoned_chk = QCheckBox("Building has a zoned fire alarm system")
        self._zoned_chk.setChecked(self._has_zoned_alarm)
        self._zoned_chk.toggled.connect(self._on_zoned_toggled)
        layout.addWidget(self._zoned_chk)

        az_row = QHBoxLayout()
        self._az_status = QLabel()
        self._az_attach_btn = QPushButton("Attach PDF…")
        self._az_attach_btn.clicked.connect(self._attach_alarm_zone)
        az_row.addWidget(QLabel("3. Fire Alarm Zone Drawings"))
        az_row.addStretch(); az_row.addWidget(self._az_status); az_row.addWidget(self._az_attach_btn)
        layout.addLayout(az_row)
        self._az_row_widgets = [self._az_attach_btn]
        self._on_zoned_toggled(self._has_zoned_alarm)

        layout.addWidget(QLabel("4. Maintenance Certificates"))
        self._cert_list = QListWidget()
        layout.addWidget(self._cert_list)
        cert_btns = QHBoxLayout()
        add_cert = QPushButton("Add…"); add_cert.clicked.connect(self._add_certificate)
        del_cert = QPushButton("Remove"); del_cert.clicked.connect(self._remove_certificate)
        cert_btns.addWidget(add_cert); cert_btns.addWidget(del_cert); cert_btns.addStretch()
        layout.addLayout(cert_btns)

        build_row = QHBoxLayout()
        build_btn = QPushButton("Build Fire Safety Plan Package")
        build_btn.setStyleSheet("background:#ff7002;color:white;padding:8px 18px;font-weight:bold;")
        build_btn.clicked.connect(self._build_package)
        build_row.addStretch(); build_row.addWidget(build_btn)
        layout.addLayout(build_row)

        self._refresh_status_labels()

    def _on_zoned_toggled(self, checked):
        self._has_zoned_alarm = checked
        for w in self._az_row_widgets:
            w.setEnabled(checked)
        self._refresh_status_labels()
        self._save()

    def _refresh_status_labels(self):
        self._vbi_status.setText("✓ filled" if any(self._vbi_values.values()) else "not started")
        self._bb_status.setText("✓ attached" if self._base_building_path else "missing")
        if self._has_zoned_alarm:
            self._az_status.setText("✓ attached" if self._alarm_zone_path else "missing")
        else:
            self._az_status.setText("not required")

    def _edit_vbi(self):
        self._vbi_values["address"] = self._address_edit.text().strip()
        self._vbi_values["building_name"] = self._project_name
        meta = {"project_name": self._project_name, "building_name": self._project_name,
                "address": self._address_edit.text().strip()}
        dlg = VBIFormDialog(existing_values=self._vbi_values, project_meta=meta, parent=self)
        dlg.exec_()   # VBIFormDialog always "accepts" on close — Save & Close, X, or Esc — so
                       # partial progress is never lost even if the user has to step away mid-form.
        self._vbi_values = dlg.result_data()
        self._save()
        self._refresh_status_labels()

    def _export_vbi_questionnaire(self):
        default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Submittals")
        os.makedirs(default_dir, exist_ok=True)
        default_name = os.path.join(default_dir, f"{self._project_name or 'VBI'}_VBI_Questionnaire.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Export Questionnaire", default_name, "PDF (*.pdf)")
        if not path:
            return
        try:
            meta = {"project_name": self._project_name, "building_name": self._project_name,
                    "address": self._address_edit.text().strip()}
            doc = build_vbi_pdf(self._vbi_values, meta, questionnaire=True)
            doc.save(path)
            doc.close()
            QMessageBox.information(self, "Exported", f"Questionnaire saved:\n{path}")
            os.startfile(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export questionnaire:\n{e}")

    def _attach_base_building(self):
        path, _ = QFileDialog.getOpenFileName(self, "Attach Base Building Drawings", "", "PDF Files (*.pdf)")
        if path:
            self._base_building_path = path
            self._save()
            self._refresh_status_labels()

    def _attach_alarm_zone(self):
        path, _ = QFileDialog.getOpenFileName(self, "Attach Fire Alarm Zone Drawings", "", "PDF Files (*.pdf)")
        if path:
            self._alarm_zone_path = path
            self._save()
            self._refresh_status_labels()

    def _open_drawing_designer(self):
        from drawing_designer import DrawingDesigner
        dlg = DrawingDesigner(self, project_name=self._project_name)
        self._dd_dlg = dlg   # keep reference so GC doesn't destroy it
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()

    def _refresh_cert_list(self):
        self._cert_list.clear()
        for c in db.get_fire_plan_certificates(self._project_id):
            item = QListWidgetItem(c["label"] or os.path.basename(c["path"]))
            item.setData(Qt.UserRole, c["id"])
            self._cert_list.addItem(item)

    def _add_certificate(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Maintenance Certificate(s)", "", "PDF Files (*.pdf)")
        for path in paths:
            label = os.path.splitext(os.path.basename(path))[0]
            db.add_fire_plan_certificate(self._project_id, label, path)
        if paths:
            self._refresh_cert_list()

    def _remove_certificate(self):
        item = self._cert_list.currentItem()
        if not item:
            return
        db.delete_fire_plan_certificate(item.data(Qt.UserRole))
        self._refresh_cert_list()

    def _save(self):
        # Keep the address field synced into vbi_values even if the user
        # never opens the full VBI form dialog — every action in this
        # window (attach a doc, toggle the checkbox, edit the address,
        # close the window) persists immediately, so work is never lost
        # between sessions.
        self._vbi_values["address"] = self._address_edit.text().strip()
        db.upsert_fire_plan(
            self._project_id,
            self._ahj_combo.currentData(),
            json.dumps(self._vbi_values),
            self._has_zoned_alarm,
            self._base_building_path,
            self._alarm_zone_path,
        )

    def closeEvent(self, event):
        # Safety net in case some future edit path forgets to call _save()
        # directly — nothing typed/toggled/attached should be lost on close.
        self._save()
        super().closeEvent(event)

    def _build_package(self):
        self._save()
        if not self._vbi_values or not any(self._vbi_values.values()):
            if QMessageBox.question(self, "VBI Form Not Filled",
                    "The VBI Form hasn't been filled out yet. Continue anyway?",
                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
        if not self._base_building_path:
            QMessageBox.warning(self, "Missing Document", "Attach Base Building Drawings first.")
            return
        if self._has_zoned_alarm and not self._alarm_zone_path:
            QMessageBox.warning(self, "Missing Document",
                "Building has a zoned alarm system — attach Fire Alarm Zone Drawings first.")
            return

        default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Submittals")
        os.makedirs(default_dir, exist_ok=True)
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save Fire Safety Plan Package",
            os.path.join(default_dir, f"{self._project_name or 'FireSafetyPlan'}_FireSafetyPlan.pdf"),
            "PDF (*.pdf)")
        if not out_path:
            return

        certs = db.get_fire_plan_certificates(self._project_id)
        attachments = [("Base Building Drawings", self._base_building_path)]
        if self._has_zoned_alarm:
            attachments.append(("Fire Alarm Zone Drawings", self._alarm_zone_path))
        for c in certs:
            attachments.append((c["label"] or "Maintenance Certificate", c["path"]))

        prog = QProgressDialog("Building fire safety plan package", "Cancel", 0, len(attachments) + 1, self)
        prog.setWindowTitle("Building Package"); prog.setMinimumDuration(0); prog.setValue(0)
        try:
            out_doc = fitz.open()
            meta = {"project_name": self._project_name, "building_name": self._project_name,
                    "address": self._address_edit.text().strip()}
            vbi_doc = build_vbi_pdf(self._vbi_values, meta)
            out_doc.insert_pdf(vbi_doc)
            vbi_doc.close()
            prog.setValue(1)

            failed = []
            for i, (label, path) in enumerate(attachments):
                QApplication.processEvents()
                if prog.wasCanceled(): break
                prog.setValue(i + 2)
                if not path or not os.path.exists(path):
                    failed.append(f"{label} — file not found: {path}")
                    continue
                try:
                    src = fitz.open(path)
                    out_doc.insert_pdf(src)
                    src.close()
                except Exception as item_err:
                    failed.append(f"{label} — {item_err}")

            out_doc.save(out_path)
            out_doc.close()
            msg = f"Fire Safety Plan package saved:\n{out_path}"
            if failed:
                msg += "\n\nSkipped (couldn't include):\n" + "\n".join(f"  {f}" for f in failed)
            QMessageBox.information(self, "Done", msg)
            os.startfile(out_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to build package:\n{e}")
