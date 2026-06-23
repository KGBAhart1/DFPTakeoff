"""
DFP TakeoffPro — License Key System
------------------------------------
Hardware-locked license keys. A machine fingerprint is signed with a secret
to produce a key that only works on that specific computer.

To enable: set LICENSING_ENABLED = True below.
To generate keys: run  python generate_key.py  and enter the user's Machine ID.
"""

import os, json, hmac, hashlib, platform, subprocess

# ── Config ────────────────────────────────────────────────────────────────────

# Set to True when you want to enforce license checks
LICENSING_ENABLED = True

# Secret used to sign keys. Loaded from _secret.py (not in git).
from _secret import LICENSE_SECRET as _SECRET

# Where activation is stored on the customer's machine
_LICENSE_DIR = os.path.join(os.path.expanduser("~"), "Documents", "DFP TakeoffPro")
_LICENSE_FILE = os.path.join(_LICENSE_DIR, "license.json")


# ── Machine ID ────────────────────────────────────────────────────────────────

def _get_windows_product_id():
    try:
        result = subprocess.run(
            ["reg", "query",
             "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion",
             "/v", "ProductId"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000)  # CREATE_NO_WINDOW
        for line in result.stdout.splitlines():
            if "ProductId" in line:
                return line.split()[-1].strip()
    except Exception:
        pass
    return ""


def get_machine_id():
    raw = platform.node() + "|" + _get_windows_product_id()
    return hashlib.sha256(raw.encode()).hexdigest()[:16].upper()


# ── Key generation (admin only — run generate_key.py) ─────────────────────────

def generate_key(fingerprint):
    sig = hmac.new(_SECRET, fingerprint.upper().encode(),
                   hashlib.sha256).hexdigest()[:24].upper()
    return f"DFP-{sig[:6]}-{sig[6:12]}-{sig[12:18]}-{sig[18:24]}"


# ── Validation ────────────────────────────────────────────────────────────────

def validate_key(key):
    fp = get_machine_id()
    expected = generate_key(fp)
    return hmac.compare_digest(expected.upper(), key.strip().upper())


def activate(key):
    if validate_key(key):
        os.makedirs(_LICENSE_DIR, exist_ok=True)
        with open(_LICENSE_FILE, "w", encoding="utf-8") as f:
            json.dump({"key": key.strip().upper()}, f)
        return True, "License activated successfully!"
    return False, "Invalid license key for this machine."


def check_activation():
    if not LICENSING_ENABLED:
        return True, "Open mode"
    try:
        with open(_LICENSE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if validate_key(data.get("key", "")):
            return True, "Licensed"
        return False, "License key does not match this machine."
    except FileNotFoundError:
        return False, "No license found. Please enter your license key."
    except Exception:
        return False, "License file is corrupted. Please re-activate."
