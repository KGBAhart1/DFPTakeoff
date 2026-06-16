@echo off
echo ============================================================
echo   DFP TakeoffPro  --  Build Script
echo ============================================================
echo.

:: Read version from version.py and patch installer.iss
python patch_version.py
if errorlevel 1 (
    echo ERROR: Could not read version from version.py
    pause & exit /b 1
)

:: Read version into batch variable
set /p APP_VERSION=<_ver.txt
del _ver.txt
echo.

:: Step 1 - Install / upgrade build tools
echo [1/4] Installing build dependencies...
python -m pip install --upgrade pyinstaller 2>nul
if errorlevel 1 (
    echo ERROR: pip failed. Make sure Python is installed.
    pause & exit /b 1
)

:: Step 2 - Clean previous build
echo [2/4] Cleaning previous build...
if exist build      rmdir /s /q build
if exist "dist"     rmdir /s /q "dist"

:: Step 3 - PyInstaller
echo [3/4] Building executable with PyInstaller...
python -m PyInstaller "DFP_TakeoffPro.spec"
if errorlevel 1 (
    echo ERROR: PyInstaller failed. See output above.
    pause & exit /b 1
)

:: Step 4 - Inno Setup
echo [4/4] Building installer with Inno Setup...
set INNO="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %INNO% set INNO="C:\Program Files\Inno Setup 6\ISCC.exe"
if not exist %INNO% set INNO="C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
if not exist %INNO% set INNO="C:\Program Files\Inno Setup 7\ISCC.exe"

if exist %INNO% (
    %INNO% installer.iss
    if errorlevel 1 (
        echo ERROR: Inno Setup compile failed.
    ) else (
        echo.
        echo ============================================================
        echo   SUCCESS!
        echo   Installer: installer_output\DFP_TakeoffPro_Setup_%APP_VERSION%.exe
        echo ============================================================
    )
) else (
    echo.
    echo NOTE: Inno Setup not found. PyInstaller build is in:
    echo         dist\DFP TakeoffPro\
    echo.
    echo To build the installer:
    echo   1. Download Inno Setup from https://jrsoftware.org/isinfo.php
    echo   2. Run this script again.
)

pause
