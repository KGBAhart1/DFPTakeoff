# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for DFP TakeoffPro
# Run:  pyinstaller DFP_TakeoffPro.spec

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# Collect PyMuPDF (fitz) data files
fitz_datas = collect_data_files('fitz')
fitz_binaries = collect_dynamic_libs('fitz')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=fitz_binaries,
    datas=fitz_datas + [('icon.ico', '.')],
    hiddenimports=[
        'fitz',
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'sqlite3',
        'csv',
        'json',
        'hmac',
        'hashlib',
        'base64',
        'struct',
        'uuid',
        'platform',
        'urllib.request',
        'threading',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['cv2', 'numpy', 'matplotlib', 'tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DFP TakeoffPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # No terminal window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DFP TakeoffPro',
)
