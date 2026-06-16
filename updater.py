"""
DFP TakeoffPro — Auto-Update Checker
--------------------------------------
Checks UPDATE_CHECK_URL (in version.py) for a newer version.
Runs in a background thread so it never blocks startup.
"""

import json, threading, os, tempfile, subprocess
from urllib.request import urlopen, Request
from urllib.error import URLError
from version import APP_VERSION, UPDATE_CHECK_URL


def _parse_version(v: str):
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0, 0, 0)


def check_for_update(callback):
    """
    Fetch version info in a background thread and call callback(info_dict | None).
    callback is called with None if no update is available or check fails.
    """
    if not UPDATE_CHECK_URL:
        return

    def _check():
        try:
            req = Request(UPDATE_CHECK_URL, headers={"User-Agent": "DFPTakeoffPro"})
            with urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            remote = data.get("version", "0.0.0")
            if _parse_version(remote) > _parse_version(APP_VERSION):
                callback(data)
            else:
                callback(None)
        except Exception:
            callback(None)

    threading.Thread(target=_check, daemon=True).start()


def download_and_install(download_url, parent=None):
    """Download the installer from the given URL and run it, then quit the app."""
    from PyQt5.QtWidgets import QProgressDialog, QMessageBox, QApplication
    from PyQt5.QtCore import Qt

    prog = QProgressDialog("Downloading update…", None, 0, 0, parent)
    prog.setWindowTitle("DFP TakeoffPro Update")
    prog.setWindowModality(Qt.WindowModal)
    prog.show()
    QApplication.processEvents()

    try:
        req = Request(download_url, headers={"User-Agent": "DFPTakeoffPro"})
        with urlopen(req, timeout=120) as resp:
            data = resp.read()
        tmp_dir = tempfile.mkdtemp()
        installer = os.path.join(tmp_dir, "DFPTakeoffPro_Setup.exe")
        with open(installer, "wb") as f:
            f.write(data)
        prog.close()
        subprocess.Popen([installer], shell=False)
        QApplication.quit()
    except Exception:
        prog.close()
        QMessageBox.warning(parent, "Update Failed",
                            "Could not download the update.\nPlease try again later.")
